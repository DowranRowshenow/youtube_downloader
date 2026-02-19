@echo off
setlocal enabledelayedexpansion

:: Check if .venv exists, if not, create and install requirements
if not exist ".venv" (
    echo [*] Virtual environment not found. Creating one...
    python -m venv .venv
    echo [*] Installing requirements...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

:: Check for system FFmpeg
where ffmpeg >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [+] System FFmpeg detected in PATH.
) else (
    echo [!] No system FFmpeg found. The script will use 'static-ffmpeg' fallback.
)

:: Run the script using the virtual environment's python
echo [*] Launching YouTube Downloader...
.venv\Scripts\python.exe youtube.py

pause
