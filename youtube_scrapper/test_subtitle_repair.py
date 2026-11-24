import datetime
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import runner
import subtitle_repair as repair


class SubtitleRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.channel = self.root / "Channel"
        self.channel.mkdir()
        self.video = self.channel / "Episode.mkv"
        self.video.write_bytes(b"video")
        self.video_id = "T0Xjx0XEfHk"

    def write_config(self, entries, languages=None):
        (self.channel / ".ytdl-sub-Channel-download-archive.json").write_text(
            json.dumps(entries), encoding="utf-8"
        )
        config = {
            "configuration": {"ffprobe_path": "ffprobe"},
            "presets": {"preset": {
                "overrides": {"tv_show_directory": str(self.root), "tv_show_name": "Channel"},
                "subtitles": {"languages": languages if languages is not None else ["vi", "en"]},
            }},
        }
        config_path = self.root / "config.yaml"
        subscriptions_path = self.root / "subscriptions.yaml"
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        subscriptions_path.write_text(yaml.safe_dump({"preset": {"Channel": "url"}}), encoding="utf-8")
        return config_path, subscriptions_path

    def test_only_recent_videos_without_subtitles_are_repaired(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        entries = {
            self.video_id: {"upload_date": today.isoformat(), "file_names": ["Episode.mkv"]},
            "OldVideo123": {"upload_date": (today - datetime.timedelta(days=3)).isoformat(), "file_names": ["Episode.mkv"]},
        }
        config, subscriptions = self.write_config(entries)
        with patch.object(repair, "has_subtitle", return_value=False), \
                patch.object(repair, "download_subtitle", return_value=True) as download:
            self.assertEqual(repair.repair_subtitles(config, subscriptions), 1)
            download.assert_called_once_with(self.video_id, self.video.resolve(), {}, ["vi", "en"])
        with patch.object(repair, "has_subtitle", return_value=True), \
                patch.object(repair, "download_subtitle") as download:
            self.assertEqual(repair.repair_subtitles(config, subscriptions), 0)
            download.assert_not_called()

    def test_disabled_language_and_unsafe_archived_paths_are_not_downloaded(self):
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        entries = {self.video_id: {"upload_date": today, "file_names": ["../outside.mkv"]}}
        config, subscriptions = self.write_config(entries, [])
        with patch.object(repair, "download_subtitle") as download:
            self.assertEqual(repair.repair_subtitles(config, subscriptions), 0)
            download.assert_not_called()
        config, subscriptions = self.write_config(entries)
        with patch.object(repair, "download_subtitle") as download:
            self.assertEqual(repair.repair_subtitles(config, subscriptions), 0)
            download.assert_not_called()

    def test_checks_external_and_embedded_subtitles(self):
        (self.channel / "Episode.vi.srt").write_text("subtitle", encoding="utf-8")
        with patch.object(repair.subprocess, "run") as run:
            self.assertTrue(repair.has_subtitle(self.video, "ffprobe"))
            run.assert_not_called()
        (self.channel / "Episode.vi.srt").unlink()
        with patch.object(repair.subprocess, "run") as run:
            run.return_value.stdout = "2\n"
            self.assertTrue(repair.has_subtitle(self.video, "ffprobe"))
            run.return_value.stdout = ""
            self.assertFalse(repair.has_subtitle(self.video, "ffprobe"))

    def test_saves_valid_requested_caption_without_touching_video(self):
        class FakeYoutubeDL:
            def __init__(self, params):
                self.params = params

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download):
                path = Path(self.params["outtmpl"]).parent / "T0Xjx0XEfHk.vi.vtt"
                path.write_bytes(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")

        with patch.object(repair.yt_dlp, "YoutubeDL", FakeYoutubeDL):
            self.assertTrue(repair.download_subtitle(self.video_id, self.video, {}, ["vi", "en"]))
        self.assertTrue((self.channel / "Episode.vi.vtt").is_file())
        self.assertEqual(self.video.read_bytes(), b"video")

    def test_invalid_caption_is_not_saved(self):
        class FakeYoutubeDL:
            def __init__(self, params):
                self.params = params

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download):
                path = Path(self.params["outtmpl"]).parent / "T0Xjx0XEfHk.vi.vtt"
                path.write_text("<html>error</html>", encoding="utf-8")

        with patch.object(repair.yt_dlp, "YoutubeDL", FakeYoutubeDL):
            with self.assertLogs(repair.LOGGER, level=logging.WARNING):
                self.assertFalse(repair.download_subtitle(self.video_id, self.video, {}, ["vi"]))
        self.assertFalse((self.channel / "Episode.vi.vtt").exists())

    def test_partial_download_failure_can_still_save_a_valid_caption(self):
        class FakeYoutubeDL:
            def __init__(self, params):
                self.params = params

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download):
                path = Path(self.params["outtmpl"]).parent / "T0Xjx0XEfHk.vi.vtt"
                path.write_bytes(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")
                raise repair.DownloadError("second subtitle failed")

        with patch.object(repair.yt_dlp, "YoutubeDL", FakeYoutubeDL):
            with self.assertLogs(repair.LOGGER, level=logging.WARNING):
                self.assertTrue(repair.download_subtitle(self.video_id, self.video, {}, ["vi", "en"]))
        self.assertTrue((self.channel / "Episode.vi.vtt").exists())

    def test_probe_failure_does_not_attempt_a_repair(self):
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        config, subscriptions = self.write_config({
            self.video_id: {"upload_date": today, "file_names": ["Episode.mkv"]},
        })
        with patch.object(repair, "has_subtitle", side_effect=repair.subprocess.TimeoutExpired("ffprobe", 60)), \
                patch.object(repair, "download_subtitle") as download:
            with self.assertLogs(repair.LOGGER, level=logging.WARNING):
                self.assertEqual(repair.repair_subtitles(config, subscriptions), 0)
            download.assert_not_called()

    def test_runner_repairs_before_refresh_but_not_for_dry_run(self):
        config, subscriptions = self.write_config({})
        with patch.object(runner, "RUNTIME_CONFIG_FILE", config), \
                patch.object(runner, "SUBSCRIPTIONS_FILE", subscriptions), \
                patch.object(runner, "generate_runtime_files"), \
                patch.object(runner, "run_ytdl_sub", return_value=0), \
                patch.object(runner, "repair_subtitles") as run_repair, \
                patch.object(runner, "trigger_jellyfin_refresh") as refresh, \
                patch.object(runner, "trigger_mytube_sync") as sync, \
                patch.dict(runner.os.environ, {"SUBTITLE_REPAIR_ENABLED": "1"}), \
                patch.object(runner.sys, "argv", ["runner.py"]):
            events = []
            run_repair.side_effect = lambda *args: events.append("repair")
            refresh.side_effect = lambda: events.append("refresh")
            sync.side_effect = lambda: events.append("sync")
            self.assertEqual(runner.main(), 0)
            self.assertEqual(events, ["repair", "refresh", "sync"])
            events.clear()
            runner.sys.argv = ["runner.py", "--dry-run"]
            self.assertEqual(runner.main(), 0)
            self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
