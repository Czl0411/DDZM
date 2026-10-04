#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
DB="${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}"
psql "$DB" -c "
INSERT INTO estrus_states (id, group_chat_id, user_id, heat, chopped_count, total_climaxes, today_climaxes, last_active_date, opted_out, created_at, updated_at)
SELECT gen_random_uuid(), g.id, u.id, 99, 0, 0, 0, NULL, false, now(), now()
FROM users u, group_chats g
WHERE u.platform_id = 'a56cbd67-3a1e-439a-8beb-d1557dbeff79'
  AND g.chatroom_id = 'c1f72c3c-409b-4c5a-be74-51370922a270'
ON CONFLICT (group_chat_id, user_id) DO UPDATE SET heat = 99, today_climaxes = 0, last_active_date = CURRENT_DATE, updated_at = now();
"
psql "$DB" -c "SELECT u.display_name, s.heat, s.chopped_count, s.opted_out FROM estrus_states s JOIN users u ON u.id = s.user_id WHERE u.display_name = '糯糯';"
