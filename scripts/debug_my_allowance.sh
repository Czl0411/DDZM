#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"

echo "===== A. 指令种子状态 ====="
psql "$DB" -c "SELECT command, enabled FROM command_definitions WHERE command LIKE '%津贴%' OR command LIKE '%罚款%';"

echo "===== A2. 群聊启用配置 ====="
psql "$DB" -c "SELECT left(name, 12) AS name, left(chatroom_id, 8) AS room, listening_enabled, games_enabled FROM group_chats;"

echo "===== B. 最近 10 条入站消息 ====="
psql "$DB" -c "SELECT received_at, left(content, 20) AS content FROM inbound_messages ORDER BY received_at DESC LIMIT 10;"

echo "===== C. 最近 6 条出站消息 ====="
psql "$DB" -c "SELECT created_at, status, left(text, 30) AS text FROM outbound_messages ORDER BY created_at DESC LIMIT 6;"

echo "===== D. worker 最近日志 ====="
journalctl -u dzmm-browser-worker -n 12 --no-pager -o short

echo "===== E. core 最近日志（错误）====="
journalctl -u dzmm-core -n 20 --no-pager -o short | grep -iE 'error|exception|traceback' | tail -5
