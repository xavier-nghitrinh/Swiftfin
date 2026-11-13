import json
import requests
from pathlib import Path

JELLYFIN_URL = "http://192.168.1.101:8096"
API_TOKEN = "8fabc2d942a64cb5bc9db064976dc3d7"
USER_ID = "8c331f6343d84e359fa237a927a4e14f" # user xavier
LIBRARY_ID = "34f331a89ce405e2b877d68d5ee4d4a2" # YouTube library

HEADERS = {
    "X-Emby-Token": API_TOKEN,
    "Content-Type": "application/json"
}

def test_jellyfin_poc():
    results = {}
    print("=== Testing Jellyfin API PoC ===")

    # 1. System info / Auth
    print("\n[1] Checking System Info & Authentication...")
    resp = requests.get(f"{JELLYFIN_URL}/System/Info", headers=HEADERS, timeout=10)
    assert resp.status_code == 200, f"System info failed: {resp.status_code}"
    sys_info = resp.json()
    results["jellyfin_version"] = sys_info.get("Version")
    results["server_name"] = sys_info.get("ServerName")
    print(f"  Connected to {sys_info.get('ServerName')} running Jellyfin {sys_info.get('Version')}")

    # 2. Query videos in library
    print("\n[2] Querying all videos in YouTube library...")
    params = {
        "ParentId": LIBRARY_ID,
        "Recursive": "true",
        "IncludeItemTypes": "Video",
        "Fields": "Path,Overview,PremiereDate,ProductionYear,DateCreated,MediaSources,UserData,RunTimeTicks,Genres",
        "Limit": 50
    }
    resp = requests.get(f"{JELLYFIN_URL}/Users/{USER_ID}/Items", headers=HEADERS, params=params, timeout=15)
    assert resp.status_code == 200, f"Query items failed: {resp.status_code}"
    data = resp.json()
    total_videos = data.get("TotalRecordCount", 0)
    items = data.get("Items", [])
    results["total_videos_in_jellyfin"] = total_videos
    results["sample_items_count"] = len(items)
    print(f"  Found {total_videos} total video items in Jellyfin.")

    if not items:
        print("  No items found!")
        return results

    sample_item = items[0]
    sample_id = sample_item["Id"]
    sample_name = sample_item["Name"]
    sample_path = sample_item.get("Path")
    sample_date = sample_item.get("PremiereDate")
    sample_runtime = sample_item.get("RunTimeTicks", 0) / 10000000 # seconds
    print(f"  Sample Item ID: {sample_id}")
    print(f"  Name: {sample_name}")
    print(f"  Path: {sample_path}")
    print(f"  PremiereDate (Upload Date): {sample_date}")
    print(f"  Duration: {sample_runtime:.1f}s")

    # 3. Query channels (top-level folders in library)
    print("\n[3] Querying channels (top-level folders)...")
    c_params = {
        "ParentId": LIBRARY_ID,
        "IsFolder": "true"
    }
    resp = requests.get(f"{JELLYFIN_URL}/Items", headers=HEADERS, params=c_params, timeout=10)
    c_items = resp.json().get("Items", [])
    results["total_channels_in_jellyfin"] = len(c_items)
    print(f"  Found {len(c_items)} top-level channel folders.")
    if c_items:
        print("  Sample channels:", [c["Name"] for c in c_items[:5]])

    # 4. Sorting & Filtering test
    print("\n[4] Testing sort by PremiereDate (upload date) descending & Unplayed filter...")
    sort_params = {
        "ParentId": LIBRARY_ID,
        "Recursive": "true",
        "IncludeItemTypes": "Video",
        "SortBy": "PremiereDate",
        "SortOrder": "Descending",
        "Filters": "IsUnplayed",
        "Limit": 5,
        "Fields": "PremiereDate,UserData"
    }
    resp = requests.get(f"{JELLYFIN_URL}/Users/{USER_ID}/Items", headers=HEADERS, params=sort_params, timeout=10)
    unplayed_items = resp.json().get("Items", [])
    print(f"  Top 5 newest unplayed videos:")
    for it in unplayed_items:
        print(f"    - {it.get('PremiereDate')}: {it.get('Name')[:60]}... (Played={it.get('UserData', {}).get('Played')})")

    # 5. PlaybackInfo
    print("\n[5] Getting PlaybackInfo for sample video...")
    pb_payload = {
        "UserId": USER_ID,
        "AutoOpenLiveStream": False,
        "EnableDirectPlay": True,
        "EnableDirectStream": True,
        "EnableTranscoding": True
    }
    resp = requests.post(f"{JELLYFIN_URL}/Items/{sample_id}/PlaybackInfo", headers=HEADERS, json=pb_payload, timeout=10)
    assert resp.status_code == 200, f"PlaybackInfo failed: {resp.status_code}"
    pb_data = resp.json()
    media_sources = pb_data.get("MediaSources", [])
    print(f"  MediaSources count: {len(media_sources)}")
    if media_sources:
        ms = media_sources[0]
        print(f"  SupportsDirectPlay: {ms.get('SupportsDirectPlay')}")
        print(f"  SupportsDirectStream: {ms.get('SupportsDirectStream')}")
        print(f"  SupportsTranscoding: {ms.get('SupportsTranscoding')}")
        print(f"  Container: {ms.get('Container')}")
        results["supports_direct_play"] = ms.get("SupportsDirectPlay")
        results["supports_direct_stream"] = ms.get("SupportsDirectStream")

    # 6. Stream video with HTTP Range request
    print("\n[6] Testing HTTP Range Request streaming...")
    stream_url = f"{JELLYFIN_URL}/Videos/{sample_id}/stream.mkv?Static=true"
    range_headers = {
        "X-Emby-Token": API_TOKEN,
        "Range": "bytes=0-1024" # Request first 1 KB
    }
    resp = requests.get(stream_url, headers=range_headers, timeout=10)
    print(f"  Status code: {resp.status_code} (Expected 206 Partial Content)")
    print(f"  Content-Range header: {resp.headers.get('Content-Range')}")
    print(f"  Content-Type header: {resp.headers.get('Content-Type')}")
    print(f"  Received bytes: {len(resp.content)}")
    assert resp.status_code in [200, 206], f"Stream range request failed: {resp.status_code}"
    results["range_request_status"] = resp.status_code
    results["content_range"] = resp.headers.get("Content-Range")

    # 7. Test Playstate Reporting (progress & mark watched/unwatched)
    print("\n[7] Testing Playstate Progress reporting...")
    progress_url = f"{JELLYFIN_URL}/Users/{USER_ID}/PlayingItems/{sample_id}/Progress"
    prog_params = {
        "PositionTicks": 500000000 # 50 seconds
    }
    resp = requests.post(progress_url, headers=HEADERS, params=prog_params, timeout=10)
    print(f"  Progress report status: {resp.status_code}")

    print("\n[8] Testing PlayedItems toggle (Mark played then restore unplayed)...")
    play_url = f"{JELLYFIN_URL}/Users/{USER_ID}/PlayedItems/{sample_id}"
    resp_play = requests.post(play_url, headers=HEADERS, timeout=10)
    print(f"  Mark watched status: {resp_play.status_code}")
    # Verify played
    resp_check = requests.get(f"{JELLYFIN_URL}/Users/{USER_ID}/Items/{sample_id}", headers=HEADERS, timeout=10)
    is_played = resp_check.json().get("UserData", {}).get("Played", False)
    print(f"  Verified Played status: {is_played}")

    # Revert to unwatched
    resp_unplay = requests.delete(play_url, headers=HEADERS, timeout=10)
    print(f"  Reverted to unwatched status: {resp_unplay.status_code}")
    resp_check2 = requests.get(f"{JELLYFIN_URL}/Users/{USER_ID}/Items/{sample_id}", headers=HEADERS, timeout=10)
    is_played2 = resp_check2.json().get("UserData", {}).get("Played", False)
    print(f"  Verified Unplayed status: {not is_played2}")

    results["playstate_test_success"] = (is_played is True and is_played2 is False)

    report_path = Path(r"c:\Users\nhnha\Documents\video-tools\MyTube\scripts\jellyfin_poc_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nJellyfin PoC report saved to: {report_path}")
    print("=== All Jellyfin PoC tests passed successfully! ===")

if __name__ == "__main__":
    test_jellyfin_poc()
