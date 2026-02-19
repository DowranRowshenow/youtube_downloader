#!/usr/bin/env python3
"""
YouTube Downloader
- Cleans YouTube URLs (removes playlist/tracking params)
- Proxy support (127.0.0.1:8888 with auto-fallback, SSL bypass for MITM proxies)
- Quality selection menu — shows every format (webm preferred, mp4 also listed)
- Merges video + audio + all subtitles via FFmpeg
- Loops back to URL prompt on any error
"""

import re
import sys
import subprocess
import shutil
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


# ── Dependency check ──────────────────────────────────────────────────────────
def install_dependencies():
    # If running as a compiled EXE, dependencies are already bundled
    if getattr(sys, "frozen", False):
        return

    # Check if ffmpeg is already in the system PATH
    ffmpeg_in_path = shutil.which("ffmpeg") is not None

    required = ["yt-dlp", "requests"]
    if not ffmpeg_in_path:
        required.append("static-ffmpeg")
        print(
            "[*] No system FFmpeg found. Adding 'static-ffmpeg' to installation list."
        )
    else:
        print("[*] System FFmpeg detected. Skipping 'static-ffmpeg' dependency.")

    for pkg in required:
        try:
            if pkg == "yt-dlp":
                import yt_dlp
            elif pkg == "requests":
                import requests
            elif pkg == "static-ffmpeg":
                import static_ffmpeg
        except ImportError:
            # Handle package names that differ from import names
            install_name = pkg
            print(f"[!] {pkg} not found. Installing...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", install_name]
            )


install_dependencies()

import yt_dlp
import requests

try:
    import static_ffmpeg

    # This adds the static-ffmpeg binaries to the environment PATH
    static_ffmpeg.add_paths()
except ImportError:
    static_ffmpeg = None

requests.packages.urllib3.disable_warnings()  # suppress InsecureRequestWarning

# ── Constants ─────────────────────────────────────────────────────────────────
PROXY_URL = "http://127.0.0.1:8888"
KEEP_PARAMS = {"v"}  # only keep video-ID param

# Resolve FFmpeg path: check system first, then static-ffmpeg
FFMPEG_PATH = shutil.which("ffmpeg")
if not FFMPEG_PATH:
    # If static_ffmpeg.add_paths() worked, shutil.which might find it now
    FFMPEG_PATH = shutil.which("ffmpeg")

# Container preference order (lower index = more preferred)
CONTAINER_PREF = ["webm", "mp4", "mkv", "mov", "avi"]


# ── URL Cleaning ──────────────────────────────────────────────────────────────
def clean_youtube_url(raw: str) -> str:
    """Strip tracking / playlist params, keep only the video ID."""
    raw = raw.strip()
    parsed = urlparse(raw)

    # Normalise youtu.be short links → youtube.com/watch
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


# ── Proxy Check ───────────────────────────────────────────────────────────────
def check_proxy(proxy_url: str, timeout: float = 3.0) -> bool:
    """Test proxy reachability. Accepts self-signed MITM certificates."""
    try:
        resp = requests.get(
            "http://www.gstatic.com/generate_204",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
            verify=False,
        )
        return resp.status_code in (200, 204)
    except Exception:
        return False


def get_proxy() -> str | None:
    print(f"\n[*] Checking proxy {PROXY_URL} ...", end=" ", flush=True)
    if check_proxy(PROXY_URL):
        print("✓ available – proxy mode (SSL verify disabled).")
        return PROXY_URL
    print("✗ not reachable – direct mode.")
    return None


# ── yt-dlp helpers ────────────────────────────────────────────────────────────
def _make_base_opts(proxy: str | None) -> dict:
    """Core yt-dlp options; disables SSL verification when proxy is active."""
    opts: dict = {"quiet": True, "no_warnings": True}
    if proxy:
        opts["proxy"] = proxy
        opts["nocheckcertificate"] = True
    return opts


def _extract_with_fallback(url: str, proxy: str | None) -> tuple[dict, str | None]:
    """Extract info; if proxy causes SSL error, silently retry direct."""
    try:
        with yt_dlp.YoutubeDL(_make_base_opts(proxy)) as ydl:
            return ydl.extract_info(url, download=False), proxy
    except Exception as e:
        if proxy and ("SSL" in str(e) or "certificate" in str(e).lower()):
            print("\n[!] Proxy SSL error – retrying direct …")
            with yt_dlp.YoutubeDL(_make_base_opts(None)) as ydl:
                return ydl.extract_info(url, download=False), None
        raise


# ── Format helpers ────────────────────────────────────────────────────────────
def _hr_size(nbytes) -> str:
    if nbytes is None:
        return "    ?"
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:6.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:6.1f} TB"


def _container(fmt: dict) -> str:
    """Determine container name from ext or codec hints."""
    ext = (fmt.get("ext") or "").lower()
    if ext in ("webm", "mp4", "mkv", "mov", "avi", "flv"):
        return ext
    vcodec = (fmt.get("vcodec") or "").lower()
    if "vp9" in vcodec or "av01" in vcodec:
        return "webm"
    return ext or "?"


def _container_rank(cont: str) -> int:
    try:
        return CONTAINER_PREF.index(cont)
    except ValueError:
        return len(CONTAINER_PREF)


def _pick_best_audio(formats: list) -> dict | None:
    audio = [
        f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"
    ]
    return max(audio, key=lambda f: f.get("abr") or 0) if audio else None


# ── Quality / Format Menu ─────────────────────────────────────────────────────
def build_format_list(formats: list) -> list[tuple[str, dict]]:
    """
    Return a sorted list of (label, fmt_dict) covering every distinct
    (height, fps, container) combination found in the stream list.

    Sort order: height DESC, fps DESC, container preference ASC (webm first).
    """
    seen: dict[tuple, dict] = {}  # key → best fmt for that slot
    for f in formats:
        height = f.get("height")
        vcodec = f.get("vcodec", "none")
        if not height or vcodec == "none":
            continue

        fps = int(f.get("fps") or 30)
        cont = _container(f)
        key = (height, fps, cont)

        # Keep the entry with the highest bitrate for each unique slot
        if key not in seen or (f.get("tbr") or 0) > (seen[key].get("tbr") or 0):
            seen[key] = f

    # Sort: height DESC, fps DESC, container rank ASC
    sorted_fmts = sorted(
        seen.items(),
        key=lambda kv: (-kv[0][0], -kv[0][1], _container_rank(kv[0][2])),
    )

    result = []
    for (height, fps, cont), f in sorted_fmts:
        label = f"{height}p" + (f"{fps}" if fps > 30 else "") + f"  [{cont}]"
        result.append((label, f))

    return result


def select_quality(url: str, proxy: str | None) -> dict:
    """Interactive quality picker. Returns the user's selection dict."""
    print("\n[*] Fetching available qualities …")
    info, proxy = _extract_with_fallback(url, proxy)

    title = info.get("title", "Unknown")
    duration = info.get("duration_string", "?")
    formats = info.get("formats", [])

    quality_list = build_format_list(formats)

    if not quality_list:
        print("[!] No video formats found – offering audio-only.")
        best_a = _pick_best_audio(formats)
        quality_list = [("audio-only", best_a)]

    # ── Display ──────────────────────────────────────────────────────────────
    print(f"\n  Title    : {title}")
    print(f"  Duration : {duration}\n")
    print(f"  {'#':<4} {'Quality':<18} {'VCodec':<14} {'ACodec':<12} {'Size':>10}")
    print("  " + "─" * 62)
    for idx, (label, f) in enumerate(quality_list, 1):
        vcodec = (f.get("vcodec") or "?")[:12]
        acodec = (f.get("acodec") or "none")[:10]
        size = _hr_size(f.get("filesize") or f.get("filesize_approx"))
        note = " ★" if "webm" in label else ""
        print(f"  {idx:<4} {label:<18} {vcodec:<14} {acodec:<12} {size}{note}")

    print("\n  ★ = WebM/VP9 (better compression, same quality)")
    print()

    while True:
        raw = (
            input("  Enter number to download (or 'q' to quit, 'u' for new URL): ")
            .strip()
            .lower()
        )
        if raw == "q":
            sys.exit(0)
        if raw == "u":
            return None  # signal: go back to URL loop
        if raw.isdigit() and 1 <= int(raw) <= len(quality_list):
            chosen_label, chosen_fmt = quality_list[int(raw) - 1]
            return {
                "label": chosen_label,
                "format": chosen_fmt,
                "info": info,
                "proxy": proxy,
            }
        print("  [!] Invalid choice – try again.")


# ── Format selector string ────────────────────────────────────────────────────
def build_format_selector(chosen_fmt: dict, formats: list) -> str:
    if chosen_fmt is None:
        return "bestaudio/best"

    fmt_id = chosen_fmt.get("format_id", "")
    height = chosen_fmt.get("height", 0)
    cont = _container(chosen_fmt)

    # Prefer exact format_id; fall back to resolution-constrained selector
    best_audio = _pick_best_audio(formats)
    aud_part = best_audio["format_id"] if best_audio else "bestaudio"

    return f"{fmt_id}+{aud_part}/bestvideo[height<={height}]+bestaudio/best"


# ── Download ──────────────────────────────────────────────────────────────────
def download(selection: dict, output_dir: str = ".") -> None:
    info = selection["info"]
    proxy = selection["proxy"]
    chosen = selection["format"]
    formats = info.get("formats", [])
    url = info["webpage_url"]

    fmt_selector = build_format_selector(chosen, formats)
    print(f"\n[*] Format selector  : {fmt_selector}")

    # ── Subtitles ─────────────────────────────────────────────────────────────
    sub_opts: dict = {}
    manual_subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}
    all_sub_langs = list(manual_subs.keys()) or list(auto_subs.keys()) or []

    if all_sub_langs:
        print(
            f"[*] Subtitles found  : {', '.join(all_sub_langs[:15])}"
            + (" …" if len(all_sub_langs) > 15 else "")
        )
        sub_opts = {
            "writesubtitles": bool(manual_subs),
            "writeautomaticsub": bool(auto_subs),
            "subtitleslangs": all_sub_langs,
            "embedsubtitles": True,
        }
    else:
        print("[*] No subtitles detected.")

    # ── Multi-dub audio tracks ────────────────────────────────────────────────
    audio_tracks = [
        f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"
    ]
    unique_langs = {f.get("language") for f in audio_tracks if f.get("language")}

    vid_id = chosen.get("format_id", "bestvideo") if chosen else "bestvideo"
    if len(unique_langs) > 1:
        all_audio_ids = "+".join(f["format_id"] for f in audio_tracks[:6])
        fmt_selector = f"{vid_id}+{all_audio_ids}/best"
        print(f"[*] Multi-dub langs  : {', '.join(sorted(unique_langs))}")

    # ── yt-dlp options ────────────────────────────────────────────────────────
    ydl_opts = {
        **_make_base_opts(proxy),
        "format": fmt_selector,
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "merge_output_format": "mkv",
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mkv"},
        ],
        "ffmpeg_location": FFMPEG_PATH or "ffmpeg",
        "noplaylist": True,
        **sub_opts,
    }

    print(f"[*] Output directory : {output_dir}")
    print("[*] Starting download …\n")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    print("\n[✓] Download complete!")


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  YouTube Downloader  –  yt-dlp + FFmpeg")
    print("=" * 60)

    if not FFMPEG_PATH:
        print("[!] WARNING: ffmpeg not found in PATH – merging may fail.\n")

    # Proxy is checked once per session (not per URL)
    proxy = get_proxy()

    while True:  # ← outer loop: re-asks URL on any error
        try:
            # 1. URL input
            raw_url = input("\nEnter YouTube URL (or 'q' to quit): ").strip()
            if raw_url.lower() == "q":
                print("Bye!")
                break
            if not raw_url:
                print("[!] No URL provided – try again.")
                continue

            clean_url = clean_youtube_url(raw_url)
            if clean_url != raw_url:
                print(f"[*] Cleaned URL      : {clean_url}")

            # 2. Quality selection (may return None if user chose 'u')
            selection = select_quality(clean_url, proxy)
            if selection is None:
                continue  # user wants a new URL

            print(f"\n[✓] Selected         : {selection['label']}")

            # Update proxy in case fallback to direct happened inside select_quality
            proxy = selection["proxy"]

            # 3. Output directory
            out_dir = input("Output directory [. for current]: ").strip() or "."

            # 4. Download + merge
            download(selection, out_dir)

            # 5. After download, ask for another
            again = input("\nDownload another? [y/N]: ").strip().lower()
            if again != "y":
                print("Bye!")
                break

        except KeyboardInterrupt:
            print(
                "\n\n[!] Interrupted – press Ctrl+C again to exit, or Enter to retry."
            )
            try:
                input()
            except KeyboardInterrupt:
                print("\nBye!")
                break

        except Exception as e:
            print(f"\n[!] Error: {e}")
            print("[*] Returning to URL prompt …\n")
            continue  # ← loop restarts at URL input


if __name__ == "__main__":
    main()
