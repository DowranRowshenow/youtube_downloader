#!/usr/bin/env python3
"""
YouTube & Playlist Downloader
- Detects Playlists automatically
- Skips unavailable/private videos automatically
- Audio Only (MP3) or MKV Video options
"""

import sys
import subprocess
import shutil
import os
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


# -- Dependency check --
def install_dependencies():
    if getattr(sys, "frozen", False):
        return
    ffmpeg_in_path = shutil.which("ffmpeg") is not None
    required = ["yt-dlp", "requests"]
    if not ffmpeg_in_path:
        required.append("static-ffmpeg")
    for pkg in required:
        try:
            if pkg == "yt-dlp":
                import yt_dlp
            elif pkg == "requests":
                import requests
            elif pkg == "static-ffmpeg":
                import static_ffmpeg
        except ImportError:
            print(f"[!] {pkg} not found. Installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


install_dependencies()

import yt_dlp
import requests

requests.packages.urllib3.disable_warnings()

# -- FFmpeg Resolution --
FFMPEG_PATH = shutil.which("ffmpeg")
if not FFMPEG_PATH:
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
        FFMPEG_PATH = shutil.which("ffmpeg")
    except:
        pass

# -- Configuration --
CONFIG_FILE = "config.json"


def load_config():
    defaults = {
        "proxy": "http://127.0.0.1:8888",
        "retries": 10,
        "fragment_retries": 10,
        "timeout": 30,
        "js_runtime": None,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception as e:
            print(f"[!] Warning: Could not load config.json: {e}")
    return defaults


CONFIG = load_config()


# -- Proxy Check --
def get_proxy(custom_proxy=None) -> str | None:
    target = custom_proxy or CONFIG.get("proxy")
    if not target:
        return None

    print(f"[*] Checking proxy {target} ...", end=" ", flush=True)
    try:
        # Use a more reliable check or just trust the config if it's set?
        # Let's keep the check but make it faster.
        resp = requests.get(
            "http://www.google.com/generate_204",
            proxies={"http": target, "https": target},
            timeout=5.0,
            verify=False,
        )
        if resp.status_code in (200, 204):
            print("✓ available.")
            return target
    except Exception:
        pass
    print("✗ using direct mode.")
    return None


KEEP_PARAMS = {"v", "list"}
CONTAINER_PREF = ["webm", "mp4", "mkv"]


# -- URL Cleaning --
def clean_youtube_url(raw: str) -> str:
    raw = raw.strip()
    parsed = urlparse(raw)
    if parsed.netloc in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/")
        parsed = parsed._replace(
            scheme="https",
            netloc="www.youtube.com",
            path="/watch",
            query=f"v={video_id}",
        )

    params = parse_qs(parsed.query, keep_blank_values=True)
    clean = {k: v for k, v in params.items() if k in KEEP_PARAMS}
    cleaned_url = urlunparse(parsed._replace(query=urlencode(clean, doseq=True)))
    return cleaned_url


def _make_base_opts(proxy: str | None) -> dict:
    opts = {
        "quiet": False,
        "no_warnings": False,
        "ignoreerrors": True,
        "retries": CONFIG.get("retries", 15),
        "fragment_retries": CONFIG.get("fragment_retries", 15),
        "socket_timeout": CONFIG.get("timeout", 60),
        "file_access_retries": 10,
        "logger": None,
        "n_threads": 8,  # Parallel downloads of fragments
    }

    # Try to mitigate JS runtime warning if defined in config
    if CONFIG.get("js_runtime"):
        opts["js_runtime"] = CONFIG["js_runtime"]

    if proxy:
        opts["proxy"] = proxy
        opts["nocheckcertificate"] = True
    return opts


# -- Quality Menu --
def select_quality(url: str, proxy: str | None):
    print("\n[*] Fetching information …")
    try:
        # For playlist extraction, we use flat_playlist to quickly get titles
        # and ignore errors if the first video is deleted.
        fetch_opts = _make_base_opts(proxy)
        fetch_opts.update({"extract_flat": "in_playlist"})

        with yt_dlp.YoutubeDL(fetch_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[!] Error fetching info: {e}")
        return None

    if not info:
        print("[!] No data found. The URL might be broken or private.")
        return None

    is_playlist = "entries" in info
    title = info.get("title", "Unknown")
    print(f"\n  Title    : {title}")

    if is_playlist:
        # Filter out 'None' entries which represent unavailable videos
        valid_entries = [e for e in info["entries"] if e is not None]
        print(f"  Type     : PLAYLIST ({len(valid_entries)} accessible items)")
        formats = valid_entries[0].get("formats", []) if valid_entries else []
    else:
        formats = info.get("formats", [])

    # 1. Build Quality List
    seen = {}
    for f in formats:
        height = f.get("height")
        if not height:
            continue
        fps = int(f.get("fps") or 30)
        ext = f.get("ext", "")
        key = (height, fps, ext)
        if key not in seen or (f.get("tbr") or 0) > (seen[key].get("tbr") or 0):
            seen[key] = f

    sorted_fmts = sorted(seen.items(), key=lambda kv: (-kv[0][0], -kv[0][1]))

    print(f"\n  {'#':<4} {'Option':<20} {'Format':<10}")
    print("  " + "─" * 40)
    print(f"  0    Download Audio (MP3)   [best]")

    options = [("Audio Only (MP3)", {"audio_only": True})]
    for idx, ((h, fps, ext), f) in enumerate(sorted_fmts, 1):
        label = f"{h}p{fps if fps > 30 else ''} Video"
        print(f"  {idx:<4} {label:<20} [{ext}]")
        options.append((label, f))

    while True:
        choice = input("\n  Selection (or 'q' to quit): ").strip().lower()
        if choice == "q":
            sys.exit(0)
        if choice.isdigit() and 0 <= int(choice) < len(options):
            return options[int(choice)], info, proxy
        print("  [!] Invalid selection.")


# -- Download Engine --
def run_download(selection_tuple, output_dir):
    (label, chosen), info, proxy = selection_tuple
    url = info.get("webpage_url") or info.get("original_url")

    ydl_opts = _make_base_opts(proxy)
    ydl_opts.update(
        {
            "outtmpl": (
                f"{output_dir}/%(playlist_title)s/%(title)s.%(ext)s"
                if "entries" in info
                else f"{output_dir}/%(title)s.%(ext)s"
            ),
            "ffmpeg_location": FFMPEG_PATH,
            "noplaylist": False,
            "ignoreerrors": True,
        }
    )

    if "audio_only" in chosen:
        print(f"[*] Mode: Audio Only (MP3)")
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        print(f"[*] Mode: Video ({label})")
        height = chosen.get("height")
        ydl_opts.update(
            {
                "format": f"bestvideo[height<={height}]+bestaudio/best",
                "merge_output_format": "mkv",
                "writesubtitles": True,
                "allsubtitles": True,
                "embedsubtitles": True,
            }
        )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"\n[!] Download failed: {e}")


def main():
    print("=" * 50)
    print(" YouTube Video & Playlist Downloader (Skip Errors Mode)")
    print("=" * 50)

    proxy = get_proxy()

    while True:
        try:
            url_raw = input("\nEnter URL: ").strip()
            if not url_raw:
                continue

            url = clean_youtube_url(url_raw)
            result = select_quality(url, proxy)
            if not result:
                continue

            out = input("Output Folder [.]: ").strip() or "."
            run_download(result, out)

            if input("\nAnother? (y/n): ").lower() != "y":
                break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n[!] Global Error: {e}")


if __name__ == "__main__":
    main()
