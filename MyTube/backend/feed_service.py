import sqlite3
from typing import List, Dict, Any, Optional
from backend.database import get_db
from backend.user_service import UserService

# Joins the requesting user's watch state for YouTube videos; binds user_id first.
YOUTUBE_PROGRESS_JOIN = "LEFT JOIN user_progress p ON p.media_id = v.video_id AND p.user_id = ? AND p.media_type = 'youtube'"

VIDEO_LIST_COLUMNS = """
                    v.video_id, v.channel_id, v.channel_name, v.title, v.description,
                    v.upload_date, v.duration, v.thumbnail_url, v.jellyfin_item_id,
                    COALESCE(p.watched, 0) AS watched, p.watched_at,
                    COALESCE(p.playback_position, 0) AS playback_position, v.file_status,
                    COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url
"""

class FeedService:
    @staticmethod
    def _paginated_videos(cursor, user_id: str, where_clauses: List[str], params: List[Any], limit: int, offset: int) -> Dict[str, Any]:
        where_sql = " AND ".join(where_clauses)

        cursor.execute(
            f"SELECT COUNT(*) FROM videos v {YOUTUBE_PROGRESS_JOIN} WHERE {where_sql}",
            [user_id] + params,
        )
        total = cursor.fetchone()[0]

        query = f"""
                SELECT {VIDEO_LIST_COLUMNS}
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                {YOUTUBE_PROGRESS_JOIN}
                WHERE {where_sql}
                ORDER BY v.upload_date DESC, v.video_id DESC
                LIMIT ? OFFSET ?
            """
        cursor.execute(query, [user_id] + params + [limit, offset])
        rows = [dict(row) for row in cursor.fetchall()]

        return {
            "items": rows,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(rows)) < total
        }

    @staticmethod
    def get_home_feed(user_id: str, limit: int = 50, offset: int = 0, unplayed_only: bool = True) -> Dict[str, Any]:
        """Fetch the user's subscription feed: latest available videos from subscribed channels."""
        with get_db() as conn:
            cursor = conn.cursor()
            where_clauses = [
                "v.file_status = 'available'",
                "v.channel_id IN (SELECT channel_id FROM user_subscriptions WHERE user_id = ?)",
            ]
            params: List[Any] = [user_id]
            if unplayed_only:
                where_clauses.append("COALESCE(p.watched, 0) = 0")
            return FeedService._paginated_videos(cursor, user_id, where_clauses, params, limit, offset)

    @staticmethod
    def _fetch_channels(cursor, user_id: str, where_sql: str = "", where_params: tuple = (), order_sql: str = "") -> List[Dict[str, Any]]:
        query = f"""
            SELECT
                c.channel_id,
                c.name,
                c.thumbnail_url,
                CASE WHEN s.user_id IS NULL THEN 0 ELSE 1 END AS subscribed,
                COUNT(v.video_id) AS total_videos,
                COALESCE(SUM(CASE WHEN v.video_id IS NOT NULL AND COALESCE(p.watched, 0) = 0 THEN 1 ELSE 0 END), 0) AS unwatched_count,
                COALESCE(SUM(v.file_size_bytes), 0) AS total_size_bytes,
                MAX(v.upload_date) AS latest_upload_date
            FROM channels c
            LEFT JOIN user_subscriptions s ON s.channel_id = c.channel_id AND s.user_id = ?
            LEFT JOIN videos v ON v.channel_id = c.channel_id AND v.file_status = 'available'
            LEFT JOIN user_progress p ON p.media_id = v.video_id AND p.user_id = ? AND p.media_type = 'youtube'
            {where_sql}
            GROUP BY c.channel_id, c.name, c.thumbnail_url, s.user_id
            {order_sql}
        """
        cursor.execute(query, [user_id, user_id, *where_params])
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            d["subscribed"] = bool(d["subscribed"])
            rows.append(d)
        return rows

    @staticmethod
    def get_channels(user_id: str, subscription: str = "all") -> List[Dict[str, Any]]:
        """All channels with the user's subscription flag and per-user unwatched counts.

        The DB can hold several channel rows with the same name (for example a folder-based ID
        and a YouTube ID from an older path). Only one row per name is listed: the one with the
        most videos, so the duplicate empty rows don't appear.
        """
        with get_db() as conn:
            rows = FeedService._fetch_channels(conn.cursor(), user_id)

        canonical: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = (row["name"] or "").casefold()
            best = canonical.get(key)
            if best is None or (row["total_videos"], row["channel_id"]) > (best["total_videos"], best["channel_id"]):
                canonical[key] = row

        channels = list(canonical.values())
        if subscription == "subscribed":
            channels = [c for c in channels if c["subscribed"]]
        elif subscription == "unsubscribed":
            channels = [c for c in channels if not c["subscribed"]]
        channels.sort(key=lambda c: (c["unwatched_count"] or 0, c["latest_upload_date"] or ""), reverse=True)
        return channels

    @staticmethod
    def get_channel_detail(channel_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            rows = FeedService._fetch_channels(conn.cursor(), user_id, "WHERE c.channel_id = ?", (channel_id,))
            return rows[0] if rows else None

    @staticmethod
    def get_channel_videos(
        channel_id: str,
        user_id: str,
        filter_type: str = "all", # 'all', 'unwatched', 'watched'
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            
            where_clauses = ["v.channel_id = ?", "v.file_status = 'available'"]
            params = [channel_id]
            
            if filter_type == "unwatched":
                where_clauses.append("COALESCE(p.watched, 0) = 0")
            elif filter_type == "watched":
                where_clauses.append("COALESCE(p.watched, 0) = 1")

            return FeedService._paginated_videos(cursor, user_id, where_clauses, params, limit, offset)

    @staticmethod
    def get_video(video_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT v.*, COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                WHERE v.video_id = ?
            """, (video_id,))
            row = cursor.fetchone()
            if not row:
                return None
            video = dict(row)
            video.update(UserService.progress_fields(UserService.get_progress(cursor, user_id, video_id)))
            return video

    @staticmethod
    def search(query_str: str, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            like_pat = f"%{query_str}%"
            results = []

            # 1. Videos
            cursor.execute("""
                SELECT 
                    v.video_id, v.channel_id, v.channel_name, v.title,
                    v.upload_date, v.duration, v.thumbnail_url, v.jellyfin_item_id,
                    COALESCE(p.watched, 0) AS watched, COALESCE(p.playback_position, 0) AS playback_position, v.file_status,
                    COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url,
                    'youtube' AS media_type
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                LEFT JOIN user_progress p ON p.media_id = v.video_id AND p.user_id = ? AND p.media_type = 'youtube'
                WHERE (v.title LIKE ? OR v.channel_name LIKE ?) AND v.file_status = 'available'
                  AND v.channel_id IN (SELECT channel_id FROM user_subscriptions WHERE user_id = ?)
                ORDER BY v.upload_date DESC
                LIMIT ?
            """, (user_id, like_pat, like_pat, user_id, limit))
            results.extend([dict(row) for row in cursor.fetchall()])

            # 2. Movies
            cursor.execute("""
                SELECT 
                    movie_id AS video_id, 'movies' AS channel_id, CAST(release_year AS TEXT) AS channel_name,
                    title, premiere_date AS upload_date, duration, COALESCE(poster_url, backdrop_url) AS thumbnail_url,
                    jellyfin_item_id, COALESCE(p.watched, 0) AS watched, COALESCE(p.playback_position, 0) AS playback_position, file_status, '' AS channel_thumbnail_url,
                    'movie' AS media_type
                FROM movies
                LEFT JOIN user_progress p ON p.media_id = movies.movie_id AND p.user_id = ? AND p.media_type = 'movie'
                WHERE (title LIKE ? OR overview LIKE ?) AND file_status = 'available'
                ORDER BY release_year DESC
                LIMIT ?
            """, (user_id, like_pat, like_pat, limit))
            results.extend([dict(row) for row in cursor.fetchall()])

            # 3. Shows
            cursor.execute("""
                SELECT 
                    show_id AS video_id, show_id AS channel_id, title AS channel_name,
                    title, CAST(start_year AS TEXT) AS upload_date, 0 AS duration, COALESCE(poster_url, backdrop_url) AS thumbnail_url,
                    jellyfin_item_id, 0 AS watched, 0 AS playback_position, file_status, '' AS channel_thumbnail_url,
                    'show' AS media_type
                FROM shows
                WHERE (title LIKE ? OR overview LIKE ?) AND file_status = 'available'
                ORDER BY start_year DESC
                LIMIT ?
            """, (like_pat, like_pat, limit))
            results.extend([dict(row) for row in cursor.fetchall()])

            return results[:limit]

    @staticmethod
    def get_stats(user_id: str) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM channels")
            total_channels = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos WHERE file_status = 'available'")
            total_videos = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM videos v
                LEFT JOIN user_progress p ON p.media_id = v.video_id AND p.user_id = ? AND p.media_type = 'youtube'
                WHERE COALESCE(p.watched, 0) = 0 AND v.file_status = 'available'
            """, (user_id,))
            unwatched_videos = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM videos v
                INNER JOIN user_progress p ON p.media_id = v.video_id AND p.user_id = ? AND p.media_type = 'youtube'
                WHERE p.watched = 1 AND v.file_status = 'available'
            """, (user_id,))
            watched_videos = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM movies WHERE file_status = 'available'")
            total_movies = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM shows WHERE file_status = 'available'")
            total_shows = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM episodes WHERE file_status = 'available'")
            total_episodes = cursor.fetchone()[0]
            
            return {
                "total_channels": total_channels,
                "total_videos": total_videos,
                "unwatched_videos": unwatched_videos,
                "watched_videos": watched_videos,
                "total_movies": total_movies,
                "total_shows": total_shows,
                "total_episodes": total_episodes
            }
