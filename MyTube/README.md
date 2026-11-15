# MyTube – Personalized YouTube Subscription & Direct Streamer

MyTube is a lightweight, self-hosted YouTube system that turns downloaded videos into a subscription feed experience streaming directly from your storage without bogging down your network.

## Architecture

- **Backend:** FastAPI (Python 3.13) + SQLite. Runs locally on Windows PC (`http://localhost:8000`).
- **Database:** `I:\mytube.db` on Windows when `I:\` is available; `/media/devmon/EXTERNAL/mytube.db` on Linux when the mount is available; otherwise `data\mytube.db`. Android uses its configured external-storage root. Override with `MYTUBE_DB_PATH` or `MYTUBE_STORAGE_ROOT`.
- **Media Engine:** Jellyfin server at `http://192.168.1.131:8096`.
- **Storage:** Local media directory (`/media/devmon/EXTERNAL/yt_video` by default), accessed directly by MyTube and Jellyfin API.
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
   - **Audio-Only Playback:** Select **Audio only** in the quality menu to stream the selected audio track without video.
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

### Linux Server
Copy the `MyTube` folder into your Linux user's home directory, make sure `/media/devmon/EXTERNAL` is mounted and writable by that user, then run:
```bash
cd ~/MyTube
bash setup_linux.sh
```

The script creates a virtual environment, installs the requirements, prompts for Jellyfin and storage settings, and installs/enables a systemd service running as your user. It stores service settings in `~/.config/mytube/mytube.env` with owner-only permissions. Leave the API-key prompt blank to use the value configured in `backend/config.py`.

Use `sudo systemctl status mytube` to check the service and `sudo journalctl -u mytube -f` to view its logs. The service listens on port `8000` by default; configure your firewall separately if clients need LAN access.

### Deploying changes to the kpserver MyTube instance

The production MyTube instance is on `192.168.1.108:11226`:

- SSH account: `xavie`
- SSH identity on the Windows development machine: `%USERPROFILE%\.ssh\kpserver-mytube`
- Application directory: `/home/devmon/MyTube`
- systemd service: `mytube.service` (runs as `devmon`, listens on port `8000`)
- Local verification URL: `http://192.168.1.108:8000`

Never put SSH passwords, private keys, Jellyfin API keys, or other credentials in this README or in source control. Use the existing SSH key; do not enable password-based automation. The server's `xavie` account cannot write into `/home/devmon/MyTube`, and `sudo` may prompt for the account password. Do not assume passwordless sudo is configured: inspect access at the start of each deployment. A temporary deployment helper from a previous session may have been removed.

For a future code change, the developer/assistant should:

1. Make and review the change locally, run the focused tests and syntax/build checks, and identify the exact runtime files that need deployment.
2. With the SSH key, verify the host and service, then stage only those changed files under `/home/xavie/mytube-audio-only-deploy`, preserving their paths relative to `MyTube` (for example, `backend/main.py` and `frontend/js/player.js`). Do not copy secrets, databases, virtual environments, caches, or the whole repository.
3. If `xavie` cannot install the staged files, ask the server owner to authorize a **temporary, narrowly scoped** root helper. The helper should install only the listed staged files into `/home/devmon/MyTube`, assign ownership to `devmon:devmon`, use normal non-executable file permissions, and restart `mytube.service`. Permit only that helper in a temporary `/etc/sudoers.d/` rule; validate the rule with `visudo` before using it. Never grant passwordless general-purpose shell, `cp`, `install`, or `systemctl` access.
4. Run the authorized helper, check `systemctl is-active mytube`, and verify the site/API plus the feature that changed. Check logs if the service fails to restart. Report whether deployment and verification succeeded.
5. Remove the staged copies and the temporary sudoers rule and helper, then verify the service is still active and the temporary access is gone. If elevated cleanup requires the owner, give them the exact cleanup commands instead of leaving temporary access in place.

The helper is deliberately created for each deployment from the actual changed-file list; do not treat a helper left by an earlier deployment as trusted or reusable without inspecting it. If SSH key access is unavailable, stop and ask the owner to restore access rather than requesting or recording a password.

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
