#!/bin/bash
set -a
source /etc/dzmm/dzmm.env
set +a
KEY="$DZMM_INTEGRATION_API_KEY"
BASE="http://127.0.0.1:18090/api/integration"

echo "===== 1. 名字匹配（糯糯） ====="
MATCH=$(curl -s -X POST "$BASE/users/match" -H "X-Api-Key: $KEY" -H "Content-Type: application/json" -d '{"name":"糯糯"}')
echo "$MATCH"
PID=$(echo "$MATCH" | grep -o '"platform_id":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "===== 2. 无 key 应 401 ====="
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/users/match" -H "Content-Type: application/json" -d '{"name":"糯糯"}'

echo "===== 3. 余额查询 ====="
curl -s "$BASE/users/$PID/balance" -H "X-Api-Key: $KEY"
echo

echo "===== 4. 发 1 币 ====="
curl -s -X POST "$BASE/coins/grant" -H "X-Api-Key: $KEY" -H "Content-Type: application/json" -d "{\"platform_id\":\"$PID\",\"amount\":1,\"reason\":\"接口联通测试\",\"idempotency_key\":\"smoke-grant-20261004\"}"
echo

echo "===== 5. 扣 1 币 ====="
curl -s -X POST "$BASE/coins/deduct" -H "X-Api-Key: $KEY" -H "Content-Type: application/json" -d "{\"platform_id\":\"$PID\",\"amount\":1,\"reason\":\"接口联通测试\",\"idempotency_key\":\"smoke-deduct-20261004\"}"
echo

echo "===== 6. 幂等重放（同 key 再扣 1，余额应不变） ====="
curl -s -X POST "$BASE/coins/deduct" -H "X-Api-Key: $KEY" -H "Content-Type: application/json" -d "{\"platform_id\":\"$PID\",\"amount\":1,\"reason\":\"接口联通测试\",\"idempotency_key\":\"smoke-deduct-20261004\"}"
echo

echo "===== 7. 最终余额 ====="
curl -s "$BASE/users/$PID/balance" -H "X-Api-Key: $KEY"
echo
