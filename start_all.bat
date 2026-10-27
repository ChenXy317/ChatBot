@echo off
setlocal
cd /d "%~dp0"
title ChatBot Launcher

echo ===================================================
echo   Starting ChatBot Backend and NapCat Protocol...
echo ===================================================

echo [1/2] Launching Backend Server (http://127.0.0.1:8090)...
start "ChatBot Backend (Port 8090)" start.bat

echo Waiting 2 seconds for backend initialization...
timeout /t 2 /nobreak >nul

echo [2/2] Launching NapCat Protocol Client...
start "NapCat Protocol" start_napcat.bat

echo.
echo All services launched!
echo Open http://127.0.0.1:8090 in your browser to manage the bot.
timeout /t 3 >nul
