#!/bin/bash
# 部署：发情值排名 → 今日最受欢迎榜 + 发情值每日清零（迁移 90）
# scp 清单与 cp 一一对应：
#   core_repository.py core_commands.py core_schema.py mig_90.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_commands.py  "$VENV/core/commands.py"
cp /tmp/core_schema.py    "$VENV/core/schema.py"

cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_commands.py   "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/core_schema.py     "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/mig_90.py          "$CUR/migrations/versions/20261004_90_estrus_popularity.py"

set -a
source /etc/dzmm/dzmm.env
set +a
cd "$CUR" && /opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini upgrade head

systemctl restart dzmm-core dzmm-admin-web
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
