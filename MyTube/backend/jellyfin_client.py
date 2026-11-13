import logging
import re
import requests
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode
from backend.config import (
    JELLYFIN_URL,
    JELLYFIN_API_KEY,
    JELLYFIN_USER_ID,
    JELLYFIN_LIBRARY_ID,
    JELLYFIN_MOVIES_LIBRARY_ID,
    JELLYFIN_SHOWS_LIBRARY_ID,
)

logger = logging.getLogger("mytube.jellyfin")

class JellyfinClient:
    def __init__(
        self,
        base_url: str = JELLYFIN_URL,
        api_key: str = JELLYFIN_API_KEY,
        user_id: str = JELLYFIN_USER_ID,
        library_id: str = JELLYFIN_LIBRARY_ID,
        movies_library_id: str = JELLYFIN_MOVIES_LIBRARY_ID,
        shows_library_id: str = JELLYFIN_SHOWS_LIBRARY_ID,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.library_id = library_id
        self.movies_library_id = movies_library_id
        self.shows_library_id = shows_library_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f'MediaBrowser Token="{self.api_key}"',
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def get_proxy_url(self, item_id: str, resource: str, params: Optional[Dict[str, Any]] = None) -> str:
        url = f"/api/jellyfin/{item_id}/{resource}"
        if params:
            url += f"?{urlencode(params)}"
        return url

    def proxy_media_request(self, item_id: str, resource: str, params: Dict[str, str], range_header: Optional[str]):
        endpoint = "Items" if resource.startswith("Images/") else "Videos"
        url = f"{self.base_url}/{endpoint}/{item_id}/{resource}"
        safe_params = {
            key: value
            for key, value in params.items()
            if key.casefold() not in {"api_key", "token", "access_token"}
        }
        headers = {"Accept-Encoding": "identity"}
        if range_header:
            headers["Range"] = range_header
        return self.session.get(url, params=safe_params, headers=headers, stream=True, timeout=(10, None))

    def get_system_info(self) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}/System/Info", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_library_items(self) -> List[Dict[str, Any]]:
        """Fetch all video items from the YouTube library."""
        params = {
            "ParentId": self.library_id,
            "Recursive": "true",
            "IncludeItemTypes": "Video",
            "Fields": "Path,Overview,PremiereDate,ProductionYear,DateCreated,MediaSources,MediaStreams,UserData,RunTimeTicks,Genres,OfficialRating",
            "Limit": 5000,
        }
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("Items", [])

    def get_movie_items(self) -> List[Dict[str, Any]]:
        """Fetch all movies from the Movies library."""
        params = {
            "ParentId": self.movies_library_id,
            "Recursive": "true",
            "IncludeItemTypes": "Movie",
            "Fields": "Path,Overview,PremiereDate,ProductionYear,DateCreated,MediaSources,MediaStreams,UserData,RunTimeTicks,Genres,OfficialRating,CommunityRating,ImageTags,BackdropImageTags",
            "Limit": 5000,
        }
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("Items", [])

    def get_show_items(self) -> List[Dict[str, Any]]:
        """Fetch all series from the Shows library."""
        params = {
            "ParentId": self.shows_library_id,
            "IncludeItemTypes": "Series",
            "Fields": "Path,Overview,PremiereDate,ProductionYear,DateCreated,MediaSources,UserData,RunTimeTicks,Genres,OfficialRating,CommunityRating,Status,ImageTags,BackdropImageTags",
            "Limit": 5000,
        }
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("Items", [])

    def get_episode_items(self, show_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all episodes from the Shows library (optionally filtered by series ID)."""
        parent_id = show_id if show_id else self.shows_library_id
        params = {
            "ParentId": parent_id,
            "Recursive": "true",
            "IncludeItemTypes": "Episode",
            "Fields": "Path,Overview,PremiereDate,ProductionYear,DateCreated,MediaSources,MediaStreams,UserData,RunTimeTicks,SeasonId,SeasonName,SeriesId,SeriesName,IndexNumber,ParentIndexNumber,ImageTags",
            "Limit": 10000,
        }
        url = f"{self.base_url}/Users/{self.user_id}/Items"
        resp = self.session.get(url, params=params, timeout=25)
        resp.raise_for_status()
        return resp.json().get("Items", [])

    def get_item_details(self, item_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/Users/{self.user_id}/Items/{item_id}"
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_playback_info(self, item_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/Items/{item_id}/PlaybackInfo"
        payload = {
            "UserId": self.user_id,
            "AutoOpenLiveStream": False,
            "EnableDirectPlay": True,
            "EnableDirectStream": True,
            "EnableTranscoding": True,
        }
        resp = self.session.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_stream_url(self, item_id: str, audio_stream_index: Optional[int] = None) -> str:
        """Return a MyTube-proxied direct stream URL."""
        params = {"Static": "true"}
        if audio_stream_index is not None:
            params["AudioStreamIndex"] = str(audio_stream_index)
        return self.get_proxy_url(item_id, "stream.mkv", params)

    def get_hls_url(
        self,
        item_id: str,
        audio_stream_index: Optional[int] = None,
        max_width: int = 1920,
        max_height: int = 1080,
        video_bitrate: int = 10000000,
        audio_codec: str = "aac",
        allow_video_copy: bool = True,
    ) -> str:
        """Return HLS fMP4 master stream URL with resolution, bitrate, and audio transcode controls."""
        a_idx = audio_stream_index if audio_stream_index is not None else 1
        video_copy_val = "true" if allow_video_copy else "false"
        max_streaming_bitrate = video_bitrate + 1500000
        params = {
            "MediaSourceId": item_id,
            "DeviceId": "mytube_web",
            "PlaySessionId": f"mytube_{item_id}_a{a_idx}_q{max_height}",
            "VideoCodec": "h264",
            "AudioCodec": audio_codec,
            "AllowVideoStreamCopy": video_copy_val,
            "AudioStreamIndex": str(a_idx),
            "MaxWidth": str(max_width),
            "MaxHeight": str(max_height),
            "VideoBitRate": str(video_bitrate),
            "AudioBitRate": "192000",
            "MaxStreamingBitrate": str(max_streaming_bitrate),
            "SegmentContainer": "mp4",
        }
        return self.get_proxy_url(item_id, "master.m3u8", params)

    def get_hls_ios_url(self, item_id: str, audio_stream_index: Optional[int] = None) -> str:
        """Return H.264 + AAC HLS master stream URL for iPads/iPhones without hardware AV1 decoding."""
        a_idx = audio_stream_index if audio_stream_index is not None else 1
        params = {
            "MediaSourceId": item_id,
            "DeviceId": "mytube_ios",
            "PlaySessionId": f"mytube_ios_{item_id}_a{a_idx}",
            "VideoCodec": "h264",
            "AudioCodec": "aac",
            "AudioStreamIndex": str(a_idx),
            "MaxWidth": "1280",
            "VideoBitRate": "2500000",
            "AudioBitRate": "128000",
            "MaxStreamingBitrate": "3000000",
            "TranscodingMaxAudioChannels": "2",
            "SegmentContainer": "ts",
        }
        return self.get_proxy_url(item_id, "master.m3u8", params)

    def stop_active_encodings(self, device_id: str = "mytube_web") -> None:
        """Stop any active ffmpeg remux/transcode sessions on Jellyfin."""
        try:
            self.session.delete(
                f"{self.base_url}/Videos/ActiveEncodings",
                params={"DeviceId": device_id},
                timeout=3,
            )
        except Exception:
            pass

    def get_subtitle_url(self, item_id: str, subtitle_index: int) -> str:
        """Return WebVTT subtitle URL pointing to Jellyfin."""
        return self.get_proxy_url(item_id, f"{item_id}/Subtitles/{subtitle_index}/Stream.vtt")

    def get_clean_subtitle_vtt(self, item_id: str, subtitle_index: int) -> str:
        """Fetch WebVTT from Jellyfin and strip YouTube Region tags for clean rendering."""
        url = f"{self.base_url}/Videos/{item_id}/{item_id}/Subtitles/{subtitle_index}/Stream.vtt"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig", errors="replace")
        # Strip 'Region: ...' header lines and inline 'region:subtitle ...' cue settings
        lines = []
        for line in text.splitlines():
            if line.startswith("Region:"):
                continue
            if "-->" in line:
                line = re.sub(r"\s+region:\S+", "", line)
                line = re.sub(r"\s+line:\S+", "", line)
            lines.append(line)
        return "\n".join(lines)

    def get_image_url(self, item_id: str, image_type: str = "Primary", fill_width: int = 400, quality: int = 80) -> str:
        """Return image artwork URL pointing to Jellyfin."""
        return self.get_proxy_url(
            item_id,
            f"Images/{image_type}",
            {"fillWidth": str(fill_width), "quality": str(quality)},
        )

    def get_image_bytes(self, item_id: str, image_type: str = "Primary", fill_width: int = 400, quality: int = 80) -> Optional[bytes]:
        """Fetch raw image bytes from Jellyfin."""
        url = f"{self.base_url}/Items/{item_id}/Images/{image_type}"
        try:
            resp = self.session.get(url, params={"fillWidth": fill_width, "quality": quality}, timeout=10)
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception:
            pass
        return None

    def report_progress(self, item_id: str, position_ticks: int) -> bool:
        url = f"{self.base_url}/Users/{self.user_id}/PlayingItems/{item_id}/Progress"
        params = {"PositionTicks": position_ticks}
        try:
            resp = self.session.post(url, params=params, timeout=5)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Failed to report progress to Jellyfin: {e}")
            return False

    def mark_played(self, item_id: str) -> bool:
        url = f"{self.base_url}/Users/{self.user_id}/PlayedItems/{item_id}"
        try:
            resp = self.session.post(url, timeout=5)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Failed to mark played in Jellyfin: {e}")
            return False

    def mark_unplayed(self, item_id: str) -> bool:
        url = f"{self.base_url}/Users/{self.user_id}/PlayedItems/{item_id}"
        try:
            resp = self.session.delete(url, timeout=5)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Failed to mark unplayed in Jellyfin: {e}")
            return False

    def delete_item(self, item_id: str) -> bool:
        """Permanently delete item and its physical media files on the server."""
        url = f"{self.base_url}/Items/{item_id}"
        try:
            resp = self.session.delete(url, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Failed to delete item {item_id} from Jellyfin: {e}")
            return False

    def trigger_refresh(self) -> bool:
        url = f"{self.base_url}/Library/Refresh"
        try:
            resp = self.session.post(url, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Failed to trigger Jellyfin library refresh: {e}")
            return False

# Global instance
jellyfin = JellyfinClient()
