# YouTube Downloader

A robust Python script to download YouTube videos with quality selection, proxy support, and subtitle/audio merging.

## Features

- **Clean URLs**: Automatically strips tracking and playlist parameters.
- **Proxy Support**: Connects through `http://127.0.0.1:8888` if available, with SSL bypass for MITM proxies (e.g., Fiddler/Charles).
- **Quality Menu**: Lists all available formats (WebM/MP4) with sizes and codecs.
- **FFmpeg Integration**: Automatically merges video and audio tracks. Uses a "pip version" of FFmpeg if no system installer is found.
- **Dubs & Subs**: Merges all available audio languages and subtitles into the final MKV container.

## Installation

1. **Clone the repository**:

   ```bash
   git clone <your-repo-url>
   cd youtube
   ```

2. **Install Dependencies**:
   This project uses `static-ffmpeg`, so you don't need to manually install FFmpeg on your system.

   ```bash
   pip install -r requirements.txt
   ```

3. **Run**:
   ```bash
   python youtube.py
   ```

## Requirements

- Python 3.7+
- All other dependencies (`yt-dlp`, `requests`, `static-ffmpeg`) are handled by the script or `requirements.txt`.

## Note on FFmpeg

If you prefer not to use the "pip version" (`static-ffmpeg`), you can install FFmpeg manually:

- **Windows**: `winget install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`
