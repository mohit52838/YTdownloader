from __future__ import annotations
APP_VERSION = "1.0.0"
GITHUB_REPO = "mohit52838/YTdownloader"


import os
import sys
import threading
import json
import traceback
from pathlib import Path
from datetime import datetime
import re
import shutil
import requests
import tempfile
import subprocess
import webbrowser

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    GUI_AVAILABLE = True
except Exception:
    ctk = None
    filedialog = None
    messagebox = None
    GUI_AVAILABLE = False
try:
    from yt_dlp import YoutubeDL
except Exception:
    raise


def has_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?"<>|:]', '', str(name))
    name = name.strip()
    return name[:120]


class Log:
    def __init__(self):
        self._lines = []
    def add(self, s: str):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f'[{ts}] {s}'
        print(line)
        self._lines.append(line)
    def text(self) -> str:
        return '\n'.join(self._lines)

logger = Log()

class YTDLDownloader:
    def __init__(self, out_dir: str, ui_log=None, ui_progress=None):
        self.out_dir = out_dir
        ensure_dir(self.out_dir)
        self.ui_log = ui_log
        self.ui_progress = ui_progress
        self._ydl = None
    def _log(self, s: str):
        logger.add(s)
        if self.ui_log:
            try:
                self.ui_log(s)
            except Exception:
                pass
    def _progress_hook(self, d):
        try:
            status = d.get('status')
            if status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                percent = int(downloaded / total * 100) if total else 0
                if self.ui_progress:
                    try:
                        self.ui_progress(percent)
                    except Exception:
                        pass
            elif status == 'finished':
                if self.ui_progress:
                    try:
                        self.ui_progress(100)
                    except Exception:
                        pass
                self._log('Download finished for: ' + str(d.get('filename', '')))
            elif status == 'error':
                self._log('Download error state')
        except Exception as e:
            self._log(f'Progress hook error: {e}')

    def _build_opts(self, fmt: str, to_mp3: bool, save_subs: bool, save_thumb: bool,
                save_meta: bool, quality_label: str, mp3_bitrate: str | None = None):

        opts = {
            'outtmpl': os.path.join(self.out_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'progress_hooks': [self._progress_hook],
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': save_subs,
            'writeautomaticsub': save_subs,
            'writethumbnail': save_thumb,
            'skip_download': False,
            'ffmpeg_location': r"C:\ffmpeg\bin"

        }

        # If ffmpeg is available, pass its folder so yt-dlp can find ffmpeg/ffprobe
        if has_ffmpeg():
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path:
                opts['ffmpeg_location'] = os.path.dirname(ffmpeg_path)

        # -----------------------------------------------------
        # 1) MP3 Mode
        # -----------------------------------------------------
        if to_mp3:
            bitrate = mp3_bitrate or '192'
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': str(bitrate),
                }],
            })
            return opts

        # -----------------------------------------------------
        # 2) Video Mode – try selecting a specific resolution
        # -----------------------------------------------------
        if quality_label and quality_label != 'auto':
            try:
                h = int(re.sub(r'[^0-9]', '', quality_label))
                requested_format = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
            except Exception:
                requested_format = 'best'
        else:
            requested_format = 'best'

        # -----------------------------------------------------
        # 3) Handle missing ffmpeg SAFELY
        #    If merging is required but ffmpeg is missing → fallback
        # -----------------------------------------------------
        if not has_ffmpeg():
            # only log a fallback when ffmpeg is actually missing
            self._log("ffmpeg not found — will prefer single-file mp4 to prevent merge errors if necessary.")
            opts['format'] = 'best[ext=mp4]/best'
            opts['abort_on_unavailable_fragments'] = False
        else:
            opts['format'] = requested_format

        # -----------------------------------------------------
        # 4) Metadata options
        # -----------------------------------------------------
        if save_meta:
            opts['writedescription'] = True
            opts['writeinfojson'] = True

        return opts

    def download(self, url: str, mode: str='video', fmt: str='mp4',
                 quality_label: str='auto', save_subs: bool=False,
                 save_thumb: bool=False, save_meta: bool=False, mp3_bitrate: str | None = None) -> bool:

        url = url.strip()
        to_mp3 = (fmt.lower() == 'mp3')
        self._log(f'Starting download: mode={mode} url={url} format={fmt} quality={quality_label}')

        try:
            opts = self._build_opts(fmt, to_mp3, save_subs, save_thumb, save_meta, quality_label, mp3_bitrate)

            # Playlist/channel enable full lists
            if mode in ('playlist', 'channel'):
                opts['noplaylist'] = False

            with YoutubeDL(opts) as ydl:
                ydl.download([url])

            self._log("Download flow finished")
            return True

        except Exception as e:
            tb = traceback.format_exc()
            self._log(f"Download failed: {e}\n{tb}")
            return False


def check_for_update():
    try:
        api = f""
        r = requests.get(api, timeout=10)
        if r.status_code != 200:
            return None, None
        response = r.json()
        latest_version = response.get("tag_name") or response.get("name")
        assets = response.get('assets', [])
        download_url = None
        if assets:
            download_url = assets[0].get('browser_download_url')
        if latest_version and latest_version != APP_VERSION and download_url:
            return download_url, latest_version
        return None, None
    except Exception:
        return None, None

def install_update(download_url: str):
    try:
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, 'update_download')
        with requests.get(download_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(temp_file, 'wb') as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
        if getattr(sys, 'frozen', False) and sys.executable.lower().endswith('.exe'):
            current_exe = sys.executable
            backup = current_exe + '.old'
            try:
                os.replace(current_exe, backup)
            except Exception:
                try:
                    os.remove(backup)
                    os.replace(current_exe, backup)
                except Exception:
                    pass
            try:
                shutil.copy(temp_file, current_exe)
            except Exception:
                try:
                    shutil.copy(temp_file, backup)
                    os.replace(backup, current_exe)
                except Exception:
                    pass
            subprocess.Popen([current_exe])
            sys.exit(0)
        else:
            return temp_file
    except Exception:
        return None

if GUI_AVAILABLE:
    class App(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("YTdownloader – Modern")
            self.geometry("1200x800")
            self.resizable(True, True)
            ctk.set_appearance_mode("System")
            self.ACCENT = "#E53935"      # Primary accent
            self.ACCENT_HOVER = "#D32F2F" # Hover color 


            # Responsive layout
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(0, weight=1)

            self.output_dir = os.path.join(os.getcwd(), "downloads")
            ensure_dir(self.output_dir)

            # Main container
            self.container = ctk.CTkFrame(self, corner_radius=20)
            self.container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.container.grid_rowconfigure(1, weight=1)
            self.container.grid_columnconfigure(0, weight=1)

            # Build UI
            self._build_header()
            self._build_body()
            self._build_footer()

            # Start update check
            threading.Thread(target=self._maybe_check_update_gui, daemon=True).start()

            # Startup animation
            self._animate_startup()

        # ------------------------------------------------------------------
        # HEADER
        # ------------------------------------------------------------------
        def _build_header(self):
            header = ctk.CTkFrame(self.container, corner_radius=16, height=80)
            header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 0))
            header.grid_columnconfigure(1, weight=1)

            # Logo + Version
            left = ctk.CTkFrame(header, fg_color="transparent")
            left.grid(row=0, column=0, sticky="w", padx=20)
            self.logo = ctk.CTkLabel(left, text="YTdownloader",
                                     font=ctk.CTkFont(size=28, weight="bold"))
            self.logo.grid(row=0, column=0, padx=(0, 10))
            ctk.CTkLabel(left, text=f"v{APP_VERSION}",
                         font=ctk.CTkFont(size=12), text_color="gray60").grid(row=0, column=1)

            # Tagline
            ctk.CTkLabel(header, text="YouTube • Video • Playlist • Channel",
                         font=ctk.CTkFont(size=14), text_color="gray60")\
                .grid(row=0, column=1, sticky="w", padx=20)

            # Controls
            right = ctk.CTkFrame(header, fg_color="transparent")
            right.grid(row=0, column=2, sticky="e", padx=20)
            self.theme_var = ctk.StringVar(value=ctk.get_appearance_mode())
            ctk.CTkOptionMenu(right, values=["System", "Light", "Dark"],
                              variable=self.theme_var, width=120, command=self._set_theme)\
                .grid(row=0, column=0, padx=(0, 10))

            ctk.CTkButton(right, text="Check updates", width=140, fg_color=self.ACCENT,
                          command=self._manual_check_update)\
                .grid(row=0, column=1, padx=(0, 10))
            ctk.CTkButton(right, text="Open folder", width=140,
                          command=self._open_folder)\
                .grid(row=0, column=2)

        # ------------------------------------------------------------------
        # BODY (Tabs + Right Panel)
        # ------------------------------------------------------------------
        def _build_body(self):
            body = ctk.CTkFrame(self.container, corner_radius=16)
            body.grid(row=1, column=0, sticky="nsew", padx=15, pady=15)
            body.grid_rowconfigure(0, weight=1)
            body.grid_columnconfigure(0, weight=1)
            body.grid_columnconfigure(1, weight=0)

            # Tabview
            self.tabview = ctk.CTkTabview(body, corner_radius=16)
            self.tabview.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.tabview.add("Download")
            self.tabview.add("Settings")
            self.tabview.add("Logs")
            self.tabview.add("About")

            # Right Panel
            self._build_right_panel(body)

            # Build tabs
            self._build_download_tab()
            self._build_settings_tab()
            self._build_logs_tab()
            self._build_about_tab()

        # ------------------------------------------------------------------
        # RIGHT PANEL
        # ------------------------------------------------------------------
        def _build_right_panel(self, parent):
            panel = ctk.CTkFrame(parent, corner_radius=16, width=320)
            panel.grid(row=0, column=1, sticky="ns", padx=(0, 15))
            panel.grid_propagate(False)

            ctk.CTkLabel(panel, text="Quick Actions", font=ctk.CTkFont(size=18, weight="bold"))\
                .grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

            # Output folder
            card = ctk.CTkFrame(panel, corner_radius=12)
            card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text="Output folder:", anchor="w")\
                .grid(row=0, column=0, sticky="w", padx=15, pady=(12, 5))
            self.output_label = ctk.CTkLabel(card, text=self.output_dir, wraplength=270,
                                             anchor="w", font=ctk.CTkFont(size=11))
            self.output_label.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 12))

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 12))
            btns.grid_columnconfigure((0, 1), weight=1)
            ctk.CTkButton(btns, text="Change", width=100, command=self._choose_output)\
                .grid(row=0, column=0, padx=(0, 5))
            ctk.CTkButton(btns, text="Open", width=100, command=self._open_folder)\
                .grid(row=0, column=1, padx=(5, 0))

            # Tips
            tips = ctk.CTkFrame(panel, corner_radius=12)
            tips.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
            tips.grid_rowconfigure(0, weight=1)
            self.tips_label = ctk.CTkLabel(tips, text="", justify="left", wraplength=270,
                                           font=ctk.CTkFont(size=11))
            self.tips_label.grid(row=0, column=0, sticky="w", padx=15, pady=15)

            self._tips = [
                "Paste a YouTube URL → Choose format → Download",
                "Use MP3 320 kbps for best audio quality",
                "Enable subtitles & thumbnails for full media",
                "Check the Logs tab for detailed progress"
            ]
            self._tip_index = 0
            self.after(3000, self._rotate_tip)

        def _rotate_tip(self):
            self._tip_index = (self._tip_index + 1) % len(self._tips)
            self.tips_label.configure(text=self._tips[self._tip_index])
            self.after(3000, self._rotate_tip)

        # ------------------------------------------------------------------
        # DOWNLOAD TAB
        # ------------------------------------------------------------------
        def _build_download_tab(self):
            tab = self.tabview.tab("Download")
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure((0, 1), weight=1)

            # Form
            left = ctk.CTkFrame(tab, corner_radius=16)
            left.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
            left.grid_columnconfigure(1, weight=1)

            r = 0
            ctk.CTkLabel(left, text="URL:", anchor="w").grid(row=r, column=0, sticky="w", padx=(15, 10), pady=(15, 5))
            url_f = ctk.CTkFrame(left, fg_color="transparent")
            url_f.grid(row=r, column=1, sticky="ew", padx=(0, 15), pady=(15, 5))
            url_f.grid_columnconfigure(0, weight=1)
            self.url_entry = ctk.CTkEntry(url_f, placeholder_text="https://youtube.com/…")
            self.url_entry.grid(row=0, column=0, sticky="ew")
            ctk.CTkButton(url_f, text="Paste", width=70, command=self._paste)\
                .grid(row=0, column=1, padx=(5, 0))
            r += 1

            ctk.CTkLabel(left, text="Mode:", anchor="w").grid(row=r, column=0, sticky="w", padx=(15, 10), pady=(10, 5))
            mode_f = ctk.CTkFrame(left, fg_color="transparent")
            mode_f.grid(row=r, column=1, sticky="w", pady=(10, 5))
            self.mode_var = ctk.StringVar(value="video")
            for txt, val in [("Video", "video"), ("Playlist", "playlist"), ("Channel", "channel")]:
                ctk.CTkRadioButton(mode_f, text=txt, variable=self.mode_var, value=val)\
                    .pack(side="left", padx=6)
            r += 1

            ctk.CTkLabel(left, text="Format:", anchor="w").grid(row=r, column=0, sticky="w", padx=(15, 10), pady=(10, 5))
            fmt_f = ctk.CTkFrame(left, fg_color="transparent")
            fmt_f.grid(row=r, column=1, sticky="w", pady=(10, 5))
            self.format_var = ctk.StringVar(value="mp4")
            ctk.CTkOptionMenu(fmt_f, values=["mp4", "mp3"], variable=self.format_var,
                              width=110, command=self._on_format_change).pack(side="left", padx=(0, 10))
            self.mp3_bitrate_var = ctk.StringVar(value="192")
            self.mp3_bitrate_menu = ctk.CTkOptionMenu(fmt_f, values=["128", "192", "320"],
                                                      variable=self.mp3_bitrate_var, width=90, state="disabled")
            self.mp3_bitrate_menu.pack(side="left")
            r += 1

            ctk.CTkLabel(left, text="Quality:", anchor="w").grid(row=r, column=0, sticky="w", padx=(15, 10), pady=(10, 5))
            qual_f = ctk.CTkFrame(left, fg_color="transparent")
            qual_f.grid(row=r, column=1, sticky="w", pady=(10, 5))
            self.quality_var = ctk.StringVar(value="auto")
            self.quality_menu = ctk.CTkOptionMenu(qual_f, values=["auto", "1080", "720", "480", "360"],
                                                  variable=self.quality_var, width=110)
            self.quality_menu.pack(side="left")
            r += 1

            ctk.CTkLabel(left, text="Options:", anchor="w").grid(row=r, column=0, sticky="w", padx=(15, 10), pady=(10, 5))
            chk_f = ctk.CTkFrame(left, fg_color="transparent")
            chk_f.grid(row=r, column=1, sticky="w", pady=(10, 5))
            self.subs_var = ctk.BooleanVar(); self.thumb_var = ctk.BooleanVar(); self.meta_var = ctk.BooleanVar()
            for txt, var in [("Subtitles", self.subs_var), ("Thumbnail", self.thumb_var), ("Metadata", self.meta_var)]:
                ctk.CTkCheckBox(chk_f, text=txt, variable=var).pack(side="left", padx=8)
            r += 1

            btn_f = ctk.CTkFrame(left, fg_color="transparent")
            btn_f.grid(row=r, column=0, columnspan=2, sticky="e", pady=(20, 15))
            ctk.CTkButton(btn_f, text="Fetch Info", width=140, command=self._fetch_info)\
                .pack(side="left", padx=(15, 5))
            self.download_btn = ctk.CTkButton(btn_f, text="Download", width=160,
                                              fg_color=self.ACCENT, command=self._start_download_thread)
            self.download_btn.pack(side="left", padx=5)
            ctk.CTkButton(btn_f, text="Open Folder", width=140, command=self._open_folder)\
                .pack(side="left", padx=(5, 15))

            # Progress Panel
            right = ctk.CTkFrame(tab, corner_radius=16)
            right.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
            right.grid_rowconfigure(2, weight=1)

            self.progress = ctk.CTkProgressBar(right, height=16, progress_color=self.ACCENT)
            self.progress.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
            self.progress.set(0)

            self.status_badge = ctk.CTkLabel(right, text="Idle", font=ctk.CTkFont(size=16, weight="bold"),
                                             corner_radius=12, width=180, height=40)
            self.status_badge.grid(row=1, column=0, pady=(0, 10))

            self.small_log = ctk.CTkTextbox(right, height=180, font=ctk.CTkFont(family="Consolas", size=11))
            self.small_log.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))

        # ------------------------------------------------------------------
        # OTHER TABS
        # ------------------------------------------------------------------
        def _build_settings_tab(self):
            tab = self.tabview.tab("Settings")
            tab.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(tab, text="Settings", font=ctk.CTkFont(size=22, weight="bold"))\
                .grid(row=0, column=0, sticky="w", padx=25, pady=(25, 15))
            sec = ctk.CTkFrame(tab, corner_radius=16)
            sec.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 25))
            sec.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(sec, text="Appearance:", anchor="w")\
                .grid(row=0, column=0, sticky="w", padx=20, pady=20)
            ctk.CTkOptionMenu(sec, values=["System", "Light", "Dark"], command=self._set_theme, width=140)\
                .grid(row=0, column=1, sticky="e", padx=20, pady=20)
            ok = has_ffmpeg()
            txt = "ffmpeg detected" if ok else "ffmpeg missing"
            fg = "#e8f5e9" if ok else "#ffebee"
            tc = "#2e7d32" if ok else "#c62828"
            ctk.CTkLabel(sec, text=txt, fg_color=fg, text_color=tc, corner_radius=8,
                         font=ctk.CTkFont(weight="bold"))\
                .grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 20))

        def _build_logs_tab(self):
            tab = self.tabview.tab("Logs")
            tab.grid_rowconfigure(1, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            top = ctk.CTkFrame(tab, fg_color="transparent")
            top.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
            top.grid_columnconfigure(0, weight=1)
            self.search_var = ctk.StringVar()
            ctk.CTkEntry(top, placeholder_text="Search logs…", textvariable=self.search_var)\
                .grid(row=0, column=0, sticky="ew", padx=(0, 10))
            self.search_var.trace("w", lambda *args: self._filter_logs())
            ctk.CTkButton(top, text="Clear", width=100, command=self._clear_logs)\
                .grid(row=0, column=1, padx=(0, 10))
            ctk.CTkButton(top, text="Copy All", width=110, command=self._copy_logs)\
                .grid(row=0, column=2)
            self.logbox = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=11))
            self.logbox.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
            self._refresh_logs()

        def _build_about_tab(self):
            tab = self.tabview.tab('About')
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            # Main card for content
            card = ctk.CTkFrame(tab, corner_radius=16)
            card.grid(row=0, column=0, sticky="nsew", padx=32, pady=32)
            card.grid_rowconfigure(0, weight=1)
            card.grid_columnconfigure(0, weight=1)

            # Header section
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
            header.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(header, text="YTdownloader", font=ctk.CTkFont(size=26, weight="bold"))\
                .grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(header, text=f"v{APP_VERSION}", font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#777")\
                .grid(row=0, column=1, sticky="e", padx=(24, 0))

            # Description text
            desc = ctk.CTkLabel(card, text=(
                "A modern YouTube downloader built with yt-dlp.\n\n"
                "Key Features:\n"
                "- Download videos, playlists, or channels\n"
                "- Convert to MP3 with custom bitrate\n"
                "- Save subtitles, thumbnails, and metadata\n"
                "- Auto-update checker for latest versions\n"
                "- Light/Dark mode support\n\n"
            ), justify="left", wraplength=720, font=ctk.CTkFont(size=14))
            desc.grid(row=1, column=0, sticky="w")

            # GitHub link button
            link_btn = ctk.CTkButton(card, text="GitHub Repository →", fg_color=self.ACCENT,
                                     hover_color=self.ACCENT_HOVER, font=ctk.CTkFont(size=14),
                                     command=lambda: webbrowser.open("https://github.com/mohit52838/YTdownloader"))
            link_btn.grid(row=2, column=0, sticky="w", pady=(24, 0))

            # Footer note
            footer = ctk.CTkLabel(card, text="© 2025 Mohit Patil. All rights reserved.",
                                  font=ctk.CTkFont(size=11), text_color="#888")
            footer.grid(row=3, column=0, sticky="sw", pady=(32, 0))
            
        # ------------------------------------------------------------------
        # FOOTER
        # ------------------------------------------------------------------
        def _build_footer(self):
            footer = ctk.CTkFrame(self.container, corner_radius=12, height=50)
            footer.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
            footer.grid_columnconfigure(0, weight=1)
            self.status_label = ctk.CTkLabel(footer, text="Status: Idle", anchor="w",
                                             font=ctk.CTkFont(size=13))
            self.status_label.grid(row=0, column=0, sticky="w", padx=20, pady=12)

        # ------------------------------------------------------------------
        # ANIMATIONS (No opacity!)
        # ------------------------------------------------------------------
        def _animate_startup(self):
            self.container.grid_remove()
            self.after(100, self._slide_in)

        def _slide_in(self):
            self.container.grid()
            x = -1200
            self.container.place(x=x, y=0, relwidth=1, relheight=1)
            self._animate_slide(x, 0)

        def _animate_slide(self, current, target):
            if abs(current - target) > 5:
                current += (target - current) * 0.15
                self.container.place(x=current, y=0, relwidth=1, relheight=1)
                self.after(16, lambda: self._animate_slide(current, target))
            else:
                self.container.place_forget()
                self.container.grid()

        # ------------------------------------------------------------------
        # STATUS & PROGRESS
        # ------------------------------------------------------------------
        def _set_status_badge(self, text: str, success: bool = None):
            self.status_badge.configure(text=text)
            if success is True:
                self.status_badge.configure(fg_color="#d4edda", text_color="#155724")
            elif success is False:
                self.status_badge.configure(fg_color="#f8d7da", text_color="#721c24")
            else:
                self.status_badge.configure(fg_color=ctk.ThemeManager.theme["CTkFrame"]["fg_color"][1],
                                           text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"][1])

        def _update_progress(self, pct: int):
            """
            yt-dlp reports:
                - video download progress
                - audio download progress
                - then a merge step (often resets to low % or 0)

            This normalizes the progress into a smooth 0–100%.
            """

            # Initialize stored progress
            if not hasattr(self, "_stable_pct"):
                self._stable_pct = 0
                self._max_seen_pct = 0

            # yt-dlp sometimes gives nonsense values like negative, None, or >100
            if not isinstance(pct, (int, float)) or pct < 0 or pct > 1000:
                return

            # yt-dlp merge step resets to a low value → ignore if we were ahead
            if pct < self._max_seen_pct:
                # ignore backward jumps (video/audio switching, merging)
                pct = self._max_seen_pct

            # Update trackers
            self._max_seen_pct = max(self._max_seen_pct, pct)
            self._stable_pct = pct

            # Clamp strictly between 0–100
            pct = max(0, min(100, pct))

            # Update UI progress bar
            self.progress.set(pct / 100)
        
            # Update bottom-left status message
            self.status_label.configure(text=f"Status: Downloading... {pct}%")

            # Show recent logs
            recent = "\n".join(logger._lines[-5:]) if logger._lines else ""
            self.small_log.delete("1.0", "end")
            self.small_log.insert("1.0", recent)

            # When reaching real 100%
            if pct == 100:
                self._max_seen_pct = 0
                self._stable_pct = 0
        
        def _set_status(self, s: str):
            self.status_label.configure(text=f"Status: {s}")
            if "idle" in s.lower():
                self._set_status_badge("Idle")
            elif "downloading" in s.lower():
                self._set_status_badge("Downloading…")
            elif "finished" in s.lower():
                self._set_status_badge("Finished", True)
            elif "failed" in s.lower() or "error" in s.lower():
                self._set_status_badge("Failed", False)
            elif "fetching" in s.lower():
                self._set_status_badge("Fetching…")

        # ------------------------------------------------------------------
        # UTILITY
        # ------------------------------------------------------------------
        def _on_format_change(self, v: str):
            self.mp3_bitrate_menu.configure(state="normal" if v == "mp3" else "disabled")

        def _paste(self):
            try: self.url_entry.delete(0, "end"); self.url_entry.insert(0, self.clipboard_get())
            except: pass

        def _choose_output(self):
            folder = filedialog.askdirectory(initialdir=self.output_dir)
            if folder:
                self.output_dir = folder
                self.output_label.configure(text=folder)

        def _open_folder(self):
            try: os.startfile(self.output_dir)
            except:
                try: subprocess.Popen(['xdg-open' if sys.platform != 'darwin' else 'open', self.output_dir])
                except Exception as e: messagebox.showinfo("Error", f"Cannot open: {e}")

        def _set_theme(self, mode):
            ctk.set_appearance_mode(mode)

        def _refresh_logs(self):
            self.logbox.delete("1.0", "end")
            self.logbox.insert("1.0", logger.text())

        def _filter_logs(self):
            term = self.search_var.get().lower()
            self.logbox.delete("1.0", "end")
            for line in logger._lines:
                if term in line.lower():
                    self.logbox.insert("end", line + "\n")

        def _clear_logs(self):
            logger._lines.clear()
            self._refresh_logs()

        def _copy_logs(self):
            self.clipboard_clear()
            self.clipboard_append(logger.text())

        def _fetch_info(self):
            url = self.url_entry.get().strip()
            if not url: return messagebox.showwarning("Input", "Please enter a URL")
            threading.Thread(target=self._fetch_info_worker, args=(url, self.mode_var.get()), daemon=True).start()

        def _fetch_info_worker(self, url, mode):
            self._set_status("Fetching info...")
            try:
                with YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                heights = sorted({f.get('height') for f in info.get('formats', []) if f.get('height')}, reverse=True)
                qvals = ['auto'] + [str(h) for h in heights[:5] if h]
                self.quality_menu.configure(values=qvals)
                self.quality_var.set('auto')
                self._log(f"Fetched: {info.get('title')}")
                self._set_status("Info fetched")
            except Exception as e:
                self._log(f"Error: {e}")
                self._set_status("Fetch failed")

        def _start_download_thread(self):
            if getattr(self, 'downloading', False): return
            threading.Thread(target=self._download_action, daemon=True).start()

        def _download_action(self):
            url = self.url_entry.get().strip()
            if not url: return messagebox.showwarning("Input", "Please enter a URL")
            self.downloading = True
            self.download_btn.configure(state="disabled")
            d = YTDLDownloader(self.output_dir, ui_log=self._log, ui_progress=self._update_progress)
            self._set_status("Downloading...")
            ok = d.download(url,
                            mode=self.mode_var.get(),
                            fmt=self.format_var.get(),
                            quality_label=self.quality_var.get(),
                            save_subs=self.subs_var.get(),
                            save_thumb=self.thumb_var.get(),
                            save_meta=self.meta_var.get(),
                            mp3_bitrate=self.mp3_bitrate_var.get() if self.format_var.get() == "mp3" else None)
            self.download_btn.configure(state="normal")
            self.downloading = False
            if ok:
                self._set_status("Finished")
                messagebox.showinfo("Success", "Download completed!")
            else:
                self._set_status("Failed")
                messagebox.showerror("Error", "Download failed. Check logs.")

        def _log(self, s: str):
            logger.add(s)
            try:
                self.logbox.insert("end", s + "\n")
                self.logbox.see("end")
            except: pass

        def _maybe_check_update_gui(self):
            try:
                url, ver = check_for_update()
                if url and ver:
                    if messagebox.askyesno("Update", f"v{ver} available. Install now?"):
                        if sys.executable.lower().endswith('.exe'):
                            install_update(url)
                        else:
                            messagebox.showinfo("Update", f"Download:\n{url}")
            except: pass

        def _manual_check_update(self):
            try:
                url, ver = check_for_update()
                if url and ver:
                    if messagebox.askyesno("Update", f"v{ver} available. Open GitHub?"):
                        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
                else:
                    messagebox.showinfo("Update", "You're up to date!")
            except:
                messagebox.showinfo("Update", "Check failed.")

if not GUI_AVAILABLE:
    def notify_cli_update():
        try:
            download_url, latest = check_for_update()
            if download_url and latest:
                print(f'New version available: {latest}')
                print(f'Download: {download_url}')
        except Exception:
            pass

def run_cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', '-u', required=False)
    parser.add_argument('--mode', '-m', choices=['video','playlist','channel'], default='video')
    parser.add_argument('--format', '-f', choices=['mp4','mp3'], default='mp4')
    parser.add_argument('--quality', '-q', default='auto')
    parser.add_argument('--output', '-o', default=os.path.join(os.getcwd(), 'downloads'))
    parser.add_argument('--subs', action='store_true')
    parser.add_argument('--thumb', action='store_true')
    parser.add_argument('--meta', action='store_true')
    parser.add_argument('--mp3-bitrate', default='192')
    args = parser.parse_args()
    if not args.url:
        if sys.stdin.isatty():
            args.url = input('Enter URL: ').strip()
            if not args.url:
                logger.add('No URL provided. Exiting.')
                return
        else:
            parser.print_help()
            return
    if not GUI_AVAILABLE:
        try:
            notify_cli_update()
        except Exception:
            pass
    d = YTDLDownloader(args.output, ui_log=lambda s: None, ui_progress=lambda p: None)
    d.download(args.url, mode=args.mode, fmt=args.format, quality_label=args.quality, save_subs=args.subs, save_thumb=args.thumb, save_meta=args.meta, mp3_bitrate=args.mp3_bitrate)

if __name__ == '__main__':
    if GUI_AVAILABLE:
        try:
            app = App()
            app.mainloop()
        except Exception as e:
            logger.add(f'GUI failure: {e}')
            logger.add('Falling back to CLI')
            run_cli()
    else:
        logger.add('GUI not available, running CLI')
        run_cli()
