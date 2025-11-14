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
            self.title('YTdownloader — Modern')
            # start window a bit larger; user can maximize
            self.geometry('1100x720')
            ctk.set_appearance_mode('System')
            # We will not change global theme, but use accent color for primary buttons
            self.ACCENT = "#E53935"

            # Prevent multiple concurrent downloads
            self.downloading = False

            # Make the window responsive
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(0, weight=1)

            self.output_dir = os.path.join(os.getcwd(), 'downloads')
            ensure_dir(self.output_dir)

            # Create main container frame
            self.container = ctk.CTkFrame(self, corner_radius=12)
            self.container.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
            self.container.grid_rowconfigure(1, weight=1)
            self.container.grid_columnconfigure(0, weight=1)

            # Header
            self._build_header()

            # Body (tabs + right-side info)
            body = ctk.CTkFrame(self.container, corner_radius=8)
            body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(12,10))
            body.grid_rowconfigure(0, weight=1)
            body.grid_columnconfigure(0, weight=1)
            body.grid_columnconfigure(1, weight=0)

            # Main tab area (left)
            self.tabview = ctk.CTkTabview(body, width=760, height=560)
            self.tabview.grid(row=0, column=0, sticky="nsew", padx=(0,12), pady=0)
            self.tabview.add('Download')
            self.tabview.add('Settings')
            self.tabview.add('Logs')
            self.tabview.add('About')

            # Right panel for quick actions / info
            self._build_right_panel(body)

            # Build each tab content
            self._build_download_tab()
            self._build_settings_tab()
            self._build_logs_tab()
            self._build_about_tab()

            # footer / status (in container)
            self.footer = ctk.CTkFrame(self.container, corner_radius=8)
            self.footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(0,8))
            self.footer.grid_columnconfigure(0, weight=1)
            self.status_label = ctk.CTkLabel(self.footer, text='Status: Idle', anchor='w')
            self.status_label.grid(row=0, column=0, sticky="w", padx=10, pady=8)

            # start update-check thread (non-blocking)
            threading.Thread(target=self._maybe_check_update_gui, daemon=True).start()

        def _build_header(self):
            header = ctk.CTkFrame(self.container, corner_radius=12, height=70)
            header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 0))
            header.grid_columnconfigure(1, weight=1)
        
            # ---- left: logo + title ------------------------------------------------
            logo_frame = ctk.CTkFrame(header, fg_color="transparent")
            logo_frame.grid(row=0, column=0, sticky="w", padx=(12, 0))

            # (Optional) you can put a small PNG/SVG here – fallback to text
            app_name = ctk.CTkLabel(
                logo_frame,
                text="YTdownloader",
                font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
            )
            app_name.grid(row=0, column=0, padx=(0, 8))

            ver = ctk.CTkLabel(
                logo_frame,
                text=f"v{APP_VERSION}",
                font=ctk.CTkFont(size=10),
                text_color=("gray70", "gray40")
            )
            ver.grid(row=0, column=1)

            # ---- centre: subtitle --------------------------------------------------
            subtitle = ctk.CTkLabel(
                header,
                text="YouTube • Video • Playlist • Channel",
                font=ctk.CTkFont(size=12),
                text_color=("gray60", "gray50")
            )
            subtitle.grid(row=0, column=1, sticky="w", padx=20)

            # ---- right: theme switch + quick buttons --------------------------------
            right = ctk.CTkFrame(header, fg_color="transparent")
            right.grid(row=0, column=2, sticky="e", padx=12)

            # Theme selector (System / Light / Dark)
            self.theme_var = ctk.StringVar(value=ctk.get_appearance_mode())
            theme_menu = ctk.CTkOptionMenu(
                right,
                values=["System", "Light", "Dark"],
                variable=self.theme_var,
                width=110,
                command=self._set_theme
            )
            theme_menu.grid(row=0, column=0, padx=(0, 8))

            ctk.CTkButton(
                right,
                text="Check updates",
                width=120,
                height=32,
                fg_color=self.ACCENT,
                command=self._manual_check_update
            ).grid(row=0, column=1, padx=(0, 6))

            ctk.CTkButton(
                right,
                text="Open folder",
                width=120,
                height=32,
                command=self._open_folder
            ).grid(row=0, column=2)

        def _build_right_panel(self, parent):
            panel = ctk.CTkFrame(parent, corner_radius=12, width=260)
            panel.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=0)
            panel.grid_propagate(False)

            # Title
            ctk.CTkLabel(
                panel,
                text="Quick Actions",
                font=ctk.CTkFont(size=15, weight="bold")
           ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

            # Output folder card
            folder_card = ctk.CTkFrame(panel, corner_radius=8)
            folder_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
            folder_card.grid_columnconfigure(0, weight=1)
        
            ctk.CTkLabel(folder_card, text="Output folder:", anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
            self.output_label = ctk.CTkLabel(
                folder_card,
                text=self.output_dir,
                wraplength=210,
                anchor="w",
                font=ctk.CTkFont(size=10)
            )
            self.output_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
        
            btns = ctk.CTkFrame(folder_card, fg_color="transparent")
            btns.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
            btns.grid_columnconfigure((0, 1), weight=1)
        
            ctk.CTkButton(btns, text="Change", width=80, command=self._choose_output).grid(row=0, column=0, padx=(0, 4))
            ctk.CTkButton(btns, text="Open", width=80, command=self._open_folder).grid(row=0, column=1, padx=(4, 0))
        
            # Tips carousel (simple rotating label)
            tips_frame = ctk.CTkFrame(panel, corner_radius=8)
            tips_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))
            tips_frame.grid_rowconfigure(0, weight=1)
            tips_frame.grid_columnconfigure(0, weight=1)
        
            self.tips_label = ctk.CTkLabel(
                tips_frame,
                text="Paste a YouTube URL → Choose format → Download",
                justify="left",
                wraplength=210,
                font=ctk.CTkFont(size=10)
            )
            self.tips_label.grid(row=0, column=0, sticky="w", padx=12, pady=12)
        
            # rotate tips every 4 s
            self._tip_index = 0
            self._tips = [
                "Paste a YouTube URL → Choose format → Download",
                "Use MP3 320 kbps for best audio quality",
                "Enable subtitles & thumbnails for full media",
                "Check the Logs tab for detailed progress"
            ]
            self.after(4000, self._rotate_tip)

        def _rotate_tip(self):
            self._tip_index = (self._tip_index + 1) % len(self._tips)
            self.tips_label.configure(text=self._tips[self._tip_index])
            self.after(4000, self._rotate_tip)

        def _build_download_tab(self):
            tab = self.tabview.tab('Download')
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure((0, 1), weight=1)

            # ---------- LEFT COLUMN (form) ----------
            left = ctk.CTkFrame(tab, corner_radius=12)
            left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
            left.grid_columnconfigure(1, weight=1)

            row = 0
            # URL
            ctk.CTkLabel(left, text="URL:", anchor="w").grid(row=row, column=0, sticky="w", padx=(12, 6), pady=(8, 2))
            url_frame = ctk.CTkFrame(left, fg_color="transparent")
            url_frame.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=(8, 2))
            url_frame.grid_columnconfigure(0, weight=1)
            self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="https://youtube.com/…")
            self.url_entry.grid(row=0, column=0, sticky="ew")
            ctk.CTkButton(url_frame, text="Paste", width=70, command=self._paste).grid(row=0, column=1, padx=(4, 0))
            row += 1
        
            # Mode
            ctk.CTkLabel(left, text="Mode:", anchor="w").grid(row=row, column=0, sticky="w", padx=(12, 6), pady=(12, 2))
            mode_f = ctk.CTkFrame(left, fg_color="transparent")
            mode_f.grid(row=row, column=1, sticky="w", pady=(12, 2))
            self.mode_var = ctk.StringVar(value="video")
            for txt, val in [("Video", "video"), ("Playlist", "playlist"), ("Channel", "channel")]:
                ctk.CTkRadioButton(mode_f, text=txt, variable=self.mode_var, value=val).pack(side="left", padx=4)
            row += 1

            # Format + MP3 bitrate
            fmt_frame = ctk.CTkFrame(left, fg_color="transparent")
            fmt_frame.grid(row=row, column=1, sticky="w", pady=(12, 2))
            ctk.CTkLabel(left, text="Format:", anchor="w").grid(row=row, column=0, sticky="w", padx=(12, 6), pady=(12, 2))

            self.format_var = ctk.StringVar(value="mp4")
            fmt_menu = ctk.CTkOptionMenu(fmt_frame, values=["mp4", "mp3"], variable=self.format_var,
                                        width=100, command=self._on_format_change)
            fmt_menu.pack(side="left", padx=(0, 8))

            self.mp3_bitrate_var = ctk.StringVar(value="192")
            self.mp3_bitrate_menu = ctk.CTkOptionMenu(fmt_frame, values=["128", "192", "320"],
                                            variable=self.mp3_bitrate_var, width=80, state="disabled")
            self.mp3_bitrate_menu.pack(side="left")
            row += 1

            # Quality
            ctk.CTkLabel(left, text="Quality:", anchor="w").grid(row=row, column=0, sticky="w", padx=(12, 6), pady=(12, 2))
            qual_f = ctk.CTkFrame(left, fg_color="transparent")
            qual_f.grid(row=row, column=1, sticky="w", pady=(12, 2))
            self.quality_var = ctk.StringVar(value="auto")
            self.quality_menu = ctk.CTkOptionMenu(qual_f, values=["auto", "1080", "720", "480", "360"],
                                         variable=self.quality_var, width=100)
            self.quality_menu.pack(side="left")
            row += 1
        
            # Checkboxes
            chk_f = ctk.CTkFrame(left, fg_color="transparent")
            chk_f.grid(row=row, column=1, sticky="w", pady=(12, 2))
            self.subs_var = ctk.BooleanVar(); self.thumb_var = ctk.BooleanVar(); self.meta_var = ctk.BooleanVar()
            ctk.CTkCheckBox(chk_f, text="Subtitles", variable=self.subs_var).pack(side="left", padx=6)
            ctk.CTkCheckBox(chk_f, text="Thumbnail", variable=self.thumb_var).pack(side="left", padx=6)
            ctk.CTkCheckBox(chk_f, text="Metadata", variable=self.meta_var).pack(side="left", padx=6)
            row += 1
        
            # Buttons
            btn_f = ctk.CTkFrame(left, fg_color="transparent")
            btn_f.grid(row=row, column=0, columnspan=2, sticky="e", pady=(20, 8))
            ctk.CTkButton(btn_f, text="Fetch Info", width=120, command=self._fetch_info).pack(side="left", padx=(12, 6))
            self.download_btn = ctk.CTkButton(btn_f, text="Download", width=140,
                                              fg_color=self.ACCENT, command=self._start_download_thread)
            self.download_btn.pack(side="left", padx=6)
            ctk.CTkButton(btn_f, text="Open Folder", width=120, command=self._open_folder).pack(side="left", padx=(6, 12))
            row += 1
        
            # ---------- RIGHT COLUMN (progress + status) ----------
            right = ctk.CTkFrame(tab, corner_radius=12)
            right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
            right.grid_rowconfigure(0, weight=1)
            right.grid_columnconfigure(0, weight=1)
        
            # Progress ring (circular)
            self.progress = ctk.CTkProgressBar(right, orientation="horizontal", height=12)
            self.progress.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))
            self.progress.set(0)
        
            # Status badge
            self.status_badge = ctk.CTkLabel(right, text="Idle", font=ctk.CTkFont(size=13, weight="bold"),
                                            text_color="gray30", corner_radius=8, fg_color="#f0f0f0")
            self.status_badge.grid(row=1, column=0, pady=(0, 12))

            # Small log preview
            log_prev = ctk.CTkTextbox(right, height=120, font=ctk.CTkFont(family="Consolas", size=10))
            log_prev.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
            self.small_log = log_prev   # keep reference for _log

        def _on_format_change(self, v: str):
            # Enable bitrate menu only when mp3 is selected
            try:
                if v == 'mp3':
                    self.mp3_bitrate_menu.configure(state='normal')
                else:
                    self.mp3_bitrate_menu.configure(state='disabled')
            except Exception:
                pass

        def _build_settings_tab(self):
            tab = self.tabview.tab('Settings')
            tab.grid_columnconfigure(0, weight=1)
        
            # Title
            ctk.CTkLabel(tab, text="Settings", font=ctk.CTkFont(size=18, weight="bold")
                         ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 12))

            # Appearance
            sec = ctk.CTkFrame(tab, corner_radius=10)
            sec.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
            sec.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(sec, text="Appearance:", anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=8)
            theme_menu = ctk.CTkOptionMenu(sec, values=["System", "Light", "Dark"],
                                           command=self._set_theme, width=120)
            theme_menu.grid(row=0, column=1, sticky="e", padx=12, pady=8)

            # ffmpeg status badge
            ffmpeg_ok = has_ffmpeg()
            badge_txt = "ffmpeg detected" if ffmpeg_ok else "ffmpeg missing"
            badge_fg = "#e0f7fa" if ffmpeg_ok else "#ffebee"
            badge_tc = "#006064" if ffmpeg_ok else "#b71c1c"
            ctk.CTkLabel(sec, text=badge_txt, fg_color=badge_fg, text_color=badge_tc,
                         corner_radius=6, font=ctk.CTkFont(weight="bold")).grid(row=1, column=0,
                         columnspan=2, sticky="w", padx=12, pady=(0, 8))
                         
        def _build_logs_tab(self):
            tab = self.tabview.tab('Logs')
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            # Search bar
            search_f = ctk.CTkFrame(tab, fg_color="transparent")
            search_f.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
            search_f.grid_columnconfigure(0, weight=1)
            self.search_var = ctk.StringVar()
            search_entry = ctk.CTkEntry(search_f, placeholder_text="Search logs…", textvariable=self.search_var)
            search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            search_entry.bind("<KeyRelease>", self._filter_logs)
        
            ctk.CTkButton(search_f, text="Clear", width=80, command=self._clear_logs).grid(row=0, column=1, padx=(0, 6))
            ctk.CTkButton(search_f, text="Copy All", width=90, command=self._copy_logs).grid(row=0, column=2)
        
            # Log textbox
            self.logbox = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=10))
            self.logbox.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        
            # initial fill
            self._refresh_logs()

        def _filter_logs(self, _=None):
            term = self.search_var.get().lower()
            self.logbox.delete("1.0", "end")
            for line in logger._lines:
                if term in line.lower():
                    self.logbox.insert("end", line + "\n")
            self.logbox.see("end")

        def _copy_logs(self):
            self.clipboard_clear()
            self.clipboard_append(logger.text())

        def _build_about_tab(self):
            tab = self.tabview.tab('About')
            txt = (
               "**YTdownloader – Modern UI**\n\n"
                "- **Engine:** `yt-dlp`\n"
                "- **Features:** Video / Playlist / Channel, MP3 conversion, thumbnails, metadata, auto-updates\n"
                "- **Version:** `" + APP_VERSION + "`\n\n"
                "[GitHub Repository](https://github.com/mohit52838/YTdownloader)"
            )
            lbl = ctk.CTkLabel(tab, text=txt, justify="left", wraplength=680,
                               font=ctk.CTkFont(size=12))
            lbl.grid(row=0, column=0, padx=24, pady=24, sticky="w")
            # make the link clickable
            lbl.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/mohit52838/YTdownloader"))

        def _set_status_badge(self, text: str, success: bool = None):
            """success: True=green, False=red, None=neutral"""
            self.status_badge.configure(text=text)
            if success is True:
                self.status_badge.configure(fg_color="#e8f5e9", text_color="#2e7d32")
            elif success is False:
                self.status_badge.configure(fg_color="#ffebee", text_color="#c62828")
            else:
                self.status_badge.configure(fg_color="#f5f5f5", text_color="#424242")

        # ---------- utility methods (unchanged behavior) ----------
        def _paste(self):
            try:
                txt = self.clipboard_get()
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, txt)
            except Exception:
                pass

        def _choose_output(self):
            try:
                folder = filedialog.askdirectory(initialdir=self.output_dir)
                if folder:
                    self.output_dir = folder
                    self.output_label.configure(text=self.output_dir)
            except Exception:
                pass

        def _open_folder(self):
            try:
                os.startfile(self.output_dir)
            except Exception:
                try:
                    import subprocess, sys
                    if sys.platform == 'darwin':
                        subprocess.Popen(['open', self.output_dir])
                    else:
                        subprocess.Popen(['xdg-open', self.output_dir])
                except Exception as e:
                    messagebox.showinfo('Error', f'Cannot open folder: {e}')

        def _set_theme(self, v):
            if v == 'Light':
                ctk.set_appearance_mode('Light')
            elif v == 'Dark':
                ctk.set_appearance_mode('Dark')
            else:
                ctk.set_appearance_mode('System')

        def _refresh_logs(self):
            try:
                self.logbox.delete('1.0', 'end')
                self.logbox.insert('1.0', logger.text())
            except Exception:
                pass

        def _clear_logs(self):
            logger._lines = []
            self._refresh_logs()

        def _fetch_info(self):
            url = self.url_entry.get().strip()
            if not url:
                messagebox.showwarning('Input', 'Please paste a URL first')
                return
            mode = self.mode_var.get()
            threading.Thread(target=self._fetch_info_worker, args=(url, mode), daemon=True).start()

        def _fetch_info_worker(self, url, mode):
            # keep existing behavior
            self._set_status('Fetching info...')
            try:
                opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                title = info.get('title')
                formats = info.get('formats', [])
                heights = sorted({str(f.get('height')) for f in formats if f.get('height')}, reverse=True)
                qvals = ['auto'] + [h for h in heights if h and h.isdigit()]
                qvals = qvals[:6]
                self.quality_menu.configure(values=qvals)
                self.quality_var.set('auto')
                self._log(f'Fetched info: {title}')
                self._set_status('Info fetched')
            except Exception as e:
                self._log(f'Fetch error: {e}')
                self._set_status('Fetch failed')

        def _start_download_thread(self):
            # Prevent multiple concurrent downloads
            if getattr(self, 'downloading', False):
                messagebox.showinfo('Download', 'A download is already in progress. Please wait for it to finish.')
                return
            threading.Thread(target=self._download_action, daemon=True).start()

        def _download_action(self):
            url = self.url_entry.get().strip()
            if not url:
                messagebox.showwarning('Input', 'Please paste a URL first')
                return
            fmt = self.format_var.get()
            quality = self.quality_var.get()
            subs = self.subs_var.get()
            thumb = self.thumb_var.get()
            meta = self.meta_var.get()
            mode = self.mode_var.get()
            mp3_bitrate = None
            if fmt.lower() == 'mp3':
                mp3_bitrate = self.mp3_bitrate_var.get()

            # set flag and disable button
            self.downloading = True
            try:
                try:
                    self.download_btn.configure(state='disabled')
                except Exception:
                    pass

                d = YTDLDownloader(self.output_dir, ui_log=self._log, ui_progress=self._update_progress)
                self._set_status('Downloading...')
                ok = d.download(url, mode=mode, fmt=fmt, quality_label=quality, save_subs=subs, save_thumb=thumb, save_meta=meta, mp3_bitrate=mp3_bitrate)
                if ok:
                    self._set_status('Finished')
                    messagebox.showinfo('Done', 'Downloads finished — check output folder')
                else:
                    self._set_status('Failed')
                    messagebox.showerror('Error', 'Download failed — check logs for details')
            except Exception as e:
                self._log(f'Download flow error: {e}')
                self._set_status('Error')
            finally:
                # re-enable
                try:
                    self.download_btn.configure(state='normal')
                except Exception:
                    pass
                self.downloading = False

        def _update_progress(self, pct: int):
            try:
                self.progress.set(pct/100)
                self.status_label.configure(text=f'Status: Downloading... {pct}%')
                self._refresh_logs()
            except Exception:
                pass

        def _set_status(self, s: str):
            try:
                # Update footer
                self.status_label.configure(text=f"Status: {s}")

                # Update badge in Download tab
                if "idle" in s.lower():
                    self._set_status_badge("Idle")
                elif "downloading" in s.lower():
                    self._set_status_badge("Downloading…", None)
                elif "finished" in s.lower():
                    self._set_status_badge("Finished", True)
                elif "failed" in s.lower() or "error" in s.lower():
                    self._set_status_badge("Failed", False)
                elif "fetching" in s.lower():
                    self._set_status_badge("Fetching…", None)
                else:
                    self._set_status_badge(s)
            except Exception:
                pass

        def _log(self, s: str):
            logger.add(s)
            try:
                self.logbox.insert('end', s + '\n')
                self.logbox.see('end')
            except Exception:
                pass

        def _maybe_check_update_gui(self):
            try:
                download_url, latest = check_for_update()
                if download_url and latest:
                    # Prompt user (non-blocking)
                    ans = messagebox.askyesno('Update available', f'New version {latest} is available. Do you want to download and install now?')
                    if ans:
                        if getattr(sys, 'frozen', False) and sys.executable.lower().endswith('.exe'):
                            install_update(download_url)
                        else:
                            messagebox.showinfo('Update available', f'New version {latest} available. Download it from:\n{download_url}')
            except Exception:
                pass

        def _manual_check_update(self):
            try:
                download_url, latest = check_for_update()
                if download_url and latest:
                    if messagebox.askyesno('Update available', f'New version {latest} is available. Open release page?'):
                        # open releases page in browser
                        import webbrowser
                        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
                else:
                    messagebox.showinfo('Update', 'No updates found')
            except Exception:
                messagebox.showinfo('Update', 'Update check failed')

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
