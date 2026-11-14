import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local media directory for metadata and thumbnail access.
REMOTE_MEDIA_DIR = os.environ.get("MYTUBE_REMOTE_MEDIA_DIR", "/media/devmon/EXTERNAL/yt_video")

# External storage root for database placement, or explicitly specified.
if os.environ.get("MYTUBE_STORAGE_ROOT"):
    EXTERNAL_STORAGE_ROOT = Path(os.environ["MYTUBE_STORAGE_ROOT"])
elif os.name == "nt":
    EXTERNAL_STORAGE_ROOT = Path("I:/")
else:
    EXTERNAL_STORAGE_ROOT = Path("/media/devmon/EXTERNAL")

def resolve_db_path() -> str:
    """
    Resolve SQLite DB location dynamically:
    1. Explicit override via MYTUBE_DB_PATH environment variable.
    2. External storage root (I:\\ on Windows or /media/devmon/EXTERNAL on Linux by default).
    3. PC / Dev environment fallback: Local workspace data directory (data/mytube.db).
    """
    explicit_db = os.environ.get("MYTUBE_DB_PATH")
    if explicit_db:
        return explicit_db

    # On server where external storage is mounted, store in the root of external storage
    try:
        if EXTERNAL_STORAGE_ROOT.is_dir() and os.access(str(EXTERNAL_STORAGE_ROOT), os.W_OK):
            return str(EXTERNAL_STORAGE_ROOT / "mytube.db")
    except Exception:
        pass

    # Default to local workspace data directory (dev / PC)
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

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://localhost:8096").rstrip("/")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "eaa1950d504a4b54a299d79526c13c06")
JELLYFIN_USER_ID = os.environ.get("JELLYFIN_USER_ID", "05e68dd11ab249ca96eb3bd4844de2c5")
JELLYFIN_LIBRARY_ID = os.environ.get("JELLYFIN_LIBRARY_ID", "34f331a89ce405e2b877d68d5ee4d4a2")
JELLYFIN_MOVIES_LIBRARY_ID = os.environ.get("JELLYFIN_MOVIES_LIBRARY_ID", "f137a2dd21bbc1b99aa5c0f6bf02a805")
JELLYFIN_SHOWS_LIBRARY_ID = os.environ.get("JELLYFIN_SHOWS_LIBRARY_ID", "a656b907eb3a73532e40e44b968d0225")



# Lifecycle & Business Rules
# Automatically hide from Feed / mark watched when remaining time is less than 30s
REMAINING_SECONDS_THRESHOLD = 30.0
# Trash retention days before permanent deletion
TRASH_RETENTION_DAYS = 30

# Server Host & Port
SERVER_HOST = os.environ.get("MYTUBE_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("MYTUBE_PORT", "8000"))
