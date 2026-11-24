import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from backend.database import get_db, now_iso
from backend.jellyfin_client import jellyfin

logger = logging.getLogger("mytube.music")

FORGOTTEN_AFTER_DAYS = 90
FORGOTTEN_MIN_PLAYS = 3

_TRACK_COLUMNS = """
    t.track_id, t.title, t.artist, t.source_group, t.image_item_id, t.duration, t.release_year,
    COALESCE(u.favorite, 0) AS favorite, COALESCE(u.play_count, 0) AS play_count,
    u.last_played_at, u.favorited_at
"""
_TRACK_FROM = """
    FROM music_tracks t
    LEFT JOIN user_music u ON u.track_id = t.track_id AND u.user_id = ?
"""


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class MusicService:
    @staticmethod
    def _track_dict(row) -> Dict[str, Any]:
        d = dict(row)
        image_item_id = d.pop("image_item_id") or d["track_id"]
        d["favorite"] = bool(d["favorite"])
        d["play_count"] = int(d["play_count"] or 0)
        d["image_url"] = jellyfin.get_image_url(image_item_id, "Primary", 300, 80)
        d["stream_url"] = jellyfin.get_proxy_url(d["track_id"], "audio", {"static": "true"})
        return d

    @classmethod
    def _query_tracks(cls, cursor, user_id: str, where_sql: str = "", params: tuple = (), order_sql: str = "t.artist, t.title") -> List[Dict[str, Any]]:
        cursor.execute(
            f"SELECT {_TRACK_COLUMNS} {_TRACK_FROM} {where_sql} ORDER BY {order_sql}",
            (user_id, *params),
        )
        return [cls._track_dict(r) for r in cursor.fetchall()]

    @staticmethod
    def _group_tracks(tracks: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        """Summarize tracks into named groups (artist or source collection) with a representative cover."""
        groups: Dict[str, Dict[str, Any]] = {}
        for track in tracks:
            name = track.get(key) or ""
            if not name:
                continue
            group = groups.setdefault(name, {"name": name, "track_count": 0, "image_url": track["image_url"]})
            group["track_count"] += 1
        return sorted(groups.values(), key=lambda g: g["name"].casefold())

    @classmethod
    def _list_playlists(cls, cursor, user_id: str) -> List[Dict[str, Any]]:
        cursor.execute("""
            SELECT p.playlist_id, p.name, p.created_at, p.updated_at, COUNT(i.item_id) AS track_count,
                (
                    SELECT COALESCE(t.image_item_id, t.track_id)
                    FROM music_playlist_items fi
                    JOIN music_tracks t ON t.track_id = fi.track_id
                    WHERE fi.playlist_id = p.playlist_id
                    ORDER BY fi.item_id
                    LIMIT 1
                ) AS image_item_id
            FROM music_playlists p
            LEFT JOIN music_playlist_items i ON i.playlist_id = p.playlist_id
            WHERE p.user_id = ?
            GROUP BY p.playlist_id
            ORDER BY p.updated_at DESC
        """, (user_id,))
        playlists = []
        for r in cursor.fetchall():
            d = dict(r)
            image_item_id = d.pop("image_item_id")
            d["image_url"] = jellyfin.get_image_url(image_item_id, "Primary", 300, 80) if image_item_id else None
            playlists.append(d)
        return playlists

    @classmethod
    def get_home(cls, user_id: str) -> Dict[str, Any]:
        """Music home: random picks, favorites, recently played, forgotten favorites, and artist/collection shelves."""
        with get_db() as conn:
            cursor = conn.cursor()
            tracks = cls._query_tracks(cursor, user_id)
            playlists = cls._list_playlists(cursor, user_id)

        favorites = sorted(
            (t for t in tracks if t["favorite"]),
            key=lambda t: t.get("favorited_at") or "",
            reverse=True,
        )
        recently_played = sorted(
            (t for t in tracks if t["last_played_at"]),
            key=lambda t: t["last_played_at"],
            reverse=True,
        )[:20]

        cutoff = datetime.now(timezone.utc) - timedelta(days=FORGOTTEN_AFTER_DAYS)
        forgotten = [
            t for t in tracks
            if t["play_count"] >= FORGOTTEN_MIN_PLAYS
            and (_parse_iso(t["last_played_at"]) or cutoff) < cutoff
        ]
        random.shuffle(forgotten)

        artists = cls._group_tracks(tracks, "artist")
        collections = cls._group_tracks(tracks, "source_group")

        return {
            "random_tracks": random.sample(tracks, min(20, len(tracks))),
            "favorites": favorites[:50],
            "recently_played": recently_played,
            "forgotten": forgotten[:20],
            "random_artists": random.sample(artists, min(12, len(artists))),
            "random_collections": random.sample(collections, min(12, len(collections))),
            "playlists": playlists,
            "total_tracks": len(tracks),
        }

    @classmethod
    def get_tracks(cls, user_id: str, query: str = "") -> List[Dict[str, Any]]:
        """All tracks sorted by artist and title, optionally filtered by a search term."""
        with get_db() as conn:
            cursor = conn.cursor()
            if query.strip():
                pattern = f"%{query.strip()}%"
                return cls._query_tracks(
                    cursor,
                    user_id,
                    "WHERE t.title LIKE ? OR t.artist LIKE ? OR t.source_group LIKE ?",
                    (pattern, pattern, pattern),
                )
            return cls._query_tracks(cursor, user_id)

    @classmethod
    def get_artists(cls, user_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            tracks = cls._query_tracks(conn.cursor(), user_id)
        return cls._group_tracks(tracks, "artist")

    @classmethod
    def get_artist_tracks(cls, user_id: str, artist: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            return cls._query_tracks(conn.cursor(), user_id, "WHERE t.artist = ?", (artist,), "t.title")

    @classmethod
    def get_collections(cls, user_id: str) -> List[Dict[str, Any]]:
        """Collections are the source playlist folders that Jellyfin records as album artist."""
        with get_db() as conn:
            tracks = cls._query_tracks(conn.cursor(), user_id)
        return cls._group_tracks(tracks, "source_group")

    @classmethod
    def get_collection_tracks(cls, user_id: str, collection: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            return cls._query_tracks(conn.cursor(), user_id, "WHERE t.source_group = ?", (collection,), "t.artist, t.title")

    @classmethod
    def get_favorites(cls, user_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            return cls._query_tracks(
                conn.cursor(), user_id, "WHERE u.favorite = 1", (), "u.favorited_at DESC"
            )

    @staticmethod
    def track_exists(track_id: str) -> bool:
        with get_db() as conn:
            return conn.execute("SELECT 1 FROM music_tracks WHERE track_id = ?", (track_id,)).fetchone() is not None

    @staticmethod
    def set_favorite(user_id: str, track_id: str, favorite: bool) -> None:
        now = now_iso()
        with get_db() as conn:
            conn.execute("""
                INSERT INTO user_music (user_id, track_id, favorite, favorited_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, track_id) DO UPDATE SET
                    favorite = excluded.favorite,
                    favorited_at = excluded.favorited_at
            """, (user_id, track_id, 1 if favorite else 0, now if favorite else None))
            conn.commit()

    @staticmethod
    def record_play(user_id: str, track_id: str) -> None:
        now = now_iso()
        with get_db() as conn:
            conn.execute("""
                INSERT INTO user_music (user_id, track_id, play_count, last_played_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, track_id) DO UPDATE SET
                    play_count = user_music.play_count + 1,
                    last_played_at = excluded.last_played_at
            """, (user_id, track_id, now))
            conn.commit()

    @classmethod
    def list_playlists(cls, user_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            return cls._list_playlists(conn.cursor(), user_id)

    @staticmethod
    def _owns_playlist(cursor, user_id: str, playlist_id: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM music_playlists WHERE playlist_id = ? AND user_id = ?",
            (playlist_id, user_id),
        )
        return cursor.fetchone() is not None

    @classmethod
    def create_playlist(cls, user_id: str, name: str) -> Dict[str, Any]:
        playlist_id = uuid.uuid4().hex
        now = now_iso()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO music_playlists (playlist_id, user_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (playlist_id, user_id, name, now, now),
            )
            conn.commit()
        return {"playlist_id": playlist_id, "name": name, "track_count": 0, "created_at": now, "updated_at": now}

    @classmethod
    def get_playlist(cls, user_id: str, playlist_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            if not cls._owns_playlist(cursor, user_id, playlist_id):
                return None
            cursor.execute(
                "SELECT playlist_id, name, created_at, updated_at FROM music_playlists WHERE playlist_id = ?",
                (playlist_id,),
            )
            playlist = dict(cursor.fetchone())
            cursor.execute(f"""
                SELECT i.item_id, {_TRACK_COLUMNS}
                FROM music_playlist_items i
                JOIN music_tracks t ON t.track_id = i.track_id
                LEFT JOIN user_music u ON u.track_id = t.track_id AND u.user_id = ?
                WHERE i.playlist_id = ?
                ORDER BY i.item_id
            """, (user_id, playlist_id))
            playlist["tracks"] = [cls._track_dict(r) for r in cursor.fetchall()]
            playlist["track_count"] = len(playlist["tracks"])
            return playlist

    @classmethod
    def rename_playlist(cls, user_id: str, playlist_id: str, name: str) -> bool:
        with get_db() as conn:
            if not cls._owns_playlist(conn.cursor(), user_id, playlist_id):
                return False
            conn.execute(
                "UPDATE music_playlists SET name = ?, updated_at = ? WHERE playlist_id = ?",
                (name, now_iso(), playlist_id),
            )
            conn.commit()
            return True

    @classmethod
    def delete_playlist(cls, user_id: str, playlist_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.cursor()
            if not cls._owns_playlist(cursor, user_id, playlist_id):
                return False
            cursor.execute("DELETE FROM music_playlist_items WHERE playlist_id = ?", (playlist_id,))
            cursor.execute("DELETE FROM music_playlists WHERE playlist_id = ?", (playlist_id,))
            conn.commit()
            return True

    @classmethod
    def add_playlist_track(cls, user_id: str, playlist_id: str, track_id: str) -> bool:
        """Append a track to the playlist. Returns False when the playlist is not owned by the user or the track is unknown."""
        with get_db() as conn:
            cursor = conn.cursor()
            if not cls._owns_playlist(cursor, user_id, playlist_id):
                return False
            cursor.execute("SELECT 1 FROM music_tracks WHERE track_id = ?", (track_id,))
            if not cursor.fetchone():
                return False
            now = now_iso()
            cursor.execute(
                "INSERT INTO music_playlist_items (playlist_id, track_id, added_at) VALUES (?, ?, ?)",
                (playlist_id, track_id, now),
            )
            cursor.execute("UPDATE music_playlists SET updated_at = ? WHERE playlist_id = ?", (now, playlist_id))
            conn.commit()
            return True

    @classmethod
    def remove_playlist_item(cls, user_id: str, playlist_id: str, item_id: int) -> bool:
        with get_db() as conn:
            cursor = conn.cursor()
            if not cls._owns_playlist(cursor, user_id, playlist_id):
                return False
            cursor.execute(
                "DELETE FROM music_playlist_items WHERE item_id = ? AND playlist_id = ?",
                (item_id, playlist_id),
            )
            removed = cursor.rowcount > 0
            if removed:
                cursor.execute("UPDATE music_playlists SET updated_at = ? WHERE playlist_id = ?", (now_iso(), playlist_id))
            conn.commit()
            return removed
