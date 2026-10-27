#!/bin/sh
# 在本机启动 ChatBot 中继。
# 使用 Termux 已安装的 MariaDB，不启动仓库内的 Windows 版 NapCat。
set -eu
cd "$(dirname "$0")"

MARIADBD="${MARIADBD:-/data/data/com.termux/files/usr/bin/mariadbd}"
MARIADB="${MARIADB:-/data/data/com.termux/files/usr/bin/mariadb}"
DATADIR="${MARIADB_DATADIR:-/data/data/com.termux/files/usr/var/lib/mysql}"
SOCK="${MARIADB_SOCKET:-/data/data/com.termux/files/usr/var/run/mysqld.sock}"
PIDFILE="$DATADIR/localhost.pid"
UV="${UV:-/data/data/com.termux/files/usr/bin/uv}"
PY="${PY:-/usr/bin/python3}"

port_open() {
  "$PY" -c 'import socket,sys
s=socket.socket(); s.settimeout(1)
try:
    s.connect(("127.0.0.1",3306)); sys.exit(0)
except Exception:
    sys.exit(1)'
}

if ! port_open; then
  if [ ! -x "$MARIADBD" ]; then
    echo "127.0.0.1:3306 没有 MariaDB，且找不到 $MARIADBD" >&2
    exit 1
  fi
  if [ -f "$PIDFILE" ]; then
    old=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "$old" ] && ! kill -0 "$old" 2>/dev/null; then
      rm -f "$PIDFILE"
    fi
  fi
  rm -f "$SOCK"
  echo "正在启动本机 MariaDB..."
  "$MARIADBD" \
    --user=root \
    --datadir="$DATADIR" \
    --socket="$SOCK" \
    --pid-file="$PIDFILE" \
    --bind-address=127.0.0.1 \
    --port=3306 \
    >>"$DATADIR/localhost.err" 2>&1 &
  i=0
  while [ "$i" -lt 20 ]; do
    if port_open; then
      break
    fi
    i=$((i + 1))
    sleep 1
  done
  if ! port_open; then
    echo "MariaDB 未能就绪，请查看 $DATADIR/localhost.err" >&2
    exit 1
  fi
fi

"$MARIADB" -h 127.0.0.1 -P 3306 -u root -e \
  "CREATE DATABASE IF NOT EXISTS qq_chatbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已根据 .env.example 生成 .env"
fi

# 项目目录在外置存储上，不能创建符号链接，虚拟环境放到用户目录。
VENV="${CHATBOT_VENV:-$HOME/.venvs/ChatBot}"
if [ ! -x "$VENV/bin/python" ]; then
  mkdir -p "$(dirname "$VENV")"
  "$UV" venv "$VENV" --python "$PY"
fi
"$UV" pip install --python "$VENV/bin/python" -r requirements.txt
exec "$VENV/bin/python" main.py
