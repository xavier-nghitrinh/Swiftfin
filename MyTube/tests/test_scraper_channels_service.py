import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.scraper_channels_service as scraper_channels
from backend.scraper_channels_service import ScraperChannelError, ScraperChannelService


def _entry(name, url="https://www.youtube.com/@example"):
    return {"name": name, "url": url, "mode": "video", "resolution": 1080, "enabled": True}


@pytest.fixture
def channels_file(tmp_path, monkeypatch):
    path = tmp_path / "channels.json"
    path.write_text(json.dumps({
        "settings": {"storage_dir": "/data", "history_dir": "/history"},
        "channels": [_entry("Other", "https://www.youtube.com/@other")],
    }), encoding="utf-8")
    monkeypatch.setattr(scraper_channels, "SCRAPER_CHANNELS_PATH", path)
    return path


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _names(path):
    return [c["name"] for c in _read(path)["channels"]]


def test_add_appends_entry_and_keeps_settings(channels_file):
    ScraperChannelService.add_channel(_entry("  New Channel  ", "  https://www.youtube.com/@new  "))

    data = _read(channels_file)
    assert data["settings"] == {"storage_dir": "/data", "history_dir": "/history"}
    assert data["channels"][-1]["name"] == "New Channel"
    assert data["channels"][-1]["url"] == "https://www.youtube.com/@new"


def test_add_rejects_duplicate_name_case_insensitively(channels_file):
    with pytest.raises(ScraperChannelError) as exc:
        ScraperChannelService.add_channel(_entry("other"))

    assert exc.value.status_code == 409
    assert _names(channels_file) == ["Other"]


def test_add_rejects_blank_name_or_url(channels_file):
    with pytest.raises(ScraperChannelError) as exc:
        ScraperChannelService.add_channel(_entry("   "))

    assert exc.value.status_code == 400
    assert _names(channels_file) == ["Other"]


def test_update_renames_and_replaces_fields(channels_file):
    ScraperChannelService.update_channel("Other", {**_entry("Renamed"), "mode": "audio", "enabled": False})

    channel = _read(channels_file)["channels"][0]
    assert channel["name"] == "Renamed"
    assert channel["mode"] == "audio"
    assert channel["enabled"] is False


def test_update_rejects_name_used_by_another_channel(channels_file):
    ScraperChannelService.add_channel(_entry("Second"))

    with pytest.raises(ScraperChannelError) as exc:
        ScraperChannelService.update_channel("Other", _entry("second"))

    assert exc.value.status_code == 409
    assert _names(channels_file) == ["Other", "Second"]


def test_update_missing_channel_is_not_found(channels_file):
    with pytest.raises(ScraperChannelError) as exc:
        ScraperChannelService.update_channel("Missing", _entry("Missing"))

    assert exc.value.status_code == 404


def test_delete_removes_only_named_channel(channels_file):
    ScraperChannelService.add_channel(_entry("Second"))

    ScraperChannelService.delete_channel("other")

    data = _read(channels_file)
    assert [c["name"] for c in data["channels"]] == ["Second"]
    assert data["settings"] == {"storage_dir": "/data", "history_dir": "/history"}


def test_delete_missing_channel_is_not_found(channels_file):
    with pytest.raises(ScraperChannelError) as exc:
        ScraperChannelService.delete_channel("Missing")

    assert exc.value.status_code == 404


def test_missing_file_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper_channels, "SCRAPER_CHANNELS_PATH", tmp_path / "missing.json")

    with pytest.raises(ScraperChannelError) as exc:
        ScraperChannelService.list_channels()
    assert exc.value.status_code == 503
