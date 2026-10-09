#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
echo "=== control: department-allowances (old endpoint) ==="
curl -s -H "X-Core-Token: $DZMM_CORE_TOKEN" http://127.0.0.1:18120/internal/game/department-allowances/settings | head -c 120
echo
echo "=== liar-dice settings ==="
curl -s -H "X-Core-Token: $DZMM_CORE_TOKEN" http://127.0.0.1:18120/internal/game/liar-dice/settings
echo
echo "=== truth-trade settings ==="
curl -s -H "X-Core-Token: $DZMM_CORE_TOKEN" http://127.0.0.1:18120/internal/game/truth-trade/settings
echo
echo "=== table ==="
psql "${DZMM_DATABASE_URL/postgresql+psycopg/postgresql}" -c "SELECT turn_seconds FROM liar_dice_settings;"
