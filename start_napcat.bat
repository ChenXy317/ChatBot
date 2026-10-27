@echo off
setlocal
title NapCatQQ Launcher
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" napcat\patch_loader.py
) else (
    python napcat\patch_loader.py
)

set "QQ_ARG=%~1"
if "%QQ_ARG%"=="" (
    if exist "napcat\.last_account" (
        set /p QQ_ARG=<"napcat\.last_account"
    )
)

cd /d "%~dp0napcat"

echo ===================================================
if not "%QQ_ARG%"=="" (
    echo   Starting NapCatQQ (Quick Login: %QQ_ARG%)...
    set "LAUNCH_CMD=call launcher-user.bat -q %QQ_ARG%"
) else (
    echo   Starting NapCatQQ (QR Code Mode)...
    set "LAUNCH_CMD=call launcher-user.bat"
)
echo   WebUI: http://127.0.0.1:6099/webui
echo ===================================================

%LAUNCH_CMD%
pause
