@echo off
setlocal
title NapCatQQ Launcher
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" napcat\patch_loader.py
) else (
    python napcat\patch_loader.py
)

cd /d "%~dp0napcat"

echo ===================================================
echo   Starting NapCatQQ...
echo   WebUI: http://127.0.0.1:6099/webui
echo ===================================================

call launcher-user.bat
pause
