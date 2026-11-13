import sqlite3
from typing import List, Dict, Any, Optional
from backend.database import get_db

class FeedService:
    @staticmethod
    def get_home_feed(limit: int = 50, offset: int = 0, unplayed_only: bool = True) -> Dict[str, Any]:
        """Fetch subscription feed: latest videos across all channels."""
        with get_db() as conn:
            cursor = conn.cursor()
            
            where_clauses = ["v.file_status = 'available'"]
            params = []
            
            if unplayed_only:
                where_clauses.append("v.watched = 0")
                
            where_sql = " AND ".join(where_clauses)
            
            count_query = f"SELECT COUNT(*) FROM videos v WHERE {where_sql}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            query = f"""
                SELECT 
                    v.video_id, v.channel_id, v.channel_name, v.title, v.description,
                    v.upload_date, v.duration, v.thumbnail_url, v.jellyfin_item_id,
                    v.watched, v.watched_at, v.playback_position, v.file_status,
                    COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                WHERE {where_sql}
                ORDER BY v.upload_date DESC, v.video_id DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, params + [limit, offset])
            rows = [dict(row) for row in cursor.fetchall()]
            
            return {
                "items": rows,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(rows)) < total
            }

    @staticmethod
    def get_channels() -> List[Dict[str, Any]]:
        """Fetch all channels with unwatched and total video counts."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    c.channel_id,
                    c.name,
                    c.thumbnail_url,
                    COUNT(v.video_id) AS total_videos,
                    SUM(CASE WHEN v.watched = 0 AND v.file_status = 'available' THEN 1 ELSE 0 END) AS unwatched_count,
                    MAX(v.upload_date) AS latest_upload_date
                FROM channels c
                LEFT JOIN videos v ON c.channel_id = v.channel_id
                GROUP BY c.channel_id, c.name, c.thumbnail_url
                ORDER BY unwatched_count DESC, latest_upload_date DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_channel_detail(channel_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    c.channel_id,
                    c.name,
                    c.thumbnail_url,
                    COUNT(v.video_id) AS total_videos,
                    SUM(CASE WHEN v.watched = 0 AND v.file_status = 'available' THEN 1 ELSE 0 END) AS unwatched_count
                FROM channels c
                LEFT JOIN videos v ON c.channel_id = v.channel_id
                WHERE c.channel_id = ?
                GROUP BY c.channel_id, c.name, c.thumbnail_url
            """, (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_channel_videos(
        channel_id: str,
        filter_type: str = "all", # 'all', 'unwatched', 'watched'
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            
            where_clauses = ["v.channel_id = ?", "v.file_status = 'available'"]
            params = [channel_id]
            
            if filter_type == "unwatched":
                where_clauses.append("v.watched = 0")
            elif filter_type == "watched":
                where_clauses.append("v.watched = 1")
                
            where_sql = " AND ".join(where_clauses)
            
            count_query = f"SELECT COUNT(*) FROM videos v WHERE {where_sql}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            query = f"""
                SELECT 
                    v.video_id, v.channel_id, v.channel_name, v.title, v.description,
                    v.upload_date, v.duration, v.thumbnail_url, v.jellyfin_item_id,
                    v.watched, v.watched_at, v.playback_position, v.file_status,
                    COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                WHERE {where_sql}
                ORDER BY v.upload_date DESC, v.video_id DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, params + [limit, offset])
            rows = [dict(row) for row in cursor.fetchall()]
            
            return {
                "items": rows,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(rows)) < total
            }

    @staticmethod
    def get_video(video_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT v.*, COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                WHERE v.video_id = ?
            """, (video_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def search(query_str: str, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            like_pat = f"%{query_str}%"
            results = []

            # 1. Videos
            cursor.execute("""
                SELECT 
                    v.video_id, v.channel_id, v.channel_name, v.title,
                    v.upload_date, v.duration, v.thumbnail_url, v.jellyfin_item_id,
                    v.watched, v.playback_position, v.file_status,
                    COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url,
                    'youtube' AS media_type
                FROM videos v
                LEFT JOIN channels c ON v.channel_id = c.channel_id
                WHERE (v.title LIKE ? OR v.channel_name LIKE ?) AND v.file_status = 'available'
                ORDER BY v.upload_date DESC
                LIMIT ?
            """, (like_pat, like_pat, limit))
            results.extend([dict(row) for row in cursor.fetchall()])

            # 2. Movies
            cursor.execute("""
                SELECT 
                    movie_id AS video_id, 'movies' AS channel_id, CAST(release_year AS TEXT) AS channel_name,
                    title, premiere_date AS upload_date, duration, COALESCE(poster_url, backdrop_url) AS thumbnail_url,
                    jellyfin_item_id, watched, playback_position, file_status, '' AS channel_thumbnail_url,
                    'movie' AS media_type
                FROM movies
                WHERE (title LIKE ? OR overview LIKE ?) AND file_status = 'available'
                ORDER BY release_year DESC
                LIMIT ?
            """, (like_pat, like_pat, limit))
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
    def get_stats() -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM channels")
            total_channels = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos WHERE file_status = 'available'")
            total_videos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos WHERE watched = 0 AND file_status = 'available'")
            unwatched_videos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos WHERE watched = 1 AND file_status = 'available'")
            watched_videos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos WHERE file_status = 'trash'")
            trash_videos = cursor.fetchone()[0]

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
                "trash_videos": trash_videos,
                "total_movies": total_movies,
                "total_shows": total_shows,
                "total_episodes": total_episodes
            }
