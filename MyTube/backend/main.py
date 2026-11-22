import logging
import re
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import BASE_DIR
from backend.database import get_db, init_db
from backend.scanner import scan_and_sync
from backend.feed_service import FeedService
from backend.playback_service import PlaybackService
from backend.cleanup_service import CleanupService
from backend.movies_service import MoviesService
from backend.shows_service import ShowsService
from backend.user_service import UserService
from backend.scraper_channels_service import ScraperChannelError, ScraperChannelService
from backend.jellyfin_client import jellyfin
from backend.synthesis_service import SynthesisError, synthesize_subtitle

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
    sync_to_jellyfin: bool = False

class UserPayload(BaseModel):
    name: Optional[str] = None

class SubscriptionPayload(BaseModel):
    subscribed: bool

class ScraperChannelPayload(BaseModel):
    name: str
    url: str
    mode: Literal["video", "audio"] = "video"
    resolution: Literal[480, 720, 1080, 1440, 2160] = 1080
    audio_format: Literal["m4a", "mp3", "flac"] = "m4a"
    voice_language: str = ""
    subtitle_language: str = ""
    min_views: int = Field(0, ge=0)
    title_contains: str = ""
    min_duration_minutes: int = Field(5, ge=0)
    date_days: int = Field(5, ge=0)
    enabled: bool = True

class SynthesisPayload(BaseModel):
    subtitle_index: int

def get_current_user(x_mytube_user: Optional[str] = Header(None, alias="X-MyTube-User")) -> Dict[str, Any]:
    """Resolve the MyTube user identified by the X-MyTube-User header."""
    if not x_mytube_user:
        raise HTTPException(status_code=400, detail="X-MyTube-User header required")
    user = UserService.get_user(x_mytube_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

def normalize_user_name(name: Optional[str]) -> str:
    cleaned = (name or "").strip()
    if not cleaned or len(cleaned) > 40:
        raise HTTPException(status_code=400, detail="Name must be 1-40 characters")
    return cleaned

# Routes
@app.get("/api/users")
def list_users():
    return UserService.list_users()

@app.post("/api/users", status_code=201)
def create_user(payload: UserPayload):
    user = UserService.create_user(normalize_user_name(payload.name))
    if not user:
        raise HTTPException(status_code=409, detail="Name already exists")
    return user

@app.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: str):
    """Delete a user and their subscriptions and progress. Media and channels are not affected."""
    if not UserService.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return Response(status_code=204)

@app.post("/api/users/ensure")
def ensure_user(payload: UserPayload):
    """Get or create a user by name (case-insensitive). Used by tvOS after Jellyfin login."""
    return UserService.ensure_user(normalize_user_name(payload.name))

@app.get("/api/home")
def get_home_feed(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unplayed_only: bool = Query(True),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """YouTube-like Subscription Feed: newest videos from the user's subscribed channels, hiding watched."""
    return FeedService.get_home_feed(user["user_id"], limit=limit, offset=offset, unplayed_only=unplayed_only)

@app.get("/api/gone-soon")
def get_gone_soon(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unplayed_only: bool = Query(True),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Subscribed videos in cleanup order: watched by anyone first, then oldest first. The next ones the automatic space cleanup will delete."""
    return FeedService.get_gone_soon(user["user_id"], limit=limit, offset=offset, unplayed_only=unplayed_only)

@app.get("/api/continue-watching")
def get_continue_watching(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Partly watched videos from any screen (subscriptions, channels, gone soon), most recently played first."""
    return FeedService.get_continue_watching(user["user_id"], limit=limit, offset=offset)

@app.get("/api/channels")
def get_channels(
    subscription: str = Query("all", pattern="^(all|subscribed|unsubscribed)$"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """All channels with the user's subscription flag and unread counts."""
    return FeedService.get_channels(user["user_id"], subscription=subscription)

@app.get("/api/channels/{channel_id}")
def get_channel(channel_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ch = FeedService.get_channel_detail(channel_id, user["user_id"])
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch

@app.put("/api/channels/{channel_id}/subscription")
def set_channel_subscription(
    channel_id: str,
    payload: SubscriptionPayload,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not FeedService.get_channel_detail(channel_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Channel not found")
    UserService.set_subscription(user["user_id"], channel_id, payload.subscribed)
    return {"channel_id": channel_id, "subscribed": payload.subscribed}

def _scraper_call(func, *args):
    try:
        return func(*args)
    except ScraperChannelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

@app.get("/api/scraper/channels")
def list_scraper_channels(user: Dict[str, Any] = Depends(get_current_user)):
    """All channels in the youtube_scrapper channels.json, as the scraper reads them."""
    return {"channels": _scraper_call(ScraperChannelService.list_channels)}

@app.post("/api/scraper/channels", status_code=201)
def add_scraper_channel(payload: ScraperChannelPayload, user: Dict[str, Any] = Depends(get_current_user)):
    """Add a channel to the scraper config. The scraper's next run picks it up."""
    return _scraper_call(ScraperChannelService.add_channel, payload.model_dump())

@app.put("/api/scraper/channels/{name:path}")
def update_scraper_channel(
    name: str,
    payload: ScraperChannelPayload,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Replace a scraper channel's settings, looked up by its current name."""
    return _scraper_call(ScraperChannelService.update_channel, name, payload.model_dump())

@app.delete("/api/scraper/channels/{name:path}", status_code=204)
def delete_scraper_channel(name: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Remove a channel from the scraper config. Downloaded files are not deleted."""
    _scraper_call(ScraperChannelService.delete_channel, name)
    return Response(status_code=204)

@app.get("/api/channels/{channel_id}/videos")
def get_channel_videos(
    channel_id: str,
    filter_type: str = Query("all", pattern="^(all|unwatched)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Browse all videos inside a specific channel with filter."""
    return FeedService.get_channel_videos(channel_id, user["user_id"], filter_type=filter_type, limit=limit, offset=offset)

@app.get("/api/videos/{video_id}")
def get_video(video_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    video = FeedService.get_video(video_id, user["user_id"])
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video

@app.get("/api/videos/{video_id}/playback")
def get_playback_info(
    video_id: str,
    audio_stream_index: Optional[int] = None,
    quality: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return proxy-backed Jellyfin stream URLs, playback options, tracks, and the user's resume position."""
    data = PlaybackService.get_playback_data(
        video_id,
        user["user_id"],
        audio_stream_index=audio_stream_index,
        quality=quality,
    )
    if not data:
        raise HTTPException(status_code=404, detail="Video not found")
    return data

@app.get("/api/jellyfin/{item_id}/{resource:path}")
def proxy_jellyfin_media(item_id: str, resource: str, request: Request):
    """Proxy browser media requests so Jellyfin credentials stay server-side."""
    allowed_resource = (
        resource in {"audio", "stream.mkv", "master.m3u8", "main.m3u8"}
        or re.fullmatch(r"hls\d+/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", resource) is not None
        or re.fullmatch(r"Images/(?:Primary|Backdrop/\d+)", resource) is not None
        or re.fullmatch(r"(?:[0-9a-f]{32}/)?Subtitles/\d+/Stream\.vtt", resource) is not None
    )
    if not allowed_resource:
        raise HTTPException(status_code=404, detail="Jellyfin resource not found")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM videos WHERE jellyfin_item_id = ?
            UNION ALL SELECT 1 FROM movies WHERE jellyfin_item_id = ?
            UNION ALL SELECT 1 FROM shows WHERE jellyfin_item_id = ?
            UNION ALL SELECT 1 FROM episodes WHERE jellyfin_item_id = ?
            LIMIT 1
        """, (item_id, item_id, item_id, item_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Jellyfin item not found")

    try:
        upstream = jellyfin.proxy_media_request(
            item_id,
            resource,
            dict(request.query_params),
            request.headers.get("range"),
        )
    except Exception as exc:
        logger.error("Jellyfin media proxy request failed for item %s: %s", item_id, exc)
        raise HTTPException(status_code=502, detail="Unable to reach Jellyfin") from exc

    response_headers = {
        key: upstream.headers[key]
        for key in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag")
        if key in upstream.headers
    }

    def stream_content():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    return StreamingResponse(
        stream_content(),
        status_code=upstream.status_code,
        headers=response_headers,
    )

@app.get("/api/videos/{video_id}/subtitles/{sub_index}.vtt")
def get_video_subtitle_vtt(video_id: str, sub_index: int):
    """Serve cleaned WebVTT subtitle from same origin to avoid browser CORS <track> blocking."""
    vtt = PlaybackService.get_subtitle_vtt(video_id, sub_index)
    if vtt is None:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    return Response(content=vtt, media_type="text/vtt; charset=utf-8")

@app.post("/api/videos/{video_id}/synthesize", dependencies=[Depends(get_current_user)])
def synthesize_video_subtitle(video_id: str, payload: SynthesisPayload):
    """AI Markdown synthesis of the complete selected subtitle track. Nothing is stored."""
    try:
        return synthesize_subtitle(video_id, payload.subtitle_index)
    except SynthesisError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

@app.post("/api/videos/{video_id}/progress")
def report_playback_progress(
    video_id: str,
    payload: ProgressPayload,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Report the user's playback position. Automatically marks watched if remaining time < 30 seconds."""
    result = PlaybackService.update_progress(video_id, user["user_id"], payload.position, payload.duration)
    if payload.sync_to_jellyfin and result["status"] == "ok" and not result["watched"]:
        background_tasks.add_task(
            PlaybackService.sync_progress_to_jellyfin,
            video_id,
            payload.position,
        )
    return result

@app.post("/api/videos/{video_id}/watched")
def mark_video_watched(video_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success = PlaybackService.mark_watched(video_id, user["user_id"])
    if not success:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"status": "ok", "video_id": video_id, "watched": True}

@app.post("/api/videos/{video_id}/unwatched")
def mark_video_unwatched(video_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success = PlaybackService.mark_unwatched(video_id, user["user_id"])
    if not success:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"status": "ok", "video_id": video_id, "watched": False}

@app.delete("/api/videos/{video_id}", dependencies=[Depends(get_current_user)])
def delete_video_permanently(video_id: str):
    """Immediately delete video permanently from SSD via Jellyfin."""
    return CleanupService.delete_permanently(video_id)

@app.get("/api/movies/home")
def get_movies_home(
    filter_type: str = Query("all", pattern="^(all|unwatched)$"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Netflix/Prime style homepage for Movies (continue watching, recently added, 5 random genres)."""
    return MoviesService.get_movies_home(user["user_id"], filter_type=filter_type)

@app.get("/api/movies/{movie_id}")
def get_movie_detail(movie_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Full movie details with recommendations."""
    detail = MoviesService.get_movie_detail(movie_id, user["user_id"])
    if not detail:
        raise HTTPException(status_code=404, detail="Movie not found")
    return detail

@app.get("/api/shows/home")
def get_shows_home(user: Dict[str, Any] = Depends(get_current_user)):
    """Netflix/Prime style homepage for Shows (continue watching, recently added, 5 random genres)."""
    return ShowsService.get_shows_home(user["user_id"])

@app.get("/api/shows/{show_id}")
def get_show_detail(show_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Full series details with seasons, episodes, and next episode to watch."""
    detail = ShowsService.get_show_detail(show_id, user["user_id"])
    if not detail:
        raise HTTPException(status_code=404, detail="Show not found")
    return detail

@app.get("/api/search")
def search_videos(q: str = Query(..., min_length=1), user: Dict[str, Any] = Depends(get_current_user)):
    return FeedService.search(q, user["user_id"])

@app.get("/api/stats")
def get_stats(user: Dict[str, Any] = Depends(get_current_user)):
    return FeedService.get_stats(user["user_id"])

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

@app.post("/api/admin/cleanup")
def trigger_space_cleanup():
    """Delete the oldest YouTube videos through Jellyfin while the media folder exceeds MYTUBE_MAX_MEDIA_GB."""
    return CleanupService.run_space_cleanup()

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
