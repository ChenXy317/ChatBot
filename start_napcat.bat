@echo off
setlocal
title NapCatQQ Launcher
cd /d "%~dp0napcat"

echo ===================================================
echo   Starting NapCatQQ...
echo   WebUI: http://127.0.0.1:6099/webui
echo ===================================================

call launcher-user.bat
pause
