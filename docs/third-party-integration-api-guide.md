# DDZM 第三方员工与摸鱼币 API 接入文档

本文供获得授权的第三方服务端开发者使用。接口连接 DDZM 的正式员工、余额、游戏额度和余额流水数据。

## 1. 接入信息

基础地址：

```text
https://49.234.20.159/api/integration
```

所有请求都必须携带管理员单独提供的集成密钥：

```http
X-Api-Key: <管理员单独提供的 API Key>
```

请求与响应正文使用 UTF-8 JSON。除读取接口外，请求应携带：

```http
Content-Type: application/json
```

安全要求：

- API Key 只能保存在第三方服务端的环境变量或密钥管理服务中。
- 禁止把 API Key 写进网页、H5、客户端包、Git 仓库、日志或 URL。
- 必须验证 HTTPS 证书；禁止使用 `curl -k` 或关闭 TLS 校验。
- 禁止把 DDZM 返回的 `platform_id` 当作秘密。真正的授权凭据只有 API Key。
- API Key 泄露后应立即联系管理员轮换。

以下示例假设已在服务端安全设置：

```bash
export DZMM_INTEGRATION_API_KEY='<管理员单独提供的 API Key>'
export DZMM_INTEGRATION_BASE_URL='https://49.234.20.159/api/integration'
```

## 2. 员工标识规则

第三方 Bot 收到平台消息时，应优先使用消息发送者的稳定平台 UID 作为 `platform_id`。不要用昵称作为结算主键，因为昵称可以修改或重名。

员工匹配接口支持三种查找方式：

- `platform_id`：平台稳定 UID，程序自动结算时首选；
- `employee_number`：员工工号，接受 `#0001`、`0001` 或 `1`；
- `name`：员工显示名或平台昵称，只适合人工查找。

只有已经在 DDZM 入职的员工能被查询和结算。名字匹配返回 `ambiguous` 时，调用方必须要求用户改用平台 UID 或工号，不能任意选择其中一个人。

## 3. 匹配员工

### 请求

```http
POST /users/match
```

请求体必须且只能提供一个查找条件。

按平台 UID：

```json
{
  "platform_id": "11111111-2222-3333-4444-555555555555"
}
```

按工号：

```json
{
  "employee_number": "#0001"
}
```

按名称：

```json
{
  "name": "小明"
}
```

### 成功响应示例

```json
{
  "status": "matched",
  "matches": [
    {
      "platform_id": "11111111-2222-3333-4444-555555555555",
      "display_name": "小明",
      "employee_number": "#0001",
      "platform_nickname": "小明",
      "balance": 37
    }
  ]
}
```

`status` 可能为：

- `matched`：唯一匹配；
- `ambiguous`：名称命中多人，`matches` 会包含候选人；
- `not_found`：没有找到已入职员工，`matches` 为空。

### curl 示例

```bash
curl --fail-with-body \
  -X POST "$DZMM_INTEGRATION_BASE_URL/users/match" \
  -H "X-Api-Key: $DZMM_INTEGRATION_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"employee_number":"#0001"}'
```

## 4. 查询员工与余额

### 请求

```http
GET /users/{platform_id}/balance
```

### 成功响应示例

```json
{
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "display_name": "小明",
  "employee_number": "#0001",
  "platform_nickname": "小明",
  "balance": 37
}
```

### curl 示例

```bash
curl --fail-with-body \
  "$DZMM_INTEGRATION_BASE_URL/users/11111111-2222-3333-4444-555555555555/balance" \
  -H "X-Api-Key: $DZMM_INTEGRATION_API_KEY"
```

员工不存在时返回 `404`。

## 5. 查询游戏额度

### 请求

```http
GET /users/{platform_id}/game-quota
```

### 成功响应示例

```json
{
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "display_name": "小明",
  "employee_number": "#0001",
  "rank_name": "正式员工",
  "rank_limit": 2,
  "unlimited": false,
  "used_today": {
    "number_bomb": 1,
    "blame_game": 0,
    "texas_holdem": 0
  },
  "used_today_total": 1,
  "bonus_remaining": 0,
  "remaining": {
    "number_bomb": 1,
    "blame_game": 2,
    "texas_holdem": 2
  }
}
```

字段说明：

- `rank_limit`：当前职级的每类多人游戏基础次数；
- `unlimited`：是否不受基础次数限制；
- `used_today`：系统当前记录的各玩法当天已用次数；
- `used_today_total`：各玩法已用次数合计，仅用于展示；
- `bonus_remaining`：所有多人游戏共享的商店额外次数余量；
- `remaining`：各玩法基础剩余次数；无限次数员工为 `null`。

第三方应直接展示或使用返回结果，不要在自己的代码中复制 DDZM 的职级与额度算法。

### curl 示例

```bash
curl --fail-with-body \
  "$DZMM_INTEGRATION_BASE_URL/users/11111111-2222-3333-4444-555555555555/game-quota" \
  -H "X-Api-Key: $DZMM_INTEGRATION_API_KEY"
```

## 6. 增加摸鱼币

### 请求

```http
POST /coins/grant
```

```json
{
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "amount": 5,
  "reason": "第三方游戏奖励",
  "idempotency_key": "reward-round-20261015-000001"
}
```

### 成功响应示例

```json
{
  "ok": true,
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "display_name": "小明",
  "amount": 5,
  "balance_after": 42
}
```

规则：

- `amount` 必须是 `1..10000` 的整数；
- `reason` 长度为 `1..200`，会进入 DDZM 正式余额流水；
- `idempotency_key` 长度为 `8..128`，每次独立业务结算必须唯一。

### curl 示例

```bash
curl --fail-with-body \
  -X POST "$DZMM_INTEGRATION_BASE_URL/coins/grant" \
  -H "X-Api-Key: $DZMM_INTEGRATION_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "platform_id":"11111111-2222-3333-4444-555555555555",
    "amount":5,
    "reason":"第三方游戏奖励",
    "idempotency_key":"reward-round-20261015-000001"
  }'
```

## 7. 扣除摸鱼币

### 请求

```http
POST /coins/deduct
```

```json
{
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "amount": 5,
  "reason": "第三方游戏消费",
  "idempotency_key": "cost-round-20261015-000001",
  "allow_partial": false
}
```

### 成功响应示例

```json
{
  "ok": true,
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "display_name": "小明",
  "amount": 5,
  "balance_after": 32
}
```

默认必须使用 `allow_partial: false`：余额不足时整个请求失败，余额不变。

只有业务明确允许“有多少扣多少”时才传 `allow_partial: true`。部分扣除成功响应会返回：

```json
{
  "ok": true,
  "platform_id": "11111111-2222-3333-4444-555555555555",
  "display_name": "小明",
  "requested": 5,
  "actual_amount": 3,
  "balance_after": 0
}
```

调用方必须以 `actual_amount` 作为实际扣款额。

### curl 示例

```bash
curl --fail-with-body \
  -X POST "$DZMM_INTEGRATION_BASE_URL/coins/deduct" \
  -H "X-Api-Key: $DZMM_INTEGRATION_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "platform_id":"11111111-2222-3333-4444-555555555555",
    "amount":5,
    "reason":"第三方游戏消费",
    "idempotency_key":"cost-round-20261015-000001",
    "allow_partial":false
  }'
```

## 8. 幂等与重试

发币和扣币都是资金操作。调用方必须先生成并持久化一个业务唯一的 `idempotency_key`，再发送请求。

- 收到 `200`：保存返回结果，业务完成。
- 网络超时或连接中断：使用原请求和原 `idempotency_key` 重试。
- 同一个键重放同一个请求：返回第一次结果，不重复增扣。
- 同一个键用于不同员工、金额、动作或 `allow_partial`：返回 `409 idempotency_conflict`。
- 不得在一次业务尚未确认结果时换新键重试，否则可能造成重复结算。
- 幂等记录当前保留 24 小时；调用方自己的业务键仍应永久保持唯一。

推荐直接使用 UUID：

```python
from uuid import uuid4

idempotency_key = str(uuid4())
```

## 9. 状态码与错误处理

| HTTP 状态 | 含义 | 建议处理 |
| --- | --- | --- |
| `200` | 成功或成功结果的幂等重放 | 使用响应中的实际余额和金额 |
| `401` | API Key 缺失或错误 | 停止重试，检查密钥配置 |
| `404` | 员工不存在 | 提示用户先入职或核对 UID |
| `409` | 余额不足或幂等键冲突 | 根据错误码显示业务提示，不盲目重试 |
| `422` | 参数缺失、格式错误或超出范围 | 修正请求后再发起新业务请求 |
| `429` | 超过每分钟 60 次调用限制 | 指数退避；资金请求保持原幂等键 |
| `503` | 集成未启用或服务暂时不可用 | 退避并联系管理员 |

余额不足示例：

```json
{
  "detail": {
    "ok": false,
    "error": {
      "code": "insufficient_balance",
      "message": "余额不足"
    },
    "balance": 3,
    "requested": 5
  }
}
```

幂等冲突示例：

```json
{
  "detail": {
    "ok": false,
    "error": {
      "code": "idempotency_conflict",
      "message": "同一 Idempotency-Key 已用于不同请求"
    }
  }
}
```

调用方必须同时检查 HTTP 状态和响应正文，不能只判断是否收到了 JSON。

## 10. 上线前联调清单

1. 使用平台消息中的真实 `sent_by`/用户 UID 调用员工匹配。
2. 确认未入职用户返回 `not_found` 或 `404`。
3. 查询一名测试员工的初始余额。
4. 发放 1 币，确认余额增加 1。
5. 原样重放同一发币请求，确认余额不再次增加。
6. 使用新的幂等键扣除 1 币，确认余额恢复。
7. 原样重放同一扣币请求，确认余额不再次减少。
8. 验证余额不足时 `allow_partial: false` 返回 `409` 且余额不变。
9. 验证服务日志不会记录 API Key。
10. 确认生产环境没有使用 `curl -k`、`verify=False` 等关闭证书验证的设置。

联调遇到问题时，请提供请求时间、接口路径、HTTP 状态、错误正文和 `idempotency_key`，不要发送 API Key。
