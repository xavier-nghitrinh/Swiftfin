import logging
from typing import Dict, Any
from backend.database import get_db, now_iso, find_media_item
from backend.jellyfin_client import jellyfin
import os

logger = logging.getLogger("mytube.cleanup")

class CleanupService:
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
