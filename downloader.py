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
                
                # Extract speed and ETA
                speed = d.get('speed') # bytes/sec
                eta = d.get('eta') # seconds
                
                if self.ui_progress:
                    try:
                        self.ui_progress(percent, speed, eta)
                    except Exception:
                        pass
            elif status == 'finished':
                if self.ui_progress:
                    try:
                        self.ui_progress(100, 0, 0)
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
            self.title("YTdownloader – Premium Masculine")
            self.geometry("1200x800")
            self.resizable(True, True)
            ctk.set_appearance_mode("Light") 
            
            # -- Premium Masculine Palette --
            self.BG_COLOR = "#eef2ff"        # Soft Ultra-Light Blue
            self.SIDEBAR_COLOR = "#141E30"   # Dark Royal Blue (Gradient Start)
            self.PANEL_COLOR = "#FFFFFF"     # Pure White Glass
            self.ACCENT = "#3A47D5"          # Indigo
            self.ACCENT_HOVER = "#243B55"    # Darker Blue
            self.TEXT_SIDEBAR = "#FFFFFF"    # White Text (High Contrast)
            self.TEXT_PRIMARY = "#141E30"    # Dark Blue/Black
            self.TEXT_SECONDARY = "#6B7280"  # Gray 500
            self.BORDER_COLOR = "#dce6ff"    # Faint Blue Border
            self.INPUT_BG = "#FFFFFF"        # White Input
            self.INPUT_FOCUS = "#3A47D5"     # Indigo Focus
            self.BTN_MAIN = "#D31027"        # Deep Red
            self.BTN_MAIN_HOVER = "#EA384D"  # Magenta-Red

            self.configure(fg_color=self.BG_COLOR)

            # Layout - Floating Panels
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=1)

            self.output_dir = os.path.join(os.getcwd(), "downloads")
            ensure_dir(self.output_dir)

            # -- Floating Sidebar --
            self.sidebar_container = ctk.CTkFrame(self, fg_color="transparent")
            self.sidebar_container.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
            self.sidebar_container.grid_rowconfigure(0, weight=1)
            self.sidebar_container.grid_columnconfigure(0, weight=1)

            self.sidebar = ctk.CTkFrame(self.sidebar_container, corner_radius=24, fg_color=self.SIDEBAR_COLOR, 
                                        border_width=0)
            self.sidebar.grid(row=0, column=0, sticky="nsew")
            self.sidebar.grid_rowconfigure(5, weight=1) 

            # Branding
            brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
            brand_frame.grid(row=0, column=0, padx=25, pady=(35, 20), sticky="w")
            
            ctk.CTkLabel(brand_frame, text="⚡", font=ctk.CTkFont(size=24), text_color=self.TEXT_SIDEBAR).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(brand_frame, text="YTdownloader", 
                         font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                         text_color=self.TEXT_SIDEBAR).pack(side="left")

            ctk.CTkLabel(self.sidebar, text=f"v{APP_VERSION}", 
                         font=ctk.CTkFont(size=11), text_color="#A5B4FC").grid(row=1, column=0, padx=25, pady=(0, 35), sticky="w")

            # Nav Buttons
            self.nav_buttons = []
            self._create_nav_btn("Download", "⬇", self._show_download, 2)
            self._create_nav_btn("Settings", "⚙", self._show_settings, 3)
            self._create_nav_btn("Logs", "☰", self._show_logs, 4)
            self._create_nav_btn("About", "ℹ", self._show_about, 5)

            # -- Floating Content Area --
            self.content_container = ctk.CTkFrame(self, fg_color="transparent")
            self.content_container.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
            self.content_container.grid_rowconfigure(0, weight=1)
            self.content_container.grid_columnconfigure(0, weight=1)

            # Frames
            self.frames = {}
            self.frames["Download"] = self._build_download_frame()
            self.frames["Settings"] = self._build_settings_frame()
            self.frames["Logs"] = self._build_logs_frame()
            self.frames["About"] = self._build_about_frame()

            # Show default
            self._select_nav("Download")

            # Update check
            threading.Thread(target=self._maybe_check_update_gui, daemon=True).start()

        def _create_nav_btn(self, text, icon, command, row):
            btn = ctk.CTkButton(self.sidebar, text=f"  {icon}   {text}", command=lambda: self._select_nav(text),
                                fg_color="transparent", text_color="#E0E7FF", 
                                hover_color="#243B55", anchor="w", height=48, corner_radius=14,
                                font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"))
            btn.grid(row=row, column=0, sticky="ew", padx=15, pady=6)
            self.nav_buttons.append((text, btn))

        def _select_nav(self, name):
            for txt, btn in self.nav_buttons:
                if txt == name:
                    # Active: Lighter Blue/Indigo Glow
                    btn.configure(fg_color="#3A47D5", text_color=self.TEXT_SIDEBAR, font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
                else:
                    btn.configure(fg_color="transparent", text_color="#E0E7FF", font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"))
            
            for f in self.frames.values():
                f.grid_remove()
            self.frames[name].grid(row=0, column=0, sticky="nsew")

        # ------------------------------------------------------------------
        # DOWNLOAD FRAME
        # ------------------------------------------------------------------
        def _build_download_frame(self):
            # Main Panel
            frame = ctk.CTkFrame(self.content_container, corner_radius=24, fg_color=self.PANEL_COLOR, border_width=1, border_color=self.BORDER_COLOR)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(3, weight=1) 

            # 1. Header
            header = ctk.CTkFrame(frame, fg_color="transparent")
            header.grid(row=0, column=0, sticky="ew", padx=35, pady=(35, 20))
            ctk.CTkLabel(header, text="New Download", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), 
                         text_color=self.TEXT_PRIMARY).pack(side="left")
            
            # 2. Input Section
            input_frame = ctk.CTkFrame(frame, fg_color="transparent")
            input_frame.grid(row=1, column=0, sticky="ew", padx=35, pady=10)
            input_frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(input_frame, text="Video URL", text_color=self.TEXT_SECONDARY,
                         font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0,6))
            
            url_box = ctk.CTkFrame(input_frame, fg_color="transparent")
            url_box.grid(row=1, column=0, sticky="ew")
            url_box.grid_columnconfigure(0, weight=1)
            
            # Input with Indigo Glow
            self.url_entry = ctk.CTkEntry(url_box, placeholder_text="Paste link here...", height=50, corner_radius=16,
                                          border_width=1, border_color=self.BORDER_COLOR, fg_color=self.INPUT_BG, 
                                          text_color=self.TEXT_PRIMARY, placeholder_text_color=self.TEXT_SECONDARY)
            self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12))
            
            self.url_entry.bind("<FocusIn>", lambda e: self.url_entry.configure(border_color=self.INPUT_FOCUS))
            self.url_entry.bind("<FocusOut>", lambda e: self.url_entry.configure(border_color=self.BORDER_COLOR))
            
            ctk.CTkButton(url_box, text="Paste", width=90, height=50, corner_radius=16, command=self._paste,
                          fg_color="#eef2ff", text_color=self.ACCENT, hover_color=self.BORDER_COLOR).grid(row=0, column=1)

            # 3. Options Grid (Premium Cards)
            opts_frame = ctk.CTkFrame(frame, fg_color="transparent")
            opts_frame.grid(row=2, column=0, sticky="ew", padx=35, pady=20)
            opts_frame.grid_columnconfigure((0,1,2), weight=1)

            def create_premium_card(parent, title, col):
                # Inner cards with subtle blue border
                card = ctk.CTkFrame(parent, fg_color="#FFFFFF", corner_radius=18, border_width=1, border_color=self.BORDER_COLOR)
                card.grid(row=0, column=col, sticky="nsew", padx=8, pady=8)
                ctk.CTkLabel(card, text=title, text_color=self.TEXT_PRIMARY, 
                             font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=18, pady=(18, 8))
                return card

            # Col 1: Mode
            c1 = create_premium_card(opts_frame, "Mode", 0)
            self.mode_var = ctk.StringVar(value="video")
            for txt, val in [("Video", "video"), ("Playlist", "playlist"), ("Channel", "channel")]:
                ctk.CTkRadioButton(c1, text=txt, variable=self.mode_var, value=val, 
                                   text_color=self.TEXT_PRIMARY, fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER,
                                   font=ctk.CTkFont(size=12)).pack(anchor="w", padx=18, pady=5)
            
            # Col 2: Format
            c2 = create_premium_card(opts_frame, "Format", 1)
            self.format_var = ctk.StringVar(value="mp4")
            ctk.CTkOptionMenu(c2, values=["mp4", "mp3"], variable=self.format_var, command=self._on_format_change, width=130, height=32,
                              fg_color="#eef2ff", button_color="#dce6ff", button_hover_color="#c7d2fe", 
                              text_color=self.ACCENT, dropdown_fg_color=self.PANEL_COLOR, dropdown_text_color=self.TEXT_PRIMARY).pack(anchor="w", padx=18, pady=(0,8))
            
            self.quality_var = ctk.StringVar(value="auto")
            self.quality_menu = ctk.CTkOptionMenu(c2, values=["auto", "1080", "720", "480"], variable=self.quality_var, width=130, height=32,
                                                  fg_color="#eef2ff", button_color="#dce6ff", button_hover_color="#c7d2fe", 
                                                  text_color=self.ACCENT, dropdown_fg_color=self.PANEL_COLOR, dropdown_text_color=self.TEXT_PRIMARY)
            self.quality_menu.pack(anchor="w", padx=18)

            self.mp3_bitrate_var = ctk.StringVar(value="192")
            self.mp3_bitrate_menu = ctk.CTkOptionMenu(c2, values=["128", "192", "320"], variable=self.mp3_bitrate_var, width=130, height=32,
                                                      fg_color="#eef2ff", button_color="#dce6ff", button_hover_color="#c7d2fe", 
                                                      text_color=self.ACCENT, dropdown_fg_color=self.PANEL_COLOR, dropdown_text_color=self.TEXT_PRIMARY)
            self.mp3_bitrate_menu.pack_forget()

            # Col 3: Extras
            c3 = create_premium_card(opts_frame, "Extras", 2)
            self.subs_var = ctk.BooleanVar()
            self.thumb_var = ctk.BooleanVar()
            self.meta_var = ctk.BooleanVar()
            for txt, var in [("Subtitles", self.subs_var), ("Thumbnail", self.thumb_var), ("Metadata", self.meta_var)]:
                ctk.CTkCheckBox(c3, text=txt, variable=var, text_color=self.TEXT_PRIMARY, 
                                fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER, border_color=self.BORDER_COLOR,
                                font=ctk.CTkFont(size=12)).pack(anchor="w", padx=18, pady=5)

            # 4. Action Area
            action_frame = ctk.CTkFrame(frame, fg_color="transparent")
            action_frame.grid(row=4, column=0, sticky="ew", padx=35, pady=30)
            
            self.download_btn = ctk.CTkButton(action_frame, text="Start Download", height=60, corner_radius=30,
                                              font=ctk.CTkFont(size=16, weight="bold"),
                                              fg_color=self.BTN_MAIN, hover_color=self.BTN_MAIN_HOVER,
                                              command=self._start_download_thread)
            self.download_btn.pack(fill="x")

            # 5. Progress Area
            self.progress_frame = ctk.CTkFrame(frame, fg_color="#eef2ff", corner_radius=18)
            self.progress_frame.grid(row=5, column=0, sticky="ew", padx=35, pady=(0, 35))
            self.progress_frame.grid_columnconfigure(0, weight=1)

            self.status_label = ctk.CTkLabel(self.progress_frame, text="Ready", anchor="w", 
                                             text_color=self.TEXT_PRIMARY, font=ctk.CTkFont(size=13, weight="normal"))
            self.status_label.grid(row=0, column=0, sticky="w", padx=20, pady=(15, 6))

            self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=10, corner_radius=5, progress_color=self.ACCENT, fg_color=self.BORDER_COLOR)
            self.progress_bar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 6))
            self.progress_bar.set(0)

            self.details_label = ctk.CTkLabel(self.progress_frame, text="", font=ctk.CTkFont(size=11), text_color=self.TEXT_SECONDARY, anchor="w")
            self.details_label.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 15))

            return frame

        def _build_settings_frame(self):
            frame = ctk.CTkFrame(self.content_container, corner_radius=24, fg_color=self.PANEL_COLOR, border_width=1, border_color=self.BORDER_COLOR)
            frame.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(frame, text="Settings", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=35, pady=35)

            # Output Dir
            out_f = ctk.CTkFrame(frame, fg_color="#eef2ff", corner_radius=18)
            out_f.grid(row=1, column=0, sticky="ew", padx=35, pady=(0, 15))
            out_f.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(out_f, text="Download Location", text_color=self.TEXT_PRIMARY, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=20, pady=20)
            self.path_label = ctk.CTkLabel(out_f, text=self.output_dir, text_color=self.TEXT_SECONDARY, anchor="e")
            self.path_label.grid(row=0, column=1, padx=15)
            
            btn_style = {"fg_color": self.PANEL_COLOR, "text_color": self.TEXT_PRIMARY, "hover_color": self.BORDER_COLOR, "height": 36, "corner_radius": 12}
            ctk.CTkButton(out_f, text="Change", width=80, command=self._choose_output, **btn_style).grid(row=0, column=2, padx=15)
            ctk.CTkButton(out_f, text="Open", width=80, command=self._open_folder, **btn_style).grid(row=0, column=3, padx=(0,20))

            # Appearance
            app_f = ctk.CTkFrame(frame, fg_color="#eef2ff", corner_radius=18)
            app_f.grid(row=2, column=0, sticky="ew", padx=35, pady=0)
            
            ctk.CTkLabel(app_f, text="Theme", text_color=self.TEXT_PRIMARY, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=20, pady=20)
            ctk.CTkOptionMenu(app_f, values=["System", "Light", "Dark"], command=self._set_theme,
                              fg_color=self.PANEL_COLOR, button_color="#dce6ff", button_hover_color="#c7d2fe", 
                              text_color=self.TEXT_PRIMARY, dropdown_fg_color=self.PANEL_COLOR, dropdown_text_color=self.TEXT_PRIMARY).pack(side="right", padx=20)

            return frame

        def _build_logs_frame(self):
            frame = ctk.CTkFrame(self.content_container, corner_radius=24, fg_color=self.PANEL_COLOR, border_width=1, border_color=self.BORDER_COLOR)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(1, weight=1)

            ctk.CTkLabel(frame, text="Logs", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=35, pady=35)

            self.logbox = ctk.CTkTextbox(frame, font=ctk.CTkFont(family="Consolas", size=12), corner_radius=16,
                                         fg_color="#eef2ff", text_color=self.TEXT_PRIMARY)
            self.logbox.grid(row=1, column=0, sticky="nsew", padx=35, pady=(0, 20))
            
            ctrls = ctk.CTkFrame(frame, fg_color="transparent")
            ctrls.grid(row=2, column=0, sticky="ew", padx=35, pady=(0, 35))
            
            btn_style = {"fg_color": "#eef2ff", "text_color": self.TEXT_PRIMARY, "hover_color": self.BORDER_COLOR, "height": 36, "corner_radius": 12}
            for txt, cmd in [("Refresh", self._refresh_logs), ("Clear", self._clear_logs), ("Copy All", self._copy_logs)]:
                ctk.CTkButton(ctrls, text=txt, width=90, command=cmd, **btn_style).pack(side="left", padx=(0, 10))
            
            self._refresh_logs()
            return frame

        def _build_about_frame(self):
            frame = ctk.CTkFrame(self.content_container, corner_radius=24, fg_color=self.PANEL_COLOR, border_width=1, border_color=self.BORDER_COLOR)
            frame.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(frame, text="About", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_PRIMARY).pack(pady=(50, 15))
            
            ctk.CTkLabel(frame, text="YTdownloader", font=ctk.CTkFont(size=30, weight="bold"), text_color=self.ACCENT).pack(pady=(0, 8))
            ctk.CTkLabel(frame, text=f"v{APP_VERSION}", text_color=self.TEXT_SECONDARY).pack(pady=(0, 35))
            
            desc = "A premium masculine experience.\nDesigned for professionals."
            ctk.CTkLabel(frame, text=desc, font=ctk.CTkFont(size=15), justify="center", text_color=self.TEXT_PRIMARY).pack(pady=10)

            ctk.CTkButton(frame, text="Visit GitHub", command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"),
                          fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER, height=48, width=160, corner_radius=24).pack(pady=40)
            
            return frame

        # ------------------------------------------------------------------
        # LOGIC
        # ------------------------------------------------------------------
        def _show_download(self): self._select_nav("Download")
        def _show_settings(self): self._select_nav("Settings")
        def _show_logs(self): self._select_nav("Logs")
        def _show_about(self): self._select_nav("About")

        def _on_format_change(self, v):
            if v == "mp3":
                self.quality_menu.pack_forget()
                self.mp3_bitrate_menu.pack(anchor="w")
            else:
                self.mp3_bitrate_menu.pack_forget()
                self.quality_menu.pack(anchor="w")

        def _paste(self):
            try: 
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, self.clipboard_get())
            except: pass

        def _choose_output(self):
            f = filedialog.askdirectory(initialdir=self.output_dir)
            if f:
                self.output_dir = f
                self.path_label.configure(text=f)

        def _open_folder(self):
            try: os.startfile(self.output_dir)
            except: pass

        def _set_theme(self, m): ctk.set_appearance_mode(m)

        def _refresh_logs(self):
            self.logbox.delete("1.0", "end")
            self.logbox.insert("1.0", logger.text())

        def _clear_logs(self):
            logger._lines.clear()
            self._refresh_logs()

        def _copy_logs(self):
            self.clipboard_clear()
            self.clipboard_append(logger.text())

        def _start_download_thread(self):
            if getattr(self, 'downloading', False): return
            threading.Thread(target=self._download_action, daemon=True).start()

        def _download_action(self):
            url = self.url_entry.get().strip()
            if not url: return messagebox.showwarning("Input", "Please enter a URL")
            
            self.downloading = True
            self.download_btn.configure(state="disabled", text="Downloading...")
            self.status_label.configure(text="Starting...", text_color="text_color")
            self.progress_bar.set(0)
            self.details_label.configure(text="")

            d = YTDLDownloader(self.output_dir, ui_log=self._log_gui, ui_progress=self._update_progress)
            
            ok = d.download(url,
                            mode=self.mode_var.get(),
                            fmt=self.format_var.get(),
                            quality_label=self.quality_var.get(),
                            save_subs=self.subs_var.get(),
                            save_thumb=self.thumb_var.get(),
                            save_meta=self.meta_var.get(),
                            mp3_bitrate=self.mp3_bitrate_var.get() if self.format_var.get() == "mp3" else None)
            
            self.downloading = False
            self.download_btn.configure(state="normal", text="Start Download")
            
            if ok:
                self.status_label.configure(text="Download Complete", text_color="green")
                self.progress_bar.set(1)
                messagebox.showinfo("Success", "Download completed!")
            else:
                self.status_label.configure(text="Download Failed", text_color="red")
                messagebox.showerror("Error", "Download failed. Check logs.")

        def _update_progress(self, pct, speed=None, eta=None):
            # pct is 0-100
            self.progress_bar.set(pct / 100)
            
            status_txt = f"Downloading... {pct}%"
            details = []
            
            if speed:
                # speed is bytes/s
                mb_s = speed / 1024 / 1024
                details.append(f"{mb_s:.1f} MB/s")
            
            if eta:
                # eta is seconds
                m, s = divmod(eta, 60)
                if m > 0: details.append(f"{int(m)}m {int(s)}s left")
                else: details.append(f"{int(s)}s left")
                
            self.status_label.configure(text=status_txt)
            self.details_label.configure(text=" • ".join(details))

        def _log_gui(self, s):
            # Also log to file/console via logger
            # logger.add(s) is called by YTDLDownloader, so we just update UI if needed
            # But YTDLDownloader calls ui_log, which we passed as this function.
            # Wait, YTDLDownloader calls logger.add() AND ui_log().
            # So we just need to refresh logs if the log tab is open, or just let the user refresh.
            # For real-time logs, we can append to the logbox if it exists.
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
