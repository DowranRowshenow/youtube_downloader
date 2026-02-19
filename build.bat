@echo off
setlocal enabledelayedexpansion

echo ################################################
echo #        YouTube Downloader EXE Builder        #
echo ################################################
echo.

:: 1. Check for Virtual Environment
if not exist ".venv" (
    echo [*] Virtual environment not found. Creating one...
    python -m venv .venv
)

:: 2. Upgrade pip and install builder dependencies
echo [*] Updating build tools and installing requirements...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install pyinstaller -r requirements.txt

:: 3. Run PyInstaller
echo.
echo [*] Starting PyInstaller Build...
echo [*] Mode: OneFile
echo [*] Name: YouTube_Downloader
echo.

.venv\Scripts\pyinstaller.exe --onefile --name "YouTube_Downloader" --icon=download.ico youtube.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ################################################
    echo # [OK] Build Successful!                       #
    echo # Your EXE is located in the "dist" folder.    #
    echo ################################################
) else (
    echo.
    echo ################################################
    echo # [!] Build Failed!                            #
    echo # Check the output above for errors.           #
    echo ################################################
)

pause
