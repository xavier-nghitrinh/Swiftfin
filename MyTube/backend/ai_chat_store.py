from typing import Any, Dict, List, Optional

from backend.database import now_iso


def get_note(cursor, user_id: str, media_id: str) -> Optional[Dict[str, Any]]:
    cursor.execute(
        "SELECT markdown, subtitle_label, created_at FROM user_ai_notes WHERE user_id = ? AND media_id = ?",
        (user_id, media_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def save_note(cursor, user_id: str, media_id: str, markdown: str, subtitle_label: str) -> Dict[str, Any]:
    created_at = now_iso()
    cursor.execute(
        """
        INSERT INTO user_ai_notes (user_id, media_id, markdown, subtitle_label, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id, media_id) DO UPDATE SET
            markdown = excluded.markdown,
            subtitle_label = excluded.subtitle_label,
            created_at = excluded.created_at
        """,
        (user_id, media_id, markdown, subtitle_label, created_at),
    )
    return {"markdown": markdown, "subtitle_label": subtitle_label, "created_at": created_at}


def list_messages(cursor, user_id: str, media_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Chat messages oldest first. With a limit, returns the most recent messages."""
    if limit is None:
        cursor.execute(
            """SELECT role, content, subtitle_label, created_at FROM user_ai_messages
               WHERE user_id = ? AND media_id = ? ORDER BY message_id""",
            (user_id, media_id),
        )
        return [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        """SELECT role, content, subtitle_label, created_at FROM user_ai_messages
           WHERE user_id = ? AND media_id = ? ORDER BY message_id DESC LIMIT ?""",
        (user_id, media_id, limit),
    )
    return [dict(row) for row in reversed(cursor.fetchall())]


def add_exchange(cursor, user_id: str, media_id: str, subtitle_label: str, question: str, answer: str) -> List[Dict[str, Any]]:
    created_at = now_iso()
    pair = [("user", question), ("assistant", answer)]
    for role, content in pair:
        cursor.execute(
            """INSERT INTO user_ai_messages (user_id, media_id, role, content, subtitle_label, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, media_id, role, content, subtitle_label, created_at),
        )
    return [
        {"role": role, "content": content, "subtitle_label": subtitle_label, "created_at": created_at}
        for role, content in pair
    ]


def delete_media_ai_data(cursor, media_id: str) -> None:
    """Remove every user's note and chat for a media item that was deleted or is gone from Jellyfin."""
    cursor.execute("DELETE FROM user_ai_notes WHERE media_id = ?", (media_id,))
    cursor.execute("DELETE FROM user_ai_messages WHERE media_id = ?", (media_id,))


def delete_user_ai_data(cursor, user_id: str) -> None:
    cursor.execute("DELETE FROM user_ai_notes WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_ai_messages WHERE user_id = ?", (user_id,))
