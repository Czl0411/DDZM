#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"

echo "===== 1. 津贴设置（submission_amount / daily_cap）====="
psql "$DB" -x -c "SELECT submission_amount, chat_drop_percent, chat_drop_cooldown_seconds, daily_cap FROM department_allowance_settings;"

echo "===== 2. 部门绑定 ====="
psql "$DB" -c "SELECT left(name, 14) AS dept, allowance_kind, enabled FROM departments WHERE enabled AND allowance_kind IS NOT NULL;"

echo "===== 3. 最近的投稿记录 ====="
psql "$DB" -c "SELECT * FROM random_event_submissions ORDER BY created_at DESC LIMIT 3;" 2>/dev/null || psql "$DB" -c "\d random_event_submissions"

echo "===== 4. 今日全部津贴台账 ====="
psql "$DB" -c "SELECT u.display_name, r.kind, r.amount, r.created_at FROM department_allowances r JOIN users u ON u.id = r.user_id WHERE r.allow_date = (now() AT TIME ZONE 'Asia/Shanghai')::date ORDER BY r.created_at DESC LIMIT 15;"
