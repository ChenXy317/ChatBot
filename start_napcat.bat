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
echo   Starting NapCatQQ...
echo   WebUI: http://127.0.0.1:6099/webui
echo ===================================================

if "%QQ_ARG%"=="" goto :qr_mode
if /i "%QQ_ARG%"=="qr" goto :qr_mode
if /i "%QQ_ARG%"=="scan" goto :qr_mode
if /i "%QQ_ARG%"=="-qr" goto :qr_mode

echo   Using quick login with QQ: %QQ_ARG%
call launcher-user.bat -q %QQ_ARG%
goto :done

:qr_mode
echo   Starting with QR code login...
call launcher-user.bat

:done
pause
