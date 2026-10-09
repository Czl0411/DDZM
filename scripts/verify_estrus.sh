#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
echo "=== estrus settings ==="
curl -s -H "X-Core-Token: $DZMM_CORE_TOKEN" http://127.0.0.1:18120/internal/game/estrus/settings
echo
echo "=== tables ==="
psql "${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}" -c "\dt estrus*;"
psql "${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}" -c "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='gender';"
