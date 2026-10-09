#!/bin/bash
# 部署：/凿 与发情值系统（迁移 88：三表 + users.gender）
# scp 清单与 cp 一一对应：
#   core_schema.py core_repository.py core_service.py core_commands.py
#   core_app.py core_api_models.py core_estrus.py
#   admin_app.py admin_core_client.py admin_admin.js admin_index.html mig_88.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_schema.py       "$VENV/core/schema.py"
cp /tmp/core_repository.py   "$VENV/core/repository.py"
cp /tmp/core_service.py      "$VENV/core/service.py"
cp /tmp/core_commands.py     "$VENV/core/commands.py"
cp /tmp/core_app.py          "$VENV/core/app.py"
cp /tmp/core_api_models.py   "$VENV/core/api_models.py"
cp /tmp/core_estrus.py       "$VENV/core/estrus.py"
cp /tmp/admin_app.py         "$VENV/admin/app.py"
cp /tmp/admin_core_client.py "$VENV/admin/core_client.py"
cp /tmp/admin_admin.js       "$VENV/admin/static/admin.js"
cp /tmp/admin_index.html     "$VENV/admin/templates/index.html"

cp /tmp/core_schema.py       "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/core_repository.py   "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_service.py      "$CUR/src/dzmm_bot/core/service.py"
cp /tmp/core_commands.py     "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/core_app.py          "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/core_api_models.py   "$CUR/src/dzmm_bot/core/api_models.py"
cp /tmp/core_estrus.py       "$CUR/src/dzmm_bot/core/estrus.py"
cp /tmp/admin_app.py         "$CUR/src/dzmm_bot/admin/app.py"
cp /tmp/admin_core_client.py "$CUR/src/dzmm_bot/admin/core_client.py"
cp /tmp/admin_admin.js       "$CUR/src/dzmm_bot/admin/static/admin.js"
cp /tmp/admin_index.html     "$CUR/src/dzmm_bot/admin/templates/index.html"
cp /tmp/mig_88.py            "$CUR/migrations/versions/20261003_88_estrus_chop.py"

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
