import sqlite3
import uuid
from typing import Any, Dict, List, Optional
from backend.ai_chat_store import delete_user_ai_data
from backend.database import get_db, now_iso

class UserService:
    @staticmethod
    def list_users() -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, name, created_at FROM users ORDER BY lower(name)")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_user(user_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, name, created_at FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_user_by_name(name: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, name, created_at FROM users WHERE lower(name) = lower(?)",
                (name,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create_user(name: str) -> Optional[Dict[str, Any]]:
        """Create a user. Returns None when the name already exists (case-insensitive)."""
        user = {"user_id": uuid.uuid4().hex, "name": name, "created_at": now_iso()}
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, created_at) VALUES (?, ?, ?)",
                    (user["user_id"], user["name"], user["created_at"]),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            return None
        return user

    @staticmethod
    def ensure_user(name: str) -> Dict[str, Any]:
        existing = UserService.get_user_by_name(name)
        if existing:
            return existing
        created = UserService.create_user(name)
        return created or UserService.get_user_by_name(name)

    @staticmethod
    def delete_user(user_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                return False
            cursor.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_subscriptions WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_music WHERE user_id = ?", (user_id,))
            cursor.execute(
                "DELETE FROM music_playlist_items WHERE playlist_id IN (SELECT playlist_id FROM music_playlists WHERE user_id = ?)",
                (user_id,),
            )
            cursor.execute("DELETE FROM music_playlists WHERE user_id = ?", (user_id,))
            delete_user_ai_data(cursor, user_id)
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
        return True

    @staticmethod
    def set_subscription(user_id: str, channel_id: str, subscribed: bool) -> None:
        with get_db() as conn:
            cursor = conn.cursor()
            if subscribed:
                cursor.execute(
                    "INSERT OR IGNORE INTO user_subscriptions (user_id, channel_id, created_at) VALUES (?, ?, ?)",
                    (user_id, channel_id, now_iso()),
                )
            else:
                cursor.execute(
                    "DELETE FROM user_subscriptions WHERE user_id = ? AND channel_id = ?",
                    (user_id, channel_id),
                )
            conn.commit()

    @staticmethod
    def get_progress(cursor, user_id: str, media_id: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT media_id, watched, watched_at, playback_position, updated_at FROM user_progress WHERE user_id = ? AND media_id = ?",
            (user_id, media_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_progress_map(cursor, user_id: str, media_type: str) -> Dict[str, Dict[str, Any]]:
        cursor.execute(
            "SELECT media_id, watched, watched_at, playback_position, updated_at FROM user_progress WHERE user_id = ? AND media_type = ?",
            (user_id, media_type),
        )
        return {row["media_id"]: dict(row) for row in cursor.fetchall()}

    @staticmethod
    def progress_fields(progress: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Per-user watch state in the field names the API exposes."""
        if not progress:
            return {"watched": 0, "watched_at": None, "playback_position": 0}
        return {
            "watched": progress["watched"] or 0,
            "watched_at": progress["watched_at"],
            "playback_position": progress["playback_position"] or 0,
        }
