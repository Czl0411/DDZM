# 第三方员工与摸鱼币集成 API 设计

## 目标

向单个已授权的第三方开发者开放现有员工与摸鱼币集成能力，使其使用另一主账号 Bot 开发功能时，可以通过 DDZM 后端读取同一批员工数据，并在同一套余额与流水中发放或扣除摸鱼币。

第三方不得直连数据库、复用后台管理员凭据或访问 Core 内部接口。所有调用必须经过独立鉴权的公网 HTTPS 集成入口。

## 已确认范围

开放当前已经实现的全部五项能力：

1. 按员工名、平台 UID 或工号匹配员工。
2. 按平台 UID 查询员工基础资料与最新余额。
3. 按平台 UID 查询小游戏每日发起额度。
4. 给指定员工增加摸鱼币。
5. 从指定员工扣除摸鱼币。

员工基础资料只包含现有集成接口已经返回的字段，不增加档案、生日、部门内部资料、聊天记录或 AI 记忆等数据。

## 不在本次范围

- 不新增、编辑或删除员工。
- 不向第三方开放管理后台、`/internal/*`、数据库或服务器权限。
- 不提供批量发币、批量扣币或全员发放接口。
- 不新增 OAuth、JWT、HMAC、多租户密钥或后台密钥管理页面。
- 不改变现有摸鱼币规则、游戏额度算法、余额流水结构或 Bot 指令。
- 不修改现有五个集成接口的请求或响应结构。

## 方案选择

### 采用：单个独立 API Key

当前只有一个第三方调用方，复用现有 `DZMM_INTEGRATION_API_KEY` 和 `X-Api-Key` 鉴权。该方案不改业务代码，部署面最小，并保留现有恒定时间比较、限流、幂等和账本事务。

### 暂不采用：读写分离 Key

可以把查询与增扣权限拆成不同密钥，但当前第三方明确需要全部现有能力。此方案需要新增权限模型与部署配置，暂时没有实际收益。

### 暂不采用：每个调用方独立签名

HMAC 或 OAuth 适合多个合作方、密钥轮换和精细审计。当前只有一个调用方，引入该体系会显著增加实现和接入成本；以后出现第二个独立合作方时再升级。

## 网络与服务边界

公网基地址：

```text
https://49.234.20.159/api/integration
```

请求链路：

```text
第三方服务端
  -> HTTPS 443 /api/integration/*
  -> Caddy
  -> 127.0.0.1:18080 管理服务
  -> X-Api-Key 鉴权与限流
  -> X-Core-Token 内部转发
  -> 127.0.0.1:18120 Core
  -> PostgreSQL 同一员工、余额与流水数据
```

Caddy 只新增 `/api/integration/*` 到管理服务的反向代理规则。不能把该路径直接转发到 Core，也不能把管理服务的其他 `/api/*` 路径一起暴露到 443。

现有 IP HTTPS 证书覆盖 `49.234.20.159`。部署前后都必须核验证书有效期和自动续期状态；第三方客户端不得关闭 TLS 证书校验。

## 鉴权与密钥管理

- 生成一把新的高熵随机密钥，写入服务器 root-only 的 `/etc/dzmm/dzmm.env`：

  ```text
  DZMM_INTEGRATION_API_KEY=<随机密钥>
  ```

- 第三方通过请求头发送：

  ```http
  X-Api-Key: <随机密钥>
  ```

- 密钥不得进入 URL、浏览器/H5 前端、本仓库、日志或公开文档。
- 最终交付文档使用占位符，不包含真实密钥；真实密钥单独交付。
- 配置后只重启 `dzmm-admin-web`。不重启 Core、Browser Worker 或已关闭的 AI Worker。
- 当前实现只有一把有效集成密钥；轮换时更新服务器和调用方后，旧密钥立即失效。

## 接口契约

### 1. 匹配员工

```http
POST /api/integration/users/match
Content-Type: application/json
X-Api-Key: <key>
```

请求体必须且只能提供以下一项：

```json
{"platform_id":"平台 UID"}
```

```json
{"employee_number":"#0001"}
```

```json
{"name":"员工名或平台昵称"}
```

返回 `matched`、`ambiguous` 或 `not_found`，并在匹配项中返回：

- `platform_id`
- `display_name`
- `employee_number`
- `platform_nickname`
- `balance`

名字可能重名；第三方不能在 `ambiguous` 时任意选择，必须要求用户改用 UID 或工号。

### 2. 查询员工与余额

```http
GET /api/integration/users/{platform_id}/balance
X-Api-Key: <key>
```

返回与员工匹配项相同的基础字段和最新余额。员工不存在时返回 `404`。

### 3. 查询游戏额度

```http
GET /api/integration/users/{platform_id}/game-quota
X-Api-Key: <key>
```

返回员工职级、是否无限次数、各玩法当天已用次数、额外额度余量和剩余额度。第三方只读取结果，不自行复制或推算 DDZM 的额度规则。

### 4. 增加摸鱼币

```http
POST /api/integration/coins/grant
Content-Type: application/json
X-Api-Key: <key>
```

```json
{
  "platform_id": "平台 UID",
  "amount": 5,
  "reason": "第三方游戏奖励",
  "idempotency_key": "第三方生成的唯一请求键"
}
```

`amount` 范围为 `1..10000`。成功后返回实际变动和 `balance_after`，并在统一余额流水中写入 `api_grant` 与 `reason`。

### 5. 扣除摸鱼币

```http
POST /api/integration/coins/deduct
Content-Type: application/json
X-Api-Key: <key>
```

```json
{
  "platform_id": "平台 UID",
  "amount": 5,
  "reason": "第三方游戏消费",
  "idempotency_key": "第三方生成的唯一请求键",
  "allow_partial": false
}
```

默认 `allow_partial=false`。余额不足时返回 `409 insufficient_balance`，余额保持不变。只有第三方业务明确接受“余额有多少扣多少”时才可传 `true`；此时响应中的 `actual_amount` 才是实际扣除额。

## 幂等、并发与账本

- 每次发币或扣币必须生成新的 `idempotency_key`，长度 `8..128`。
- 同一个键和同一个请求在 24 小时内重放，返回第一次结果，不重复结算。
- 同一个键用于不同动作、员工、金额或 `allow_partial` 时返回 `409 idempotency_conflict`。
- `reason` 长度 `1..200`，用于余额流水审计，但不参与当前请求指纹；第三方不得用同一幂等键表达新的业务操作。
- 发扣币与余额流水在同一数据库事务中完成，复用现有原子余额更新。
- 每把 Key 当前共享每分钟 60 次集成调用限额，超过时返回 `429`。

## 错误处理

第三方必须按 HTTP 状态处理结果，不能把非 `2xx` 当成功：

| 状态 | 含义 | 调用方处理 |
| --- | --- | --- |
| `200` | 成功或幂等重放成功 | 使用响应中的实际余额和金额 |
| `401` | Key 缺失或错误 | 停止重试并检查密钥配置 |
| `404` | 员工不存在 | 要求用户先入职或核对 UID |
| `409` | 余额不足或幂等冲突 | 展示业务错误；冲突时生成新业务请求前先排查 |
| `422` | 参数格式或范围错误 | 修正请求，不原样重试 |
| `429` | 超过每分钟 60 次 | 退避后重试只读请求；写请求继续使用原幂等键 |
| `503` | 集成未启用或服务不可用 | 退避并联系管理员，不切换为直连数据库 |

网络超时后的写请求必须使用原 `idempotency_key` 重试，不能生成新键。

## 部署步骤

1. 备份 `/etc/caddy/Caddyfile` 和 `/etc/dzmm/dzmm.env` 的当前版本。
2. 生成并配置 `DZMM_INTEGRATION_API_KEY`，保持环境文件权限为 `600`。
3. 在 Caddy 中新增精确的 `/api/integration/*` 反向代理到 `127.0.0.1:18080`。
4. 运行 `caddy validate`，通过后仅 reload Caddy。
5. 重启 `dzmm-admin-web` 以加载密钥。
6. 确认 Core、Browser Worker 和 Bot 消息收发未受影响。

## 验收标准

部署完成必须满足：

1. HTTPS 证书校验成功，证书包含 IP `49.234.20.159`，自动续期处于可用状态。
2. 未带 Key 和错误 Key 请求返回 `401`；不能返回员工数据。
3. 正确 Key 可完成员工匹配、余额查询和游戏额度查询。
4. 使用测试员工发放 1 币后余额与流水各增加一次。
5. 重放同一发币请求，响应一致且余额不再次增加。
6. 使用另一个幂等键扣除 1 币后余额恢复，流水记录一次。
7. 重放同一扣币请求，余额不再次减少。
8. 对余额不足员工默认扣币返回 `409`，余额不变。
9. `/api/integration/*` 之外的管理 API 仍不通过 443 暴露。
10. Bot 的 Core、管理服务和 Browser Worker 均保持运行，消息队列无积压。

## 第三方交付物

实施完成后另行生成一份不含真实密钥的接入文档，内容包括：

- 基地址和鉴权头；
- 五个接口的请求、响应和 `curl` 示例；
- 字段说明；
- 幂等规则；
- 错误码及重试规则；
- 安全要求；
- 联调检查清单。

真实 API Key 与文档分开交付。
