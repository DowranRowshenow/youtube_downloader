# Run the YouTube Downloader

# 1. Check for Virtual Environment
if (-not (Test-Path ".venv")) {
    Write-Host "[*] Virtual environment not found. Creating one..." -ForegroundColor Cyan
    py -m venv .venv
    Write-Host "[*] Installing requirements..." -ForegroundColor Cyan
    & .venv\Scripts\python.exe -m pip install -r requirements.txt
}

# 2. Check for system FFmpeg
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "[+] System FFmpeg detected in PATH." -ForegroundColor Green
} else {
    Write-Host "[!] No system FFmpeg found. The script will use 'static-ffmpeg' fallback." -ForegroundColor Yellow
}

# 3. Run the Script
Write-Host "[*] Launching YouTube Downloader..." -ForegroundColor Green
& .venv\Scripts\python.exe youtube.py

# Keep window open
Read-Host -Prompt "Press Enter to exit"
