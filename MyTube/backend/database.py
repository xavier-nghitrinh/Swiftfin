import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from backend.config import DB_PATH

logger = logging.getLogger("mytube.database")

def init_db():
    logger.info("Initializing SQLite database at: %s", DB_PATH)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Channels table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder_path TEXT,
                thumbnail_url TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Videos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT,
                channel_name TEXT,
                title TEXT NOT NULL,
                description TEXT,
                upload_date TEXT,
                duration REAL DEFAULT 0,
                file_path TEXT,
                thumbnail_url TEXT,
                jellyfin_item_id TEXT,
                watched INTEGER DEFAULT 0,
                watched_at TEXT,
                playback_position REAL DEFAULT 0,
                file_status TEXT DEFAULT 'available',
                trash_at TEXT,
                audio_meta TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            )
        """)
        try:
            cursor.execute("ALTER TABLE videos ADD COLUMN audio_meta TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        
        # Indexes for fast querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_watched_upload ON videos (watched, upload_date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos (channel_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_jellyfin ON videos (jellyfin_item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON videos (file_status)")
        
        # Playback sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playback_sessions (
                video_id TEXT PRIMARY KEY,
                position_seconds REAL DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)

        # Movies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                movie_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                overview TEXT DEFAULT '',
                release_year INTEGER,
                premiere_date TEXT,
                duration REAL DEFAULT 0,
                genres TEXT DEFAULT '[]',
                official_rating TEXT DEFAULT '',
                community_rating REAL DEFAULT 0,
                poster_url TEXT DEFAULT '',
                backdrop_url TEXT DEFAULT '',
                file_path TEXT,
                jellyfin_item_id TEXT NOT NULL,
                watched INTEGER DEFAULT 0,
                watched_at TEXT,
                playback_position REAL DEFAULT 0,
                file_status TEXT DEFAULT 'available',
                trash_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_movies_watched ON movies (watched)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_movies_year ON movies (release_year DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_movies_status ON movies (file_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_movies_jellyfin ON movies (jellyfin_item_id)")

        # Shows (Series) table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shows (
                show_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                overview TEXT DEFAULT '',
                start_year INTEGER,
                status TEXT DEFAULT '',
                genres TEXT DEFAULT '[]',
                official_rating TEXT DEFAULT '',
                community_rating REAL DEFAULT 0,
                poster_url TEXT DEFAULT '',
                backdrop_url TEXT DEFAULT '',
                file_path TEXT,
                jellyfin_item_id TEXT NOT NULL,
                file_status TEXT DEFAULT 'available',
                trash_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shows_status ON shows (file_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shows_jellyfin ON shows (jellyfin_item_id)")

        # Episodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY,
                show_id TEXT NOT NULL,
                show_name TEXT NOT NULL,
                season_id TEXT,
                season_name TEXT DEFAULT 'Season 1',
                season_number INTEGER DEFAULT 1,
                episode_number INTEGER DEFAULT 1,
                title TEXT NOT NULL,
                overview TEXT DEFAULT '',
                premiere_date TEXT,
                duration REAL DEFAULT 0,
                thumbnail_url TEXT DEFAULT '',
                file_path TEXT,
                jellyfin_item_id TEXT NOT NULL,
                watched INTEGER DEFAULT 0,
                watched_at TEXT,
                playback_position REAL DEFAULT 0,
                file_status TEXT DEFAULT 'available',
                trash_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (show_id) REFERENCES shows(show_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_show ON episodes (show_id, season_number, episode_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_watched ON episodes (watched)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_jellyfin ON episodes (jellyfin_item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes (file_status)")

        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def find_media_item(cursor, media_id: str):
    """
    Search for a media item by ID across videos (YouTube), movies, and episodes.
    Returns tuple: (item_dict, media_type) or (None, None).
    """
    # 1. Check videos
    cursor.execute("""
        SELECT v.*, COALESCE(c.thumbnail_url, '') AS channel_thumbnail_url
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.video_id = ?
    """, (media_id,))
    row = cursor.fetchone()
    if row:
        d = dict(row)
        d["media_type"] = "youtube"
        return d, "youtube"

    # 2. Check movies
    cursor.execute("SELECT * FROM movies WHERE movie_id = ?", (media_id,))
    row = cursor.fetchone()
    if row:
        d = dict(row)
        d["media_type"] = "movie"
        d["video_id"] = d["movie_id"]
        d["channel_name"] = str(d.get("release_year") or "Movie")
        d["channel_id"] = "movies"
        d["channel_thumbnail_url"] = ""
        d["thumbnail_url"] = d.get("backdrop_url") or d.get("poster_url") or ""
        return d, "movie"

    # 3. Check episodes
    cursor.execute("SELECT * FROM episodes WHERE episode_id = ?", (media_id,))
    row = cursor.fetchone()
    if row:
        d = dict(row)
        d["media_type"] = "episode"
        d["video_id"] = d["episode_id"]
        d["channel_name"] = d["show_name"]
        d["channel_id"] = d["show_id"]
        d["channel_thumbnail_url"] = ""
        return d, "episode"

    return None, None

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
