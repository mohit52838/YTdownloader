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

    def _build_opts(self, fmt: str, to_mp3: bool, save_subs: bool, save_thumb: bool, save_meta: bool, quality_label: str):
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
        }

        # If mp3 conversion requested, prefer bestaudio + ffmpeg postprocessor (yt-dlp will require ffmpeg)
        if to_mp3:
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            return opts

        # Not mp3: select video format
        # If user asked a specific height, yt-dlp would try to grab separate bestvideo+bestaudio and merge;
        # merging needs ffmpeg — so if ffmpeg is missing we fall back to single-file mp4 where possible.
        if quality_label and quality_label != 'auto':
            try:
                h = int(re.sub(r'[^0-9]', '', quality_label))
                requested_format = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
            except Exception:
                requested_format = 'best'
        else:
            requested_format = 'best'

        # If ffmpeg is not installed and requested format requires merging, fallback to a single-file format
        if not has_ffmpeg():
            # log a warning via self._log (will appear in GUI logs)
            self._log("ffmpeg not found on PATH — forcing single-file download to avoid merge errors.")
            # Prefer mp4 single-file if available, else best fallback
            # 'best[ext=mp4]/best' tells yt-dlp to pick a single-file mp4 if possible
            opts['format'] = 'best[ext=mp4]/best'
            # don't abort on merge errors because we prevented merging
            opts['abort_on_unavailable_fragments'] = False
        else:
            # ffmpeg present — use requested format
            opts['format'] = requested_format

        if save_meta:
            opts['writedescription'] = True
            opts['writeinfojson'] = True
        return opts
    
    def download(self, url: str, mode: str='video', fmt: str='mp4',
                 quality_label: str='auto', save_subs: bool=False,
                 save_thumb: bool=False, save_meta: bool=False) -> bool:

        url = url.strip()
        to_mp3 = (fmt.lower() == 'mp3')
        self._log(f'Starting download: mode={mode} url={url} format={fmt} quality={quality_label}')

        try:
            opts = self._build_opts(fmt, to_mp3, save_subs, save_thumb, save_meta, quality_label)

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
        api = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
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
            self.title('YouTube Downloader — yt-dlp')
            self.geometry('920x680')
            ctk.set_appearance_mode('System')
            ctk.set_default_color_theme('blue')
            self.output_dir = os.path.join(os.getcwd(), 'downloads')
            ensure_dir(self.output_dir)
            self._create_ui()
            self.downloader = None
            threading.Thread(target=self._maybe_check_update_gui, daemon=True).start()
        def _create_ui(self):
            self.tabview = ctk.CTkTabview(self, width=900, height=640)
            self.tabview.pack(padx=10, pady=10, fill='both', expand=True)
            self.tabview.add('Download')
            self.tabview.add('Settings')
            self.tabview.add('Logs')
            self.tabview.add('About')
            self._build_download_tab()
            self._build_settings_tab()
            self._build_logs_tab()
            self._build_about_tab()
        def _build_download_tab(self):
            tab = self.tabview.tab('Download')
            self.url_entry = ctk.CTkEntry(tab, width=740, height=36, placeholder_text='Paste video / playlist / channel URL here')
            self.url_entry.place(x=20, y=20)
            self.paste_btn = ctk.CTkButton(tab, text='Paste', width=100, height=36, command=self._paste)
            self.paste_btn.place(x=770, y=20)
            self.mode_var = ctk.StringVar(value='video')
            ctk.CTkLabel(tab, text='Mode:').place(x=20, y=70)
            ctk.CTkRadioButton(tab, text='Single Video', variable=self.mode_var, value='video').place(x=80, y=70)
            ctk.CTkRadioButton(tab, text='Playlist', variable=self.mode_var, value='playlist').place(x=200, y=70)
            ctk.CTkRadioButton(tab, text='Channel', variable=self.mode_var, value='channel').place(x=320, y=70)
            self.format_var = ctk.StringVar(value='mp4')
            ctk.CTkLabel(tab, text='Format:').place(x=20, y=110)
            ctk.CTkOptionMenu(tab, values=['mp4','mp3'], variable=self.format_var, width=120, height=36).place(x=80, y=110)
            ctk.CTkLabel(tab, text='Quality:').place(x=220, y=110)
            self.quality_var = ctk.StringVar(value='auto')
            self.quality_menu = ctk.CTkOptionMenu(tab, values=['auto','1080','720','480','360'], variable=self.quality_var, width=140, height=36)
            self.quality_menu.place(x=280, y=110)
            self.subs_var = ctk.BooleanVar(value=False)
            self.thumb_var = ctk.BooleanVar(value=False)
            self.meta_var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(tab, text='Download Subtitles', variable=self.subs_var).place(x=20, y=150)
            ctk.CTkCheckBox(tab, text='Download Thumbnail', variable=self.thumb_var).place(x=240, y=150)
            ctk.CTkCheckBox(tab, text='Save Metadata (JSON)', variable=self.meta_var).place(x=460, y=150)
            ctk.CTkLabel(tab, text='Output Folder:').place(x=20, y=190)
            self.output_label = ctk.CTkLabel(tab, text=self.output_dir)
            self.output_label.place(x=120, y=190)
            ctk.CTkButton(tab, text='Choose', width=100, height=36, command=self._choose_output).place(x=770, y=190)
            ctk.CTkButton(tab, text='Fetch Info', width=120, height=36, command=self._fetch_info).place(x=20, y=230)
            ctk.CTkButton(tab, text='Download', width=120, height=36, fg_color='#1f6aa5', command=self._start_download_thread).place(x=160, y=230)
            ctk.CTkButton(tab, text='Open Folder', width=120, height=36, command=self._open_folder).place(x=300, y=230)
            self.progress = ctk.CTkProgressBar(tab, width=840)
            self.progress.place(x=20, y=280)
            self.status_label = ctk.CTkLabel(tab, text='Status: Idle')
            self.status_label.place(x=20, y=320)
        def _build_settings_tab(self):
            tab = self.tabview.tab('Settings')
            ctk.CTkLabel(tab, text='Settings').place(x=20, y=20)
            ctk.CTkLabel(tab, text='Appearance:').place(x=20, y=80)
            theme_menu = ctk.CTkOptionMenu(tab, values=['System','Light','Dark'], command=self._set_theme)
            theme_menu.place(x=120, y=80)
        def _build_logs_tab(self):
            tab = self.tabview.tab('Logs')
            self.logbox = ctk.CTkTextbox(tab, width=860, height=480)
            self.logbox.place(x=20, y=20)
            ctk.CTkButton(tab, text='Refresh', width=120, height=36, command=self._refresh_logs).place(x=20, y=520)
            ctk.CTkButton(tab, text='Clear', width=120, height=36, command=self._clear_logs).place(x=160, y=520)
        def _build_about_tab(self):
            tab = self.tabview.tab('About')
            txt = 'YouTube Downloader\nEngine: yt-dlp\nSupports: video/playlist/channel, mp3 conversion, subtitles, thumbnails, metadata'
            ctk.CTkLabel(tab, text=txt, justify='left').place(x=20, y=20)
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
            self.downloader = YTDLDownloader(self.output_dir, ui_log=self._log, ui_progress=self._update_progress)
            try:
                self._set_status('Downloading...')
                ok = self.downloader.download(url, mode=mode, fmt=fmt, quality_label=quality, save_subs=subs, save_thumb=thumb, save_meta=meta)
                if ok:
                    self._set_status('Finished')
                    messagebox.showinfo('Done', 'Downloads finished — check output folder')
                else:
                    self._set_status('Failed')
                    messagebox.showerror('Error', 'Download failed — check logs for details')
            except Exception as e:
                self._log(f'Download flow error: {e}')
                self._set_status('Error')
                messagebox.showerror('Error', f'Download failed: {e}')

        def _update_progress(self, pct: int):
            try:
                for child in self.tabview.tab('Download').winfo_children():
                    if isinstance(child, ctk.CTkProgressBar):
                        child.set(pct/100)
                        break
                self.status_label.configure(text=f'Status: Downloading... {pct}%')
                self._refresh_logs()
            except Exception:
                pass
        def _set_status(self, s: str):
            try:
                self.status_label.configure(text=f'Status: {s}')
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
                    def on_choice(ans: str):
                        if ans == 'yes':
                            if getattr(sys, 'frozen', False) and sys.executable.lower().endswith('.exe'):
                                install_update(download_url)
                            else:
                                messagebox.showinfo('Update available', f'New version {latest} available. Download it from:\n{download_url}')
                    ans = messagebox.askyesno('Update available', f'New version {latest} is available. Do you want to download and install now?')
                    if ans:
                        on_choice('yes')
            except Exception:
                pass

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
    d.download(args.url, mode=args.mode, fmt=args.format, quality_label=args.quality, save_subs=args.subs, save_thumb=args.thumb, save_meta=args.meta)

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
