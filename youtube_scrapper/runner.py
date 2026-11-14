from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Union

import yt_dlp
import yaml
from yt_dlp.networking.impersonate import ImpersonateTarget

from config_builder import generate_runtime_files

if sys.platform == "win32":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

APP_DIR = Path(__file__).resolve().parent
RUNTIME_CONFIG_FILE = APP_DIR / ".runtime" / "config.yaml"
SUBSCRIPTIONS_FILE = APP_DIR / ".runtime" / "subscriptions.yaml"
LOGGER = logging.getLogger("youtube_scrapper")


def patch_file_handler():
    try:
        import ytdl_sub.utils.file_handler as fh
    except ImportError:
        return lambda: None

    original_get_md5 = fh.get_file_md5_hash
    original_files_equal = fh.files_equal
    original_copy = fh.FileHandler.copy
    original_move = fh.FileHandler.move

    def robust_get_file_md5_hash(full_file_path: Path | str, *args, **kwargs) -> str:
        last_exc = None
        for attempt in range(1, 4):
            try:
                return original_get_md5(full_file_path)
            except OSError as exc:
                last_exc = exc
                LOGGER.warning(
                    "Error reading/hashing file '%s' (attempt %d/3): %s",
                    full_file_path,
                    attempt,
                    exc,
                )
                time.sleep(1.0 * attempt)
        raise last_exc

    def robust_files_equal(full_file_path_a: Path | str, full_file_path_b: Path | str, *args, **kwargs) -> bool:
        if not (os.path.isfile(full_file_path_a) and os.path.isfile(full_file_path_b)):
            return False
        try:
            if os.path.getsize(full_file_path_a) != os.path.getsize(full_file_path_b):
                return False
        except OSError as exc:
            LOGGER.warning(
                "Could not compare sizes between '%s' and '%s': %s. Treating as not equal.",
                full_file_path_a,
                full_file_path_b,
                exc,
            )
            return False

        try:
            hash_a = robust_get_file_md5_hash(full_file_path_a)
        except OSError as exc:
            LOGGER.error("Failed to hash source file '%s': %s", full_file_path_a, exc)
            return False

        try:
            hash_b = robust_get_file_md5_hash(full_file_path_b)
        except OSError as exc:
            LOGGER.warning(
                "Destination file '%s' cannot be read/hashed (%s). It may be corrupted or locked. Treating as not equal to overwrite it.",
                full_file_path_b,
                exc,
            )
            return False

        return hash_a == hash_b

    @classmethod
    def robust_copy(cls, src_file_path: Union[str, Path], dst_file_path: Union[str, Path], *args, **kwargs):
        last_exc = None
        for attempt in range(1, 4):
            try:
                original_copy(src_file_path, dst_file_path)
                return
            except OSError as exc:
                last_exc = exc
                LOGGER.warning(
                    "Copy failed from '%s' to '%s' (attempt %d/3): %s",
                    src_file_path,
                    dst_file_path,
                    attempt,
                    exc,
                )
                if os.path.isfile(dst_file_path):
                    try:
                        os.remove(dst_file_path)
                    except OSError:
                        pass
                time.sleep(1.0 * attempt)
        LOGGER.error("Failed to copy '%s' to '%s' after 3 attempts: %s", src_file_path, dst_file_path, last_exc)
        raise last_exc

    @classmethod
    def robust_move(cls, src_file_path: Union[str, Path], dst_file_path: Union[str, Path], *args, **kwargs):
        last_exc = None
        for attempt in range(1, 4):
            try:
                original_move(src_file_path, dst_file_path)
                return
            except OSError as exc:
                last_exc = exc
                LOGGER.warning(
                    "Move failed from '%s' to '%s' (attempt %d/3): %s",
                    src_file_path,
                    dst_file_path,
                    attempt,
                    exc,
                )
                if os.path.isfile(dst_file_path):
                    try:
                        os.remove(dst_file_path)
                    except OSError:
                        pass
                time.sleep(1.0 * attempt)
        LOGGER.error("Failed to move '%s' to '%s' after 3 attempts: %s", src_file_path, dst_file_path, last_exc)
        raise last_exc

    fh.get_file_md5_hash = robust_get_file_md5_hash
    fh.files_equal = robust_files_equal
    fh.FileHandler.copy = robust_copy
    fh.FileHandler.move = robust_move

    def restore():
        fh.get_file_md5_hash = original_get_md5
        fh.files_equal = original_files_equal
        fh.FileHandler.copy = original_copy
        fh.FileHandler.move = original_move

    return restore


def run_ytdl_sub(arguments: list[str]) -> int:
    from ytdl_sub.main import main as ytdl_sub_main

    original_init = yt_dlp.YoutubeDL.__init__
    original_argv = sys.argv

    def normalized_init(self, params=None, *args, **kwargs):
        if isinstance(params, dict) and isinstance(params.get("impersonate"), str):
            params = copy.deepcopy(params)
            params["impersonate"] = ImpersonateTarget.from_str(params["impersonate"])
        original_init(self, params, *args, **kwargs)

    yt_dlp.YoutubeDL.__init__ = normalized_init
    restore_fh = patch_file_handler()
    sys.argv = ["ytdl-sub", *arguments]
    try:
        ytdl_sub_main()
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 1
    finally:
        restore_fh()
        yt_dlp.YoutubeDL.__init__ = original_init
        sys.argv = original_argv
    return 0


def trigger_jellyfin_refresh() -> bool:
    api_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    server_url = os.environ.get("JELLYFIN_URL", "").strip()

    config_file = APP_DIR / "jellyfin.json"
    if not api_key and config_file.is_file():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            api_key = str(cfg.get("api_key", "")).strip()
            if not server_url:
                server_url = str(cfg.get("url", "")).strip()
        except Exception as exc:
            LOGGER.warning("Could not read jellyfin.json: %s", exc)

    if not api_key:
        return False

    if not server_url:
        server_url = "http://127.0.0.1:8096"

    server_url = server_url.rstrip("/")
    refresh_url = f"{server_url}/Library/Refresh"

    LOGGER.info("Triggering Jellyfin library scan at %s...", server_url)
    try:
        req = urllib.request.Request(
            refresh_url,
            method="POST",
            headers={
                "Authorization": f'MediaBrowser Token="{api_key}"',
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status in (200, 204):
                LOGGER.info("Jellyfin library refresh triggered successfully.")
                return True
            else:
                LOGGER.warning("Jellyfin returned status code: %s", response.status)
                return False
    except urllib.error.HTTPError as exc:
        LOGGER.error("Failed to trigger Jellyfin refresh (HTTP %d: %s)", exc.code, exc.reason)
        return False
    except Exception as exc:
        LOGGER.error("Could not connect to Jellyfin at %s: %s", server_url, exc)
        return False


def trigger_mytube_sync(mytube_url: str | None = None) -> bool:
    if not mytube_url:
        mytube_url = os.environ.get("MYTUBE_URL", "").strip()

    config_file = APP_DIR / "mytube.json"
    if not mytube_url and config_file.is_file():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            mytube_url = str(cfg.get("url", "")).strip()
        except Exception as exc:
            LOGGER.warning("Could not read mytube.json: %s", exc)

    if not mytube_url:
        mytube_url = "http://127.0.0.1:8000"

    mytube_url = mytube_url.rstrip("/")

    LOGGER.info("Triggering MyTube library scan at %s...", mytube_url)
    try:
        req = urllib.request.Request(
            f"{mytube_url}/api/admin/scan",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            if response.status == 200:
                try:
                    data = json.loads(response.read().decode("utf-8"))
                    LOGGER.info(
                        "MyTube library scan completed successfully: %d total (%d new, %d updated), %d channels synced.",
                        data.get("synced_videos", 0),
                        data.get("new_videos", 0),
                        data.get("updated_videos", 0),
                        data.get("synced_channels", 0),
                    )
                except Exception:
                    LOGGER.info("MyTube library scan completed successfully.")
            else:
                LOGGER.warning("MyTube scan returned status code: %s", response.status)
    except Exception as exc:
        LOGGER.warning("Could not trigger MyTube scan at %s: %s", mytube_url, exc)
        return False

    LOGGER.info("Triggering MyTube trash cleanup...")
    try:
        req = urllib.request.Request(
            f"{mytube_url}/api/admin/cleanup",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                LOGGER.info("MyTube trash cleanup completed successfully.")
            else:
                LOGGER.warning("MyTube cleanup returned status code: %s", response.status)
    except Exception as exc:
        LOGGER.warning("Could not trigger MyTube cleanup: %s", exc)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one ytdl-sub sync using YAML generated by the UI")
    parser.add_argument("--dry-run", action="store_true", help="Preview without downloading media")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    try:
        generate_runtime_files()
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        LOGGER.error("Could not generate YAML from channel settings: %s", exc)
        return 2

    missing_files = [
        path for path in (RUNTIME_CONFIG_FILE, SUBSCRIPTIONS_FILE) if not path.is_file()
    ]
    if missing_files:
        LOGGER.error("Generated YAML is missing. Open ui.py and save the configuration first.")
        return 2

    command: list[str] = []
    if args.dry_run:
        command.append("--dry-run")
    command.extend(["--config", str(RUNTIME_CONFIG_FILE), "sub", str(SUBSCRIPTIONS_FILE)])
    LOGGER.info("Starting one ytdl-sub sync")
    try:
        return_code = run_ytdl_sub(command)
    except (ImportError, OSError) as exc:
        LOGGER.error("Could not start ytdl-sub: %s", exc)
        return 1
    if return_code:
        LOGGER.error("ytdl-sub exited with status %d", return_code)
    else:
        LOGGER.info("Sync finished successfully")
        if not args.dry_run:
            trigger_jellyfin_refresh()
            trigger_mytube_sync()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())