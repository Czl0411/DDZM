#!/bin/bash
# 部署：/凿 高潮文字 v2（显示 100/100 + 调教库/词库 + 兜底槽位组装）
# 无迁移。scp 清单与 cp 一一对应：
#   core_commands.py core_estrus.py core_repository.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_commands.py   "$VENV/core/commands.py"
cp /tmp/core_estrus.py     "$VENV/core/estrus.py"
cp /tmp/core_repository.py "$VENV/core/repository.py"

cp /tmp/core_commands.py   "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/core_estrus.py     "$CUR/src/dzmm_bot/core/estrus.py"
cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"

systemctl restart dzmm-core dzmm-admin-web
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
