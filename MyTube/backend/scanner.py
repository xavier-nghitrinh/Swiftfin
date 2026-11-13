import base64
import logging
import re
import json
import os
try:
    import paramiko
except ImportError:
    paramiko = None
from typing import Dict, Any, List, Tuple

from backend.config import (
    SSH_HOST,
    SSH_PORT,
    SSH_USER,
    SSH_PASS,
    REMOTE_MEDIA_DIR,
)
from backend.database import get_db, now_iso
from backend.jellyfin_client import jellyfin

logger = logging.getLogger("mytube.scanner")

REMOTE_SCANNER_CODE = r"""
import os, json

root = '/storage/0692F50692F4FACF/yt_video'
results = {}

for dirpath, _, filenames in os.walk(root):
    for f in filenames:
        if f.endswith('.info.json'):
            json_path = os.path.join(dirpath, f)
            video_name = f[:-10]
            video_mkv = os.path.join(dirpath, video_name + '.mkv')
            thumb_jpg = os.path.join(dirpath, video_name + '-thumb.jpg')
            has_thumb = os.path.isfile(thumb_jpg)
            try:
                with open(json_path, 'r', encoding='utf-8') as jf:
                    data = json.load(jf)
                    results[video_mkv] = {
                        'video_id': data.get('id'),
                        'channel': data.get('channel'),
                        'channel_id': data.get('channel_id'),
                        'title': data.get('title'),
                        'upload_date': data.get('upload_date'),
                        'duration': data.get('duration'),
                        'description': data.get('description'),
                        'format': data.get('format'),
                        'language': data.get('language'),
                        'thumb_path': thumb_jpg if has_thumb else None
                    }
            except Exception:
                pass

print('SCAN_DATA_START')
print(json.dumps(results, ensure_ascii=False))
print('SCAN_DATA_END')
"""

def parse_audio_labels_from_meta(format_str: str, lang_str: str) -> List[str]:
    """Extract human-readable audio track labels from yt-dlp format & language strings."""
    labels: List[str] = []
    if format_str:
        # e.g. '398 - 1280x720 (720p)+251-46 - audio only (English (US) original (default), medium)+251-45 - audio only (Vietnamese, medium)'
        matches = re.findall(r"audio only \((.+?)\)(?=\+|$)", format_str)
        for m in matches:
            cleaned = re.sub(r",\s*(low|medium|high|ultralow)$", "", m.strip(), flags=re.IGNORECASE)
            labels.append(cleaned)
    if not labels and lang_str and "+" in lang_str:
        for code in lang_str.split("+"):
            labels.append(code.strip())
    return labels

def fetch_remote_metadata_cache() -> Dict[str, Dict[str, Any]]:
    """Extract yt-dlp metadata from all .info.json files (locally if on server, or over SSH)."""
    # 1. Direct local scan if running on server where REMOTE_MEDIA_DIR exists
    if os.path.isdir(REMOTE_MEDIA_DIR):
        try:
            results = {}
            for dirpath, _, filenames in os.walk(REMOTE_MEDIA_DIR):
                for f in filenames:
                    if f.endswith('.info.json'):
                        json_path = os.path.join(dirpath, f)
                        video_name = f[:-10]
                        video_mkv = os.path.join(dirpath, video_name + '.mkv')
                        thumb_jpg = os.path.join(dirpath, video_name + '-thumb.jpg')
                        has_thumb = os.path.isfile(thumb_jpg)
                        try:
                            with open(json_path, 'r', encoding='utf-8') as jf:
                                data = json.load(jf)
                                results[video_mkv] = {
                                    'video_id': data.get('id'),
                                    'channel': data.get('channel'),
                                    'channel_id': data.get('channel_id'),
                                    'title': data.get('title'),
                                    'upload_date': data.get('upload_date'),
                                    'duration': data.get('duration'),
                                    'description': data.get('description'),
                                    'format': data.get('format'),
                                    'language': data.get('language'),
                                    'thumb_path': thumb_jpg if has_thumb else None
                                }
                        except Exception:
                            pass
            logger.info(f"Loaded {len(results)} metadata records directly from local SSD.")
            return results
        except Exception as e:
            logger.warning(f"Local metadata scan error: {e}")

    # 2. Remote SSH scan fallback (e.g. when developing on Windows PC)
    if paramiko:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=8)
            
            sftp = client.open_sftp()
            temp_path = "/data/data/com.termux/files/home/mytube_scanner_worker.py"
            with sftp.file(temp_path, "w") as f:
                f.write(REMOTE_SCANNER_CODE)
            sftp.close()
            
            stdin, stdout, stderr = client.exec_command(f"python3 {temp_path}")
            out = stdout.read().decode("utf-8", errors="replace")
            client.exec_command(f"rm -f {temp_path}")
            client.close()
            
            if "SCAN_DATA_START" in out:
                raw = out.split("SCAN_DATA_START")[1].split("SCAN_DATA_END")[0].strip()
                cache = json.loads(raw)
                logger.info(f"Loaded {len(cache)} metadata records directly from SSD via SSH.")
                return cache
        except Exception as e:
            logger.warning(f"Could not fetch metadata cache via SSH ({e}). Falling back to Jellyfin data only.")
    return {}

def load_single_info_json(file_path: str, sftp=None) -> Dict[str, Any]:
    """Load metadata for a single video file from its corresponding .info.json file."""
    if not file_path:
        return {}
    base_path = file_path[:-4] if file_path.endswith(".mkv") else file_path
    json_path = base_path + ".info.json"
    thumb_path = base_path + "-thumb.jpg"

    # 1. Local direct read (on server or when path exists locally)
    if os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                data = json.load(jf)
                return {
                    "video_id": data.get("id"),
                    "channel": data.get("channel"),
                    "channel_id": data.get("channel_id"),
                    "title": data.get("title"),
                    "upload_date": data.get("upload_date"),
                    "duration": data.get("duration"),
                    "description": data.get("description"),
                    "format": data.get("format"),
                    "language": data.get("language"),
                    "thumb_path": thumb_path if os.path.isfile(thumb_path) else None,
                }
        except Exception as e:
            logger.debug(f"Failed to read local info.json at {json_path}: {e}")

    # 2. SFTP read fallback (when running on PC against remote Termux server)
    if sftp:
        try:
            with sftp.open(json_path, "r") as rf:
                data = json.load(rf)
                has_thumb = False
                try:
                    sftp.stat(thumb_path)
                    has_thumb = True
                except Exception:
                    pass
                return {
                    "video_id": data.get("id"),
                    "channel": data.get("channel"),
                    "channel_id": data.get("channel_id"),
                    "title": data.get("title"),
                    "upload_date": data.get("upload_date"),
                    "duration": data.get("duration"),
                    "description": data.get("description"),
                    "format": data.get("format"),
                    "language": data.get("language"),
                    "thumb_path": thumb_path if has_thumb else None,
                }
        except Exception as e:
            logger.debug(f"Failed to read remote info.json via SFTP at {json_path}: {e}")

    return {}

def extract_channel_folder_from_path(file_path: str) -> str:
    """Path format: /storage/0692F50692F4FACF/yt_video/Channel_Name/Season 2026/video.mkv"""
    if "yt_video/" in file_path:
        sub = file_path.split("yt_video/")[1]
        parts = sub.split("/")
        if parts:
            return parts[0]
    return "YouTube"

def sync_missing_thumbnails_to_sqlite(
    video_thumb_tasks: List[Tuple[str, str, str]],
    channel_thumb_tasks: List[Tuple[str, str]]
) -> int:
    """Fetch missing thumbnails into Base64 strings and store directly in SQLite rows."""
    if not video_thumb_tasks and not channel_thumb_tasks:
        return 0

    is_local = os.path.isdir(REMOTE_MEDIA_DIR)
    sftp = None
    ssh_client = None

    if not is_local and paramiko:
        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=8)
            sftp = ssh_client.open_sftp()
        except Exception as e:
            logger.warning(f"SFTP connection for thumbnails unavailable ({e}), using Jellyfin fallback.")

    cached = 0
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Channel Posters -> Base64 in channels.thumbnail_url
        for channel_id, remote_poster in channel_thumb_tasks:
            raw_bytes = None
            if remote_poster:
                if is_local and os.path.isfile(remote_poster):
                    try:
                        with open(remote_poster, "rb") as f:
                            raw_bytes = f.read()
                    except Exception:
                        pass
                elif sftp:
                    try:
                        with sftp.open(remote_poster, "rb") as rf:
                            raw_bytes = rf.read()
                    except Exception:
                        pass
            if raw_bytes:
                b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
                cursor.execute("UPDATE channels SET thumbnail_url = ? WHERE channel_id = ?", (b64, channel_id))
                cached += 1

        # 2. Video Thumbnails -> Base64 in videos.thumbnail_url
        for video_id, remote_thumb, jf_item_id in video_thumb_tasks:
            raw_bytes = None
            if remote_thumb:
                if is_local and os.path.isfile(remote_thumb):
                    try:
                        with open(remote_thumb, "rb") as f:
                            raw_bytes = f.read()
                    except Exception:
                        pass
                elif sftp:
                    try:
                        with sftp.open(remote_thumb, "rb") as rf:
                            raw_bytes = rf.read()
                    except Exception:
                        pass
            if not raw_bytes and jf_item_id:
                try:
                    url = f"{jellyfin.base_url}/Items/{jf_item_id}/Images/Thumb?fillWidth=640&quality=85"
                    resp = jellyfin.session.get(url, timeout=8)
                    if resp.status_code == 200 and resp.content:
                        raw_bytes = resp.content
                except Exception:
                    pass
            if raw_bytes:
                b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
                cursor.execute("UPDATE videos SET thumbnail_url = ? WHERE video_id = ?", (b64, video_id))
                cached += 1

        conn.commit()

    if sftp:
        try:
            sftp.close()
        except Exception:
            pass
    if ssh_client:
        try:
            ssh_client.close()
        except Exception:
            pass

    if cached > 0:
        logger.info(f"Stored {cached} thumbnails as Base64 directly in SQLite.")
    return cached

def scan_and_sync(force_full: bool = False) -> Dict[str, Any]:
    """Scan Jellyfin items and SSD .info.json metadata incrementally, storing metadata & Base64 thumbnails in SQLite."""
    logger.info(f"Starting MyTube library scan (force_full={force_full})...")
    jellyfin_items = jellyfin.get_library_items()
    logger.info(f"Fetched {len(jellyfin_items)} items from Jellyfin.")
    
    # SFTP client fallback for remote PC development if needed
    is_local = os.path.isdir(REMOTE_MEDIA_DIR)
    sftp = None
    ssh_client = None
    if not is_local and paramiko:
        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=8)
            sftp = ssh_client.open_sftp()
        except Exception as e:
            logger.debug(f"SSH client not available: {e}")

    # If force_full is explicitly requested, load full cache
    metadata_cache = {}
    if force_full:
        metadata_cache = fetch_remote_metadata_cache()

    synced_videos = 0
    new_videos = 0
    updated_videos = 0
    synced_channels = 0
    now = now_iso()

    video_thumb_tasks: List[Tuple[str, str, str]] = []
    channel_thumb_tasks: List[Tuple[str, str]] = []
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Ensure audio_meta column exists
        try:
            cursor.execute("ALTER TABLE videos ADD COLUMN audio_meta TEXT DEFAULT ''")
        except Exception:
            pass

        # 1. Preload existing channels
        cursor.execute("SELECT channel_id, name, folder_path, thumbnail_url FROM channels")
        existing_channels = {r["channel_id"]: dict(r) for r in cursor.fetchall()}

        # 2. Preload existing videos in a single query
        cursor.execute("""
            SELECT video_id, channel_id, channel_name, title, description,
                   upload_date, duration, file_path, thumbnail_url, jellyfin_item_id,
                   watched, watched_at, playback_position, file_status, trash_at, audio_meta
            FROM videos
        """)
        existing_rows = cursor.fetchall()
        existing_by_path: Dict[str, dict] = {}
        existing_by_id: Dict[str, dict] = {}
        for r in existing_rows:
            d = dict(r)
            if d.get("file_path"):
                existing_by_path[d["file_path"]] = d
            if d.get("video_id"):
                existing_by_id[d["video_id"]] = d

        processed_channels = set()
        
        for item in jellyfin_items:
            item_id = item["Id"]
            file_path = item.get("Path", "")
            premiere_date = item.get("PremiereDate", "")
            overview = item.get("Overview", "")
            user_data = item.get("UserData", {})
            jellyfin_played = 1 if user_data.get("Played", False) else 0
            jellyfin_pos = user_data.get("PlaybackPositionTicks", 0) / 10000000.0
            duration = item.get("RunTimeTicks", 0) / 10000000.0
            
            channel_folder = extract_channel_folder_from_path(file_path)
            channel_name = channel_folder

            existing = existing_by_path.get(file_path)

            if existing and not force_full:
                # FAST PATH: Existing video in DB - bypass info.json disk read completely
                video_id = existing["video_id"]
                channel_id = existing["channel_id"]
                channel_name = existing["channel_name"]

                final_watched = existing["watched"]
                watched_at = existing["watched_at"]
                if jellyfin_played == 1 and final_watched == 0:
                    final_watched = 1
                    watched_at = now

                playback_pos = existing["playback_position"]
                if jellyfin_pos > playback_pos:
                    playback_pos = jellyfin_pos

                # Check if thumbnail is cached
                existing_vid_thumb = existing["thumbnail_url"] or ""
                if not existing_vid_thumb.startswith("data:image/"):
                    remote_video_thumb = (file_path[:-4] if file_path.endswith(".mkv") else file_path) + "-thumb.jpg"
                    video_thumb_tasks.append((video_id, remote_video_thumb, item_id))

                # Update playback / watch status if changed
                needs_update = (
                    final_watched != existing["watched"] or
                    abs(playback_pos - existing["playback_position"]) > 1.0 or
                    item_id != existing["jellyfin_item_id"]
                )
                if needs_update:
                    cursor.execute("""
                        UPDATE videos
                        SET watched = ?, watched_at = ?, playback_position = ?, jellyfin_item_id = ?, updated_at = ?
                        WHERE video_id = ?
                    """, (final_watched, watched_at, playback_pos, item_id, now, video_id))
                    updated_videos += 1

                synced_videos += 1

            else:
                # SLOW PATH: New video (or force_full) -> Load metadata for this item only
                meta = metadata_cache.get(file_path) if force_full else load_single_info_json(file_path, sftp=sftp)
                if not meta:
                    meta = {}

                video_id = meta.get("video_id")
                channel_id = meta.get("channel_id")
                title = meta.get("title") or item.get("Name", "")
                
                if meta.get("channel"):
                    channel_name = meta.get("channel")
                if meta.get("duration"):
                    try:
                        duration = float(meta.get("duration"))
                    except (ValueError, TypeError):
                        pass

                upload_date = meta.get("upload_date")
                if not upload_date and premiere_date:
                    upload_date = premiere_date[:10].replace("-", "")

                if not video_id:
                    m = re.search(r"watch\?v=([a-zA-Z0-9_-]{11})", overview)
                    if m:
                        video_id = m.group(1)
                    else:
                        video_id = f"jf_{item_id}"

                if not channel_id:
                    channel_id = re.sub(r'[^a-zA-Z0-9_-]', '_', channel_name).lower()

                iso_upload_date = upload_date
                if upload_date and len(upload_date) == 8 and upload_date.isdigit():
                    iso_upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

                audio_labels = parse_audio_labels_from_meta(meta.get("format", ""), meta.get("language", ""))
                audio_meta_json = json.dumps(audio_labels, ensure_ascii=False)

                # Check if video_id already exists (e.g. file was moved or path updated)
                prev_vid = existing_by_id.get(video_id) or existing
                final_watched = jellyfin_played
                watched_at = now if jellyfin_played else None
                playback_pos = jellyfin_pos
                file_status = 'available'
                trash_at = None
                existing_vid_thumb = ""

                if prev_vid:
                    if prev_vid["watched"] == 1:
                        final_watched = 1
                        watched_at = prev_vid["watched_at"]
                    if prev_vid["playback_position"] > playback_pos:
                        playback_pos = prev_vid["playback_position"]
                    file_status = prev_vid["file_status"]
                    trash_at = prev_vid["trash_at"]
                    existing_vid_thumb = prev_vid["thumbnail_url"] or ""

                has_b64_vid_thumb = existing_vid_thumb.startswith("data:image/")
                if not has_b64_vid_thumb:
                    remote_video_thumb = meta.get("thumb_path") or (file_path[:-4] + "-thumb.jpg" if file_path.endswith(".mkv") else "")
                    video_thumb_tasks.append((video_id, remote_video_thumb, item_id))

                cursor.execute("""
                    INSERT INTO videos (
                        video_id, channel_id, channel_name, title, description,
                        upload_date, duration, file_path, thumbnail_url, jellyfin_item_id,
                        watched, watched_at, playback_position, file_status, trash_at,
                        audio_meta, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        channel_name = excluded.channel_name,
                        title = excluded.title,
                        description = excluded.description,
                        upload_date = excluded.upload_date,
                        duration = excluded.duration,
                        file_path = excluded.file_path,
                        jellyfin_item_id = excluded.jellyfin_item_id,
                        watched = excluded.watched,
                        watched_at = excluded.watched_at,
                        playback_position = excluded.playback_position,
                        file_status = excluded.file_status,
                        trash_at = excluded.trash_at,
                        audio_meta = excluded.audio_meta,
                        updated_at = excluded.updated_at
                """, (
                    video_id, channel_id, channel_name, title, meta.get("description", overview),
                    iso_upload_date, duration, file_path, existing_vid_thumb if has_b64_vid_thumb else "", item_id,
                    final_watched, watched_at, playback_pos, file_status, trash_at,
                    audio_meta_json, now, now
                ))
                new_videos += 1
                synced_videos += 1

            # Channel processing
            if channel_id not in processed_channels:
                processed_channels.add(channel_id)
                ch_info = existing_channels.get(channel_id)
                
                if not ch_info:
                    remote_channel_poster = f"{REMOTE_MEDIA_DIR}/{channel_folder}/poster.jpg"
                    channel_thumb_tasks.append((channel_id, remote_channel_poster))
                    cursor.execute("""
                        INSERT INTO channels (channel_id, name, folder_path, thumbnail_url, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        channel_id,
                        channel_name,
                        f"{REMOTE_MEDIA_DIR}/{channel_folder}",
                        "",
                        now
                    ))
                    existing_channels[channel_id] = {
                        "channel_id": channel_id,
                        "thumbnail_url": "",
                        "name": channel_name,
                        "folder_path": f"{REMOTE_MEDIA_DIR}/{channel_folder}"
                    }
                    synced_channels += 1
                else:
                    ch_thumb = ch_info.get("thumbnail_url") or ""
                    if not ch_thumb.startswith("data:image/"):
                        remote_channel_poster = f"{REMOTE_MEDIA_DIR}/{channel_folder}/poster.jpg"
                        channel_thumb_tasks.append((channel_id, remote_channel_poster))

        conn.commit()

    if sftp:
        try:
            sftp.close()
        except Exception:
            pass
    if ssh_client:
        try:
            ssh_client.close()
        except Exception:
            pass

    cached_thumbs = sync_missing_thumbnails_to_sqlite(video_thumb_tasks, channel_thumb_tasks)
        
    logger.info(
        f"YouTube Scan complete: {synced_videos} videos ({new_videos} new, {updated_videos} updated), "
        f"{len(processed_channels)} channels ({synced_channels} new), {cached_thumbs} Base64 thumbnails cached."
    )

    # Sync Movies and Shows libraries
    movie_stats = sync_movies()
    show_stats = sync_shows_and_episodes()

    return {
        "synced_videos": synced_videos,
        "new_videos": new_videos,
        "updated_videos": updated_videos,
        "synced_channels": len(processed_channels),
        "new_channels": synced_channels,
        "cached_thumbnails": cached_thumbs,
        **movie_stats,
        **show_stats,
    }


def sync_movies() -> Dict[str, Any]:
    """Scan and sync Movies library from Jellyfin into SQLite with Base64 thumbnails."""
    logger.info("Scanning Movies library from Jellyfin...")
    try:
        items = jellyfin.get_movie_items()
    except Exception as e:
        logger.error(f"Failed to fetch movies from Jellyfin: {e}")
        return {"synced_movies": 0, "new_movies": 0, "cached_movie_thumbs": 0}

    logger.info(f"Fetched {len(items)} movies from Jellyfin.")
    now = now_iso()
    synced = 0
    new_count = 0
    thumb_tasks: List[Tuple[str, str, str]] = []  # (movie_id, image_type, column_name)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT movie_id, watched, watched_at, playback_position, file_status, trash_at, poster_url, backdrop_url FROM movies")
        existing_movies = {row["movie_id"]: dict(row) for row in cursor.fetchall()}

        for item in items:
            movie_id = item["Id"]
            title = item.get("Name") or "Untitled Movie"
            overview = item.get("Overview") or ""
            release_year = item.get("ProductionYear")
            premiere_date = item.get("PremiereDate")
            ticks = item.get("RunTimeTicks") or 0
            duration = round(ticks / 10000000.0, 2)
            genres = json.dumps(item.get("Genres") or [], ensure_ascii=False)
            official_rating = item.get("OfficialRating") or ""
            community_rating = round(float(item.get("CommunityRating") or 0), 1)
            file_path = item.get("Path") or ""

            user_data = item.get("UserData") or {}
            jf_played = 1 if user_data.get("Played") else 0
            jf_pos = round((user_data.get("PlaybackPositionTicks") or 0) / 10000000.0, 2)

            prev = existing_movies.get(movie_id)
            final_watched = jf_played
            watched_at = now if jf_played else None
            playback_pos = jf_pos
            file_status = "available"
            trash_at = None
            poster_url = ""
            backdrop_url = ""

            if prev:
                if prev["watched"] == 1:
                    final_watched = 1
                    watched_at = prev["watched_at"]
                if prev["playback_position"] > playback_pos:
                    playback_pos = prev["playback_position"]
                file_status = prev["file_status"]
                trash_at = prev["trash_at"]
                poster_url = prev["poster_url"] or ""
                backdrop_url = prev["backdrop_url"] or ""
            else:
                new_count += 1
                # Default to Jellyfin image URLs as initial fallback
                poster_url = jellyfin.get_image_url(movie_id, "Primary", 400, 80)
                if item.get("BackdropImageTags"):
                    backdrop_url = jellyfin.get_image_url(movie_id, "Backdrop/0", 960, 75)

            cursor.execute("""
                INSERT INTO movies (
                    movie_id, title, overview, release_year, premiere_date,
                    duration, genres, official_rating, community_rating,
                    poster_url, backdrop_url, file_path, jellyfin_item_id,
                    watched, watched_at, playback_position, file_status, trash_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(movie_id) DO UPDATE SET
                    title = excluded.title,
                    overview = excluded.overview,
                    release_year = excluded.release_year,
                    premiere_date = excluded.premiere_date,
                    duration = excluded.duration,
                    genres = excluded.genres,
                    official_rating = excluded.official_rating,
                    community_rating = excluded.community_rating,
                    poster_url = CASE WHEN movies.poster_url LIKE 'data:image/%' THEN movies.poster_url ELSE excluded.poster_url END,
                    backdrop_url = CASE WHEN movies.backdrop_url LIKE 'data:image/%' THEN movies.backdrop_url ELSE excluded.backdrop_url END,
                    file_path = excluded.file_path,
                    jellyfin_item_id = excluded.jellyfin_item_id,
                    watched = excluded.watched,
                    watched_at = excluded.watched_at,
                    playback_position = excluded.playback_position,
                    file_status = excluded.file_status,
                    trash_at = excluded.trash_at,
                    updated_at = excluded.updated_at
            """, (
                movie_id, title, overview, release_year, premiere_date,
                duration, genres, official_rating, community_rating,
                poster_url, backdrop_url, file_path, movie_id,
                final_watched, watched_at, playback_pos, file_status, trash_at,
                now, now
            ))
            synced += 1

            if not poster_url.startswith("data:image/"):
                thumb_tasks.append((movie_id, "Primary", "poster_url"))
            if not backdrop_url.startswith("data:image/") and item.get("BackdropImageTags"):
                thumb_tasks.append((movie_id, "Backdrop/0", "backdrop_url"))

        conn.commit()

    cached_thumbs = 0
    if thumb_tasks:
        logger.info(f"Caching {len(thumb_tasks)} movie images to Base64 in SQLite...")
        with get_db() as conn:
            cursor = conn.cursor()
            for mid, img_type, col in thumb_tasks:
                w = 400 if "Primary" in img_type else 960
                q = 80 if "Primary" in img_type else 75
                raw_bytes = jellyfin.get_image_bytes(mid, img_type, w, q)
                if raw_bytes:
                    b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
                    cursor.execute(f"UPDATE movies SET {col} = ? WHERE movie_id = ?", (b64, mid))
                    cached_thumbs += 1
            conn.commit()

    logger.info(f"Movies scan complete: {synced} synced ({new_count} new), {cached_thumbs} Base64 images cached.")
    return {
        "synced_movies": synced,
        "new_movies": new_count,
        "cached_movie_thumbs": cached_thumbs
    }


def sync_shows_and_episodes() -> Dict[str, Any]:
    """Scan and sync Shows and Episodes libraries from Jellyfin into SQLite with Base64 thumbnails."""
    logger.info("Scanning Shows library from Jellyfin...")
    try:
        show_items = jellyfin.get_show_items()
    except Exception as e:
        logger.error(f"Failed to fetch shows from Jellyfin: {e}")
        return {"synced_shows": 0, "new_shows": 0, "synced_episodes": 0, "new_episodes": 0, "cached_show_thumbs": 0}

    logger.info(f"Fetched {len(show_items)} series from Jellyfin.")
    now = now_iso()
    synced_shows = 0
    new_shows = 0
    show_thumb_tasks: List[Tuple[str, str, str]] = []

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT show_id, poster_url, backdrop_url, file_status, trash_at FROM shows")
        existing_shows = {row["show_id"]: dict(row) for row in cursor.fetchall()}

        for item in show_items:
            show_id = item["Id"]
            title = item.get("Name") or "Untitled Show"
            overview = item.get("Overview") or ""
            start_year = item.get("ProductionYear")
            status = item.get("Status") or ""
            genres = json.dumps(item.get("Genres") or [], ensure_ascii=False)
            official_rating = item.get("OfficialRating") or ""
            community_rating = round(float(item.get("CommunityRating") or 0), 1)
            file_path = item.get("Path") or ""

            prev = existing_shows.get(show_id)
            file_status = "available"
            trash_at = None
            poster_url = ""
            backdrop_url = ""

            if prev:
                file_status = prev["file_status"]
                trash_at = prev["trash_at"]
                poster_url = prev["poster_url"] or ""
                backdrop_url = prev["backdrop_url"] or ""
            else:
                new_shows += 1
                poster_url = jellyfin.get_image_url(show_id, "Primary", 400, 80)
                if item.get("BackdropImageTags"):
                    backdrop_url = jellyfin.get_image_url(show_id, "Backdrop/0", 960, 75)

            cursor.execute("""
                INSERT INTO shows (
                    show_id, title, overview, start_year, status, genres,
                    official_rating, community_rating, poster_url, backdrop_url,
                    file_path, jellyfin_item_id, file_status, trash_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(show_id) DO UPDATE SET
                    title = excluded.title,
                    overview = excluded.overview,
                    start_year = excluded.start_year,
                    status = excluded.status,
                    genres = excluded.genres,
                    official_rating = excluded.official_rating,
                    community_rating = excluded.community_rating,
                    poster_url = CASE WHEN shows.poster_url LIKE 'data:image/%' THEN shows.poster_url ELSE excluded.poster_url END,
                    backdrop_url = CASE WHEN shows.backdrop_url LIKE 'data:image/%' THEN shows.backdrop_url ELSE excluded.backdrop_url END,
                    file_path = excluded.file_path,
                    jellyfin_item_id = excluded.jellyfin_item_id,
                    file_status = excluded.file_status,
                    trash_at = excluded.trash_at,
                    updated_at = excluded.updated_at
            """, (
                show_id, title, overview, start_year, status, genres,
                official_rating, community_rating, poster_url, backdrop_url,
                file_path, show_id, file_status, trash_at, now, now
            ))
            synced_shows += 1

            if not poster_url.startswith("data:image/"):
                show_thumb_tasks.append((show_id, "Primary", "poster_url"))
            if not backdrop_url.startswith("data:image/") and item.get("BackdropImageTags"):
                show_thumb_tasks.append((show_id, "Backdrop/0", "backdrop_url"))

        conn.commit()

    cached_show_thumbs = 0
    if show_thumb_tasks:
        with get_db() as conn:
            cursor = conn.cursor()
            for sid, img_type, col in show_thumb_tasks:
                w = 400 if "Primary" in img_type else 960
                q = 80 if "Primary" in img_type else 75
                raw_bytes = jellyfin.get_image_bytes(sid, img_type, w, q)
                if raw_bytes:
                    b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
                    cursor.execute(f"UPDATE shows SET {col} = ? WHERE show_id = ?", (b64, sid))
                    cached_show_thumbs += 1
            conn.commit()

    # Now sync all episodes
    logger.info("Scanning Episodes from Jellyfin...")
    try:
        episode_items = jellyfin.get_episode_items()
    except Exception as e:
        logger.error(f"Failed to fetch episodes from Jellyfin: {e}")
        return {
            "synced_shows": synced_shows,
            "new_shows": new_shows,
            "synced_episodes": 0,
            "new_episodes": 0,
            "cached_show_thumbs": cached_show_thumbs
        }

    logger.info(f"Fetched {len(episode_items)} episodes from Jellyfin.")
    synced_episodes = 0
    new_episodes = 0
    episode_thumb_tasks: List[str] = []  # episode_ids needing thumbnails

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT episode_id, watched, watched_at, playback_position, file_status, trash_at, thumbnail_url FROM episodes")
        existing_episodes = {row["episode_id"]: dict(row) for row in cursor.fetchall()}

        for item in episode_items:
            episode_id = item["Id"]
            show_id = item.get("SeriesId") or ""
            show_name = item.get("SeriesName") or "Unknown Show"
            season_id = item.get("SeasonId") or ""
            season_name = item.get("SeasonName") or "Season 1"
            season_number = item.get("ParentIndexNumber") if item.get("ParentIndexNumber") is not None else 1
            episode_number = item.get("IndexNumber") if item.get("IndexNumber") is not None else 1
            title = item.get("Name") or f"Episode {episode_number}"
            overview = item.get("Overview") or ""
            premiere_date = item.get("PremiereDate")
            ticks = item.get("RunTimeTicks") or 0
            duration = round(ticks / 10000000.0, 2)
            file_path = item.get("Path") or ""

            user_data = item.get("UserData") or {}
            jf_played = 1 if user_data.get("Played") else 0
            jf_pos = round((user_data.get("PlaybackPositionTicks") or 0) / 10000000.0, 2)

            prev = existing_episodes.get(episode_id)
            final_watched = jf_played
            watched_at = now if jf_played else None
            playback_pos = jf_pos
            file_status = "available"
            trash_at = None
            thumbnail_url = ""

            if prev:
                if prev["watched"] == 1:
                    final_watched = 1
                    watched_at = prev["watched_at"]
                if prev["playback_position"] > playback_pos:
                    playback_pos = prev["playback_position"]
                file_status = prev["file_status"]
                trash_at = prev["trash_at"]
                thumbnail_url = prev["thumbnail_url"] or ""
            else:
                new_episodes += 1
                thumbnail_url = jellyfin.get_image_url(episode_id, "Primary", 480, 75)

            cursor.execute("""
                INSERT INTO episodes (
                    episode_id, show_id, show_name, season_id, season_name,
                    season_number, episode_number, title, overview, premiere_date,
                    duration, thumbnail_url, file_path, jellyfin_item_id,
                    watched, watched_at, playback_position, file_status, trash_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    show_id = excluded.show_id,
                    show_name = excluded.show_name,
                    season_id = excluded.season_id,
                    season_name = excluded.season_name,
                    season_number = excluded.season_number,
                    episode_number = excluded.episode_number,
                    title = excluded.title,
                    overview = excluded.overview,
                    premiere_date = excluded.premiere_date,
                    duration = excluded.duration,
                    thumbnail_url = CASE WHEN episodes.thumbnail_url LIKE 'data:image/%' THEN episodes.thumbnail_url ELSE excluded.thumbnail_url END,
                    file_path = excluded.file_path,
                    jellyfin_item_id = excluded.jellyfin_item_id,
                    watched = excluded.watched,
                    watched_at = excluded.watched_at,
                    playback_position = excluded.playback_position,
                    file_status = excluded.file_status,
                    trash_at = excluded.trash_at,
                    updated_at = excluded.updated_at
            """, (
                episode_id, show_id, show_name, season_id, season_name,
                season_number, episode_number, title, overview, premiere_date,
                duration, thumbnail_url, file_path, episode_id,
                final_watched, watched_at, playback_pos, file_status, trash_at,
                now, now
            ))
            synced_episodes += 1

            if not thumbnail_url.startswith("data:image/"):
                episode_thumb_tasks.append(episode_id)

        conn.commit()

    cached_ep_thumbs = 0
    if episode_thumb_tasks:
        logger.info(f"Caching {len(episode_thumb_tasks)} episode screenshots to Base64 in SQLite...")
        with get_db() as conn:
            cursor = conn.cursor()
            for epid in episode_thumb_tasks:
                raw_bytes = jellyfin.get_image_bytes(epid, "Primary", 480, 75)
                if raw_bytes:
                    b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
                    cursor.execute("UPDATE episodes SET thumbnail_url = ? WHERE episode_id = ?", (b64, epid))
                    cached_ep_thumbs += 1
            conn.commit()

    logger.info(
        f"Shows & Episodes scan complete: {synced_shows} series ({new_shows} new), "
        f"{synced_episodes} episodes ({new_episodes} new), {cached_show_thumbs + cached_ep_thumbs} Base64 thumbnails cached."
    )
    return {
        "synced_shows": synced_shows,
        "new_shows": new_shows,
        "synced_episodes": synced_episodes,
        "new_episodes": new_episodes,
        "cached_show_thumbs": cached_show_thumbs + cached_ep_thumbs
    }
