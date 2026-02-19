@echo off
setlocal enabledelayedexpansion

:: Check if .venv exists, if not, create and install requirements
if not exist ".venv" (
    echo [*] Virtual environment not found. Creating one...
    python -m venv .venv
    echo [*] Installing requirements...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

:: Run the script using the virtual environment's python
echo [*] Launching YouTube Downloader...
.venv\Scripts\python.exe youtube.py

pause
