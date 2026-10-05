#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"

echo "===== 1. worker 最近 8 条日志 ====="
journalctl -u dzmm-browser-worker -n 8 --no-pager -o short

echo "===== 2. 最近 8 条入站消息 ====="
psql "$DB" -c "SELECT received_at, left(content, 24) AS content FROM inbound_messages ORDER BY received_at DESC LIMIT 8;"

echo "===== 3. 凿系指令种子 ====="
psql "$DB" -c "SELECT command, enabled FROM command_definitions WHERE command LIKE '%凿%' OR command LIKE '%发情%' OR command LIKE '%性别%';"

echo "===== 4. 最近 5 条出站 ====="
psql "$DB" -c "SELECT created_at, status, left(text, 30) AS text FROM outbound_messages ORDER BY created_at DESC LIMIT 5;"
