#!/bin/bash
# 部署：集成接口新增 GET game-quota（小游戏每日发起额度查询）——无迁移
# scp 清单与 cp 一一对应：
#   core_repository.py core_app.py admin_app.py admin_core_client.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_app.py       "$VENV/core/app.py"
cp /tmp/admin_app.py      "$VENV/admin/app.py"
cp /tmp/admin_core_client.py "$VENV/admin/core_client.py"

cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_app.py        "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/admin_app.py       "$CUR/src/dzmm_bot/admin/app.py"
cp /tmp/admin_core_client.py "$CUR/src/dzmm_bot/admin/core_client.py"

systemctl restart dzmm-core dzmm-admin-web
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
