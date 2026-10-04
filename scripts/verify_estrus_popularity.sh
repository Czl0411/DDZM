#!/bin/bash
# 验证迁移 90 与新指令种子
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='estrus_states' AND column_name IN ('last_active_date','last_climax_date');"
psql "$DB" -c "SELECT command, enabled FROM command_definitions WHERE command IN ('/最受欢迎','/发情值排名');"
curl -s -o /dev/null -w 'healthz:%{http_code}\n' http://127.0.0.1:18120/healthz
