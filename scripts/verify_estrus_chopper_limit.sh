#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
echo "===== services ====="
systemctl list-units 'dzmm-*' --no-legend --plain | grep dzmm
curl -s -o /dev/null -w 'healthz:%{http_code}\n' http://127.0.0.1:18120/healthz
echo "===== command rename ====="
psql "$DB" -c "SELECT command, enabled FROM command_definitions WHERE command IN ('/我的凿','/我的发情值');"
echo "===== new column ====="
psql "$DB" -c "SELECT chopper_daily_limit FROM estrus_settings;"
