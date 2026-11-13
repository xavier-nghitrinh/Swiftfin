import json
import logging
from typing import Dict, Any, Optional, List
from backend.config import (
    REMAINING_SECONDS_THRESHOLD,
)
from backend.database import get_db, now_iso, find_media_item
from backend.jellyfin_client import jellyfin

logger = logging.getLogger("mytube.playback")

class PlaybackService:
    @staticmethod
    def get_playback_data(
        video_id: str,
        audio_stream_index: Optional[int] = None,
        quality: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve stream URL, quality choices, tracks, and resume state for client playback across YouTube, Movies, and Episodes."""
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return None

        item_id = media["jellyfin_item_id"]
        audio_meta_labels: List[str] = []
        raw_audio_meta = media.get("audio_meta") or ""
        if raw_audio_meta:
            try:
                audio_meta_labels = json.loads(raw_audio_meta)
            except Exception:
                pass
        
        audio_tracks = []
        subtitle_tracks = []
        video_stream = {}
        try:
            jf_item = jellyfin.get_item_details(item_id)
            streams = jf_item.get("MediaStreams", [])
            audio_pos = 0
            for s in streams:
                stype = s.get("Type")
                sindex = s.get("Index")
                lang = s.get("Language", "und")
                title = s.get("DisplayTitle", lang)
                codec = s.get("Codec", "")
                
                if stype == "Video" and not video_stream:
                    video_stream = s
                elif stype == "Audio":
                    if audio_pos < len(audio_meta_labels):
                        custom_label = audio_meta_labels[audio_pos]
                        display_label = f"Track {audio_pos + 1}: {custom_label}"
                    else:
                        display_label = f"Track {audio_pos + 1}: {title}"
                    audio_tracks.append({
                        "index": sindex,
                        "language": lang,
                        "title": display_label,
                        "codec": codec,
                        "is_default": audio_pos == 0
                    })
                    audio_pos += 1
                elif stype == "Subtitle":
                    subtitle_tracks.append({
                        "index": sindex,
                        "language": lang,
                        "title": s.get("Title") or title,
                        "codec": codec,
                        "url": f"/api/videos/{video_id}/subtitles/{sindex}.vtt",
                        "direct_url": jellyfin.get_subtitle_url(item_id, sindex),
                        "is_default": s.get("IsDefault", False)
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch streams from Jellyfin for {item_id}: {e}")

        first_audio_index = audio_tracks[0]["index"] if audio_tracks else 1
        target_audio_index = audio_stream_index if audio_stream_index is not None else first_audio_index
        use_hls_for_audio = (audio_stream_index is not None and audio_stream_index != first_audio_index)

        # Inspect video properties
        video_width = video_stream.get("Width") or 0
        video_height = video_stream.get("Height") or 0
        video_codec = (video_stream.get("Codec") or "").lower()
        is_over_1080p = (video_width > 1920 or video_height > 1080)
        is_hevc = ("hevc" in video_codec or "h265" in video_codec)

        # Inspect target audio codec compatibility
        target_audio = next((a for a in audio_tracks if a["index"] == target_audio_index), None)
        target_audio_codec = (target_audio.get("codec") or "").lower() if target_audio else ""
        unsupported_audio_codecs = {"truehd", "eac3", "dts", "dtshd", "dca", "mlp"}
        needs_audio_transcode = target_audio_codec in unsupported_audio_codecs

        # Quality presets
        quality_map = {
            "1080p": {"width": 1920, "height": 1080, "bitrate": 10000000, "label": "1080p (10 Mbps)"},
            "720p": {"width": 1280, "height": 720, "bitrate": 4000000, "label": "720p (4 Mbps)"},
            "480p": {"width": 854, "height": 480, "bitrate": 1500000, "label": "480p (1.5 Mbps)"},
        }

        # Resolve requested quality
        if quality == "direct":
            active_quality = "direct"
            use_hls = False
            q_cfg = quality_map["1080p"]
        elif quality in quality_map:
            active_quality = quality
            use_hls = True
            q_cfg = quality_map[quality]
        else:
            active_quality = "auto"
            q_cfg = quality_map["1080p"]
            # Enforce 1080p HLS + AAC transcode if 4K, HEVC, unsupported audio, or audio track switch
            use_hls = bool(is_over_1080p or is_hevc or needs_audio_transcode or use_hls_for_audio)

        available_qualities = [
            {"id": "auto", "label": "Auto (1080p)", "is_active": active_quality == "auto"},
            {"id": "1080p", "label": "1080p (10 Mbps)", "is_active": active_quality == "1080p"},
            {"id": "720p", "label": "720p (4 Mbps)", "is_active": active_quality == "720p"},
            {"id": "480p", "label": "480p (1.5 Mbps)", "is_active": active_quality == "480p"},
            {"id": "direct", "label": "Original / Direct", "is_active": active_quality == "direct"},
        ]

        # Clean up any previous active ffmpeg encoding sessions before starting a new stream
        jellyfin.stop_active_encodings("mytube_web")
        jellyfin.stop_active_encodings("mytube_ios")

        stream_url = jellyfin.get_stream_url(item_id, audio_stream_index=target_audio_index)
        hls_url = jellyfin.get_hls_url(
            item_id,
            audio_stream_index=target_audio_index,
            max_width=q_cfg["width"],
            max_height=q_cfg["height"],
            video_bitrate=q_cfg["bitrate"],
            audio_codec="aac",
            allow_video_copy=True,
        )
        hls_ios_url = jellyfin.get_hls_ios_url(item_id, audio_stream_index=target_audio_index)

        # Format title and display info based on media type
        if media_type == "movie":
            display_title = media["title"]
            channel_name = str(media.get("release_year") or "Movie")
            channel_id = "movies"
            thumb = media.get("backdrop_url") or media.get("poster_url") or ""
            desc = media.get("overview") or ""
            upload_date = str(media.get("release_year") or "")
        elif media_type == "episode":
            display_title = f"{media['show_name']} - S{media['season_number']}:E{media['episode_number']} {media['title']}"
            channel_name = media["show_name"]
            channel_id = media["show_id"]
            thumb = media.get("thumbnail_url") or ""
            desc = media.get("overview") or ""
            upload_date = media.get("premiere_date") or ""
        else:
            display_title = media["title"]
            channel_name = media["channel_name"]
            channel_id = media.get("channel_id") or ""
            thumb = media.get("thumbnail_url") or ""
            desc = media.get("description") or ""
            upload_date = media.get("upload_date") or ""

        return {
            "video_id": media["video_id"],
            "title": display_title,
            "description": desc,
            "upload_date": upload_date,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "channel_thumbnail_url": media.get("channel_thumbnail_url") or "",
            "duration": media["duration"],
            "playback_position": media["playback_position"],
            "watched": bool(media["watched"]),
            "thumbnail_url": thumb,
            "stream_url": stream_url,
            "hls_url": hls_url,
            "hls_ios_url": hls_ios_url,
            "use_hls": use_hls,
            "current_quality": active_quality,
            "qualities": available_qualities,
            "selected_audio_index": target_audio_index,
            "jellyfin_item_id": item_id,
            "media_type": media_type,
            "audio_tracks": audio_tracks,
            "subtitles": subtitle_tracks,
        }

    @staticmethod
    def get_subtitle_vtt(video_id: str, subtitle_index: int) -> Optional[str]:
        with get_db() as conn:
            cursor = conn.cursor()
            media, _ = find_media_item(cursor, video_id)
            if not media:
                return None
            item_id = media["jellyfin_item_id"]
        try:
            return jellyfin.get_clean_subtitle_vtt(item_id, subtitle_index)
        except Exception as e:
            logger.error(f"Failed to fetch subtitle {subtitle_index} for {video_id}: {e}")
            return None

    @staticmethod
    def update_progress(video_id: str, position_seconds: float, duration_seconds: float) -> Dict[str, Any]:
        """Update playback position and auto-mark watched (>95% for movies/shows, <30s or >=98% for youtube)."""
        now = now_iso()
        remaining_seconds = duration_seconds - position_seconds if duration_seconds > 0 else 999.0
        
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return {"status": "error", "message": "Media item not found"}
                
            item_id = media["jellyfin_item_id"]
            already_watched = bool(media["watched"])

            # Rule: > 95% duration for movies and shows; < 30s remaining or >= 98% for YouTube
            if media_type in ("movie", "episode"):
                should_mark_watched = (duration_seconds > 0 and position_seconds >= duration_seconds * 0.95)
            else:
                should_mark_watched = (
                    (duration_seconds > 30 and remaining_seconds <= REMAINING_SECONDS_THRESHOLD)
                    or (duration_seconds > 0 and position_seconds >= duration_seconds * 0.98)
                )

            # Update the appropriate table
            if media_type == "movie":
                table_name = "movies"
                id_col = "movie_id"
            elif media_type == "episode":
                table_name = "episodes"
                id_col = "episode_id"
            else:
                table_name = "videos"
                id_col = "video_id"

            if should_mark_watched:
                cursor.execute(f"""
                    UPDATE {table_name} 
                    SET watched = 1, 
                        watched_at = COALESCE(watched_at, ?), 
                        playback_position = ?, 
                        updated_at = ?
                    WHERE {id_col} = ?
                """, (now, position_seconds, now, video_id))
            else:
                cursor.execute(f"""
                    UPDATE {table_name} 
                    SET playback_position = ?, 
                        updated_at = ?
                    WHERE {id_col} = ?
                """, (position_seconds, now, video_id))
                
            cursor.execute("""
                INSERT INTO playback_sessions (video_id, position_seconds, duration_seconds, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    position_seconds = excluded.position_seconds,
                    duration_seconds = excluded.duration_seconds,
                    updated_at = excluded.updated_at
            """, (video_id, position_seconds, duration_seconds, now))
            
            conn.commit()

        if should_mark_watched and not already_watched:
            jellyfin.mark_played(item_id)
        else:
            position_ticks = int(position_seconds * 10000000)
            jellyfin.report_progress(item_id, position_ticks)

        return {
            "status": "ok",
            "video_id": video_id,
            "media_type": media_type,
            "position_seconds": position_seconds,
            "watched": should_mark_watched or already_watched,
            "remaining_seconds": remaining_seconds
        }

    @staticmethod
    def mark_watched(video_id: str) -> bool:
        now = now_iso()
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return False
            item_id = media["jellyfin_item_id"]

            if media_type == "movie":
                cursor.execute("UPDATE movies SET watched = 1, watched_at = ?, updated_at = ? WHERE movie_id = ?", (now, now, video_id))
            elif media_type == "episode":
                cursor.execute("UPDATE episodes SET watched = 1, watched_at = ?, updated_at = ? WHERE episode_id = ?", (now, now, video_id))
            else:
                cursor.execute("UPDATE videos SET watched = 1, watched_at = ?, updated_at = ? WHERE video_id = ?", (now, now, video_id))
            conn.commit()
            
        jellyfin.mark_played(item_id)
        return True

    @staticmethod
    def mark_unwatched(video_id: str) -> bool:
        now = now_iso()
        with get_db() as conn:
            cursor = conn.cursor()
            media, media_type = find_media_item(cursor, video_id)
            if not media:
                return False
            item_id = media["jellyfin_item_id"]

            if media_type == "movie":
                cursor.execute("UPDATE movies SET watched = 0, watched_at = NULL, playback_position = 0, updated_at = ? WHERE movie_id = ?", (now, video_id))
            elif media_type == "episode":
                cursor.execute("UPDATE episodes SET watched = 0, watched_at = NULL, playback_position = 0, updated_at = ? WHERE episode_id = ?", (now, video_id))
            else:
                cursor.execute("UPDATE videos SET watched = 0, watched_at = NULL, playback_position = 0, updated_at = ? WHERE video_id = ?", (now, video_id))
            cursor.execute("DELETE FROM playback_sessions WHERE video_id = ?", (video_id,))
            conn.commit()
            
        jellyfin.mark_unplayed(item_id)
        return True
