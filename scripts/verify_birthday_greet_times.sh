#!/bin/bash
# 验证迁移 89 与生产生日设置
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='birthday_settings' AND column_name IN ('greet_time','greet_times');"
psql "$DB" -c "SELECT greet_times, enabled FROM birthday_settings;"
psql "$DB" -c "\d birthday_greet_announcements" | head -12
curl -s -o /dev/null -w 'healthz:%{http_code}\n' http://127.0.0.1:18120/healthz
