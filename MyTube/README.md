# MyTube – Personalized YouTube Subscription & Direct Streamer

MyTube is a lightweight, self-hosted YouTube system that turns downloaded videos into a subscription feed experience streaming directly from your storage without bogging down your network.

## Architecture

- **Backend:** FastAPI (Python 3.13) + SQLite. Runs locally on Windows PC (`http://localhost:8000`).
- **Database:** `I:\mytube.db` on Windows when `I:\` is available; otherwise `data\mytube.db`. Android uses its configured external-storage root. Override with `MYTUBE_DB_PATH` or `MYTUBE_STORAGE_ROOT`.
- **Media Engine:** Jellyfin server at `http://192.168.1.131:8096`.
- **Storage:** External SSD mounted on Android (`/storage/0692F50692F4FACF/yt_video`), synced via SSH + Jellyfin API.
- **Client:** Modern Progressive Web App (PWA) compatible with Desktop Chrome/Edge/Firefox, Android phones/tablets, and iPhone/iPad.

For Jellyfin credentials, user/library IDs, and migration steps, see [JELLYFIN_SETUP.md](./JELLYFIN_SETUP.md).

---

## Key Features

1. **YouTube Subscription Feed:**
   - Mixed chronologically by original YouTube upload date (`upload_date DESC`).
   - Auto-hides watched videos from feed once remaining playback time is **< 30 seconds**.
   - Filter chips: `Unwatched` vs `All Videos`.

2. **Channel Browser:**
   - Channel directory with unwatched badges.
   - Channel detail page with filters: `All`, `Unwatched`, `Watched`.

3. **High-Performance Player:**
   - **Direct Play from Jellyfin:** Client streams directly from Jellyfin without proxying media bytes through MyTube.
   - **Multi-Audio Selector:** Supports multiple audio tracks (e.g. English, Vietnamese).
   - **Subtitle Selector:** WebVTT captions directly from Jellyfin with `Off` toggle.
   - **Hold for 1.8x Speed:** Press and hold screen or mouse anywhere on the video for > 250ms to speed up to 1.8x with animated on-screen badge; restores previous speed on release.
   - **Speed Selector:** 0.5x to 2.0x.
   - **Fullscreen Support:** Desktop Fullscreen API + iOS Safari WebKit fullscreen.
   - **Background Playback on Lock Screen:** Utilizes `MediaSession API` so audio/video continues playing until the end of the file when phone screen is locked.
   - **Automatic Progress Sync:** Position reported every 3 seconds to keep resume points.

4. **Trash & Auto-Cleanup:**
   - Deleted items are held in `.trash` for 30 days before permanent deletion from SSD.
   - Option to permanently delete immediately with one click.
   - Automatic cleanup integrated with `youtube_scrapper/runner.py`.

---

## How to Run

### 1. Launch MyTube Server
Double-click `start_mytube.bat` or run:
```powershell
cd c:\Users\nhnha\Documents\video-tools\MyTube
.\.venv\Scripts\activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Access Web UI / PWA
- **On this PC:** [http://localhost:8000](http://localhost:8000)
- **On Android / iPhone / iPad:** `http://<YOUR_PC_LAN_IP>:8000` (e.g., `http://192.168.1.100:8000`)
- On mobile browsers, tap **"Add to Home Screen"** to install as a full standalone app!

### 3. Automated Scraper Sync
When `youtube_scrapper/runner.py` finishes downloading new videos, it automatically:
1. Calls Jellyfin library refresh.
2. Calls `http://127.0.0.1:8000/api/admin/scan` to index new videos into MyTube SQLite.

curl -X POST http://127.0.0.1:8000/api/admin/scan
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/admin/scan

3. Calls `http://127.0.0.1:8000/api/admin/cleanup` to delete expired trash files (> 30 days old).
