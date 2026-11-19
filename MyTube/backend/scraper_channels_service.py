"""Lists, adds, updates, and removes channels in the youtube_scrapper channels.json.

The scraper re-reads channels.json on every run, so changes made here apply to its next run.
Entries use the same fields, validation, and uniqueness rules as youtube_scrapper/ui.py.
A channel's name is its folder name under yt_video, so renaming a channel moves its folder.
"""
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import SCRAPER_CHANNELS_PATH

_write_lock = threading.Lock()

TEXT_FIELDS = ("name", "url", "voice_language", "subtitle_language", "title_contains")


class ScraperChannelError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(SCRAPER_CHANNELS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ScraperChannelError(503, f"Scraper config not found at {SCRAPER_CHANNELS_PATH}")
    except (OSError, json.JSONDecodeError) as exc:
        raise ScraperChannelError(500, f"Could not read scraper config: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("channels"), list):
        raise ScraperChannelError(500, "Scraper config has no channels list")
    return data


def _save(data: Dict[str, Any]) -> None:
    path = SCRAPER_CHANNELS_PATH
    try:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            shutil.copymode(path, tmp_name)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ScraperChannelError(500, f"Could not write scraper config: {exc}")


def _normalize(entry: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(entry)
    for key in TEXT_FIELDS:
        cleaned[key] = str(cleaned.get(key, "")).strip()
    if not cleaned["name"] or not cleaned["url"]:
        raise ScraperChannelError(400, "Name and URL are required")
    return cleaned


def _find_index(channels: List[Any], name: str) -> Optional[int]:
    key = name.casefold()
    for index, channel in enumerate(channels):
        if isinstance(channel, dict) and str(channel.get("name", "")).strip().casefold() == key:
            return index
    return None


class ScraperChannelService:
    @staticmethod
    def list_channels() -> List[Dict[str, Any]]:
        return _load()["channels"]

    @staticmethod
    def add_channel(entry: Dict[str, Any]) -> Dict[str, Any]:
        with _write_lock:
            entry = _normalize(entry)
            data = _load()
            if _find_index(data["channels"], entry["name"]) is not None:
                raise ScraperChannelError(409, "Another scraper channel already uses that name")
            data["channels"].append(entry)
            _save(data)
        return entry

    @staticmethod
    def update_channel(original_name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        with _write_lock:
            data = _load()
            index = _find_index(data["channels"], original_name)
            if index is None:
                raise ScraperChannelError(404, "Channel not found in scraper config")
            entry = _normalize(entry)
            clash = _find_index(data["channels"], entry["name"])
            if clash is not None and clash != index:
                raise ScraperChannelError(409, "Another scraper channel already uses that name")
            data["channels"][index] = entry
            _save(data)
        return entry

    @staticmethod
    def delete_channel(name: str) -> None:
        with _write_lock:
            data = _load()
            index = _find_index(data["channels"], name)
            if index is None:
                raise ScraperChannelError(404, "Channel not found in scraper config")
            del data["channels"][index]
            _save(data)
