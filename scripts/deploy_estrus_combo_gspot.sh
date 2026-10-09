#!/bin/bash
# 部署：/凿 v3 —— 连凿开关 + G点 + 职级每日配额 + 发情值不清零（迁移 95）
# scp 清单与 cp 一一对应（勿删改，核对用）：
#   core_schema.py core_repository.py core_commands.py core_app.py core_api_models.py
#   admin_app.py admin.js mig_95.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_schema.py     "$VENV/core/schema.py"
cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_commands.py   "$VENV/core/commands.py"
cp /tmp/core_app.py        "$VENV/core/app.py"
cp /tmp/core_api_models.py "$VENV/core/api_models.py"
cp /tmp/admin_app.py       "$VENV/admin/app.py"
cp /tmp/admin.js           "$VENV/admin/static/admin.js"

cp /tmp/core_schema.py     "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_commands.py   "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/core_app.py        "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/core_api_models.py "$CUR/src/dzmm_bot/core/api_models.py"
cp /tmp/admin_app.py       "$CUR/src/dzmm_bot/admin/app.py"
cp /tmp/admin.js           "$CUR/src/dzmm_bot/admin/static/admin.js"
cp /tmp/mig_95.py          "$CUR/migrations/versions/20261005_95_estrus_combo_gspot_quotas.py"

systemctl stop dzmm-core
mkdir -p /home/ubuntu/backups
sudo -u postgres pg_dump dzmm | gzip > /home/ubuntu/backups/dzmm_pre95_$(date +%Y%m%d_%H%M%S).sql.gz
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
