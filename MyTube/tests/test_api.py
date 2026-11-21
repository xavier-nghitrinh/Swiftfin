import asyncio
import random
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import BackgroundTasks
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
import backend.database as database
import backend.main as main
from backend.database import get_db, init_db
from backend.main import app, report_playback_progress, ProgressPayload
from backend.playback_service import PlaybackService
from backend.movies_service import MoviesService
from backend.jellyfin_client import JellyfinClient
from backend.user_service import UserService
import backend.playback_service as playback_service
import backend.synthesis_service as synthesis_service
from backend.synthesis_service import vtt_to_transcript

client = TestClient(app)

def _no_progress(cursor, user_id, media_id):
    return None

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
    monkeypatch.setattr(UserService, "get_progress", staticmethod(_no_progress))
    monkeypatch.setattr(playback_service.jellyfin, "get_item_details", lambda item_id: {})
    monkeypatch.setattr(playback_service.jellyfin, "stop_active_encodings", lambda device_id: None)
    monkeypatch.setattr(playback_service.jellyfin, "get_stream_url", lambda *args, **kwargs: "/direct")
    monkeypatch.setattr(playback_service.jellyfin, "get_hls_url", lambda *args, **kwargs: "/hls")
    monkeypatch.setattr(playback_service.jellyfin, "get_hls_ios_url", lambda *args, **kwargs: "/hls-ios")

    result = PlaybackService.get_playback_data("test-video", "user-1")

    assert result["current_quality"] == "480p"
    assert result["use_hls"] is True
    assert next(q for q in result["qualities"] if q["id"] == "480p")["is_active"] is True
    assert next(q for q in result["qualities"] if q["id"] == "480p")["label"] == "480p (675 MB/h)"

    direct = PlaybackService.get_playback_data("test-video", "user-1", quality="direct")
    assert direct["current_quality"] == "direct"
    assert direct["use_hls"] is False


def test_playback_audio_only_uses_selected_audio_track(monkeypatch):
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
    monkeypatch.setattr(UserService, "get_progress", staticmethod(_no_progress))
    monkeypatch.setattr(
        playback_service.jellyfin,
        "get_item_details",
        lambda item_id: {
            "MediaStreams": [
                {"Type": "Video", "Index": 0, "Width": 1920, "Height": 1080},
                {"Type": "Audio", "Index": 1, "Language": "en", "Codec": "aac"},
                {"Type": "Audio", "Index": 2, "Language": "vi", "Codec": "aac"},
            ]
        },
    )
    monkeypatch.setattr(playback_service.jellyfin, "stop_active_encodings", lambda device_id: None)
    monkeypatch.setattr(playback_service.jellyfin, "get_stream_url", lambda *args, **kwargs: "/direct")
    monkeypatch.setattr(
        playback_service.jellyfin,
        "get_audio_only_url",
        lambda item_id, audio_index: f"/api/jellyfin/{item_id}/audio?AudioStreamIndex={audio_index}",
    )
    monkeypatch.setattr(playback_service.jellyfin, "get_hls_url", lambda *args, **kwargs: "/hls")
    monkeypatch.setattr(playback_service.jellyfin, "get_hls_ios_url", lambda *args, **kwargs: "/hls-ios")

    result = PlaybackService.get_playback_data(
        "test-video",
        "user-1",
        audio_stream_index=2,
        quality="audio_only",
    )

    assert result["current_quality"] == "audio_only"
    assert result["use_hls"] is False
    assert result["audio_only_url"] == "/api/jellyfin/jellyfin-item/audio?AudioStreamIndex=2"
    assert next(q for q in result["qualities"] if q["id"] == "audio_only")["is_active"] is True


def test_audio_proxy_resource_is_limited_to_audio_stream(monkeypatch):
    class FakeCursor:
        def execute(self, query, params):
            pass

        def fetchone(self):
            return ("exists",)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakeUpstream:
        status_code = 200
        headers = {"Content-Type": "audio/mpeg"}

        def iter_content(self, chunk_size):
            yield b"audio"

        def close(self):
            pass

    calls = []
    monkeypatch.setattr(main, "get_db", lambda: nullcontext(FakeConnection()))
    monkeypatch.setattr(
        main.jellyfin,
        "proxy_media_request",
        lambda *args: (calls.append(args) or FakeUpstream()),
    )

    response = client.get("/api/jellyfin/jellyfin-item/audio?AudioCodec=mp3")

    assert response.status_code == 200
    assert response.content == b"audio"
    assert calls == [("jellyfin-item", "audio", {"AudioCodec": "mp3"}, None)]
    assert client.get("/api/jellyfin/jellyfin-item/audio/anything").status_code == 404


def test_audio_only_url_and_proxy_target_jellyfin_audio_controller():
    class FakeSession:
        def get(self, url, **kwargs):
            self.url = url
            self.kwargs = kwargs
            return object()

    client = JellyfinClient(base_url="http://jellyfin")
    client.session = FakeSession()
    client.proxy_media_request("item-id", "audio", {"AudioCodec": "mp3"}, None)

    assert client.session.url == "http://jellyfin/Audio/item-id/stream"
    assert client.session.kwargs["params"] == {"AudioCodec": "mp3"}


def test_progress_jellyfin_sync_is_backgrounded(monkeypatch):
    sync_calls = []
    monkeypatch.setattr(
        PlaybackService,
        "update_progress",
        staticmethod(lambda video_id, user_id, position, duration: {"status": "ok", "watched": False}),
    )
    monkeypatch.setattr(
        PlaybackService,
        "sync_progress_to_jellyfin",
        staticmethod(lambda video_id, position: sync_calls.append((video_id, position))),
    )
    user = {"user_id": "user-1", "name": "Ann", "created_at": "now"}

    background_tasks = BackgroundTasks()
    result = report_playback_progress(
        "test-video",
        ProgressPayload(position=12, duration=100),
        background_tasks,
        user,
    )
    assert result["status"] == "ok"
    assert background_tasks.tasks == []
    assert sync_calls == []

    background_tasks = BackgroundTasks()
    report_playback_progress(
        "test-video",
        ProgressPayload(position=17, duration=100, sync_to_jellyfin=True),
        background_tasks,
        user,
    )
    assert sync_calls == []
    assert len(background_tasks.tasks) == 1
    asyncio.run(background_tasks())
    assert sync_calls == [("test-video", 17)]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "mytube.db"))
    init_db()
    return tmp_path

def _seed_channel_with_video(channel_id, video_id):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO channels (channel_id, name, folder_path, thumbnail_url, created_at) VALUES (?, ?, '', '', '2024-01-01T00:00:00+00:00')",
            (channel_id, channel_id.title()),
        )
        conn.execute(
            """INSERT INTO videos (video_id, channel_id, channel_name, title, upload_date, jellyfin_item_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, '20240101', ?, '2024-01-01T00:00:00+00:00', '2024-01-01T00:00:00+00:00')""",
            (video_id, channel_id, channel_id.title(), f"Video {video_id}", video_id),
        )
        conn.commit()

def _create_user(name):
    resp = client.post("/api/users", json={"name": name})
    assert resp.status_code == 201, resp.text
    return {"X-MyTube-User": resp.json()["user_id"]}

def test_user_header_is_required_and_must_match_a_user(temp_db):
    resp = client.get("/api/home")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "X-MyTube-User header required"}

    resp = client.get("/api/home", headers={"X-MyTube-User": "no-such-user"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "User not found"}

def test_home_feed_only_lists_subscribed_channels(temp_db):
    _seed_channel_with_video("alpha", "a1")
    _seed_channel_with_video("beta", "b1")
    headers = _create_user("Ann")

    assert client.get("/api/home", headers=headers).json()["items"] == []

    resp = client.put("/api/channels/alpha/subscription", json={"subscribed": True}, headers=headers)
    assert resp.json() == {"channel_id": "alpha", "subscribed": True}
    items = client.get("/api/home", headers=headers).json()["items"]
    assert [item["video_id"] for item in items] == ["a1"]

def test_progress_is_isolated_per_user(temp_db):
    _seed_channel_with_video("alpha", "a1")
    ann = _create_user("Ann")
    ben = _create_user("Ben")

    resp = client.post("/api/videos/a1/progress", json={"position": 40, "duration": 100}, headers=ann)
    assert resp.status_code == 200
    assert resp.json()["user_id"] == ann["X-MyTube-User"]

    ann_video = client.get("/api/videos/a1", headers=ann).json()
    ben_video = client.get("/api/videos/a1", headers=ben).json()
    assert ann_video["playback_position"] == 40
    assert ben_video["playback_position"] == 0
    assert ben_video["watched"] == 0

def test_duplicate_channel_rows_list_once_with_their_videos(temp_db):
    _seed_channel_with_video("folder_alpha", "a1")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO channels (channel_id, name, folder_path, thumbnail_url, created_at) VALUES ('UCalpha', 'Folder_Alpha', '', '', '2024-01-01T00:00:00+00:00')"
        )
        conn.commit()
    headers = _create_user("Ann")

    channels = client.get("/api/channels", headers=headers).json()
    assert [c["channel_id"] for c in channels] == ["folder_alpha"]
    assert channels[0]["total_videos"] == 1

def test_deleting_user_removes_their_subscriptions_and_progress(temp_db):
    _seed_channel_with_video("alpha", "a1")
    ann = _create_user("Ann")
    client.put("/api/channels/alpha/subscription", json={"subscribed": True}, headers=ann)
    client.post("/api/videos/a1/progress", json={"position": 40, "duration": 100}, headers=ann)

    assert client.delete(f"/api/users/{ann['X-MyTube-User']}").status_code == 204
    assert all(u["user_id"] != ann["X-MyTube-User"] for u in client.get("/api/users").json())
    assert client.delete(f"/api/users/{ann['X-MyTube-User']}").status_code == 404
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_subscriptions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_progress").fetchone()[0] == 0

def test_migration_backfills_legacy_state_for_xavier(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "legacy.db"))
    init_db()
    with get_db() as conn:
        # Recreate a pre-multi-user database: no user tables, legacy columns hold the state
        for table in ("user_progress", "user_subscriptions", "users"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("INSERT INTO channels (channel_id, name, created_at) VALUES ('c1', 'One', '2024-01-01')")
        conn.execute("INSERT INTO channels (channel_id, name, created_at) VALUES ('c2', 'Two', '2024-01-01')")
        conn.execute("""INSERT INTO videos (video_id, channel_id, title, watched, watched_at, playback_position, file_status, created_at, updated_at)
                        VALUES ('v1', 'c1', 'Watched', 1, '2024-01-02', 0, 'available', '2024-01-01', '2024-01-01')""")
        conn.execute("""INSERT INTO videos (video_id, channel_id, title, watched, playback_position, file_status, trash_at, created_at, updated_at)
                        VALUES ('v2', 'c1', 'Trashed', 0, 30, 'trash', '2024-01-03', '2024-01-01', '2024-01-01')""")
        conn.execute("""INSERT INTO movies (movie_id, title, watched, playback_position, jellyfin_item_id, created_at, updated_at)
                        VALUES ('m1', 'Movie', 0, 500, 'm1', '2024-01-01', '2024-01-01')""")
        conn.commit()

    init_db()
    init_db()

    with get_db() as conn:
        users = conn.execute("SELECT user_id, name FROM users").fetchall()
        assert [u["name"] for u in users] == ["xavier"]
        xavier_id = users[0]["user_id"]

        progress = {r["media_id"]: dict(r) for r in conn.execute(
            "SELECT * FROM user_progress WHERE user_id = ?", (xavier_id,)
        )}
        assert progress["v1"]["watched"] == 1 and progress["v1"]["media_type"] == "youtube"
        assert progress["v2"]["playback_position"] == 30
        assert progress["m1"]["playback_position"] == 500 and progress["m1"]["media_type"] == "movie"

        subscribed = {r["channel_id"] for r in conn.execute(
            "SELECT channel_id FROM user_subscriptions WHERE user_id = ?", (xavier_id,)
        )}
        assert subscribed == {"c1", "c2"}

        restored = conn.execute("SELECT file_status, trash_at FROM videos WHERE video_id = 'v2'").fetchone()
        assert restored["file_status"] == "available" and restored["trash_at"] is None
        assert conn.execute("SELECT COUNT(*) FROM videos WHERE file_status = 'trash'").fetchone()[0] == 0


def _seed_dated_video(video_id, channel_id, upload_date, file_path="", jellyfin_item_id=None):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO channels (channel_id, name, folder_path, thumbnail_url, created_at) VALUES (?, ?, '', '', '2024-01-01T00:00:00+00:00')",
            (channel_id, channel_id.title()),
        )
        conn.execute(
            """INSERT INTO videos (video_id, channel_id, channel_name, title, upload_date, file_path, file_status, jellyfin_item_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'available', ?, '2024-01-01T00:00:00+00:00', '2024-01-01T00:00:00+00:00')""",
            (video_id, channel_id, channel_id.title(), f"Video {video_id}", upload_date, file_path, jellyfin_item_id or video_id),
        )
        conn.commit()

def _video_ids():
    with get_db() as conn:
        return [r["video_id"] for r in conn.execute("SELECT video_id FROM videos ORDER BY video_id")]

def test_gone_soon_lists_subscribed_videos_oldest_first_in_batches(temp_db):
    _seed_dated_video("new", "alpha", "2024-06-01")
    _seed_dated_video("old", "alpha", "2023-01-01")
    _seed_dated_video("mid", "alpha", "2023-06-01")
    _seed_dated_video("other", "beta", "2022-01-01")
    headers = _create_user("Ann")
    client.put("/api/channels/alpha/subscription", json={"subscribed": True}, headers=headers)

    first = client.get("/api/gone-soon?limit=2", headers=headers).json()
    assert [item["video_id"] for item in first["items"]] == ["old", "mid"]
    assert first["has_more"] is True

    second = client.get("/api/gone-soon?limit=2&offset=2", headers=headers).json()
    assert [item["video_id"] for item in second["items"]] == ["new"]
    assert second["has_more"] is False

def test_gone_soon_can_include_watched_videos(temp_db):
    _seed_dated_video("old", "alpha", "2023-01-01")
    _seed_dated_video("new", "alpha", "2024-06-01")
    headers = _create_user("Ann")
    client.put("/api/channels/alpha/subscription", json={"subscribed": True}, headers=headers)
    client.post("/api/videos/old/progress", json={"position": 100, "duration": 100}, headers=headers)

    unplayed = client.get("/api/gone-soon", headers=headers).json()["items"]
    assert [item["video_id"] for item in unplayed] == ["new"]

    everything = client.get("/api/gone-soon?unplayed_only=false", headers=headers).json()["items"]
    assert [item["video_id"] for item in everything] == ["old", "new"]

def test_continue_watching_spans_all_channels_and_skips_finished_or_barely_started(temp_db):
    _seed_dated_video("subscribed", "alpha", "2024-01-01")
    _seed_dated_video("other", "beta", "2024-01-02")
    _seed_dated_video("barely", "beta", "2024-01-03")
    _seed_dated_video("finished", "beta", "2024-01-04")
    headers = _create_user("Ann")
    client.put("/api/channels/alpha/subscription", json={"subscribed": True}, headers=headers)
    client.post("/api/videos/subscribed/progress", json={"position": 40, "duration": 100}, headers=headers)
    client.post("/api/videos/other/progress", json={"position": 60, "duration": 100}, headers=headers)
    client.post("/api/videos/barely/progress", json={"position": 3, "duration": 100}, headers=headers)
    client.post("/api/videos/finished/progress", json={"position": 100, "duration": 100}, headers=headers)

    items = client.get("/api/continue-watching", headers=headers).json()["items"]
    assert sorted(item["video_id"] for item in items) == ["other", "subscribed"]

def test_unwatched_recent_count_only_covers_subscribed_videos_from_last_day(temp_db):
    today = datetime.now(timezone.utc).date()
    _seed_dated_video("fresh", "alpha", today.isoformat())
    _seed_dated_video("fresh_watched", "alpha", today.isoformat())
    _seed_dated_video("fresh_other", "beta", today.isoformat())
    _seed_dated_video("stale", "alpha", (today - timedelta(days=3)).isoformat())
    headers = _create_user("Ann")
    client.put("/api/channels/alpha/subscription", json={"subscribed": True}, headers=headers)
    client.post("/api/videos/fresh_watched/progress", json={"position": 100, "duration": 100}, headers=headers)

    assert client.get("/api/stats", headers=headers).json()["unwatched_recent_videos"] == 1

def test_space_cleanup_deletes_oldest_videos_until_under_limit(temp_db, tmp_path, monkeypatch):
    import backend.cleanup_service as cleanup_service

    media = tmp_path / "media" / "alpha"
    media.mkdir(parents=True)
    jellyfin_deleted = []
    monkeypatch.setattr(cleanup_service, "REMOTE_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(cleanup_service, "MAX_MEDIA_GB", 2.5 / 1024)  # 2.5 MiB
    monkeypatch.setattr(cleanup_service.jellyfin, "delete_item", lambda item_id: jellyfin_deleted.append(item_id) or True)
    monkeypatch.setattr(cleanup_service.jellyfin, "trigger_refresh", lambda: True)
    for name, date in [("old", "2023-01-01"), ("mid", "2023-06-01"), ("new", "2024-06-01")]:
        path = media / f"{name}.mp4"
        path.write_bytes(b"x" * 1024 * 1024)
        (media / f"{name}.info.json").write_text("{}")
        _seed_dated_video(name, "alpha", date, file_path=str(path))

    result = cleanup_service.CleanupService.run_space_cleanup()

    assert result["deleted"] == ["old"]
    assert jellyfin_deleted == ["old"]
    assert not (media / "old.mp4").exists()
    assert not (media / "old.info.json").exists()
    assert (media / "mid.mp4").exists()
    assert _video_ids() == ["mid", "new"]

def test_local_files_and_rows_survive_when_jellyfin_refuses_delete(temp_db, tmp_path, monkeypatch):
    import backend.cleanup_service as cleanup_service

    path = tmp_path / "keep.mp4"
    path.write_bytes(b"x")
    _seed_dated_video("keep", "alpha", "2023-01-01", file_path=str(path))
    monkeypatch.setattr(cleanup_service.jellyfin, "delete_item", lambda item_id: False)

    result = cleanup_service.CleanupService.delete_permanently("keep")

    assert result["status"] == "error"
    assert path.exists()
    assert _video_ids() == ["keep"]

def test_scan_drops_rows_missing_from_jellyfin_but_not_on_empty_fetch(temp_db, monkeypatch):
    import backend.scanner as scanner

    _seed_dated_video("kept", "alpha", "2023-01-01", file_path="/media/alpha/kept.mp4", jellyfin_item_id="jf-kept")
    _seed_dated_video("gone", "alpha", "2023-01-01", file_path="/media/alpha/gone.mp4", jellyfin_item_id="jf-gone")
    monkeypatch.setattr(scanner, "sync_movies", lambda: {})
    monkeypatch.setattr(scanner, "sync_shows_and_episodes", lambda: {})
    monkeypatch.setattr(scanner, "sync_missing_thumbnails_to_sqlite", lambda *args, **kwargs: 0)

    monkeypatch.setattr(scanner.jellyfin, "get_library_items", lambda: [])
    scanner.scan_and_sync()
    assert _video_ids() == ["gone", "kept"]

    monkeypatch.setattr(
        scanner.jellyfin, "get_library_items",
        lambda: [{"Id": "jf-kept", "Path": "/media/alpha/kept.mp4"}],
    )
    result = scanner.scan_and_sync()
    assert _video_ids() == ["kept"]
    assert result["removed_videos"] == 1

def _seed_movie(movie_id):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO movies (movie_id, title, file_path, jellyfin_item_id, created_at, updated_at)
               VALUES (?, ?, '', ?, '2024-01-01T00:00:00+00:00', '2024-01-01T00:00:00+00:00')""",
            (movie_id, f"Movie {movie_id}", movie_id),
        )
        conn.commit()

def test_movie_sync_removes_items_deleted_in_jellyfin_with_their_progress(temp_db, monkeypatch):
    import backend.scanner as scanner

    _seed_movie("kept")
    _seed_movie("gone")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO user_progress (user_id, media_id, media_type, watched, playback_position, updated_at)
               VALUES ('u1', 'gone', 'movie', 0, 10, '2024-01-01T00:00:00+00:00')"""
        )
        conn.commit()
    monkeypatch.setattr(scanner.jellyfin, "get_image_bytes", lambda *args, **kwargs: None)

    monkeypatch.setattr(scanner.jellyfin, "get_movie_items", lambda: [{"Id": "kept", "Name": "Movie kept"}])
    assert scanner.sync_movies()["removed_movies"] == 1
    with get_db() as conn:
        assert [r["movie_id"] for r in conn.execute("SELECT movie_id FROM movies")] == ["kept"]
        assert conn.execute("SELECT COUNT(*) FROM user_progress WHERE media_id = 'gone'").fetchone()[0] == 0

    monkeypatch.setattr(scanner.jellyfin, "get_movie_items", lambda: [])
    assert scanner.sync_movies()["removed_movies"] == 0
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 1

def _paged_response(items, total):
    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Items": items, "TotalRecordCount": total}

    return _Response()

def test_jellyfin_fetch_pages_through_whole_library(monkeypatch):
    import backend.jellyfin_client as jellyfin_client

    monkeypatch.setattr(jellyfin_client, "JELLYFIN_PAGE_SIZE", 2)
    all_items = [{"Id": f"id-{i}"} for i in range(5)]
    jf = JellyfinClient(base_url="http://jf", api_key="k", user_id="u", library_id="l")
    monkeypatch.setattr(
        jf.session, "get",
        lambda url, params, timeout: _paged_response(
            all_items[params["StartIndex"]:params["StartIndex"] + params["Limit"]], len(all_items)
        ),
    )

    assert jf.get_library_items() == all_items

def test_jellyfin_fetch_raises_on_short_read_instead_of_returning_partial_list(monkeypatch):
    jf = JellyfinClient(base_url="http://jf", api_key="k", user_id="u", library_id="l")
    monkeypatch.setattr(jf.session, "get", lambda url, params, timeout: _paged_response([], 3))

    with pytest.raises(RuntimeError):
        jf.get_movie_items()

def test_api():
    print("=== Testing MyTube Backend API ===")
    xavier = next(u for u in client.get("/api/users").json() if u["name"] == "xavier")
    headers = {"X-MyTube-User": xavier["user_id"]}

    
    # 1. Stats
    print("\n[1] Testing /api/stats...")
    resp = client.get("/api/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    print("  Stats:", stats)
    assert stats["total_videos"] > 0
    assert stats["total_channels"] > 0

    # 2. Home Feed
    print("\n[2] Testing /api/home (Subscription Feed)...")
    resp = client.get("/api/home?limit=10&unplayed_only=true", headers=headers)
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    print(f"  Total unwatched: {feed['total']}, Returned items: {len(feed['items'])}")
    assert len(feed["items"]) > 0
    sample_video = feed["items"][0]
    sample_vid = sample_video["video_id"]
    print(f"  Sample video: {sample_vid} - '{sample_video['title']}' ({sample_video['upload_date']})")

    # 3. Channels
    print("\n[3] Testing /api/channels...")
    resp = client.get("/api/channels", headers=headers)
    assert resp.status_code == 200, resp.text
    channels = resp.json()
    print(f"  Total channels: {len(channels)}")
    sample_ch = channels[0]
    sample_cid = sample_ch["channel_id"]
    print(f"  Sample channel: {sample_cid} - '{sample_ch['name']}' (Unwatched: {sample_ch['unwatched_count']}/{sample_ch['total_videos']})")

    # 4. Channel Videos
    print(f"\n[4] Testing /api/channels/{sample_cid}/videos...")
    resp = client.get(f"/api/channels/{sample_cid}/videos?filter_type=all&limit=5", headers=headers)
    assert resp.status_code == 200, resp.text
    ch_videos = resp.json()
    print(f"  Channel videos count: {ch_videos['total']}")

    # 5. Playback Info
    print(f"\n[5] Testing /api/videos/{sample_vid}/playback...")
    resp = client.get(f"/api/videos/{sample_vid}/playback", headers=headers)
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
    resp = client.post(f"/api/videos/{sample_vid}/progress", json={"position": 10.0, "duration": 100.0}, headers=headers)
    assert resp.status_code == 200
    res = resp.json()
    print(f"  Progress at 10s/100s -> watched: {res['watched']}, remaining: {res['remaining_seconds']}")
    assert res["watched"] is False

    # Test auto mark watched when remaining time < 30 seconds
    resp = client.post(f"/api/videos/{sample_vid}/progress", json={"position": 75.0, "duration": 100.0}, headers=headers)
    assert resp.status_code == 200
    res2 = resp.json()
    print(f"  Progress at 75s/100s (25s remaining < 30s) -> watched: {res2['watched']}")
    assert res2["watched"] is True

    # Revert to unwatched
    resp = client.post(f"/api/videos/{sample_vid}/unwatched", headers=headers)
    assert resp.status_code == 200
    print("  Reverted to unwatched status successfully.")

    # 7. Search
    print("\n[7] Testing /api/search...")
    resp = client.get("/api/search?q=VTV", headers=headers)
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

def test_vtt_to_transcript_drops_timings_tags_and_rolling_duplicates():
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000 align:start\n"
        "Hello <c>world</c>\n\n"
        "00:00:02.000 --> 00:00:04.000\n"
        "Hello world\nSecond &amp; last line\n\n"
        "00:00:04.000 --> 00:00:06.000\n"
        "Second &amp; last line\n"
    )
    assert vtt_to_transcript(vtt) == "Hello world\nSecond & last line"


class _FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


_GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "## Notes\n- point"}]}}]}


def test_gemini_call_retries_with_exponential_backoff_then_succeeds(monkeypatch):
    responses = [_FakeResponse(429), _FakeResponse(503), _FakeResponse(200, _GEMINI_OK)]
    sleeps = []
    monkeypatch.setattr(synthesis_service, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(synthesis_service.requests, "post", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(synthesis_service.time, "sleep", sleeps.append)

    assert synthesis_service.call_gemini("transcript") == "## Notes\n- point"
    assert sleeps == [1, 2]


def test_gemini_call_gives_up_after_three_retries_and_does_not_retry_client_errors(monkeypatch):
    calls = []
    sleeps = []
    monkeypatch.setattr(synthesis_service, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(synthesis_service.requests, "post", lambda *a, **k: calls.append(1) or _FakeResponse(429))
    monkeypatch.setattr(synthesis_service.time, "sleep", sleeps.append)

    with pytest.raises(synthesis_service.SynthesisError) as exc:
        synthesis_service.call_gemini("transcript")
    assert exc.value.status_code == 503
    assert len(calls) == 4 and sleeps == [1, 2, 4]

    calls.clear()
    monkeypatch.setattr(synthesis_service.requests, "post", lambda *a, **k: calls.append(1) or _FakeResponse(400))
    with pytest.raises(synthesis_service.SynthesisError):
        synthesis_service.call_gemini("transcript")
    assert len(calls) == 1


def test_featured_movie_changes_between_home_loads(temp_db):
    with get_db() as conn:
        for i in range(6):
            conn.execute(
                """INSERT INTO movies (movie_id, title, jellyfin_item_id, backdrop_url, file_status, created_at, updated_at)
                   VALUES (?, ?, ?, 'backdrop.jpg', 'available', '2024-01-01T00:00:00+00:00', '2024-01-01T00:00:00+00:00')""",
                (f"movie-{i}", f"Movie {i}", f"jf-{i}"),
            )
        conn.commit()

    featured_ids = set()
    for seed in range(20):
        random.seed(seed)
        featured_ids.add(MoviesService.get_movies_home("user-1")["featured"]["movie_id"])
    assert len(featured_ids) > 1


if __name__ == "__main__":
    test_api()
