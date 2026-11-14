#!/usr/bin/env python3
"""
Continuous loop runner for YouTube Scrapper and MyTube Sync.
Runs `runner.py` every N hours (default 2 hours) endlessly with crash protection.
"""

import argparse
import datetime
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / "loop_runner.pid"
LOG_FILE = BASE_DIR / "loop_runner.log"

# Setup logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("loop_runner")

_running = True

def handle_signal(signum, frame):
    global _running
    sig_name = signal.Signals(signum).name
    logger.info(f"Received termination signal ({sig_name}). Finishing current iteration and shutting down...")
    _running = False

def acquire_termux_wake_lock():
    """Ensure CPU does not go to sleep on Android when screen turns off."""
    try:
        subprocess.run(["termux-wake-lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        logger.info("Acquired Android wake lock (termux-wake-lock). CPU sleep disabled.")
    except Exception:
        pass

def write_pid():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

def remove_pid():
    try:
        if PID_FILE.is_file():
            PID_FILE.unlink()
    except Exception:
        pass

def run_single_sync() -> int:
    """Run runner.py as an isolated child process so all memory and locks are cleanly released."""
    runner_script = BASE_DIR / "runner.py"
    if not runner_script.is_file():
        logger.error(f"runner.py not found at {runner_script}")
        return 1

    cmd = [sys.executable, str(runner_script)]
    logger.info(f"Executing: {' '.join(cmd)}")
    
    t0 = time.time()
    try:
        # Run process and stream output to logger
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                clean = line.rstrip()
                if clean:
                    logger.info(f"[runner] {clean}")
            proc.stdout.close()

        ret = proc.wait()
        elapsed = time.time() - t0
        logger.info(f"runner.py exited with code {ret} (duration: {elapsed:.1f}s)")
        return ret
    except Exception as exc:
        elapsed = time.time() - t0
        logger.error(f"Error while executing runner.py ({elapsed:.1f}s): {exc}", exc_info=True)
        return 1

def main():
    parser = argparse.ArgumentParser(description="Endless loop runner for YouTube Scrapper")
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=2.0,
        help="Break duration between runs in hours (default: 2.0 hours)",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        default=True,
        help="Run immediately on startup before waiting (default: True)",
    )
    args = parser.parse_args()

    interval_seconds = int(args.interval * 3600)
    if interval_seconds < 60:
        interval_seconds = 60  # Minimum 1 minute safety safeguard

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    write_pid()
    acquire_termux_wake_lock()

    logger.info("=" * 60)
    logger.info(f"YouTube Scrapper Loop Runner started (PID: {os.getpid()})")
    logger.info(f"Break interval: {args.interval} hours ({interval_seconds} seconds)")
    logger.info(f"Log output: {LOG_FILE}")
    logger.info("=" * 60)

    iteration = 0

    try:
        while _running:
            iteration += 1
            start_time = datetime.datetime.now()
            logger.info(f"\n{'='*20} ITERATION #{iteration} START: {start_time.strftime('%Y-%m-%d %H:%M:%S')} {'='*20}")

            try:
                run_single_sync()
            except Exception as exc:
                logger.error(f"Unexpected error in iteration #{iteration}: {exc}", exc_info=True)

            if not _running:
                break

            next_run = datetime.datetime.now() + datetime.timedelta(seconds=interval_seconds)
            logger.info(f"{'='*20} ITERATION #{iteration} COMPLETE {'='*20}")
            logger.info(f"Next sync scheduled at: {next_run.strftime('%Y-%m-%d %H:%M:%S')} (sleeping {args.interval}h)...")

            # Sleep in 1-second chunks so signal handlers exit immediately
            for _ in range(interval_seconds):
                if not _running:
                    break
                time.sleep(1)

    finally:
        remove_pid()
        logger.info("Loop runner stopped cleanly. Goodbye.")

if __name__ == "__main__":
    main()
