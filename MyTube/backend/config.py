import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local media directory for metadata and thumbnail access.
REMOTE_MEDIA_DIR = os.environ.get("MYTUBE_REMOTE_MEDIA_DIR", "/media/devmon/EXTERNAL/yt_video")

# Space-based auto-deletion: when the YouTube media folder exceeds this many GiB,
# the oldest available videos are deleted (via Jellyfin) until it fits again.
MAX_MEDIA_GB = float(os.environ.get("MYTUBE_MAX_MEDIA_GB", "200"))

# The youtube_scrapper channels.json that the scraper re-reads on every run.
SCRAPER_CHANNELS_PATH = Path(
    os.environ.get("MYTUBE_SCRAPER_CHANNELS_PATH", "/home/devmon/youtube_scrapper/channels.json")
)

def resolve_db_path() -> str:
    """
    Resolve SQLite DB location:
    1. Explicit override via MYTUBE_DB_PATH environment variable.
    2. Default: data/mytube.db inside the project (internal disk on the server, faster than the external drive).
    """
    explicit_db = os.environ.get("MYTUBE_DB_PATH")
    if explicit_db:
        return explicit_db
    return str(DATA_DIR / "mytube.db")

DB_PATH = resolve_db_path()

# Jellyfin Configuration
# JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://192.168.1.131:8096").rstrip("/")
# JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "98c1e33663a14ad396184abaf04812a0")
# JELLYFIN_USER_ID = os.environ.get("JELLYFIN_USER_ID", "0b9269f3641e42f090749ae1f2a97d85")
# JELLYFIN_LIBRARY_ID = os.environ.get("JELLYFIN_LIBRARY_ID", "34f331a89ce405e2b877d68d5ee4d4a2")
# JELLYFIN_MOVIES_LIBRARY_ID = os.environ.get("JELLYFIN_MOVIES_LIBRARY_ID", "f137a2dd21bbc1b99aa5c0f6bf02a805")
# JELLYFIN_SHOWS_LIBRARY_ID = os.environ.get("JELLYFIN_SHOWS_LIBRARY_ID", "a656b907eb3a73532e40e44b968d0225")
# Jellyfin Configuration

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://192.168.1.108:8096").rstrip("/")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "eaa1950d504a4b54a299d79526c13c06")
JELLYFIN_USER_ID = os.environ.get("JELLYFIN_USER_ID", "05e68dd11ab249ca96eb3bd4844de2c5")
JELLYFIN_LIBRARY_ID = os.environ.get("JELLYFIN_LIBRARY_ID", "34f331a89ce405e2b877d68d5ee4d4a2")
JELLYFIN_MOVIES_LIBRARY_ID = os.environ.get("JELLYFIN_MOVIES_LIBRARY_ID", "f137a2dd21bbc1b99aa5c0f6bf02a805")
JELLYFIN_SHOWS_LIBRARY_ID = os.environ.get("JELLYFIN_SHOWS_LIBRARY_ID", "a656b907eb3a73532e40e44b968d0225")

# Google AI Studio (Gemini) for AI subtitle synthesis. The key is read from the environment only; never commit it.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


# Lifecycle & Business Rules
# Automatically hide from Feed / mark watched when remaining time is less than 30s
REMAINING_SECONDS_THRESHOLD = 30.0

# Server Host & Port
SERVER_HOST = os.environ.get("MYTUBE_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("MYTUBE_PORT", "8000"))
