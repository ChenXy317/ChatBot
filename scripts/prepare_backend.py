"""检查端口上的后端版本，必要时停止同项目的旧后端。"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
HEALTH_APP = "qq-chatbot"
HEALTH_VERSION = "2026-10-27.7"
EXIT_START_NEW = 0
EXIT_CONFLICT = 1
EXIT_ALREADY_RUNNING = 10


def is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def request_json(host: str, port: int, path: str, token: str) -> tuple[int, dict]:
    headers = {"X-Dashboard-Token": token} if token else {}
    request = urllib.request.Request(f"http://{host}:{port}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        return error.code, body


def listening_pid(port: int) -> int | None:
    """从 netstat 中读取监听端口的进程号。"""
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP":
            continue
        local_address, state, pid_text = fields[1], fields[-2].upper(), fields[-1]
        if state == "LISTENING" and local_address.rsplit(":", 1)[-1] == str(port):
            try:
                return int(pid_text)
            except ValueError:
                return None
    return None


def stop_process_tree(pid: int) -> bool:
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.returncode == 0


def main() -> int:
    load_dotenv(ROOT_DIR / ".env")
    port = int(os.getenv("SERVER_PORT", "8090"))
    probe_host = "127.0.0.1"
    dashboard_token = os.getenv("DASHBOARD_TOKEN", "").strip()

    if not is_listening(probe_host, port):
        return EXIT_START_NEW

    try:
        status_code, health = request_json(probe_host, port, "/api/health", dashboard_token)
    except (OSError, ValueError):
        status_code, health = 0, {}

    if (
        status_code == 200
        and health.get("app") == HEALTH_APP
        and health.get("api_version") == HEALTH_VERSION
    ):
        print(f"ChatBot backend is already running on port {port}.")
        return EXIT_ALREADY_RUNNING

    # 旧版 ChatBot 没有 /api/health，但仍有 /api/status；只在这种情况下自动替换。
    try:
        legacy_status_code, legacy_status = request_json(
            probe_host, port, "/api/status", dashboard_token
        )
    except (OSError, ValueError):
        legacy_status_code, legacy_status = 0, {}
    is_legacy_chatbot = (
        legacy_status_code == 200
        and "napcat_connected" in legacy_status
        and "active_debouncers" in legacy_status
    )
    if not is_legacy_chatbot:
        print(
            f"Port {port} is occupied by another service; ChatBot was not started.",
            file=sys.stderr,
        )
        return EXIT_CONFLICT

    pid = listening_pid(port)
    if not pid:
        print(f"Port {port} is running an old ChatBot backend, but its PID was not found.", file=sys.stderr)
        return EXIT_CONFLICT

    print(f"Stopping old ChatBot backend on port {port} (PID {pid})...")
    if not stop_process_tree(pid):
        print(f"Could not stop old ChatBot backend PID {pid}.", file=sys.stderr)
        return EXIT_CONFLICT

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not is_listening(probe_host, port):
            print("Old backend stopped; starting the current version.")
            return EXIT_START_NEW
        time.sleep(0.2)

    print(f"Port {port} is still occupied after stopping the old backend.", file=sys.stderr)
    return EXIT_CONFLICT


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"Backend preflight failed: {error}", file=sys.stderr)
        sys.exit(EXIT_CONFLICT)
