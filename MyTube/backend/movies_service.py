import json
import logging
import random
from typing import Dict, Any, List, Optional
from backend.database import get_db

logger = logging.getLogger("mytube.movies")

class MoviesService:
    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        d = dict(row)
        if isinstance(d.get("genres"), str):
            try:
                d["genres"] = json.loads(d["genres"])
            except Exception:
                d["genres"] = []
        d["media_type"] = "movie"
        duration = float(d.get("duration") or 0)
        pos = float(d.get("playback_position") or 0)
        d["progress_percent"] = round((pos / duration * 100), 1) if duration > 0 else 0
        return d

    @classmethod
    def get_movies_home(cls) -> Dict[str, Any]:
        """Fetch Netflix/Prime style homepage payload for Movies."""
        with get_db() as conn:
            cursor = conn.cursor()

            # 1. Continue Watching (in progress, unwatched)
            cursor.execute("""
                SELECT * FROM movies
                WHERE file_status = 'available'
                  AND watched = 0
                  AND playback_position > 15
                ORDER BY updated_at DESC
                LIMIT 15
            """)
            continue_watching = [cls._row_to_dict(r) for r in cursor.fetchall()]

            # 2. Recently Added
            cursor.execute("""
                SELECT * FROM movies
                WHERE file_status = 'available'
                ORDER BY created_at DESC, release_year DESC
                LIMIT 20
            """)
            recently_added = [cls._row_to_dict(r) for r in cursor.fetchall()]

            # 3. All Available Movies (for browsing and genre grouping)
            cursor.execute("""
                SELECT * FROM movies
                WHERE file_status = 'available'
                ORDER BY title ASC
            """)
            all_movies = [cls._row_to_dict(r) for r in cursor.fetchall()]

            # 4. Group by genres and pick 5 random genres
            genre_map: Dict[str, List[Dict[str, Any]]] = {}
            for m in all_movies:
                for g in m.get("genres", []):
                    if g:
                        genre_map.setdefault(g, []).append(m)

            all_genres = list(genre_map.keys())
            sampled_genres = random.sample(all_genres, min(5, len(all_genres)))

            genre_shelves = []
            for g in sampled_genres:
                movies_in_g = list(genre_map[g])
                random.shuffle(movies_in_g)
                genre_shelves.append({
                    "genre": g,
                    "movies": movies_in_g[:15]
                })

            # 5. Featured / Hero movie banner
            # Pick a movie with backdrop and highest community rating or recently added
            featured = None
            candidates = [m for m in all_movies if m.get("backdrop_url")]
            if candidates:
                candidates.sort(key=lambda x: (x.get("community_rating") or 0, x.get("release_year") or 0), reverse=True)
                featured = candidates[0]
            elif all_movies:
                featured = all_movies[0]

            return {
                "featured": featured,
                "continue_watching": continue_watching,
                "recently_added": recently_added,
                "genres": genre_shelves,
                "all_movies": all_movies,
                "total_movies": len(all_movies)
            }

    @classmethod
    def get_movie_detail(cls, movie_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full movie details and related recommendations."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM movies WHERE movie_id = ?", (movie_id,))
            row = cursor.fetchone()
            if not row:
                return None

            movie = cls._row_to_dict(row)

            # Recommendations based on same genres
            cursor.execute("SELECT * FROM movies WHERE movie_id != ? AND file_status = 'available'", (movie_id,))
            other_rows = [cls._row_to_dict(r) for r in cursor.fetchall()]

            my_genres = set(movie.get("genres", []))
            related = []
            for other in other_rows:
                common = len(my_genres.intersection(set(other.get("genres", []))))
                related.append((common, other))

            related.sort(key=lambda x: (x[0], x[1].get("community_rating") or 0), reverse=True)
            movie["recommendations"] = [item[1] for item in related[:8]]

            return movie
