#!/bin/bash
# 水群掉落排查：设置面额 / 部门绑定 / 今日台账 / 活跃游戏上下文
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
TARGET_UID='a56cbd67-3a1e-439a-8beb-d1557dbeff79'  # 糯糯

echo "===== 1. 津贴设置（重点看 chat_drop_amount 是否为 0）====="
psql "$DB" -x -c "SELECT chat_drop_percent, chat_drop_amount, chat_drop_cooldown_seconds, daily_cap FROM department_allowance_settings;"

echo "===== 2. 测试者部门绑定 ====="
psql "$DB" -x -c "SELECT u.display_name, d.name AS dept, d.enabled AS dept_enabled, d.allowance_kind FROM users u LEFT JOIN departments d ON d.id = u.department_id WHERE u.platform_id='$TARGET_UID';"

echo "===== 3. 今日津贴台账（最近 10 条）====="
psql "$DB" -c "SELECT r.allow_date, r.kind, r.amount, r.created_at FROM department_allowances r JOIN users u ON u.id = r.user_id WHERE u.platform_id='$TARGET_UID' ORDER BY r.created_at DESC LIMIT 10;"

echo "===== 4. 活跃游戏上下文（与 user_has_active_game_context 完全一致的 5 项）====="
psql "$DB" -c "
SELECT 'random_event' AS src, e.id::text, e.state AS detail FROM random_event_participants p JOIN random_events e ON e.id = p.event_id JOIN users u ON u.id = p.user_id WHERE u.platform_id='$TARGET_UID' AND p.left_at IS NULL AND e.state IN ('signup','in_progress','tipping')
UNION ALL SELECT 'undercover', s.id::text, s.active_key FROM undercover_session_members m JOIN undercover_sessions s ON s.id = m.session_id JOIN users u ON u.id = m.user_id WHERE u.platform_id='$TARGET_UID' AND m.state='joined' AND s.active_key IS NOT NULL
UNION ALL SELECT 'memory_assessment', g.id::text, g.active_key FROM memory_assessment_participants p JOIN memory_assessment_games g ON g.id = p.game_id JOIN users u ON u.id = p.user_id WHERE u.platform_id='$TARGET_UID' AND g.active_key IS NOT NULL
UNION ALL SELECT 'hide_and_seek(selecting)', g.id::text, g.state FROM hide_and_seek_games g JOIN users u ON u.id = g.user_id WHERE u.platform_id='$TARGET_UID' AND g.state='selecting'
UNION ALL SELECT 'blame', g.id::text, g.active_key FROM blame_game_players p JOIN blame_games g ON g.id = p.game_id JOIN users u ON u.id = p.user_id WHERE u.platform_id='$TARGET_UID' AND p.state='joined' AND g.active_key IS NOT NULL;
"
echo "===== done（4 无输出 = 无活跃上下文）====="

echo "===== 5. 测试者最近 15 条入站消息（验证消息是否到达 core）====="
psql "$DB" -c "SELECT received_at, source_type, left(content, 30) AS content FROM inbound_messages WHERE sender_platform_id='$TARGET_UID' ORDER BY received_at DESC LIMIT 15;"

echo "===== 6. 最近 10 条入站消息（任意人，看群消息流是否活着）====="
psql "$DB" -c "SELECT received_at, sender_platform_id, left(content, 24) AS content FROM inbound_messages ORDER BY received_at DESC LIMIT 10;"

echo "===== 7. 近 12 小时入站消息按小时计数 ====="
psql "$DB" -c "SELECT date_trunc('hour', received_at) AS hr, count(*) FROM inbound_messages WHERE received_at > now() - interval '12 hours' GROUP BY 1 ORDER BY 1;"

echo "===== 8. 历史全部 dept_chat 台账（最近 10 条）====="
psql "$DB" -c "SELECT r.allow_date, u.display_name, r.amount, r.created_at FROM department_allowances r JOIN users u ON u.id = r.user_id WHERE r.kind='dept_chat' ORDER BY r.created_at DESC LIMIT 10;"

echo "===== 9. 另两位测试者档案 ====="
psql "$DB" -c "SELECT u.platform_id, u.display_name, u.department_id IS NOT NULL AS employed, d.name AS dept, d.allowance_kind FROM users u LEFT JOIN departments d ON d.id = u.department_id WHERE u.platform_id IN ('fbe07655-1e51-41c7-af90-2f28580810cd','7a052895-9738-46ab-8e41-00de358372f7','a56cbd67-3a1e-439a-8beb-d1557dbeff79');"

echo "===== 10. 当前活跃随机事件与最近事件时间线 ====="
psql "$DB" -c "SELECT id, state, group_chat_id, created_at FROM random_events ORDER BY created_at DESC LIMIT 5;"

echo "===== 11. 最近出站消息（机器人最后发声时间）====="
psql "$DB" -c "SELECT created_at, status, left(text, 40) AS text FROM outbound_messages ORDER BY created_at DESC LIMIT 12;"
