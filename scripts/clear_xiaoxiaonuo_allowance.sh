#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"

echo "===== 删除前：小小糯的津贴台账 ====="
psql "$DB" -c "SELECT r.kind, r.amount, r.allow_date, r.created_at FROM department_allowances r JOIN users u ON u.id = r.user_id WHERE u.display_name = '小小糯' ORDER BY r.created_at;"

echo "===== 执行清空 ====="
psql "$DB" -c "DELETE FROM department_allowances r USING users u WHERE r.user_id = u.id AND u.display_name = '小小糯';"

echo "===== 验证：删除后台账 ====="
psql "$DB" -c "SELECT count(*) AS remaining FROM department_allowances r JOIN users u ON u.id = r.user_id WHERE u.display_name = '小小糯';"
