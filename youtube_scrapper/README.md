# YouTube Media Ingestion

A cross-platform one-shot `ytdl-sub` runner with a Windows-only Tkinter configuration UI. The UI saves subscription settings and generates YAML; it does not launch downloads or manage a schedule. Video subscriptions use ytdl-sub's built-in Jellyfin TV Show by Date preset. Audio subscriptions use its built-in `Single` music preset, with artist/album/track folders and music tags.

## Files

- `config.yaml`: shared Jellyfin video/audio base presets.
- `channels.json`: subscriptions and local storage paths.
- `config_builder.py`: generates `.runtime/config.yaml` and `.runtime/subscriptions.yaml` from `channels.json`.
- `runner.py`: runs one ytdl-sub sync from the generated YAML and exits.
- `ui.py`: Windows configuration interface; saving regenerates the YAML and never starts a download.
- `requirements.txt`: Python dependencies, including ytdl-sub and PyYAML.

## PC Setup

Install Python 3.11 or newer and FFmpeg/ffprobe. On Windows, install FFmpeg and ensure `ffmpeg.exe` and `ffprobe.exe` are on `PATH`. Install the Python requirements below; `curl-cffi` is required for Chrome impersonation.

From this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install "curl-cffi>=0.7"
.\.venv\Scripts\python.exe ui.py
```

Or double-click `run_windows.bat`. Choose the external drive's media directory, add or edit subscriptions, and use **Save Settings** and **Add Channel / Save Channel**. The UI generates the YAML files under `.runtime/`. To perform one sync:

```powershell
.\.venv\Scripts\python.exe runner.py
```

The runner exits when that sync finishes. Scheduling is external. For example, a deployment PowerShell loop can regenerate YAML, run one sync, and then wait two hours:

```powershell
while ($true) {
	.\.venv\Scripts\python.exe config_builder.py
	.\.venv\Scripts\python.exe runner.py
	Start-Sleep -Seconds 7200
}
```


## Linux Setup

Install Python 3.11+, `ytdl-sub`, and FFmpeg/ffprobe using the upstream [Linux instructions](https://ytdl-sub.readthedocs.io/en/latest/guides/install/linux.html). Copy the configuration folder, including `channels.json`, to the server. Generate YAML with server paths and run one sync:

```sh
python3 -m pip install -r requirements.txt
export STORAGE_DIR="/media/your-drive"
export HISTORY_DIR="$HOME/.local/share/youtube-scrapper-history"
python3 config_builder.py
python3 runner.py
```

Use a deployment scheduler or service for recurring runs; neither the UI nor `runner.py` loops. The 2-hour delay belongs in that deployment configuration.

## Android Server with Termux

Install Termux from F-Droid or the official GitHub releases. Grant shared-storage access and install the runtime tools:

```sh
termux-setup-storage
pkg update && pkg upgrade
pkg install python ffmpeg deno
python -m pip install -r requirements.txt
deno --version
```

yt-dlp needs a supported JavaScript runtime and EJS challenge scripts to solve YouTube's signature and `n` challenges. The `ytdl-sub` dependency installs yt-dlp with its `default` extras, including the EJS scripts; Deno is installed separately by Termux. Verify Deno is available with `deno --version` (Deno 2.6.6 or newer for the yt-dlp version currently pinned by ytdl-sub). If the logs still show challenge-solving warnings, check `python -m pip show yt-dlp yt-dlp-ejs ytdl-sub` and confirm `deno` is on `PATH`.

Copy this folder to Termux's private home or another persistent app directory. Set the external-drive path to the path Android exposes on your device, for example `/storage/XXXX-XXXX/Media` (confirm the actual mount path on the device):

```sh
export STORAGE_DIR="/storage/XXXX-XXXX/Media"
export HISTORY_DIR="$HOME/.local/share/youtube-scrapper-history"
python config_builder.py
python runner.py
```

Copy a Netscape-format YouTube cookie export to `youtube_scrapper/www.youtube.com_cookies.txt` on the device. Keep this file private; it grants access to your signed-in YouTube session and may expire. The generator configures yt-dlp to use the file when present.

Put scheduling in the Termux deployment layer, not in the runner. For a simple shell deployment loop:

```sh
while true; do
	python config_builder.py && python runner.py
	sleep 7200
done
```

Termux cannot guarantee a process remains alive when Android suspends or kills the app. Keep Termux exempt from battery optimization; while plugged in, `termux-wake-lock` can reduce suspension. For a more persistent service, install Termux:Boot and start the deployment loop on boot, or use `termux-services`. Android may still stop processes under memory pressure. Network errors are retried by yt-dlp during a run; the deployment loop provides the next attempt.

## Settings and History

The UI stores subscription and path settings in `channels.json` and regenerates YAML on save. `runner.py` also rebuilds the YAML from `channels.json` before each sync, so headless runs always use the current channel criteria and machine's `STORAGE_DIR` and `HISTORY_DIR` environment variables. On PC / Windows testing environments, the storage directory defaults locally to `youtube_scrapper/media`; set the storage directory in the UI or `channels.json` (for example, `I:/`) to use an external drive. Video and music are written to `yt_video` and `yt_music` subfolders under that directory. The history directory defaults to `youtube_scrapper/history` and is deliberately outside the media drive. Keep it on persistent storage and back it up. To share the no-redownload history across PC and Android, point both installations at the same synchronized `HISTORY_DIR`; do not run both processes concurrently while sharing a history file.

The external yt-dlp text archive in `HISTORY_DIR` is authoritative: yt-dlp skips IDs recorded there even when their media files are later deleted. The generator also maintains ytdl-sub's per-library JSON mapping archive, which records downloaded IDs and their output files. `break_on_existing: true` lets repeat runs stop at the first archived entry. A failed or interrupted download is not recorded as complete and will be retried. Keep the external archive on persistent storage; do not delete it unless you intentionally want to allow downloads again.

The generator configures yt-dlp to use `www.youtube.com_cookies.txt` from this folder when the file is present. Keep the file private and refresh the export if YouTube authentication starts failing. `curl-cffi` enables Chrome impersonation; cookie-file authentication does not require Chrome.

The generated YouTube extractor options use `web_safari` and `web_embedded`, explicitly excluding `tv_downgraded`. This follows the workaround reported in [yt-dlp issue #17405](https://github.com/yt-dlp/yt-dlp/issues/17405) for intermittent `The page needs to be reloaded` errors. It is not guaranteed and can change which formats YouTube offers; check the resulting audio quality, especially for audio subscriptions.

## Per-Subscription Options

The UI controls `mode` (`video` or `audio`), maximum resolution (`480`, `720`, `1080`, `1440`, `2160`), audio output (`m4a`, `mp3`, `flac`), voice language (optional; blank takes the default audio stream without filtering, while specific codes like `vi`, `en`, or `en, vi` select or mux preferred languages), subtitle language (optional; blank disables subtitle downloading, while codes like `vi`, `en`, or `en, vi` download and embed requested subtitles), minimum views, an optional title phrase, minimum duration in minutes, and the upload window in days. A title phrase matches case-insensitively and is combined with the minimum-view criterion, when set. The generated `match_filters` preset follows [ytdl-sub's preset configuration](https://ytdl-sub.readthedocs.io/en/latest/config_reference/config_yaml.html#presets) and [yt-dlp's filter syntax](https://github.com/yt-dlp/yt-dlp#filtering-formats). A zero-day window means no date cutoff. The default duration filter is five minutes and the default resolution is 1080p (or 480p for faster downloads).

For date-limited YouTube feeds, the YAML enables yt-dlp's `youtubetab.approximate_date` and `lazy_playlist`. The date-range break stops metadata scanning at the first older upload only for non-playlist URLs, which are treated as chronological feeds. Explicit playlist URLs are not assumed to be date-sorted, so they are scanned fully to avoid missing newer eligible entries after an older one. Approximate dates come from YouTube's relative-time labels and can be off by about a day; widen the window by a day if avoiding a missed boundary upload matters more than the extra scan. A view-count filter cannot be applied by YouTube to return a pre-filtered playlist: yt-dlp must inspect candidate entries to learn their dates and view counts. ytdl-sub first collects matching metadata, then starts its media-download pass, so seeing playlist scan activity before downloads is expected. For faster bounded scans, subscribe to a channel's chronological uploads feed instead of an arbitrary playlist. With `date_days` set to 0, lazy playlist mode is disabled and the entire source is intentionally scanned.

The media drive has two separate Jellyfin library roots: `STORAGE_DIR/yt_video` for a TV Shows library, and `STORAGE_DIR/yt_music` for a Music library. Video content follows the Jellyfin date-based show/season/episode structure. Audio content follows the music preset's `Artist/[year] Album/track` structure and receives music tags rather than episode NFOs, so songs are not scanned as TV episodes.

Video mode caps format selection at the chosen height, muxes/remuxes to MKV, and only downloads subtitle tracks when explicitly selected. If no voice language is chosen, yt-dlp automatically selects the default audio track without language filtering. Audio mode extracts the chosen audio format but keeps ytdl-sub's Jellyfin episode/NFO organization.

Generated files are in `.runtime/`: `config.yaml` contains one custom preset per channel and `subscriptions.yaml` lists the URLs. The UI regenerates them whenever settings or subscriptions are saved. On a headless host, run `config_builder.py` after setting that host's paths and before `runner.py`.

## Commands

```sh
python runner.py --once
python runner.py --interval 3600
python runner.py --dry-run --once
```
python runner.py
python runner.py --dry-run
## Upstream References

`runner.py` performs exactly one sync and exits. Configure repeat timing, retries after process failure, and startup behavior in the deployment scheduler/service.
- [ytdl-sub music presets](https://ytdl-sub.readthedocs.io/en/latest/prebuilt_presets/music.html)
- [Media quality presets](https://ytdl-sub.readthedocs.io/en/latest/prebuilt_presets/media_quality.html)
- [ytdl-sub plugins](https://ytdl-sub.readthedocs.io/en/latest/config_reference/plugins.html)
- [ytdl-sub Windows install](https://ytdl-sub.readthedocs.io/en/latest/guides/install/windows.html)
- [ytdl-sub Linux install](https://ytdl-sub.readthedocs.io/en/latest/guides/install/linux.html)




ssh u@100.114.226.6 -p 8022
ssh u@192.168.1.131 -p 8022

termux-wake-lock
sshd


termux-setup-storage
pkg update && pkg upgrade
pkg install python ffmpeg deno

cp ~/storage/shared/ytdl ~/youtube_scrapper

pip install -r requirements.txt
pip install "curl-cffi>=0.7"

ls -la ~/storage/

export STORAGE_DIR="/storage/0692F50692F4FACF"

python config_builder.py
python runner.py

while true; do
	python config_builder.py && python runner.py
	sleep 7200
done

screen
screen -r

termux-wake-lock

./start_mytube.sh

tail -f ~/youtube_scrapper/loop_runner.log

## Linux server service

On the server, the scraper runs as the `youtube-scrapper.service` systemd service under `devmon`. It is enabled to start automatically at boot. It starts a sync immediately, then waits two hours after each sync completes. Video output is stored in `/media/devmon/EXTERNAL/yt_video`.

Start or resume the service:

```bash
sudo systemctl start youtube-scrapper.service
```

Check whether it is running and enabled at boot:

```bash
sudo systemctl status youtube-scrapper.service
systemctl is-enabled youtube-scrapper.service
```

Follow the service log, or view the scraper's log file:

```bash
sudo journalctl -u youtube-scrapper.service -f
sudo tail -f /home/devmon/youtube_scrapper/loop_runner.log
```

To run the loop in the foreground yourself, stop the service first to avoid running two scrapers at once:

```bash
sudo systemctl stop youtube-scrapper.service
sudo -u devmon -- bash -c 'set -a; . /home/devmon/.config/youtube-scrapper/scraper.env; set +a; cd /home/devmon/youtube_scrapper; exec .venv/bin/python -u loop_runner.py --interval 2'
```

Press `Ctrl+C` to stop the foreground loop. Start the systemd service again with `sudo systemctl start youtube-scrapper.service`.