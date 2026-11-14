import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from backend.config import TRASH_RETENTION_DAYS
from backend.database import get_db, now_iso, find_media_item
from backend.jellyfin_client import jellyfin
import os

logger = logging.getLogger("mytube.cleanup")

class CleanupService:
    @staticmethod
    def move_to_trash(video_id: str) -> Dict[str, Any]:
        """Move item to MyTube trash for 30-day retention across videos, movies, and episodes."""
        now = now_iso()
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return {"status": "error", "message": "Media item not found"}

            if media_type == "movie":
                cursor.execute("UPDATE movies SET file_status = 'trash', trash_at = ?, updated_at = ? WHERE movie_id = ?", (now, now, video_id))
            elif media_type == "episode":
                cursor.execute("UPDATE episodes SET file_status = 'trash', trash_at = ?, updated_at = ? WHERE episode_id = ?", (now, now, video_id))
            else:
                cursor.execute("UPDATE videos SET file_status = 'trash', trash_at = ?, updated_at = ? WHERE video_id = ?", (now, now, video_id))
            conn.commit()
            
        logger.info(f"{media_type.capitalize()} {video_id} moved to trash.")
        return {"status": "ok", "video_id": video_id, "media_type": media_type, "action": "moved_to_trash", "trash_at": now}

    @staticmethod
    def restore_from_trash(video_id: str) -> Dict[str, Any]:
        """Restore item from trash back to available."""
        now = now_iso()
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return {"status": "error", "message": "Media item not found"}

            if media_type == "movie":
                cursor.execute("UPDATE movies SET file_status = 'available', trash_at = NULL, updated_at = ? WHERE movie_id = ?", (now, video_id))
            elif media_type == "episode":
                cursor.execute("UPDATE episodes SET file_status = 'available', trash_at = NULL, updated_at = ? WHERE episode_id = ?", (now, video_id))
            else:
                cursor.execute("UPDATE videos SET file_status = 'available', trash_at = NULL, updated_at = ? WHERE video_id = ?", (now, video_id))
            conn.commit()
            
        logger.info(f"{media_type.capitalize()} {video_id} restored from trash.")
        return {"status": "ok", "video_id": video_id, "media_type": media_type, "action": "restored"}

    @staticmethod
    def delete_permanently(video_id: str) -> Dict[str, Any]:
        """Delete an item through Jellyfin and remove any local sidecar files."""
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return {"status": "error", "message": "Media item not found"}
                
            item_id = media["jellyfin_item_id"]
            file_path = media.get("file_path")
            title = media.get("title")

        logger.info(f"Permanently deleting {media_type} {video_id} ({title}) - Jellyfin item: {item_id}")
        
        # 1. Delete via Jellyfin API (removes physical media from SSD)
        jf_success = jellyfin.delete_item(item_id)
        if not jf_success:
            logger.error("Jellyfin could not delete %s %s; leaving it available in MyTube", media_type, video_id)
            return {"status": "error", "message": "Jellyfin could not delete the media item"}

        # 2. Clean up sidecar files (.info.json, .nfo, .jpg)
        if file_path:
            base_path = os.path.splitext(file_path)[0]
            for ext in (".info.json", ".nfo", ".jpg", ".webp"):
                p = f"{base_path}{ext}"
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception as e:
                    logger.warning(f"Failed to delete local sidecar {p}: {e}")

        # 3. Mark as deleted in SQLite
        now = now_iso()
        with get_db() as conn:
            cursor = conn.cursor()
            if media_type == "movie":
                cursor.execute("UPDATE movies SET file_status = 'deleted', updated_at = ? WHERE movie_id = ?", (now, video_id))
            elif media_type == "episode":
                cursor.execute("UPDATE episodes SET file_status = 'deleted', updated_at = ? WHERE episode_id = ?", (now, video_id))
            else:
                cursor.execute("UPDATE videos SET file_status = 'deleted', updated_at = ? WHERE video_id = ?", (now, video_id))
            conn.commit()

        # 4. Trigger Jellyfin library refresh
        jellyfin.trigger_refresh()

        return {"status": "ok", "video_id": video_id, "media_type": media_type, "action": "permanently_deleted"}

    @staticmethod
    def get_trash_items() -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            items = []
            
            # 1. Videos
            cursor.execute("""
                SELECT video_id, channel_id, channel_name, title, upload_date, duration, thumbnail_url, trash_at, 'youtube' as media_type
                FROM videos
                WHERE file_status = 'trash'
            """)
            items.extend([dict(r) for r in cursor.fetchall()])

            # 2. Movies
            cursor.execute("""
                SELECT movie_id AS video_id, 'movies' AS channel_id, CAST(release_year AS TEXT) AS channel_name,
                       title, premiere_date AS upload_date, duration, COALESCE(poster_url, backdrop_url) AS thumbnail_url,
                       trash_at, 'movie' as media_type
                FROM movies
                WHERE file_status = 'trash'
            """)
            items.extend([dict(r) for r in cursor.fetchall()])

            # 3. Episodes
            cursor.execute("""
                SELECT episode_id AS video_id, show_id AS channel_id, show_name AS channel_name,
                       title, premiere_date AS upload_date, duration, thumbnail_url,
                       trash_at, 'episode' as media_type
                FROM episodes
                WHERE file_status = 'trash'
            """)
            items.extend([dict(r) for r in cursor.fetchall()])

            items.sort(key=lambda x: x.get("trash_at") or "", reverse=True)

            now = datetime.now(timezone.utc)
            for item in items:
                trash_at_str = item.get("trash_at")
                days_until_deletion = TRASH_RETENTION_DAYS
                if trash_at_str:
                    try:
                        trash_date = datetime.fromisoformat(trash_at_str)
                        if trash_date.tzinfo is None:
                            trash_date = trash_date.replace(tzinfo=timezone.utc)
                        expiry_date = trash_date + timedelta(days=TRASH_RETENTION_DAYS)
                        diff = expiry_date - now
                        days_until_deletion = max(0, int(math.ceil(diff.total_seconds() / 86400)))
                    except Exception:
                        days_until_deletion = TRASH_RETENTION_DAYS
                item["days_until_deletion"] = days_until_deletion
                item["trashed_at"] = trash_at_str
            return items

    @staticmethod
    def process_due_trash() -> Dict[str, Any]:
        """Permanently delete trashed media items after the retention period."""
        threshold_date = (datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)).isoformat()
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT video_id AS media_id FROM videos
                WHERE file_status = 'trash' AND trash_at <= ?
                UNION ALL
                SELECT movie_id AS media_id FROM movies
                WHERE file_status = 'trash' AND trash_at <= ?
                UNION ALL
                SELECT episode_id AS media_id FROM episodes
                WHERE file_status = 'trash' AND trash_at <= ?
            """, (threshold_date, threshold_date, threshold_date))
            rows = cursor.fetchall()
            due_ids = [r["media_id"] for r in rows]

        deleted_count = 0
        for vid in due_ids:
            res = CleanupService.delete_permanently(vid)
            if res.get("status") == "ok":
                deleted_count += 1

        return {"due_count": len(due_ids), "deleted_count": deleted_count}
