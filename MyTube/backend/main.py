import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import BASE_DIR
from backend.database import init_db
from backend.scanner import scan_and_sync
from backend.feed_service import FeedService
from backend.playback_service import PlaybackService
from backend.cleanup_service import CleanupService
from backend.movies_service import MoviesService
from backend.shows_service import ShowsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("mytube.api")

# Initialize SQLite database
init_db()

app = FastAPI(title="MyTube API", version="1.0.0")

# CORS middleware for local LAN / VPN access from PC, iPad, Android, TV
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class ProgressPayload(BaseModel):
    position: float
    duration: float

# Routes
@app.get("/api/home")
def get_home_feed(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unplayed_only: bool = Query(True)
):
    """YouTube-like Subscription Feed: newest videos from all channels, hiding watched."""
    return FeedService.get_home_feed(limit=limit, offset=offset, unplayed_only=unplayed_only)

@app.get("/api/channels")
def get_channels():
    """All subscribed channels with unread counts."""
    return FeedService.get_channels()

@app.get("/api/channels/{channel_id}")
def get_channel(channel_id: str):
    ch = FeedService.get_channel_detail(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch

@app.get("/api/channels/{channel_id}/videos")
def get_channel_videos(
    channel_id: str,
    filter_type: str = Query("all", pattern="^(all|unwatched|watched)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Browse all videos inside a specific channel with filter."""
    return FeedService.get_channel_videos(channel_id, filter_type=filter_type, limit=limit, offset=offset)

@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    video = FeedService.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video

@app.get("/api/videos/{video_id}/playback")
def get_playback_info(
    video_id: str,
    audio_stream_index: Optional[int] = None,
    quality: Optional[str] = None
):
    """Return direct Jellyfin stream/HLS URL, quality presets, audio tracks, WebVTT subtitles, and resume position."""
    data = PlaybackService.get_playback_data(video_id, audio_stream_index=audio_stream_index, quality=quality)
    if not data:
        raise HTTPException(status_code=404, detail="Video not found")
    return data

@app.get("/api/videos/{video_id}/subtitles/{sub_index}.vtt")
def get_video_subtitle_vtt(video_id: str, sub_index: int):
    """Serve cleaned WebVTT subtitle from same origin to avoid browser CORS <track> blocking."""
    vtt = PlaybackService.get_subtitle_vtt(video_id, sub_index)
    if vtt is None:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    return Response(content=vtt, media_type="text/vtt; charset=utf-8")

@app.post("/api/videos/{video_id}/progress")
def report_playback_progress(video_id: str, payload: ProgressPayload):
    """Report playback position. Automatically marks watched if remaining time < 30 seconds."""
    return PlaybackService.update_progress(video_id, payload.position, payload.duration)

@app.post("/api/videos/{video_id}/watched")
def mark_video_watched(video_id: str):
    success = PlaybackService.mark_watched(video_id)
    if not success:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"status": "ok", "video_id": video_id, "watched": True}

@app.post("/api/videos/{video_id}/unwatched")
def mark_video_unwatched(video_id: str):
    success = PlaybackService.mark_unwatched(video_id)
    if not success:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"status": "ok", "video_id": video_id, "watched": False}

@app.post("/api/videos/{video_id}/trash")
def move_video_to_trash(video_id: str):
    """Move video to trash (30 day retention)."""
    return CleanupService.move_to_trash(video_id)

@app.post("/api/videos/{video_id}/restore")
def restore_video_from_trash(video_id: str):
    """Restore video from trash."""
    return CleanupService.restore_from_trash(video_id)

@app.delete("/api/videos/{video_id}")
def delete_video_permanently(video_id: str):
    """Immediately delete video permanently from SSD via Jellyfin."""
    return CleanupService.delete_permanently(video_id)

@app.get("/api/movies/home")
def get_movies_home():
    """Netflix/Prime style homepage for Movies (continue watching, recently added, 5 random genres)."""
    return MoviesService.get_movies_home()

@app.get("/api/movies/{movie_id}")
def get_movie_detail(movie_id: str):
    """Full movie details with recommendations."""
    detail = MoviesService.get_movie_detail(movie_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Movie not found")
    return detail

@app.get("/api/shows/home")
def get_shows_home():
    """Netflix/Prime style homepage for Shows (continue watching, recently added, 5 random genres)."""
    return ShowsService.get_shows_home()

@app.get("/api/shows/{show_id}")
def get_show_detail(show_id: str):
    """Full series details with seasons, episodes, and next episode to watch."""
    detail = ShowsService.get_show_detail(show_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Show not found")
    return detail

@app.get("/api/trash")
def get_trash():
    return CleanupService.get_trash_items()

@app.get("/api/search")
def search_videos(q: str = Query(..., min_length=1)):
    return FeedService.search(q)

@app.get("/api/stats")
def get_stats():
    return FeedService.get_stats()

@app.api_route("/api/admin/scan", methods=["GET", "POST"])
async def trigger_scan(request: Request, force: bool = False):
    """Trigger library indexing from Jellyfin and SSD metadata."""
    is_force = force
    if not is_force and request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("force"):
                is_force = True
        except Exception:
            pass
    return scan_and_sync(force_full=is_force)

@app.api_route("/api/admin/cleanup", methods=["GET", "POST"])
def trigger_cleanup():
    """Process expired trash items (> 30 days old)."""
    return CleanupService.process_due_trash()

@app.post("/api/videos/stop-encodings")
def stop_active_encodings():
    """Stop any active Jellyfin ffmpeg transcode sessions."""
    from backend.jellyfin_client import jellyfin
    jellyfin.stop_active_encodings("mytube_ios")
    jellyfin.stop_active_encodings("mytube_web")
    return {"status": "ok"}

# Serve Frontend PWA Static Files if frontend directory exists
frontend_dir = BASE_DIR / "frontend"
frontend_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
