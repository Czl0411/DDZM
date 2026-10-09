#!/bin/bash
# 部署：/我的津贴 指令 + /我 封顶值动态化（core_commands.py / core_repository.py）
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_commands.py   "$VENV/core/commands.py"
cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_commands.py   "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"

systemctl restart dzmm-core
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
