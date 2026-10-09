#!/bin/bash
# 部署：集成接口（用户匹配 + 摸鱼币查/发/扣，X-Api-Key + 幂等）+ 迁移 92
# scp 清单与 cp 一一对应：
#   core_repository.py core_app.py core_schema.py core_api_models.py
#   admin_app.py admin_core_client.py runtime_settings.py mig_92.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

set -a
source /etc/dzmm/dzmm.env
set +a
: "${DZMM_INTEGRATION_API_KEY:?请先在 /etc/dzmm/dzmm.env 中配置集成接口密钥}"

cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_app.py       "$VENV/core/app.py"
cp /tmp/core_schema.py    "$VENV/core/schema.py"
cp /tmp/core_api_models.py "$VENV/core/api_models.py"
cp /tmp/admin_app.py      "$VENV/admin/app.py"
cp /tmp/admin_core_client.py "$VENV/admin/core_client.py"
cp /tmp/runtime_settings.py "$VENV/runtime/settings.py"

cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_app.py        "$CUR/src/dzmm_bot/core/app.py"
cp /tmp/core_schema.py     "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/core_api_models.py "$CUR/src/dzmm_bot/core/api_models.py"
cp /tmp/admin_app.py       "$CUR/src/dzmm_bot/admin/app.py"
cp /tmp/admin_core_client.py "$CUR/src/dzmm_bot/admin/core_client.py"
cp /tmp/runtime_settings.py  "$CUR/src/dzmm_bot/runtime/settings.py"
cp /tmp/mig_92.py "$CUR/migrations/versions/20261004_92_integration_api.py"

cd "$CUR" && /opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini upgrade head

systemctl restart dzmm-core dzmm-admin-web
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
