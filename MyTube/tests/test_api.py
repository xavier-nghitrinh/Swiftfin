import asyncio
import sys
from contextlib import nullcontext
from pathlib import Path
from fastapi import BackgroundTasks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from backend.main import app, report_playback_progress, ProgressPayload
from backend.playback_service import PlaybackService
from backend.cleanup_service import CleanupService
import backend.playback_service as playback_service
import backend.cleanup_service as cleanup_service

client = TestClient(app)

def test_playback_defaults_to_original_direct(monkeypatch):
    media = {
        "video_id": "test-video",
        "jellyfin_item_id": "jellyfin-item",
        "title": "Test video",
        "channel_name": "Test channel",
        "duration": 120,
        "playback_position": 0,
        "watched": False,
    }

    class FakeConnection:
        def cursor(self):
            return object()

    monkeypatch.setattr(playback_service, "get_db", lambda: nullcontext(FakeConnection()))
    monkeypatch.setattr(playback_service, "find_media_item", lambda cursor, video_id: (media, "video"))
    monkeypatch.setattr(playback_service.jellyfin, "get_item_details", lambda item_id: {})
    monkeypatch.setattr(playback_service.jellyfin, "stop_active_encodings", lambda device_id: None)
    monkeypatch.setattr(playback_service.jellyfin, "get_stream_url", lambda *args, **kwargs: "/direct")
    monkeypatch.setattr(playback_service.jellyfin, "get_hls_url", lambda *args, **kwargs: "/hls")
    monkeypatch.setattr(playback_service.jellyfin, "get_hls_ios_url", lambda *args, **kwargs: "/hls-ios")

    result = PlaybackService.get_playback_data("test-video")

    assert result["current_quality"] == "direct"
    assert result["use_hls"] is False
    assert next(q for q in result["qualities"] if q["id"] == "direct")["is_active"] is True


def test_progress_jellyfin_sync_is_backgrounded(monkeypatch):
    sync_calls = []
    monkeypatch.setattr(
        PlaybackService,
        "update_progress",
        staticmethod(lambda video_id, position, duration: {"status": "ok", "watched": False}),
    )
    monkeypatch.setattr(
        PlaybackService,
        "sync_progress_to_jellyfin",
        staticmethod(lambda video_id, position: sync_calls.append((video_id, position))),
    )

    background_tasks = BackgroundTasks()
    result = report_playback_progress(
        "test-video",
        ProgressPayload(position=12, duration=100),
        background_tasks,
    )
    assert result["status"] == "ok"
    assert background_tasks.tasks == []
    assert sync_calls == []

    background_tasks = BackgroundTasks()
    report_playback_progress(
        "test-video",
        ProgressPayload(position=17, duration=100, sync_to_jellyfin=True),
        background_tasks,
    )
    assert sync_calls == []
    assert len(background_tasks.tasks) == 1
    asyncio.run(background_tasks())
    assert sync_calls == [("test-video", 17)]


def test_due_trash_includes_movies_and_episodes(monkeypatch):
    class FakeCursor:
        def execute(self, query, params):
            assert "FROM movies" in query
            assert "FROM episodes" in query
            assert len(params) == 3

        def fetchall(self):
            return [{"media_id": "movie-id"}, {"media_id": "episode-id"}]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self):
            return FakeCursor()

    deleted_ids = []
    monkeypatch.setattr(cleanup_service, "get_db", lambda: FakeConnection())
    monkeypatch.setattr(
        CleanupService,
        "delete_permanently",
        staticmethod(lambda media_id: deleted_ids.append(media_id) or {"status": "ok"}),
    )

    result = CleanupService.process_due_trash()

    assert result == {"due_count": 2, "deleted_count": 2}
    assert deleted_ids == ["movie-id", "episode-id"]


def test_api():
    print("=== Testing MyTube Backend API ===")
    
    # 1. Stats
    print("\n[1] Testing /api/stats...")
    resp = client.get("/api/stats")
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    print("  Stats:", stats)
    assert stats["total_videos"] > 0
    assert stats["total_channels"] > 0

    # 2. Home Feed
    print("\n[2] Testing /api/home (Subscription Feed)...")
    resp = client.get("/api/home?limit=10&unplayed_only=true")
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    print(f"  Total unwatched: {feed['total']}, Returned items: {len(feed['items'])}")
    assert len(feed["items"]) > 0
    sample_video = feed["items"][0]
    sample_vid = sample_video["video_id"]
    print(f"  Sample video: {sample_vid} - '{sample_video['title']}' ({sample_video['upload_date']})")

    # 3. Channels
    print("\n[3] Testing /api/channels...")
    resp = client.get("/api/channels")
    assert resp.status_code == 200, resp.text
    channels = resp.json()
    print(f"  Total channels: {len(channels)}")
    sample_ch = channels[0]
    sample_cid = sample_ch["channel_id"]
    print(f"  Sample channel: {sample_cid} - '{sample_ch['name']}' (Unwatched: {sample_ch['unwatched_count']}/{sample_ch['total_videos']})")

    # 4. Channel Videos
    print(f"\n[4] Testing /api/channels/{sample_cid}/videos...")
    resp = client.get(f"/api/channels/{sample_cid}/videos?filter_type=all&limit=5")
    assert resp.status_code == 200, resp.text
    ch_videos = resp.json()
    print(f"  Channel videos count: {ch_videos['total']}")

    # 5. Playback Info
    print(f"\n[5] Testing /api/videos/{sample_vid}/playback...")
    resp = client.get(f"/api/videos/{sample_vid}/playback")
    assert resp.status_code == 200, resp.text
    pb = resp.json()
    print(f"  Stream URL: {pb['stream_url']}")
    print(f"  HLS URL: {pb['hls_url']}")
    print(f"  Audio tracks count: {len(pb['audio_tracks'])}")
    print(f"  Subtitles count: {len(pb['subtitles'])}")
    assert "stream.mkv" in pb["stream_url"]

    # 6. Progress & Auto-watch threshold (< 30s remaining)
    print("\n[6] Testing /api/videos/{id}/progress...")
    # Test normal progress (not watched)
    resp = client.post(f"/api/videos/{sample_vid}/progress", json={"position": 10.0, "duration": 100.0})
    assert resp.status_code == 200
    res = resp.json()
    print(f"  Progress at 10s/100s -> watched: {res['watched']}, remaining: {res['remaining_seconds']}")
    assert res["watched"] is False

    # Test auto mark watched when remaining time < 30 seconds
    resp = client.post(f"/api/videos/{sample_vid}/progress", json={"position": 75.0, "duration": 100.0})
    assert resp.status_code == 200
    res2 = resp.json()
    print(f"  Progress at 75s/100s (25s remaining < 30s) -> watched: {res2['watched']}")
    assert res2["watched"] is True

    # Revert to unwatched
    resp = client.post(f"/api/videos/{sample_vid}/unwatched")
    assert resp.status_code == 200
    print("  Reverted to unwatched status successfully.")

    # 7. Search
    print("\n[7] Testing /api/search...")
    resp = client.get("/api/search?q=VTV")
    assert resp.status_code == 200
    search_res = resp.json()
    print(f"  Search for 'VTV' found {len(search_res)} videos.")

    # 8. Frontend Static Files
    print("\n[8] Testing Frontend Static Files...")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MyTube" in resp.text
    print("  / (index.html) -> OK")

    for asset in ["/css/style.css", "/js/api.js", "/js/player.js", "/js/app.js", "/manifest.json", "/sw.js"]:
        r = client.get(asset)
        assert r.status_code == 200, f"Failed to get {asset}"
        print(f"  {asset} -> OK ({len(r.content)} bytes)")

    print("\n=== ALL BACKEND & FRONTEND TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_api()
