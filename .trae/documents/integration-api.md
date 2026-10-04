# 摸鱼币集成接口使用说明

> 版本：2026-10-04（v1，随迁移 92 上线）
> 基地址：`http://43.153.194.94:18090/api/integration`
> 鉴权方式：请求头 `X-Api-Key`（独立 API Key，由管理员提供，与后台密码无关）

## 1. 接入要点

| 项 | 说明 |
|---|---|
| 协议 | HTTP + JSON（请求/响应均为 UTF-8 JSON） |
| 鉴权 | 每个请求带 `X-Api-Key: <你的Key>`；缺失或错误返回 401 |
| 限流 | 同一 Key 60 次/分钟，超限返回 429 |
| 金额单位 | 摸鱼币，正整数，单次 1 ~ 10000 |
| 幂等 | 发币/扣币必须携带 `idempotency_key`（8~128 字符），服务端按 key 去重 |
| 审计 | 每笔发/扣都会写入摸鱼币流水（来源 `api_grant` / `api_deduct`，备注为 reason） |

## 2. 接口一览

| # | 方法 | 路径 | 用途 |
|---|---|---|---|
| 1 | POST | `/users/match` | 按用户名 / 工号 / 平台ID 匹配注册员工 |
| 2 | GET | `/users/{platform_id}/balance` | 查询余额 |
| 3 | POST | `/coins/grant` | 发币 |
| 4 | POST | `/coins/deduct` | 扣币 |

## 3. 接口详情

### 3.1 匹配员工 `POST /users/match`

三个参数**三选一**，同时传多个或都不传返回 422。

```json
{ "name": "糯糯" }
{ "employee_number": "#0001" }
{ "platform_id": "a56cbd67-3a1e-439a-8beb-d1557dbeff79" }
```

成功响应（`status` 三种取值）：

```json
{
  "status": "matched",
  "matches": [
    {
      "platform_id": "a56cbd67-3a1e-439a-8beb-d1557dbeff79",
      "display_name": "糯糯",
      "employee_number": "#0001",
      "platform_nickname": null,
      "balance": 61
    }
  ]
}
```

- `matched`：唯一命中，直接取 `matches[0].platform_id` 去调用发/扣币
- `ambiguous`：名字/昵称命中多个，`matches` 返回全部候选（含工号），需要调用方让用户消歧后用 platform_id 或工号重查
- `not_found`：没有命中

匹配规则：名字先按系统注册名（display_name）精确匹配，未命中再按平台昵称精确匹配；工号接受 `#0001`、`0001`、`1` 三种写法。

### 3.2 查询余额 `GET /users/{platform_id}/balance`

```
GET /api/integration/users/{platform_id}/balance
```

```json
{
  "platform_id": "a56cbd67-...",
  "display_name": "糯糯",
  "employee_number": "#0001",
  "platform_nickname": null,
  "balance": 61
}
```

员工不存在返回 404。

### 3.3 发币 `POST /coins/grant`

```json
{
  "platform_id": "a56cbd67-3a1e-439a-8beb-d1557dbeff79",
  "amount": 5,
  "reason": "直播抽奖",
  "idempotency_key": "your-unique-key-0001"
}
```

成功（200）：

```json
{
  "ok": true,
  "platform_id": "a56cbd67-...",
  "display_name": "糯糯",
  "amount": 5,
  "balance_after": 66
}
```

### 3.4 扣币 `POST /coins/deduct`

```json
{
  "platform_id": "a56cbd67-3a1e-439a-8beb-d1557dbeff79",
  "amount": 5,
  "reason": "商城兑换",
  "idempotency_key": "your-unique-key-0002",
  "allow_partial": false
}
```

成功（200）：

```json
{ "ok": true, "platform_id": "a56cbd67-...", "display_name": "糯糯", "amount": 5, "balance_after": 56 }
```

**余额不足**（默认拒绝，409）：

```json
{
  "ok": false,
  "error": { "code": "insufficient_balance", "message": "余额不足" },
  "balance": 3,
  "requested": 5
}
```

**部分扣除**：请求加 `"allow_partial": true` → 余额不够时扣到 0 为止，返回实际扣除额：

```json
{ "ok": true, "requested": 5, "actual_amount": 3, "balance_after": 0 }
```

（余额为 0 时 `actual_amount` 为 0，也返回 200。）

## 4. 幂等机制（重要）

- 每次发/扣生成**全局唯一**的 `idempotency_key`（建议 UUID 或 `业务前缀+单号`）。
- **网络超时后重试请复用同一个 key**：服务端返回首次的完整响应，不会重复加/扣钱。
- 同一个 key 若用于**内容不同**的请求（金额不同等），返回 409 `idempotency_conflict`。
- key 的去重窗口为 24 小时，之后同 key 可再使用（不要复用旧 key 发新单）。
- 查询接口（match/balance）无需幂等键。

## 5. 错误码汇总

| HTTP | 场景 | body |
|---|---|---|
| 401 | X-Api-Key 缺失或错误 | `{"detail":"unauthorized"}` |
| 404 | platform_id 不存在 | `{"detail":"没找到员工（platform_id=...）"}` |
| 409 | 余额不足（默认模式） | `{"ok":false,"error":{"code":"insufficient_balance",...},"balance":N,"requested":M}` |
| 409 | 幂等键冲突 | `{"ok":false,"error":{"code":"idempotency_conflict","message":"同一 Idempotency-Key 已用于不同请求"}}` |
| 422 | 参数非法（金额越界/多选一/缺字段等） | `{"detail":"..."}` |
| 429 | 超过 60 次/分钟 | `{"detail":"rate limit exceeded"}` |
| 503 | 服务端未启用集成接口 | `{"detail":"integration disabled"}` |

## 6. curl 示例

```bash
KEY="你的X-Api-Key"
BASE="http://43.153.194.94:18090/api/integration"

# 1. 按名字找员工
curl -s -X POST "$BASE/users/match" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name":"糯糯"}'

# 2. 查余额
curl -s "$BASE/users/<platform_id>/balance" -H "X-Api-Key: $KEY"

# 3. 发 5 币
curl -s -X POST "$BASE/coins/grant" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"platform_id":"<platform_id>","amount":5,"reason":"直播抽奖","idempotency_key":"live-20261004-0001"}'

# 4. 扣 5 币（不足则报 409）
curl -s -X POST "$BASE/coins/deduct" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"platform_id":"<platform_id>","amount":5,"reason":"商城兑换","idempotency_key":"shop-20261004-0001"}'
```

## 7. 注意事项

1. **发币计入当日收益榜**：`api_grant` 是正流水，会出现在群内"今日收益榜"推送里；扣币不影响榜单。
2. **reason 会永久落库**（流水 memo），请写有业务含义的短句，便于对账。
3. 本接口**不占**群内"每人每日 5 币津贴封顶"，是独立的资金通道。
4. 请妥善保管 X-Api-Key，不要写入前端代码或公开仓库；泄露后联系管理员轮换。
5. 限流为 60 次/分钟，批量操作请自行控制节奏（收到 429 后建议退避 60 秒）。
