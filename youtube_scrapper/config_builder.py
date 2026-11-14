from __future__ import annotations

import copy
import json
import os
import re
import shutil
from importlib.util import find_spec
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml


APP_DIR = Path(__file__).resolve().parent
CHANNELS_FILE = APP_DIR / "channels.json"
BASE_CONFIG_FILE = APP_DIR / "config.yaml"
RUNTIME_DIR = APP_DIR / ".runtime"
RUNTIME_CONFIG_FILE = RUNTIME_DIR / "config.yaml"
SUBSCRIPTIONS_FILE = RUNTIME_DIR / "subscriptions.yaml"


def get_storage_dir(settings: dict[str, Any]) -> Path:
    if os.environ.get("STORAGE_DIR"):
        return Path(os.environ["STORAGE_DIR"]).expanduser().resolve()

    is_termux = (
        "TERMUX_VERSION" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
        or Path("/data/data/com.termux").exists()
        or Path("/storage/0692F50692F4FACF").exists()
        or os.name != "nt"
    )
    if is_termux:
        return Path("/storage/0692F50692F4FACF")

    configured = (settings.get("storage_dir") or "").strip() if settings else ""
    # On PC / Windows, default to local media directory for testing, avoiding external drive
    if configured:
        try:
            target = Path(configured).expanduser().resolve()
            if target.exists() or (target.anchor and Path(target.anchor).exists()):
                return target
        except Exception:
            pass

    return (APP_DIR / "media").resolve()


def parse_language_list(value: Any) -> list[str]:
    """Parse a language setting into a list of cleaned language codes."""
    if not value:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = re.split(r"[,;\s]+", value.strip())
    else:
        items = [str(value)]

    result: list[str] = []
    for item in items:
        cleaned = item.strip().lower()
        if cleaned and cleaned not in {"none", "default", "off", "no"}:
            if cleaned not in result:
                result.append(cleaned)
    return result


def find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                user_path, _ = winreg.QueryValueEx(key, "Path")
                found = shutil.which(name, path=user_path)
                if found:
                    return found
        except Exception:
            pass
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            packages_dir = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
            if packages_dir.is_dir():
                matches = list(packages_dir.glob(f"**/{name}.exe"))
                if matches:
                    return str(matches[0])
    return None


def configured_path(env_name: str, setting: str, settings: dict[str, Any], fallback: Path) -> Path:
    configured = os.environ.get(env_name) or settings.get(setting)
    return Path(configured).expanduser().resolve() if configured else fallback.resolve()


def validate_channels(channels: list[dict[str, Any]]) -> None:
    names: set[str] = set()
    for channel in channels:
        name = str(channel.get("name", "")).strip()
        url = str(channel.get("url", "")).strip()
        if not name or not url:
            raise ValueError("Every enabled subscription needs a name and URL")
        if name.casefold() in names:
            raise ValueError(f"Subscription names must be unique: {name}")
        names.add(name.casefold())
        mode = channel.get("mode", "video")
        if mode not in {"video", "audio"}:
            raise ValueError(f"Unsupported media mode for {name}")
        if mode == "video" and int(channel.get("resolution", 1080)) not in {480, 720, 1080, 1440, 2160}:
            raise ValueError(f"Unsupported resolution for {name}")
        if mode == "audio" and channel.get("audio_format", "m4a").lower() not in {"mp3", "flac", "m4a"}:
            raise ValueError(f"Unsupported audio format for {name}")
        for key in ("min_views", "min_duration_minutes", "date_days"):
            if int(channel.get(key, 0)) < 0:
                raise ValueError(f"{key} cannot be negative for {name}")
        title_contains = channel.get("title_contains", "")
        if not isinstance(title_contains, str):
            raise ValueError(f"title_contains must be text for {name}")
        for key in ("voice_language", "subtitle_language"):
            val = channel.get(key, "")
            if val is not None and not isinstance(val, (str, list)):
                raise ValueError(f"{key} must be text for {name}")


def build_runtime_files(storage_dir: Path, history_dir: Path, channels: list[dict[str, Any]]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "working").mkdir(exist_ok=True)
    (RUNTIME_DIR / "locks").mkdir(exist_ok=True)
    (RUNTIME_DIR / "logs").mkdir(exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    base_config = yaml.safe_load(BASE_CONFIG_FILE.read_text(encoding="utf-8")) or {}
    config = copy.deepcopy(base_config)
    configuration = config.setdefault("configuration", {})
    ffmpeg_path = find_executable("ffmpeg")
    ffprobe_path = find_executable("ffprobe")
    if ffmpeg_path:
        configuration["ffmpeg_path"] = ffmpeg_path
        bin_dir = str(Path(ffmpeg_path).parent)
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    if ffprobe_path:
        configuration["ffprobe_path"] = ffprobe_path
    presets = config.setdefault("presets", {})
    subscriptions: dict[str, Any] = {}

    for index, channel in enumerate(channels, start=1):
        name = str(channel["name"]).strip()
        source_url = str(channel["url"]).strip()
        is_playlist = bool(parse_qs(urlparse(source_url).query).get("list"))
        mode = str(channel.get("mode", "video")).lower()
        preset_name = f"Managed subscription {index:03d}"
        base_preset = "YouTube Audio Base" if mode == "audio" else "YouTube Video Base"
        parents = [base_preset, "Filter Duration"]
        if mode == "video":
            resolution = int(channel.get("resolution", 1080))
            if resolution != 1080:
                parents.append(f"Max {resolution}p")
        else:
            parents.append("Max Audio Quality")

        overrides: dict[str, Any] = {
            "filter_duration_min_s": int(channel.get("min_duration_minutes", 5)) * 60,
        }
        if mode == "video":
            overrides.update({
                "tv_show_directory": str(storage_dir / "yt_video"),
                "tv_show_name": name,
            })
        else:
            overrides["music_directory"] = str(storage_dir / "yt_music")

        preset: dict[str, Any] = {
            "preset": parents,
            "overrides": overrides,
            "date_range": {
                "after": f"now-{int(channel.get('date_days', 0))}days" if int(channel.get("date_days", 0)) else "19000101",
                "before": "now+1day",
                "breaks": not is_playlist,
                "type": "upload_date",
            },
            "ytdl_options": {
                # "download_archive": str(history_dir / "yt-dlp-download-archive.txt"),
                "break_on_existing": True,
                "retries": 10,
                "socket_timeout": 30,
                "lazy_playlist": int(channel.get("date_days", 0)) > 0,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web_safari", "web_embedded", "-tv_downgraded"],
                    },
                    "youtubetab": {
                        "approximate_date": [""],
                    },
                },
            },
            "output_options": {"maintain_download_archive": True},
        }
        cookie_file = APP_DIR / "www.youtube.com_cookies.txt"
        if cookie_file.is_file():
            preset["ytdl_options"]["cookiefile"] = str(cookie_file)
        if find_spec("curl_cffi") is not None:
            preset["ytdl_options"]["impersonate"] = "chrome"
        filters = []
        min_views = int(channel.get("min_views", 0))
        if min_views > 0:
            filters.append(f"view_count >= {min_views}")
        title_contains = str(channel.get("title_contains", "")).strip()
        if title_contains:
            phrases = [re.escape(p.strip()) for p in title_contains.split("|") if p.strip()]
            if len(phrases) == 1:
                filters.append(f"title ~= (?i){phrases[0]}")
            elif len(phrases) > 1:
                filters.append(f"title ~= (?i)({'|'.join(phrases)})")
        if filters:
            preset["match_filters"] = {"filters": [" & ".join(filters)]}
        voice_langs = parse_language_list(channel.get("voice_language"))
        sub_langs = parse_language_list(channel.get("subtitle_language"))

        if mode == "video":
            if not voice_langs:
                preset["format"] = f"bv*[height<={resolution}]+ba/b[height<={resolution}]"
            elif len(voice_langs) == 1:
                lang = voice_langs[0]
                preset["format"] = (
                    f"bv*[height<={resolution}]+ba[language^={lang}]/"
                    f"bv*[height<={resolution}]+ba/b[height<={resolution}]"
                )
            else:
                multi_ba = "+".join(f"ba[language^={lang}]" for lang in voice_langs)
                single_fallbacks = "/".join(f"bv*[height<={resolution}]+ba[language^={lang}]" for lang in voice_langs)
                preset["format"] = (
                    f"bv*[height<={resolution}]+{multi_ba}/"
                    f"{single_fallbacks}/"
                    f"bv*[height<={resolution}]+ba/b[height<={resolution}]"
                )
                preset["ytdl_options"]["allow_multiple_audio_streams"] = True

            preset["ytdl_options"].update({
                "merge_output_format": "mkv",
                "remuxvideo": "mkv",
            })
            if sub_langs:
                preset["subtitles"] = {
                    "languages": sub_langs,
                    "subtitles_type": "srt",
                    "embed_subtitles": True,
                    "allow_auto_generated_subtitles": True,
                }
        else:
            if voice_langs:
                lang = voice_langs[0]
                preset["format"] = f"ba[language^={lang}]/ba"
            preset["audio_extract"] = {
                "codec": str(channel.get("audio_format", "m4a")).lower(),
                "quality": 0,
            }

        presets[preset_name] = preset
        subscriptions[preset_name] = {name: source_url}

    RUNTIME_CONFIG_FILE.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    SUBSCRIPTIONS_FILE.write_text(yaml.safe_dump(subscriptions, sort_keys=False, allow_unicode=True), encoding="utf-8")


def generate_runtime_files(data: dict[str, Any] | None = None) -> tuple[Path, Path]:
    if data is None:
        data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    settings = data.get("settings", {})
    channels = [channel for channel in data.get("channels", []) if channel.get("enabled", True)]
    validate_channels(channels)
    storage_dir = get_storage_dir(settings)
    print(f"Using storage directory: {storage_dir}")
    history_dir = configured_path("HISTORY_DIR", "history_dir", settings, APP_DIR / "history")
    build_runtime_files(storage_dir, history_dir, channels)
    return RUNTIME_CONFIG_FILE, SUBSCRIPTIONS_FILE


if __name__ == "__main__":
    config_path, subscriptions_path = generate_runtime_files()
    print(f"Generated {config_path}")
    print(f"Generated {subscriptions_path}")