@echo off
setlocal
cd /d "%~dp0"
title QQ ChatBot Server

echo ===================================================
echo   QQ ChatBot Agent Server Launcher
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)

echo Starting FastAPI server at http://127.0.0.1:8090 ...
"%PY_BIN%" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server exited with error code %ERRORLEVEL%.
    pause
)
