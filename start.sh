#!/bin/sh
# 一条命令启动本机中继和 NapCat。
# 中继放进后台，当前终端继续跑 NapCat，用来看登录二维码。
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
  port=$1
  "$PY" -c 'import socket,sys
s=socket.socket(); s.settimeout(1)
try:
    s.connect(("127.0.0.1", int(sys.argv[1]))); sys.exit(0)
except Exception:
    sys.exit(1)' "$port"
}

if ! port_open 3306; then
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
  setsid "$MARIADBD" \
    --user=root \
    --datadir="$DATADIR" \
    --socket="$SOCK" \
    --pid-file="$PIDFILE" \
    --bind-address=127.0.0.1 \
    --port=3306 \
    >>"$DATADIR/localhost.err" 2>&1 < /dev/null &
  i=0
  while [ "$i" -lt 20 ]; do
    if port_open 3306; then
      break
    fi
    i=$((i + 1))
    sleep 1
  done
  if ! port_open 3306; then
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

SERVER_LOG="${CHATBOT_LOG:-/tmp/chatbot-server.log}"
SERVER_PID="${CHATBOT_PID:-/tmp/chatbot-server.pid}"
if port_open 8090; then
  echo "中继已在运行: http://127.0.0.1:8090"
else
  echo "正在后台启动中继，日志: $SERVER_LOG"
  # 新会话，避免后面在本终端按 Ctrl+C 时把中继一起关掉。
  setsid "$VENV/bin/python" main.py >>"$SERVER_LOG" 2>&1 < /dev/null &
  echo $! >"$SERVER_PID"
  i=0
  while [ "$i" -lt 20 ]; do
    if port_open 8090; then
      break
    fi
    i=$((i + 1))
    sleep 1
  done
  if ! port_open 8090; then
    echo "中继未能就绪，请查看 $SERVER_LOG" >&2
    exit 1
  fi
  echo "中继已在后台: http://127.0.0.1:8090"
fi

QQ_BIN="${QQ_BIN:-/root/Napcat/opt/QQ/qq}"
if [ ! -x "$QQ_BIN" ]; then
  echo "未找到 $QQ_BIN，QQ 登录未启动。中继继续在后台运行。" >&2
  exit 1
fi
if pgrep -f "$QQ_BIN" >/dev/null 2>&1; then
  echo "NapCat 已在运行。二维码见 ${QQ_BIN%/*}/resources/app/app_launcher/napcat/cache/qrcode.png"
  exit 0
fi

echo "接下来在本终端登录 QQ。Ctrl+C 只退出 NapCat，中继继续在后台。"
cd "${QQ_BIN%/*}"
if [ -n "${QQ:-}" ]; then
  exec xvfb-run -a -s "-screen 0 1280x800x24" "$QQ_BIN" --no-sandbox --disable-gpu -q "$QQ"
fi
exec xvfb-run -a -s "-screen 0 1280x800x24" "$QQ_BIN" --no-sandbox --disable-gpu
