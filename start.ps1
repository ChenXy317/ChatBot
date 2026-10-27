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

& $PyBin "$PSScriptRoot\scripts\start_local_db.py"
if ($LASTEXITCODE -ne 0) {
    throw "Local database startup failed."
}

& $PyBin "$PSScriptRoot\scripts\prepare_backend.py"
$BackendPreflight = $LASTEXITCODE
if ($BackendPreflight -eq 1) {
    throw "Backend port check failed. See the message above."
}

$Port = 8090
if (Test-Path ".env") {
    $PortLine = Get-Content ".env" | Where-Object { $_ -match '^\s*SERVER_PORT\s*=' } | Select-Object -Last 1
    if ($PortLine) {
        $Port = ($PortLine -split '=', 2)[1].Trim().Trim("'`"")
    }
}

if ($BackendPreflight -eq 10) {
    Write-Host "后端已运行且为当前版本：http://127.0.0.1:$Port" -ForegroundColor Green
} else {
    Write-Host "启动服务：http://127.0.0.1:$Port" -ForegroundColor Green
    & $PyBin main.py
}
