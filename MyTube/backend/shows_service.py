import json
import logging
import random
from typing import Dict, Any, List, Optional
from backend.database import get_db

logger = logging.getLogger("mytube.shows")

class ShowsService:
    @staticmethod
    def _show_row_to_dict(row) -> Dict[str, Any]:
        d = dict(row)
        if isinstance(d.get("genres"), str):
            try:
                d["genres"] = json.loads(d["genres"])
            except Exception:
                d["genres"] = []
        d["media_type"] = "show"
        return d

    @staticmethod
    def _episode_row_to_dict(row) -> Dict[str, Any]:
        d = dict(row)
        d["media_type"] = "episode"
        duration = float(d.get("duration") or 0)
        pos = float(d.get("playback_position") or 0)
        d["progress_percent"] = round((pos / duration * 100), 1) if duration > 0 else 0
        return d

    @classmethod
    def get_shows_home(cls) -> Dict[str, Any]:
        """Fetch Netflix/Prime style homepage payload for Shows."""
        with get_db() as conn:
            cursor = conn.cursor()

            # 1. Continue Watching:
            # Find in-progress episodes (watched = 0 AND playback_position > 15), grouped by show
            cursor.execute("""
                SELECT e.*, s.poster_url AS show_poster_url, s.backdrop_url AS show_backdrop_url
                FROM episodes e
                JOIN shows s ON e.show_id = s.show_id
                WHERE e.file_status = 'available'
                  AND s.file_status = 'available'
                  AND e.watched = 0
                  AND e.playback_position > 15
                ORDER BY e.updated_at DESC
            """)
            in_progress_rows = cursor.fetchall()
            seen_shows = set()
            continue_watching = []

            for r in in_progress_rows:
                sid = r["show_id"]
                if sid in seen_shows:
                    continue
                seen_shows.add(sid)
                ep = cls._episode_row_to_dict(r)
                item = {
                    "show_id": sid,
                    "title": r["show_name"],
                    "poster_url": r["show_poster_url"] or ep.get("thumbnail_url") or "",
                    "backdrop_url": r["show_backdrop_url"] or "",
                    "media_type": "show",
                    "current_episode": ep,
                    "playback_position": ep["playback_position"],
                    "duration": ep["duration"],
                    "progress_percent": ep["progress_percent"],
                }
                continue_watching.append(item)

            # 2. Recently Added Shows
            cursor.execute("""
                SELECT * FROM shows
                WHERE file_status = 'available'
                ORDER BY created_at DESC, start_year DESC
                LIMIT 20
            """)
            recently_added = [cls._show_row_to_dict(r) for r in cursor.fetchall()]

            # 3. All Shows
            cursor.execute("""
                SELECT * FROM shows
                WHERE file_status = 'available'
                ORDER BY title ASC
            """)
            all_shows = [cls._show_row_to_dict(r) for r in cursor.fetchall()]

            # 4. 5 Random Genres with matching shows
            genre_map: Dict[str, List[Dict[str, Any]]] = {}
            for s in all_shows:
                for g in s.get("genres", []):
                    if g:
                        genre_map.setdefault(g, []).append(s)

            all_genres = list(genre_map.keys())
            sampled_genres = random.sample(all_genres, min(5, len(all_genres)))

            genre_shelves = []
            for g in sampled_genres:
                shows_in_g = list(genre_map[g])
                random.shuffle(shows_in_g)
                genre_shelves.append({
                    "genre": g,
                    "shows": shows_in_g[:15]
                })

            # 5. Featured / Hero Show Banner
            featured = None
            candidates = [s for s in all_shows if s.get("backdrop_url")]
            if candidates:
                candidates.sort(key=lambda x: (x.get("community_rating") or 0, x.get("start_year") or 0), reverse=True)
                featured = candidates[0]
            elif all_shows:
                featured = all_shows[0]

            return {
                "featured": featured,
                "continue_watching": continue_watching,
                "recently_added": recently_added,
                "genres": genre_shelves,
                "all_shows": all_shows,
                "total_shows": len(all_shows)
            }

    @classmethod
    def get_show_detail(cls, show_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full series metadata, grouped seasons, episodes, and the next-to-watch episode."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM shows WHERE show_id = ?", (show_id,))
            show_row = cursor.fetchone()
            if not show_row:
                return None

            show = cls._show_row_to_dict(show_row)

            # Fetch all episodes for this show
            cursor.execute("""
                SELECT * FROM episodes
                WHERE show_id = ? AND file_status = 'available'
                ORDER BY season_number ASC, episode_number ASC
            """, (show_id,))
            ep_rows = cursor.fetchall()
            episodes = [cls._episode_row_to_dict(r) for r in ep_rows]

            # Group episodes by seasons
            seasons_map: Dict[int, Dict[str, Any]] = {}
            for ep in episodes:
                s_num = ep.get("season_number") or 1
                s_name = ep.get("season_name") or f"Season {s_num}"
                if s_num not in seasons_map:
                    seasons_map[s_num] = {
                        "season_number": s_num,
                        "season_name": s_name,
                        "episodes": []
                    }
                seasons_map[s_num]["episodes"].append(ep)

            seasons_list = [seasons_map[k] for k in sorted(seasons_map.keys())]

            # Determine next_episode to play:
            # 1. In-progress episode (playback_position > 10 and watched = 0)
            next_ep = None
            in_progress = [e for e in episodes if e["watched"] == 0 and e["playback_position"] > 10]
            if in_progress:
                in_progress.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
                next_ep = in_progress[0]
            else:
                # 2. First unwatched episode
                unwatched = [e for e in episodes if e["watched"] == 0]
                if unwatched:
                    next_ep = unwatched[0]
                elif episodes:
                    # 3. Default to Season 1 Episode 1
                    next_ep = episodes[0]

            show["seasons"] = seasons_list
            show["next_episode"] = next_ep
            show["total_episodes"] = len(episodes)

            return show
