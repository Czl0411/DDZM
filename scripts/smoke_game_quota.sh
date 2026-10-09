#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
echo "===== workers ====="
systemctl is-active dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker
echo "===== game-quota 冒烟（糯糯） ====="
curl -s "http://127.0.0.1:18090/api/integration/users/a56cbd67-3a1e-439a-8beb-d1557dbeff79/game-quota" -H "X-Api-Key: $DZMM_INTEGRATION_API_KEY"
echo
curl -s -o /dev/null -w 'healthz:%{http_code}\n' http://127.0.0.1:18120/healthz
