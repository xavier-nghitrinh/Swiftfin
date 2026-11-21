# MyTube – Personalized YouTube Subscription & Direct Streamer

MyTube is a lightweight, self-hosted YouTube system that turns downloaded videos into a subscription feed experience streaming directly from your storage without bogging down your network.

## Architecture

- **Backend:** FastAPI (Python 3.13) + SQLite. Runs locally on Windows PC (`http://localhost:8000`).
- **Database:** `data/mytube.db` inside the project by default (internal disk on the server). Override with `MYTUBE_DB_PATH`.
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
   - **AI Subtitle Synthesis:** While a subtitle track is selected, the sparkle button sends the complete track to Google Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`) and shows a compact Markdown note in the subtitle's language. Nothing is saved. Set the `GEMINI_API_KEY` environment variable on the server; it is never stored in the repository. Rate limits and server errors are retried up to 3 times with exponential backoff.
   - **Hold for 1.8x Speed:** Press and hold screen or mouse anywhere on the video for > 250ms to speed up to 1.8x with animated on-screen badge; restores previous speed on release.
   - **Swipe to Seek:** On touch, swipe right to jump forward or left to jump back 5 seconds (keyboard arrows, double-tap, and lock-screen seek also use 5 seconds).
   - **Speed Selector:** 1.0x to 2.0x.
   - **Quality Selector:** 1080p to 144p (default 480p), with each option labeled by its estimated data use in MB per hour. Direct/original and audio-only don't show an estimate.
   - **Data Usage Readout:** Estimated data consumed since the current playback started, shown under the player. Not stored.
   - **Fullscreen Support:** Desktop Fullscreen API + iOS Safari WebKit fullscreen.
   - **Background Playback on Lock Screen:** Utilizes `MediaSession API` so audio/video continues playing until the end of the file when phone screen is locked.
   - **Automatic Progress Sync:** Position reported every 3 seconds to keep resume points.

4. **Users & Subscriptions:**
   - Each user has their own watch progress and resume positions for YouTube videos, movies and episodes.
   - Channel subscriptions are per user; the home feed and search only show videos from channels you subscribe to. Movies and shows are shared.
   - Delete permanently with one click (`DELETE /api/videos/{id}`).

5. **Gone soon:**
   - The bin tab (web and tvOS) lists your subscribed YouTube videos oldest first by `upload_date`, loaded in batches as you scroll (`GET /api/gone-soon`). These are the videos the space cleanup removes next.

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

Never put SSH passwords, private keys, Jellyfin API keys, or other credentials in this README or in source control. The server's `xavie` account cannot write into `/home/devmon/MyTube`, and `sudo` may prompt for the account password. Do not assume passwordless sudo is configured: inspect access at the start of each deployment. A temporary deployment helper from a previous session may have been removed.

For a future code change, the developer/assistant should:

1. Make and review the change locally, run the focused tests and syntax/build checks, and identify the exact runtime files that need deployment.
2. With the SSH key, verify the host and service, then stage only those changed files under `/home/xavie/mytube-audio-only-deploy`, preserving their paths relative to `MyTube` (for example, `backend/main.py` and `frontend/js/player.js`). Do not copy secrets, databases, virtual environments, caches, or the whole repository.
3. If `xavie` cannot install the staged files, ask the server owner to authorize a **temporary, narrowly scoped** root helper. The helper should install only the listed staged files into `/home/devmon/MyTube`, assign ownership to `devmon:devmon`, use normal non-executable file permissions, and restart `mytube.service`. Permit only that helper in a temporary `/etc/sudoers.d/` rule; validate the rule with `visudo` before using it. Never grant passwordless general-purpose shell, `cp`, `install`, or `systemctl` access.
4. Run the authorized helper, check `systemctl is-active mytube`, and verify the site/API plus the feature that changed. Check logs if the service fails to restart. Report whether deployment and verification succeeded.
5. Remove the staged copies and the temporary sudoers rule and helper, then verify the service is still active and the temporary access is gone. If elevated cleanup requires the owner, give them the exact cleanup commands instead of leaving temporary access in place.

The helper is deliberately created for each deployment from the actual changed-file list; do not treat a helper left by an earlier deployment as trusted or reusable without inspecting it.

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

### 2b. Android App (background playback)
Chrome on Android only installs the PWA over HTTPS and pauses video when the screen locks or you switch apps. `MyTube/android/` is a thin WebView wrapper that loads the same web UI from the server, so web UI changes need no APK rebuild. It adds a media notification, lock-screen/Bluetooth controls, and keeps playback alive in the background.

Build (requires JDK 17 and the Android SDK; `local.properties` holds `sdk.dir`):
```powershell
cd MyTube\android
.\gradlew.bat assembleDebug
```
Install `app\build\outputs\apk\debug\app-debug.apk` on the phone (allow "Install unknown apps"). On first launch, enter the server address, e.g. `http://192.168.1.108:8000`. Long-press the app icon → **Change server** to edit it later.

Rebuild the APK only when the native wrapper changes. The web player talks to it through `window.MyTubeAndroid` (see `notifyNativePlayback` / `nativeCommand` in `frontend/js/player.js`).

### 3. Automated Scraper Sync
When `youtube_scrapper/runner.py` finishes downloading new videos, it automatically:
1. Calls Jellyfin library refresh.
2. Calls `http://127.0.0.1:8000/api/admin/scan` to index new videos into MyTube SQLite. The scan also removes DB rows for items no longer in Jellyfin, so a file deleted elsewhere cannot stay listed but unplayable.
3. Calls `http://127.0.0.1:8000/api/admin/cleanup` to free space (see the scraper README).

curl -X POST http://127.0.0.1:8000/api/admin/scan
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/admin/scan
curl -X POST http://127.0.0.1:8000/api/admin/cleanup
