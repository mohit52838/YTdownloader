# 🎬 YTdownloader  
### A Modern YouTube Video/Playlist/Channel Downloader (GUI + CLI) powered by **yt-dlp**

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge">
  <img src="https://img.shields.io/badge/Platform-Windows-green?style=for-the-badge">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-1f6aa5?style=for-the-badge">
  <img src="https://img.shields.io/badge/Downloader-yt--dlp-orange?style=for-the-badge">
</div>

---

## 📥 Download (EXE)

👉 **Download latest version:**  
https://github.com/mohit52838/YTdownloader/releases/latest

**SHA-256 checksum:**
f8462325921d6f4a3603e5f2ab476cb3e665f7f6b4c26b0d4d8432f313119755

---

## ⚡ Overview

**YTdownloader** is a fast, clean, feature-rich desktop application for downloading:

- 🎞️ YouTube **videos**  
- 📼 **Playlists**  
- 📺 **Channels**  
- 🎧 Convert directly to **MP3**  
- 🖼️ **Thumbnails**  
- 📝 **Metadata, JSON & subtitles**  
- 🔄 Built-in **auto-update** support  
- 🖥️ Works in both **GUI mode** and **CLI mode**

Engine powered by **yt-dlp** for maximum speed and compatibility.

---

## ✨ Features

### 🎨 Modern CustomTkinter UI  
- Clean & simple interface  
- Dark / Light / System themes  
- Real-time progress bar  
- Status updates  
- Built-in logs viewer  

### 🎯 Smart Download Handling  
- MP4 / MP3 formats  
- Quality selection (1080p / 720p / 480p / 360p / auto)  
- Automatic merging when **ffmpeg** is installed  
- Safe fallback when ffmpeg is **NOT** installed (no merge errors)

### 📦 Playlist & Channel Support  
Paste any playlist or channel URL — downloads everything automatically.

### 🔄 Auto-Update System  
- Checks GitHub Releases  
- Notifies user when a new update is available  
- Can auto-download & replace the EXE  

### 🪶 Lightweight  
- One single file: `downloader.py`  
- No unnecessary files or libs  

---

## 📁 Where do downloads go?

### GUI version  
Downloads are saved inside a **downloads/** folder (same folder as the EXE).  
You can change the folder from the UI.

### CLI version  
Defaults to a **downloads/** folder unless you specify:

-o "path/to/folder"

yaml
Copy code

---

## 📥 Installation

### Option 1 — **Run the EXE** (Recommended)
1. Go to **Releases**  
2. Download `YTdownloader.exe`  
3. Run it  
No installation required.

---

### Option 2 — **Run from Python source**

Install dependencies:

```sh
pip install yt-dlp customtkinter requests
Run:

sh
Copy code
python downloader.py
🖥️ CLI Usage
sh
Copy code
python downloader.py --url "<video_url>" --format mp4 --quality 720
Full options
css
Copy code
--url / -u        YouTube URL
--mode            video / playlist / channel
--format          mp4 / mp3
--quality         auto / 1080 / 720 / 480 / 360
--output / -o     Output folder
--subs            Download subtitles
--thumb           Download thumbnail
--meta            Save metadata JSON
🔨 Build Your Own EXE
sh
Copy code
pip install pyinstaller
pyinstaller --onefile --windowed downloader.py
EXE will be in the dist/ folder.

🤝 Contributing
Pull requests, issues, and improvements are welcome!

⭐ Support the Project
If you like this project, give it a star ⭐ on GitHub!

yaml
Copy code
