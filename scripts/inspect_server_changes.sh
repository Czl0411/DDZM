#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
echo "===== 1. alembic 当前版本 ====="
cd /opt/dzmm/current && /opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini current 2>/dev/null
echo "===== 2. 迁移 93/94 是否在服务器 ====="
ls -la /opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot/../..//dzmm_bot 2>/dev/null >/dev/null
ls -la /opt/dzmm/current/migrations/versions/ | tail -5
echo "===== 3. 服务状态 ====="
systemctl list-units 'dzmm-*' --no-legend --plain | grep dzmm
curl -s -o /dev/null -w 'core healthz:%{http_code}\n' http://127.0.0.1:18120/healthz
echo "===== 4. 关键文件最近修改时间（venv 运行时） ====="
V=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
ls -la --time-style='+%m-%d %H:%M' $V/core/shop_management.py $V/core/shop_effects.py $V/admin/shop_excel.py $V/core/estrus.py $V/core/repository.py $V/admin/static/admin.js 2>&1
echo "===== 5. 新表是否存在 ====="
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "\dt" | grep -Ei 'shop_excel|chop' || echo "(无相关新表)"
echo "===== 6. 最近服务重启时间 ====="
for s in dzmm-core dzmm-admin-web dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker; do
  echo "$s: $(systemctl show $s -p ActiveEnterTimestamp --value)"
done
