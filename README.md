# 🎬 YTdownloader  
### A Modern YouTube Video/Playlist/Channel Downloader (GUI + CLI) powered by **yt-dlp**

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge">
  <img src="https://img.shields.io/badge/Platform-Windows-green?style=for-the-badge">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-1f6aa5?style=for-the-badge">
  <img src="https://img.shields.io/badge/Downloader-yt--dlp-orange?style=for-the-badge">
</div>

---

## ⚡ Overview

**YTdownloader** is a fast, clean, feature-rich desktop app for downloading:

- 🎞️ YouTube **videos**
- 📼 **Playlists**
- 📺 **Channels**
- 🎧 Convert directly to **MP3**
- 🖼️ Download **thumbnails**
- 📝 Download **metadata, JSON & subtitles**
- 🚀 Optional **self-updating support**
- 🖥️ Works in both **GUI mode** and **CLI mode**

All downloads use **yt-dlp**, the modern fork of youtube-dl — giving the best speed and highest format compatibility.

---

## ✨ Features

### 🎨 Modern CustomTkinter UI  
- Clean interface  
- Dark/Light/System themes  
- Live progress bar  
- Status updates  
- Logs tab  

### 🎯 Smart Format Handling  
- Auto fallback when `ffmpeg` is missing  
- MP4 / MP3 support  
- Quality selection (1080p, 720p, 480p…)  
- Automatic merging when ffmpeg is available  

### 📦 Playlist & Channel Support  
Just paste any playlist/channel URL and download everything.

### 🔄 Auto-Update System  
- Checks latest GitHub Release  
- Prompts user when a newer version exists  
- Can automatically download & replace `.exe`

### 🪶 Lightweight  
- Only one Python file (`downloader.py`)  
- No unnecessary dependencies  

---

## 📥 Installation

### Option 1 — **Run the EXE**
(If you uploaded the .exe release)
1. Go to **Releases**  
2. Download the latest `.exe`  
3. Run it — no installation required

### Option 2 — **Run from Python source**
Requirements:

```sh
pip install yt-dlp customtkinter
