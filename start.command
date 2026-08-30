#!/bin/bash
# Homework Lab 一键启动（macOS 双击 / 终端运行）
# 用法：双击本文件，或终端执行 ./start.command
cd "$(dirname "$0")" || exit 1

PY=python3
command -v $PY >/dev/null 2>&1 || { echo "❌ 未找到 python3，请先安装 Python 3"; read -n 1; exit 1; }

# 读取配置里的端口（无 config.json 时用默认 8877）
PORT=$($PY -c "
import json, os
try:
    cfg = json.load(open('config.json', encoding='utf-8'))
    print(cfg.get('port', 8877))
except Exception:
    print(os.environ.get('HOMELAB_PORT', 8877))
" 2>/dev/null || echo 8877)

# 已在运行 → 直接打开浏览器
if curl -s -m 2 "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
    echo "✅ 服务已在运行 http://127.0.0.1:$PORT"
    open "http://127.0.0.1:$PORT"
    exit 0
fi

# 未运行 → 后台启动（日志在 data/server.log）
mkdir -p data
nohup $PY server/app.py >> data/server.log 2>&1 &
PID=$!
echo "⏳ 正在启动（PID $PID）…"

# 等待服务就绪（最多 10 秒）
for i in $(seq 1 20); do
    if curl -s -m 1 "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
        echo "✅ 已启动 → http://127.0.0.1:$PORT"
        open "http://127.0.0.1:$PORT"
        exit 0
    fi
    sleep 0.5
done

echo "❌ 启动超时，请查看 data/server.log"
read -n 1
