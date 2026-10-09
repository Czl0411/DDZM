#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
echo "===== 1. 糯糯与最近活跃用户的性别 ====="
psql "$DB" -c "SELECT display_name, gender, platform_id FROM users WHERE display_name IN ('糯糯','小小糯','墨莲') OR gender IS DISTINCT FROM 'unknown' ORDER BY display_name LIMIT 20;"
echo "===== 2. 最近 5 次凿击 ====="
psql "$DB" -c "SELECT c.heat_gain, c.coins, c.climax_triggered, c.created_at, tu.display_name AS target, cu.display_name AS chopper FROM estrus_chops c JOIN users tu ON tu.id = c.target_user_id JOIN users cu ON cu.id = c.chopper_user_id ORDER BY c.created_at DESC LIMIT 5;"
echo "===== 3. 最近出站消息（看高潮正文用了哪套词） ====="
psql "$DB" -c "SELECT status, left(text, 260) AS text FROM outbound_messages ORDER BY created_at DESC LIMIT 6;"
