import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from backend.main import app

client = TestClient(app)

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
