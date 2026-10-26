# QQ ChatBot Agent PowerShell 启动脚本
$Host.UI.RawUI.WindowTitle = "QQ ChatBot Agent Server"
Set-Location -Path $PSScriptRoot

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  QQ ChatBot Agent Server Launcher" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$PyBin = if (Test-Path ".\.venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
} else {
    "python"
}

Write-Host "启动服务：http://127.0.0.1:8090" -ForegroundColor Green
& $PyBin main.py
