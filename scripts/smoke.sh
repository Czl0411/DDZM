#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
TOKEN=$(printf '%s' "$DZMM_CORE_TOKEN" | md5sum >/dev/null; echo "$DZMM_CORE_TOKEN")
curl -s -H "X-Core-Token: $DZMM_CORE_TOKEN" http://127.0.0.1:18120/internal/game/department-allowances/settings | head -c 400
echo
env | grep -oE '^DZMM_[A-Z_]+=' | head -10
