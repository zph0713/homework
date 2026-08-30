#!/bin/bash
# Homework Lab 一键启动（Linux / macOS 终端）
# 用法：./start.sh
cd "$(dirname "$0")" || exit 1

PY=python3
command -v $PY >/dev/null 2>&1 || { echo "❌ 未找到 python3"; exit 1; }

PORT=$($PY -c "
import json, os
try:
    cfg = json.load(open('config.json', encoding='utf-8'))
    print(cfg.get('port', 8877))
except Exception:
    print(os.environ.get('HOMELAB_PORT', 8877))
" 2>/dev/null || echo 8877)

if curl -s -m 2 "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
    echo "✅ 服务已在运行 http://127.0.0.1:$PORT"
    exit 0
fi

mkdir -p data
nohup $PY server/app.py >> data/server.log 2>&1 &
echo "⏳ 正在启动（日志：data/server.log）…"

for i in $(seq 1 20); do
    if curl -s -m 1 "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
        echo "✅ 已启动 → http://127.0.0.1:$PORT"
        exit 0
    fi
    sleep 0.5
done

echo "❌ 启动超时，请查看 data/server.log"
exit 1
