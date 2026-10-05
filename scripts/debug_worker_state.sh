#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
echo "===== worker 心跳状态 ====="
psql "$DB" -c "SELECT worker_id, login_state, listening, listening_desired, recorded_at FROM worker_instances ORDER BY recorded_at DESC LIMIT 3;"
