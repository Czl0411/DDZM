#!/bin/bash
# 部署：大话骰子/真心换真心 后台参数面板（迁移 87 建 liar_dice_settings）
# scp 清单与 cp 一一对应：
#   core_schema.py core_repository.py core_app.py core_api_models.py
#   admin_app.py admin_core_client.py admin_admin.js admin_index.html mig_87.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_schema.py       "$VENV/core/schema.py"
cp /tmp/core_repository.py   "$VENV/core/repository.py"
cp /tmp/core_app.py          "$VENV/core/app.py"
cp /tmp/core_api_models.py   "$VENV/core/api_models.py"
cp /tmp/admin_app.py         "$VENV/admin/app.py"
cp /tmp/admin_core_client.py "$VENV/admin/core_client.py"
cp /tmp/admin_admin.js       "$VENV/admin/static/admin.js"
cp /tmp/admin_index.html     "$VENV/admin/templates/index.html"

cp /tmp/core_schema.py       "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/core_repository.py   "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_app.py          "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/core_api_models.py   "$CUR/src/dzmm_bot/core/api_models.py"
cp /tmp/admin_app.py         "$CUR/src/dzmm_bot/admin/app.py"
cp /tmp/admin_core_client.py "$CUR/src/dzmm_bot/admin/core_client.py"
cp /tmp/admin_admin.js       "$CUR/src/dzmm_bot/admin/static/admin.js"
cp /tmp/admin_index.html     "$CUR/src/dzmm_bot/admin/templates/index.html"
cp /tmp/mig_87.py            "$CUR/migrations/versions/20261003_87_liar_dice_settings.py"

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
