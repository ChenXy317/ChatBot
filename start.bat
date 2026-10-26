@echo off
chcp 65001 >nul
title QQ ChatBot Agent
echo 正在启动 QQ 接管中继服务...

if not exist ".venv\Scripts\python.exe" (
    echo 正在通过 uv 初始化虚拟环境并安装依赖...
    uv venv
    uv pip install -r requirements.txt
)

echo 启动 FastAPI 服务 (http://127.0.0.1:8000)...
".venv\Scripts\python.exe" main.py
pause
