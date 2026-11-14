from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from config_builder import generate_runtime_files


APP_DIR = Path(__file__).resolve().parent
CHANNELS_FILE = APP_DIR / "channels.json"


class IngestionUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("YouTube Media Ingestion")
        self.root.geometry("1120x760")
        self.root.minsize(900, 640)
        self.data = self.load_data()
        self.selected_index: int | None = None
        self.fields: dict[str, tk.Variable] = {}
        self.channel_save_button: ttk.Button | None = None
        self._build()
        self._refresh_channels()
        self._load_settings()
        try:
            generate_runtime_files(self.data)
            self.status.set("YAML ready")
        except Exception as exc:
            self.status.set("Could not generate YAML")
            messagebox.showerror("Configuration error", str(exc))

    @staticmethod
    def load_data() -> dict[str, Any]:
        try:
            return json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"settings": {"storage_dir": "", "history_dir": ""}, "channels": []}

    def _build(self) -> None:
        self.root.configure(bg="#eef1ed")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef1ed")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("TLabel", background="#eef1ed", foreground="#1f302b", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22), foreground="#173c32")
        style.configure("Section.TLabel", background="#ffffff", font=("Segoe UI Semibold", 12), foreground="#173c32")
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        style.configure("Accent.TButton", background="#176e58", foreground="#ffffff", padding=(12, 7))
        style.map("Accent.TButton", background=[("active", "#125943")])

        shell = ttk.Frame(self.root, padding=18)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Media ingestion", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="YouTube subscriptions  /  Jellyfin library", foreground="#66766f").pack(anchor="w", pady=(2, 14))

        settings = ttk.Frame(shell, style="Panel.TFrame", padding=12)
        settings.pack(fill="x", pady=(0, 12))
        self.fields["storage_dir"] = tk.StringVar()
        self.fields["history_dir"] = tk.StringVar()
        ttk.Label(settings, text="Media destination", background="#ffffff").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.fields["storage_dir"]).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(settings, text="Browse", command=self._browse_storage).grid(row=1, column=1, sticky="ew", padx=(0, 18))
        ttk.Label(settings, text="History location (keep off the media drive)", background="#ffffff").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.fields["history_dir"]).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(settings, text="Browse", command=self._browse_history).grid(row=1, column=3, sticky="ew", padx=(0, 18))
        settings.columnconfigure(0, weight=2)
        settings.columnconfigure(2, weight=2)

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        list_panel = ttk.Frame(body, style="Panel.TFrame", padding=12)
        list_panel.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(list_panel, text="Subscriptions", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        columns = ("name", "mode", "url")
        self.tree = ttk.Treeview(list_panel, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="NAME")
        self.tree.heading("mode", text="MODE")
        self.tree.heading("url", text="CHANNEL OR PLAYLIST URL")
        self.tree.column("name", width=190, stretch=False)
        self.tree.column("mode", width=75, stretch=False)
        self.tree.column("url", width=430)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._select_channel)
        list_actions = ttk.Frame(list_panel, style="Panel.TFrame")
        list_actions.pack(fill="x", pady=(10, 0))
        ttk.Button(list_actions, text="New", command=self._clear_form).pack(side="left")
        ttk.Button(list_actions, text="Remove", command=self._remove_channel).pack(side="left", padx=6)

        editor = ttk.Frame(body, style="Panel.TFrame", padding=14, width=340)
        editor.pack(side="right", fill="y")
        editor.pack_propagate(False)
        ttk.Label(editor, text="Subscription settings", style="Section.TLabel").pack(anchor="w", pady=(0, 12))

        form_area = ttk.Frame(editor, style="Panel.TFrame")
        form_area.pack(fill="both", expand=True)
        canvas = tk.Canvas(form_area, background="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(form_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        form = ttk.Frame(canvas, style="Panel.TFrame")
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(form_window, width=event.width))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))

        self.fields["name"] = tk.StringVar()
        self.fields["url"] = tk.StringVar()
        self.fields["mode"] = tk.StringVar(value="video")
        self.fields["resolution"] = tk.StringVar(value="1080")
        self.fields["audio_format"] = tk.StringVar(value="m4a")
        self.fields["voice_language"] = tk.StringVar(value="")
        self.fields["subtitle_language"] = tk.StringVar(value="")
        self.fields["min_views"] = tk.StringVar(value="0")
        self.fields["title_contains"] = tk.StringVar()
        self.fields["min_duration_minutes"] = tk.StringVar(value="5")
        self.fields["date_days"] = tk.StringVar(value="5")
        self.fields["enabled"] = tk.BooleanVar(value=True)
        self._entry(form, "Display name", "name")
        self._entry(form, "YouTube URL", "url")
        self._combo(form, "Download mode", "mode", ("video", "audio"))
        self._combo(form, "Maximum video resolution", "resolution", ("480", "720", "1080", "1440", "2160"))
        self._combo(form, "Audio output format", "audio_format", ("m4a", "mp3", "flac"))
        self._combo(
            form,
            "Voice language (blank = default)",
            "voice_language",
            ("", "vi", "en", "en, vi", "vi, en", "ja", "ko"),
            readonly=False,
        )
        self._combo(
            form,
            "Subtitle language (blank = none)",
            "subtitle_language",
            ("", "vi", "en", "en, vi", "vi, en", "ja", "ko"),
            readonly=False,
        )
        self._entry(form, "Minimum views (0 disables)", "min_views")
        self._entry(form, "Title contains phrase (optional)", "title_contains")
        self._entry(form, "Minimum duration (minutes)", "min_duration_minutes")
        self._entry(form, "Recent upload window (days; 0 = all)", "date_days")
        ttk.Checkbutton(form, text="Enabled", variable=self.fields["enabled"]).pack(anchor="w", pady=(2, 12))
        ttk.Label(
            form,
            text="Video uses Jellyfin show folders and MKV. Audio uses artist/album/track folders and music tags. Blank voice keeps default audio; blank subtitle skips subtitles.",
            wraplength=280,
            foreground="#66766f",
            background="#ffffff",
        ).pack(anchor="w", pady=(4, 14))

        footer = ttk.Frame(shell)
        footer.pack(fill="x", pady=(12, 0))
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Save Paths + Generate YAML", command=self._save_settings).pack(side="right")
        self.channel_save_button = ttk.Button(footer, text="Add Channel", style="Accent.TButton", command=self._save_channel)
        self.channel_save_button.pack(side="right", padx=8)

    def _entry(self, parent: ttk.Frame, label: str, key: str) -> None:
        ttk.Label(parent, text=label, background="#ffffff").pack(anchor="w", pady=(0, 3))
        ttk.Entry(parent, textvariable=self.fields[key]).pack(fill="x", pady=(0, 9))

    def _combo(self, parent: ttk.Frame, label: str, key: str, values: tuple[str, ...], readonly: bool = True) -> None:
        ttk.Label(parent, text=label, background="#ffffff").pack(anchor="w", pady=(0, 3))
        state = "readonly" if readonly else "normal"
        combo = ttk.Combobox(parent, textvariable=self.fields[key], values=values, state=state)
        combo.pack(fill="x", pady=(0, 9))

    def _refresh_channels(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, channel in enumerate(self.data.get("channels", [])):
            mode = channel.get("mode", "video")
            if not channel.get("enabled", True):
                mode = f"{mode} (off)"
            self.tree.insert("", "end", iid=str(index), values=(channel.get("name", ""), mode, channel.get("url", "")))

    def _select_channel(self, _event: object = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0])
        channel = self.data["channels"][index]
        self.selected_index = index
        if self.channel_save_button is not None:
            self.channel_save_button.configure(text="Save Channel")
        for key in ("name", "url", "mode", "resolution", "audio_format", "voice_language", "subtitle_language", "min_views", "title_contains", "min_duration_minutes", "date_days", "enabled"):
            default = {
                "mode": "video",
                "resolution": 1080,
                "audio_format": "m4a",
                "voice_language": "",
                "subtitle_language": "",
                "min_views": 0,
                "title_contains": "",
                "min_duration_minutes": 5,
                "date_days": 5,
                "enabled": True,
            }.get(key, "")
            self.fields[key].set(channel.get(key, default))

    def _clear_form(self) -> None:
        self.selected_index = None
        if self.channel_save_button is not None:
            self.channel_save_button.configure(text="Add Channel")
        self.tree.selection_remove(*self.tree.selection())
        for key, value in {
            "name": "",
            "url": "",
            "mode": "video",
            "resolution": "1080",
            "audio_format": "m4a",
            "voice_language": "",
            "subtitle_language": "",
            "min_views": "0",
            "title_contains": "",
            "min_duration_minutes": "5",
            "date_days": "5",
            "enabled": True,
        }.items():
            self.fields[key].set(value)

    def _save_channel(self) -> None:
        try:
            channel = {
                "name": self.fields["name"].get().strip(),
                "url": self.fields["url"].get().strip(),
                "mode": self.fields["mode"].get(),
                "resolution": int(self.fields["resolution"].get()),
                "audio_format": self.fields["audio_format"].get(),
                "voice_language": self.fields["voice_language"].get().strip(),
                "subtitle_language": self.fields["subtitle_language"].get().strip(),
                "min_views": int(self.fields["min_views"].get()),
                "title_contains": self.fields["title_contains"].get().strip(),
                "min_duration_minutes": int(self.fields["min_duration_minutes"].get()),
                "date_days": int(self.fields["date_days"].get()),
                "enabled": bool(self.fields["enabled"].get()),
            }
            if not channel["name"] or not channel["url"]:
                raise ValueError("Name and URL are required")
            if any(channel[key] < 0 for key in ("min_views", "min_duration_minutes", "date_days")):
                raise ValueError("Thresholds cannot be negative")
            duplicate = next((i for i, saved in enumerate(self.data["channels"]) if saved["name"].casefold() == channel["name"].casefold() and i != self.selected_index), None)
            if duplicate is not None:
                raise ValueError("Another subscription already uses that name")
            is_new_channel = self.selected_index is None
            if is_new_channel:
                self.data["channels"].append(channel)
            else:
                self.data["channels"][self.selected_index] = channel
            self._write_data()
            self._refresh_channels()
            self._clear_form()
            self.status.set("Channel added" if is_new_channel else "Channel updated")
        except (ValueError, KeyError, RuntimeError, OSError) as exc:
            messagebox.showerror("Invalid subscription", str(exc))

    def _remove_channel(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0])
        del self.data["channels"][index]
        try:
            self._write_data()
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Configuration error", str(exc))
            return
        self._refresh_channels()
        self._clear_form()
        self.status.set("Subscription removed")

    def _load_settings(self) -> None:
        settings = self.data.get("settings", {})
        storage = settings.get("storage_dir", "")
        if os.name == "nt" and (not storage or storage in {"I:/", "I:\\", "I:"}):
            storage = str(APP_DIR / "media")
        self.fields["storage_dir"].set(storage)
        self.fields["history_dir"].set(settings.get("history_dir", ""))

    def _save_settings(self) -> bool:
        self.data["settings"] = {
            "storage_dir": self.fields["storage_dir"].get().strip(),
            "history_dir": self.fields["history_dir"].get().strip(),
        }
        try:
            self._write_data()
            self.status.set("Settings saved")
            return True
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Could not save settings", str(exc))
            return False

    def _write_data(self) -> None:
        self.data.setdefault("settings", {}).pop("interval_seconds", None)
        try:
            generate_runtime_files(self.data)
            CHANNELS_FILE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(f"Could not write the ytdl-sub YAML files: {exc}") from exc

    def _browse_storage(self) -> None:
        selected = filedialog.askdirectory(title="Choose media destination")
        if selected:
            self.fields["storage_dir"].set(selected)

    def _browse_history(self) -> None:
        selected = filedialog.askdirectory(title="Choose persistent history location")
        if selected:
            self.fields["history_dir"].set(selected)

def main() -> None:
    root = tk.Tk()
    IngestionUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()