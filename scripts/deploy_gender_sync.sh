#!/bin/bash
# 部署：性别平台回填链路 + 高潮文字单段 + 截断修复
# 无迁移。scp 清单与 cp 一一对应：
#   core_app.py core_api_models.py core_repository.py core_estrus.py
#   browser_worker.py browser_aikda_socket.py browser_core_client.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_app.py          "$VENV/core/app.py"
cp /tmp/core_api_models.py   "$VENV/core/api_models.py"
cp /tmp/core_repository.py   "$VENV/core/repository.py"
cp /tmp/core_estrus.py       "$VENV/core/estrus.py"
cp /tmp/browser_worker.py    "$VENV/browser/worker.py"
cp /tmp/browser_aikda_socket.py "$VENV/browser/aikda_socket.py"
cp /tmp/browser_core_client.py  "$VENV/browser/core_client.py"

cp /tmp/core_app.py          "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/core_api_models.py   "$CUR/src/dzmm_bot/core/api_models.py"
cp /tmp/core_repository.py   "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_estrus.py       "$CUR/src/dzmm_bot/core/estrus.py"
cp /tmp/browser_worker.py    "$CUR/src/dzmm_bot/browser/worker.py"
cp /tmp/browser_aikda_socket.py "$CUR/src/dzmm_bot/browser/aikda_socket.py"
cp /tmp/browser_core_client.py  "$CUR/src/dzmm_bot/browser/core_client.py"

systemctl restart dzmm-core dzmm-admin-web dzmm-browser-worker
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
