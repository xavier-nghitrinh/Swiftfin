import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SSH Configuration for direct SSD metadata sync if needed
SSH_HOST = os.environ.get("MYTUBE_SSH_HOST", "192.168.1.101")
SSH_PORT = int(os.environ.get("MYTUBE_SSH_PORT", "8022"))
SSH_USER = os.environ.get("MYTUBE_SSH_USER", "u")
SSH_PASS = os.environ.get("MYTUBE_SSH_PASS", "16468878")
REMOTE_MEDIA_DIR = os.environ.get("MYTUBE_REMOTE_MEDIA_DIR", "/storage/0692F50692F4FACF/yt_video")

# External storage candidate (parent of media directory, or explicitly specified)
EXTERNAL_STORAGE_ROOT = Path(os.environ.get("MYTUBE_STORAGE_ROOT", str(Path(REMOTE_MEDIA_DIR).parent)))

def resolve_db_path() -> str:
    """
    Resolve SQLite DB location dynamically:
    1. Explicit override via MYTUBE_DB_PATH environment variable.
    2. Android server: Root of external storage (e.g. /storage/0692F50692F4FACF/mytube.db).
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
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://192.168.1.101:8096").rstrip("/")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "8fabc2d942a64cb5bc9db064976dc3d7")
JELLYFIN_USER_ID = os.environ.get("JELLYFIN_USER_ID", "8c331f6343d84e359fa237a927a4e14f")
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
