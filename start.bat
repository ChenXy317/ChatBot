@echo off
setlocal
title QQ ChatBot Unified Launcher
cd /d "%~dp0"

:: Locate Python
if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)

echo ===================================================
echo   Starting QQ ChatBot System...
echo ===================================================

:: 1. Patch QQNT loader
"%PY_BIN%" napcat\patch_loader.py

:: 2. Determine target account
set "QQ_ARG=%~1"
if "%QQ_ARG%"=="" (
    if exist "napcat\.last_account" (
        set /p QQ_ARG=<"napcat\.last_account"
    )
)

:: 3. Launch NapCat in separate window
if "%QQ_ARG%"=="" goto :start_qr
if /i "%QQ_ARG%"=="qr" goto :start_qr
if /i "%QQ_ARG%"=="scan" goto :start_qr
if /i "%QQ_ARG%"=="-qr" goto :start_qr

echo   Starting NapCatQQ with quick login: %QQ_ARG%
start "NapCatQQ" cmd /c "cd /d "%~dp0napcat" && call launcher-user.bat -q %QQ_ARG% || pause"
goto :launch_browser

:start_qr
echo   Starting NapCatQQ with QR code login...
start "NapCatQQ" cmd /c "cd /d "%~dp0napcat" && call launcher-user.bat || pause"

:launch_browser
:: 4. Automatically open browser after 2 seconds
echo   Opening web dashboard at http://127.0.0.1:8090 ...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8090"

:: 5. Launch FastAPI backend in this console
echo   Starting FastAPI backend...
echo ===================================================
"%PY_BIN%" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server exited with error code %ERRORLEVEL%.
    pause
)
