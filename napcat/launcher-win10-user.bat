@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1
chcp 65001 >nul
set "NAPCAT_PATCH_PACKAGE=%cd%\qqnt.json"
set "NAPCAT_LOAD_PATH=%cd%\loadNapCat.js"
set "NAPCAT_INJECT_PATH=%cd%\NapCatWinBootHook.dll"
set "NAPCAT_LAUNCHER_PATH=%cd%\NapCatWinBootMain.exe"
set "NAPCAT_MAIN_PATH=%cd%\napcat.mjs"

:: 1. 优先读取环境变量或 .qq_path 记录
if defined QQ_PATH if exist "%QQ_PATH%" (
    set "QQPath=%QQ_PATH%"
    goto :napcat_boot
)
if exist ".qq_path" (
    set /p QQPath=<".qq_path"
    if exist "%QQPath%" goto :napcat_boot
)

:: 2. 尝试常见安装路径
for %%G in (
    "D:\工具2\QQ\QQ.exe"
    "%ProgramFiles%\Tencent\QQNT\QQ.exe"
    "%ProgramFiles(x86)%\Tencent\QQNT\QQ.exe"
    "%ProgramFiles%\Tencent\QQ\Bin\QQ.exe"
    "%ProgramFiles(x86)%\Tencent\QQ\Bin\QQ.exe"
    "%ProgramFiles%\Tencent\QQ\QQ.exe"
    "%ProgramFiles(x86)%\Tencent\QQ\QQ.exe"
    "%LocalAppData%\Programs\Tencent\QQNT\QQ.exe"
) do (
    if exist "%%~G" (
        set "QQPath=%%~G"
        goto :napcat_boot
    )
)

:napcat_boot
if not defined QQPath (
    echo QQNT installation was not found.
    pause
    exit /b 1
)

"%NAPCAT_LAUNCHER_PATH%" "%QQPath%" "%NAPCAT_INJECT_PATH%" %*
set "napcat_exit_code=%ERRORLEVEL%"
pause
exit /b %napcat_exit_code%
