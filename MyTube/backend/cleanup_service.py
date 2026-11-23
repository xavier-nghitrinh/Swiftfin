import logging
import os
import re
from typing import Dict, Any, List
from backend.ai_chat_store import delete_media_ai_data
from backend.config import MAX_MEDIA_GB, REMOTE_MEDIA_DIR
from backend.database import get_db, now_iso, find_media_item
from backend.jellyfin_client import jellyfin

logger = logging.getLogger("mytube.cleanup")

SIDECAR_SUFFIXES = (".info.json", ".nfo", ".jpg", ".webp", "-thumb.jpg")
SUBTITLE_PATTERN = r"\.[\w-]+\.(vtt|srt|ass)"

def _related_files(file_path: str) -> List[str]:
    """Existing files that belong to a YouTube video: the media file plus its sidecars and subtitles."""
    directory, filename = os.path.split(file_path)
    if not directory or not os.path.isdir(directory):
        return []
    stem = os.path.splitext(filename)[0]
    names = {filename, *(f"{stem}{suffix}" for suffix in SIDECAR_SUFFIXES)}
    subtitle_re = re.compile(re.escape(stem) + SUBTITLE_PATTERN)
    found = []
    for name in os.listdir(directory):
        if name in names or subtitle_re.fullmatch(name):
            found.append(os.path.join(directory, name))
    return found

def _size_of(paths: List[str]) -> int:
    total = 0
    for p in paths:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total

def _folder_size(root: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total

class CleanupService:
    @staticmethod
    def delete_permanently(video_id: str, refresh_library: bool = True) -> Dict[str, Any]:
        """Delete an item through Jellyfin, then remove its local files and database rows.

        Jellyfin goes first: if it refuses, nothing local is touched. Videos are hard-deleted
        from SQLite so MyTube stops listing them; movies and episodes keep a 'deleted' tombstone.
        """
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

        # 2. Remove leftovers Jellyfin does not own (sidecars, thumbnails, subtitles) so nothing is orphaned
        if file_path:
            for p in _related_files(file_path):
                try:
                    os.remove(p)
                except Exception as e:
                    logger.warning(f"Failed to delete local file {p}: {e}")

        # 3. Update SQLite
        now = now_iso()
        with get_db() as conn:
            cursor = conn.cursor()
            if media_type == "movie":
                cursor.execute("UPDATE movies SET file_status = 'deleted', updated_at = ? WHERE movie_id = ?", (now, video_id))
            elif media_type == "episode":
                cursor.execute("UPDATE episodes SET file_status = 'deleted', updated_at = ? WHERE episode_id = ?", (now, video_id))
            else:
                cursor.execute("DELETE FROM user_progress WHERE media_id = ? AND media_type = 'youtube'", (video_id,))
                cursor.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
            delete_media_ai_data(cursor, video_id)
            conn.commit()

        if refresh_library:
            jellyfin.trigger_refresh()

        return {"status": "ok", "video_id": video_id, "media_type": media_type, "action": "permanently_deleted"}

    @staticmethod
    def run_space_cleanup() -> Dict[str, Any]:
        """Delete YouTube videos until the media folder fits in MAX_MEDIA_GB.

        Candidates are ordered with videos watched by any user first, then unwatched ones. Within each
        group, oldest upload_date first (unknown dates last). Each one goes through delete_permanently,
        so Jellyfin removes the files and SQLite drops the row.
        """
        limit_bytes = int(MAX_MEDIA_GB * 1024 ** 3)
        root = REMOTE_MEDIA_DIR
        if not os.path.isdir(root):
            logger.warning(f"Space cleanup skipped: media folder not found at {root}")
            return {"status": "skipped", "reason": "media folder not found", "path": root}

        used = _folder_size(root)
        result: Dict[str, Any] = {
            "status": "ok",
            "used_bytes": used,
            "limit_bytes": limit_bytes,
            "deleted": [],
            "failed": [],
        }
        if used <= limit_bytes:
            result["final_bytes"] = used
            return result

        with get_db() as conn:
            candidates = conn.execute("""
                SELECT v.video_id, v.title, v.file_path FROM videos v
                WHERE v.file_status = 'available'
                  AND v.jellyfin_item_id IS NOT NULL AND v.jellyfin_item_id != ''
                  AND v.file_path IS NOT NULL AND v.file_path != ''
                ORDER BY
                  EXISTS (
                    SELECT 1 FROM user_progress p
                    WHERE p.media_id = v.video_id AND p.media_type = 'youtube' AND p.watched = 1
                  ) DESC,
                  (v.upload_date IS NULL), v.upload_date ASC, v.created_at ASC, v.video_id ASC
            """).fetchall()

        logger.info(f"Space cleanup: {used / 1024 ** 3:.1f} GiB used, limit {MAX_MEDIA_GB:g} GiB")
        for row in candidates:
            if used <= limit_bytes:
                break
            freed = _size_of(_related_files(row["file_path"]))
            res = CleanupService.delete_permanently(row["video_id"], refresh_library=False)
            if res.get("status") == "ok":
                used -= freed
                result["deleted"].append(row["video_id"])
            else:
                result["failed"].append({"video_id": row["video_id"], "message": res.get("message")})

        if result["deleted"]:
            jellyfin.trigger_refresh()

        result["final_bytes"] = _folder_size(root)
        logger.info(
            f"Space cleanup finished: deleted {len(result['deleted'])}, failed {len(result['failed'])}, "
            f"now {result['final_bytes'] / 1024 ** 3:.1f} GiB"
        )
        return result
