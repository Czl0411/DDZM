#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "SELECT created_at, status, left(text, 400) AS text FROM outbound_messages WHERE text LIKE '%爆表%' OR text LIKE '%发情值排名%' ORDER BY created_at DESC LIMIT 3;"
