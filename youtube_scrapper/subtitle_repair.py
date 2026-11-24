from __future__ import annotations

import datetime
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp
import yaml
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError


LOGGER = logging.getLogger("youtube_scrapper.subtitle_repair")
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".webm", ".m4v"}
SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass", ".ssa", ".sub"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def has_subtitle(video: Path, ffprobe: str) -> bool:
    for path in video.parent.iterdir():
        if (path.is_file() and path.name.startswith(video.stem + ".")
                and path.suffix.lower() in SUBTITLE_EXTENSIONS and path.stat().st_size > 0):
            return True
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "s", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(video)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return bool(result.stdout.strip())


def download_subtitle(video_id: str, video: Path, options: dict[str, Any], languages: list[str]) -> bool:
    with tempfile.TemporaryDirectory(prefix="mytube-subtitle-") as temp_dir:
        params = {
            key: options[key]
            for key in ("cookiefile", "extractor_args", "js_runtimes", "socket_timeout", "retries",
                        "impersonate")
            if key in options
        }
        if isinstance(params.get("impersonate"), str):
            params["impersonate"] = ImpersonateTarget.from_str(params["impersonate"])
        params.update({
            "outtmpl": str(Path(temp_dir) / "%(id)s.%(ext)s"),
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": languages,
            "subtitlesformat": "vtt",
            "sleep_interval_subtitles": 5.367,
            "ignoreerrors": True,
            "noplaylist": True,
            "logger": LOGGER,
        })
        try:
            with yt_dlp.YoutubeDL(params) as downloader:
                downloader.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
        except DownloadError as exc:
            LOGGER.warning("Subtitle repair %s: download failed: %s", video_id, exc)

        for language in languages:
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", language):
                LOGGER.warning("Subtitle repair %s: invalid language %r", video_id, language)
                continue
            downloaded = Path(temp_dir) / f"{video_id}.{language}.vtt"
            if not downloaded.is_file():
                continue
            data = downloaded.read_bytes()
            if not data.lstrip(b"\xef\xbb\xbf").startswith(b"WEBVTT") or b"-->" not in data:
                LOGGER.warning("Subtitle repair %s: invalid or empty %s subtitle", video_id, language)
                continue
            target = video.with_name(f"{video.stem}.{language}.vtt")
            try:
                with target.open("xb") as output:
                    try:
                        output.write(data)
                    except OSError:
                        target.unlink(missing_ok=True)
                        raise
            except FileExistsError:
                LOGGER.warning("Subtitle repair %s: not overwriting %s", video_id, target)
                continue
            LOGGER.info("Subtitle repair %s: added %s", video_id, target.name)
            return True
    LOGGER.info("Subtitle repair %s: no usable requested subtitle; will retry next run", video_id)
    return False


def repair_subtitles(config_file: Path, subscriptions_file: Path) -> int:
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    subscriptions = yaml.safe_load(subscriptions_file.read_text(encoding="utf-8"))
    ffprobe = config.get("configuration", {}).get("ffprobe_path") or shutil.which("ffprobe")
    if not ffprobe:
        LOGGER.error("Subtitle repair skipped: ffprobe is unavailable")
        return 0

    today = datetime.datetime.now(datetime.timezone.utc).date()
    earliest = today - datetime.timedelta(days=2)
    checked = attempted = fixed = errors = 0
    for preset_name, channels in subscriptions.items():
        preset = config["presets"][preset_name]
        languages = preset.get("subtitles", {}).get("languages", [])
        if not languages or "tv_show_directory" not in preset.get("overrides", {}):
            continue
        options = preset.get("ytdl_options", {})
        for channel in channels:
            folder = Path(preset["overrides"]["tv_show_directory"]) / preset["overrides"]["tv_show_name"]
            archive = folder / f".ytdl-sub-{channel}-download-archive.json"
            if not archive.is_file():
                LOGGER.warning("Subtitle repair: archive missing for %s", channel)
                continue
            try:
                entries = json.loads(archive.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                LOGGER.error("Subtitle repair: cannot read archive for %s: %s", channel, exc)
                errors += 1
                continue
            for video_id, entry in entries.items():
                try:
                    upload_date = datetime.date.fromisoformat(entry["upload_date"])
                    if not earliest <= upload_date <= today:
                        continue
                    if not VIDEO_ID.fullmatch(video_id):
                        raise ValueError("invalid YouTube video ID")
                    video_files = [name for name in entry["file_names"] if Path(name).suffix.lower() in VIDEO_EXTENSIONS]
                    if len(video_files) != 1:
                        raise ValueError("expected exactly one archived video file")
                    video = (folder / video_files[0]).resolve()
                    if not video.is_relative_to(folder.resolve()):
                        raise ValueError("archive video path is outside the channel folder")
                    if not video.is_file():
                        LOGGER.warning("Subtitle repair %s: archived video is missing", video_id)
                        errors += 1
                        continue
                    checked += 1
                    if has_subtitle(video, ffprobe):
                        continue
                    attempted += 1
                    LOGGER.info("Subtitle repair %s: attempting %s", video_id, ", ".join(languages))
                    if download_subtitle(video_id, video, options, languages):
                        fixed += 1
                except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
                    errors += 1
                    LOGGER.warning("Subtitle repair %s: could not check or repair: %s", video_id, exc)
    LOGGER.info("Subtitle repair summary: checked=%d attempted=%d fixed=%d not_fixed=%d errors=%d",
                checked, attempted, fixed, attempted - fixed, errors)
    return fixed
