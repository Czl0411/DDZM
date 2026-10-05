#!/bin/bash
# 部署：Bot 用户后台配置 —— users.is_bot 列（迁移 96）+ /凿 bot 判定改配置驱动
# + 后台员工列表「设为 Bot/取消 Bot」。
# scp 清单与 cp 一一对应（勿删改，核对用）：
#   core_schema.py core_repository.py core_app.py core_api_models.py
#   admin_app.py admin_core_client.py admin.js mig_96.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_schema.py       "$VENV/core/schema.py"
cp /tmp/core_repository.py   "$VENV/core/repository.py"
cp /tmp/core_app.py          "$VENV/core/app.py"
cp /tmp/core_api_models.py   "$VENV/core/api_models.py"
cp /tmp/admin_app.py         "$VENV/admin/app.py"
cp /tmp/admin_core_client.py "$VENV/admin/core_client.py"
cp /tmp/admin.js             "$VENV/admin/static/admin.js"

cp /tmp/core_schema.py       "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/core_repository.py   "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_app.py          "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/core_api_models.py   "$CUR/src/dzmm_bot/core/api_models.py"
cp /tmp/admin_app.py         "$CUR/src/dzmm_bot/admin/app.py"
cp /tmp/admin_core_client.py "$CUR/src/dzmm_bot/admin/core_client.py"
cp /tmp/admin.js             "$CUR/src/dzmm_bot/admin/static/admin.js"
cp /tmp/mig_96.py            "$CUR/migrations/versions/20261005_96_user_bot_flag.py"

systemctl stop dzmm-core
set -a
source /etc/dzmm/dzmm.env
set +a
cd /opt/dzmm/current && /opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini upgrade head
systemctl start dzmm-core
sleep 3
systemctl restart dzmm-admin-web
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
/opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini current
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
