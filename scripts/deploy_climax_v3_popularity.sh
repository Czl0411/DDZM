#!/bin/bash
# 部署：高潮文案 v3 尺度加码 + /人气榜改名 + /凿特殊目标 + /我生日性别。无迁移。
# scp 清单与 cp 一一对应（勿删改，核对用）：
#   core_estrus.py core_repository.py core_commands.py ai_client.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_estrus.py     "$VENV/core/estrus.py"
cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_commands.py   "$VENV/core/commands.py"
cp /tmp/ai_client.py       "$VENV/ai/client.py"

cp /tmp/core_estrus.py     "$CUR/src/dzmm_bot/core/estrus.py"
cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_commands.py   "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/ai_client.py       "$CUR/src/dzmm_bot/ai/client.py"

systemctl restart dzmm-core
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
