"""Start the optional per-user MariaDB installation on Windows."""

import configparser
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def main() -> int:
    if os.name != "nt":
        return 0

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        print("LOCALAPPDATA 未设置，跳过本地数据库启动。", file=sys.stderr)
        return 0
    config_path = Path(local_app_data) / "ChatBot" / "mariadb.ini"
    if not config_path.is_file():
        return 0

    config = configparser.ConfigParser(interpolation=None)
    if not config.read(config_path, encoding="utf-8") or not config.has_section("mysqld"):
        print(f"本地数据库配置不完整: {config_path}", file=sys.stderr)
        return 1
    options = config["mysqld"]
    host = options.get("bind-address", "127.0.0.1")
    port = options.getint("port", 3306)
    if is_listening(host, port):
        print(f"Local database is available on {host}:{port}.")
        return 0

    executable = Path(options["basedir"]) / "bin" / "mariadbd.exe"
    if not executable.is_file():
        print(f"找不到 MariaDB 可执行文件: {executable}", file=sys.stderr)
        return 1
    process = subprocess.Popen(
        [str(executable), f"--defaults-file={config_path}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if is_listening(host, port):
            print(f"Local database started on {host}:{port}.")
            return 0
        time.sleep(0.25)

    print(
        f"Local database did not start. Check {options.get('log-error', config_path)}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, configparser.Error, ValueError) as error:
        print(f"Local database startup failed: {error}", file=sys.stderr)
        sys.exit(1)
