import base64
import logging
import re
import json
import os
from typing import Dict, Any, List, Optional, Tuple

from backend.ai_chat_store import delete_media_ai_data
from backend.config import REMOTE_MEDIA_DIR
from backend.database import get_db, now_iso
from backend.jellyfin_client import jellyfin

logger = logging.getLogger("mytube.scanner")

def get_file_size(file_path: str) -> Optional[int]:
    """Size in bytes of a local video file, or None when the path is not accessible."""
    if file_path and os.path.isfile(file_path):
        try:
            return os.path.getsize(file_path)
        except OSError:
            return None
    return None

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
    """Extract yt-dlp metadata from local .info.json files."""
    if not os.path.isdir(REMOTE_MEDIA_DIR):
        logger.warning("Media directory is unavailable locally: %s", REMOTE_MEDIA_DIR)
        return {}

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
        logger.info("Loaded %d metadata records from local storage.", len(results))
        return results
    except Exception as e:
        logger.warning("Local metadata scan error: %s", e)
        return {}

def load_single_info_json(file_path: str) -> Dict[str, Any]:
    """Load metadata for a single video file from its corresponding .info.json file."""
    if not file_path:
        return {}
    base_path = file_path[:-4] if file_path.endswith(".mkv") else file_path
    json_path = base_path + ".info.json"
    thumb_path = base_path + "-thumb.jpg"

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

    return {}

def extract_channel_folder_from_path(file_path: str) -> str:
    """Get the channel folder from a path under the yt_video library."""
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

    cached = 0
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Channel Posters -> Base64 in channels.thumbnail_url
        for channel_id, remote_poster in channel_thumb_tasks:
            raw_bytes = None
            if remote_poster and os.path.isfile(remote_poster):
                try:
                    with open(remote_poster, "rb") as f:
                        raw_bytes = f.read()
                except Exception:
                    pass
            if raw_bytes:
                b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
                cursor.execute("UPDATE channels SET thumbnail_url = ? WHERE channel_id = ?", (b64, channel_id))
                cached += 1

        # 2. Video Thumbnails -> Base64 in videos.thumbnail_url
        for video_id, remote_thumb, jf_item_id in video_thumb_tasks:
            raw_bytes = None
            if remote_thumb and os.path.isfile(remote_thumb):
                try:
                    with open(remote_thumb, "rb") as f:
                        raw_bytes = f.read()
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

    if cached > 0:
        logger.info(f"Stored {cached} thumbnails as Base64 directly in SQLite.")
    return cached

def _remove_missing_items(cursor, table: str, pk_col: str, jellyfin_col: str, media_type: str, present_ids: set) -> int:
    """Delete rows whose Jellyfin item is no longer in the library, along with their watch progress and AI chat."""
    cursor.execute(
        f"SELECT {pk_col}, {jellyfin_col} FROM {table} WHERE {jellyfin_col} IS NOT NULL AND {jellyfin_col} != ''"
    )
    stale = [r[pk_col] for r in cursor.fetchall() if r[jellyfin_col] not in present_ids]
    for pk in stale:
        cursor.execute("DELETE FROM user_progress WHERE media_id = ? AND media_type = ?", (pk, media_type))
        delete_media_ai_data(cursor, pk)
        cursor.execute(f"DELETE FROM {table} WHERE {pk_col} = ?", (pk,))
    if stale:
        logger.info(f"Removed {len(stale)} {table} rows no longer present in Jellyfin.")
    return len(stale)


def scan_and_sync(force_full: bool = False) -> Dict[str, Any]:
    """Scan Jellyfin items and SSD .info.json metadata incrementally, storing metadata & Base64 thumbnails in SQLite."""
    logger.info(f"Starting MyTube library scan (force_full={force_full})...")
    jellyfin_items = jellyfin.get_library_items()
    logger.info(f"Fetched {len(jellyfin_items)} items from Jellyfin.")
    
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
                   file_status, audio_meta, file_size_bytes
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
            duration = item.get("RunTimeTicks", 0) / 10000000.0
            
            channel_folder = extract_channel_folder_from_path(file_path)
            channel_name = channel_folder

            existing = existing_by_path.get(file_path)

            if existing and not force_full:
                # FAST PATH: Existing video in DB - bypass info.json disk read completely
                video_id = existing["video_id"]
                channel_id = existing["channel_id"]
                channel_name = existing["channel_name"]

                # Check if thumbnail is cached
                existing_vid_thumb = existing["thumbnail_url"] or ""
                if not existing_vid_thumb.startswith("data:image/"):
                    remote_video_thumb = (file_path[:-4] if file_path.endswith(".mkv") else file_path) + "-thumb.jpg"
                    video_thumb_tasks.append((video_id, remote_video_thumb, item_id))

                # Refresh the Jellyfin item id and fill in file size when it was never recorded
                file_size = existing["file_size_bytes"]
                if file_size is None:
                    file_size = get_file_size(file_path)
                if item_id != existing["jellyfin_item_id"] or file_size != existing["file_size_bytes"]:
                    cursor.execute("""
                        UPDATE videos
                        SET jellyfin_item_id = ?, file_size_bytes = ?, updated_at = ?
                        WHERE video_id = ?
                    """, (item_id, file_size, now, video_id))
                    updated_videos += 1

                synced_videos += 1

            else:
                # SLOW PATH: New video (or force_full) -> Load metadata for this item only
                meta = metadata_cache.get(file_path) if force_full else load_single_info_json(file_path)
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
                file_status = 'available'
                existing_vid_thumb = ""

                if prev_vid:
                    file_status = prev_vid["file_status"]
                    existing_vid_thumb = prev_vid["thumbnail_url"] or ""

                has_b64_vid_thumb = existing_vid_thumb.startswith("data:image/")
                if not has_b64_vid_thumb:
                    remote_video_thumb = meta.get("thumb_path") or (file_path[:-4] + "-thumb.jpg" if file_path.endswith(".mkv") else "")
                    video_thumb_tasks.append((video_id, remote_video_thumb, item_id))

                cursor.execute("""
                    INSERT INTO videos (
                        video_id, channel_id, channel_name, title, description,
                        upload_date, duration, file_path, thumbnail_url, jellyfin_item_id,
                        file_status, audio_meta, file_size_bytes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        channel_name = excluded.channel_name,
                        title = excluded.title,
                        description = excluded.description,
                        upload_date = excluded.upload_date,
                        duration = excluded.duration,
                        file_path = excluded.file_path,
                        jellyfin_item_id = excluded.jellyfin_item_id,
                        file_status = excluded.file_status,
                        audio_meta = excluded.audio_meta,
                        file_size_bytes = COALESCE(excluded.file_size_bytes, videos.file_size_bytes),
                        updated_at = excluded.updated_at
                """, (
                    video_id, channel_id, channel_name, title, meta.get("description", overview),
                    iso_upload_date, duration, file_path, existing_vid_thumb if has_b64_vid_thumb else "", item_id,
                    file_status, audio_meta_json, get_file_size(file_path), now, now
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

        # Reconcile: a video whose Jellyfin item is gone (deleted in Jellyfin) is removed from SQLite so
        # MyTube does not list an unplayable file. Skipped for an empty fetch so a misconfigured library
        # cannot wipe rows; get_library_items raises on partial reads, so a short page never gets here.
        removed_videos = 0
        if jellyfin_items:
            jellyfin_ids = {item["Id"] for item in jellyfin_items}
            removed_videos = _remove_missing_items(cursor, "videos", "video_id", "jellyfin_item_id", "youtube", jellyfin_ids)

        conn.commit()

    cached_thumbs = sync_missing_thumbnails_to_sqlite(video_thumb_tasks, channel_thumb_tasks)
        
    logger.info(
        f"YouTube Scan complete: {synced_videos} videos ({new_videos} new, {updated_videos} updated, {removed_videos} removed), "
        f"{len(processed_channels)} channels ({synced_channels} new), {cached_thumbs} Base64 thumbnails cached."
    )

    # Sync Movies, Shows, and Music libraries
    movie_stats = sync_movies()
    show_stats = sync_shows_and_episodes()
    music_stats = sync_music()

    return {
        "synced_videos": synced_videos,
        "new_videos": new_videos,
        "updated_videos": updated_videos,
        "removed_videos": removed_videos,
        "synced_channels": len(processed_channels),
        "new_channels": synced_channels,
        "cached_thumbnails": cached_thumbs,
        **movie_stats,
        **show_stats,
        **music_stats,
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
        cursor.execute("SELECT movie_id, file_status, poster_url, backdrop_url FROM movies")
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

            prev = existing_movies.get(movie_id)
            file_status = "available"
            poster_url = ""
            backdrop_url = ""

            if prev:
                file_status = prev["file_status"]
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
                    file_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    file_status = excluded.file_status,
                    updated_at = excluded.updated_at
            """, (
                movie_id, title, overview, release_year, premiere_date,
                duration, genres, official_rating, community_rating,
                poster_url, backdrop_url, file_path, movie_id,
                file_status, now, now
            ))
            synced += 1

            if not poster_url.startswith("data:image/"):
                thumb_tasks.append((movie_id, "Primary", "poster_url"))
            if not backdrop_url.startswith("data:image/") and item.get("BackdropImageTags"):
                thumb_tasks.append((movie_id, "Backdrop/0", "backdrop_url"))

        removed = 0
        if items:
            removed = _remove_missing_items(cursor, "movies", "movie_id", "jellyfin_item_id", "movie", {item["Id"] for item in items})
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

    logger.info(f"Movies scan complete: {synced} synced ({new_count} new, {removed} removed), {cached_thumbs} Base64 images cached.")
    return {
        "synced_movies": synced,
        "new_movies": new_count,
        "removed_movies": removed,
        "cached_movie_thumbs": cached_thumbs
    }


_MUSIC_NOISE_RE = re.compile(
    r"\s*[\(\[][^\)\]]*(official|music video|lyric|audio|visuali[sz]er|\bHD\b|\b4K\b)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def parse_music_title(name: str) -> Tuple[str, str]:
    """Split a track name like 'Artist - Title (Official Video)' into (artist, title)."""
    cleaned = _MUSIC_NOISE_RE.sub("", name or "").strip()
    if " - " in cleaned:
        artist, title = cleaned.split(" - ", 1)
        return artist.strip() or "Unknown Artist", title.strip() or cleaned
    return "Unknown Artist", cleaned or "Untitled Track"


def _first_artist_name(entries: Any) -> str:
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        return entries[0].get("Name") or ""
    return ""


def sync_music() -> Dict[str, Any]:
    """Sync the Jellyfin Music library into music_tracks. Tracks missing from Jellyfin are removed with their user data."""
    logger.info("Scanning Music library from Jellyfin...")
    try:
        items = jellyfin.get_music_items()
    except Exception as e:
        logger.error(f"Failed to fetch music from Jellyfin: {e}")
        return {"synced_music": 0, "new_music": 0, "removed_music": 0}
    if items is None:
        return {"synced_music": 0, "new_music": 0, "removed_music": 0}

    logger.info(f"Fetched {len(items)} tracks from Jellyfin Music library.")
    now = now_iso()
    new_count = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT track_id FROM music_tracks")
        existing_ids = {row["track_id"] for row in cursor.fetchall()}

        for item in items:
            track_id = item["Id"]
            artist, title = parse_music_title(item.get("Name") or "")
            source_group = _first_artist_name(item.get("AlbumArtists")) or _first_artist_name(item.get("Artists"))
            image_item_id = item.get("AlbumId") or track_id
            duration = round((item.get("RunTimeTicks") or 0) / 10000000.0, 2)
            release_year = item.get("ProductionYear")
            if track_id not in existing_ids:
                new_count += 1

            cursor.execute("""
                INSERT INTO music_tracks (
                    track_id, title, artist, source_group, image_item_id,
                    duration, release_year, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    source_group = excluded.source_group,
                    image_item_id = excluded.image_item_id,
                    duration = excluded.duration,
                    release_year = excluded.release_year,
                    updated_at = excluded.updated_at
            """, (track_id, title, artist, source_group, image_item_id, duration, release_year, now, now))

        removed = 0
        present_ids = {item["Id"] for item in items}
        # An empty fetch is ignored so a misconfigured library cannot wipe the music tables
        if present_ids:
            stale = existing_ids - present_ids
            for track_id in stale:
                cursor.execute("DELETE FROM user_music WHERE track_id = ?", (track_id,))
                cursor.execute("DELETE FROM music_playlist_items WHERE track_id = ?", (track_id,))
                cursor.execute("DELETE FROM music_tracks WHERE track_id = ?", (track_id,))
            removed = len(stale)
        conn.commit()

    logger.info(f"Music scan complete: {len(items)} synced ({new_count} new, {removed} removed).")
    return {
        "synced_music": len(items),
        "new_music": new_count,
        "removed_music": removed,
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
        cursor.execute("SELECT show_id, poster_url, backdrop_url, file_status FROM shows")
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
            poster_url = ""
            backdrop_url = ""

            if prev:
                file_status = prev["file_status"]
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
                    file_path, jellyfin_item_id, file_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    updated_at = excluded.updated_at
            """, (
                show_id, title, overview, start_year, status, genres,
                official_rating, community_rating, poster_url, backdrop_url,
                file_path, show_id, file_status, now, now
            ))
            synced_shows += 1

            if not poster_url.startswith("data:image/"):
                show_thumb_tasks.append((show_id, "Primary", "poster_url"))
            if not backdrop_url.startswith("data:image/") and item.get("BackdropImageTags"):
                show_thumb_tasks.append((show_id, "Backdrop/0", "backdrop_url"))

        removed_shows = 0
        if show_items:
            removed_shows = _remove_missing_items(cursor, "shows", "show_id", "jellyfin_item_id", "show", {item["Id"] for item in show_items})
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
            "removed_shows": removed_shows,
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
        cursor.execute("SELECT episode_id, file_status, thumbnail_url FROM episodes")
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

            prev = existing_episodes.get(episode_id)
            file_status = "available"
            thumbnail_url = ""

            if prev:
                file_status = prev["file_status"]
                thumbnail_url = prev["thumbnail_url"] or ""
            else:
                new_episodes += 1
                thumbnail_url = jellyfin.get_image_url(episode_id, "Primary", 480, 75)

            cursor.execute("""
                INSERT INTO episodes (
                    episode_id, show_id, show_name, season_id, season_name,
                    season_number, episode_number, title, overview, premiere_date,
                    duration, thumbnail_url, file_path, jellyfin_item_id,
                    file_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    file_status = excluded.file_status,
                    updated_at = excluded.updated_at
            """, (
                episode_id, show_id, show_name, season_id, season_name,
                season_number, episode_number, title, overview, premiere_date,
                duration, thumbnail_url, file_path, episode_id,
                file_status, now, now
            ))
            synced_episodes += 1

            if not thumbnail_url.startswith("data:image/"):
                episode_thumb_tasks.append(episode_id)

        removed_episodes = 0
        if episode_items:
            removed_episodes = _remove_missing_items(cursor, "episodes", "episode_id", "jellyfin_item_id", "episode", {item["Id"] for item in episode_items})
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
        f"Shows & Episodes scan complete: {synced_shows} series ({new_shows} new, {removed_shows} removed), "
        f"{synced_episodes} episodes ({new_episodes} new, {removed_episodes} removed), {cached_show_thumbs + cached_ep_thumbs} Base64 thumbnails cached."
    )
    return {
        "synced_shows": synced_shows,
        "new_shows": new_shows,
        "removed_shows": removed_shows,
        "synced_episodes": synced_episodes,
        "new_episodes": new_episodes,
        "removed_episodes": removed_episodes,
        "cached_show_thumbs": cached_show_thumbs + cached_ep_thumbs
    }
