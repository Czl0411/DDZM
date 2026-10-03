#!/bin/bash
# 设置三位人设账号性别为女
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "
UPDATE users SET gender = 'female'
WHERE platform_id IN (
  'a56cbd67-3a1e-439a-8beb-d1557dbeff79',  -- 糯糯
  '503e3cb9-ee6f-4e17-be51-e4ca399b4515',  -- 小小糯
  '7a052895-9738-46ab-8e41-00de358372f7'   -- 墨莲
);
"
psql "$DB" -c "SELECT display_name, gender FROM users WHERE display_name IN ('糯糯','小小糯','墨莲');"
