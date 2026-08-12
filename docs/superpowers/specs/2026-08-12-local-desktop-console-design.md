# 本机 DZMM 机器人管理桌面端设计

## 目标

提供一个可安装在 macOS 和 Windows 的本机 DZMM 机器人控制台。第一期只包含专用账号登录会话、多目标群实时消息监控与手动发送、Worker 控制、日志和每日签到；不迁移现有 DDZM 的游戏、AI、远程 Core 或 PostgreSQL 功能。

## 范围与约束

- 使用 Electron、React 和 TypeScript 构建跨平台桌面端。
- 运行时完全本机化：SQLite、配置、消息记录、签到记录、日志索引和 DZMM 专用浏览器会话均保存于应用数据目录。
- 应用内嵌 DZMM 登录页，登录会话与 Worker 使用同一个 Electron 持久化 session。
- DZMM Cookie、短期 access token 和用户密码不得写入 SQLite、应用日志或 UI。
- 可配置多个目标群：新增、移除、命名、启用或停用；群由绝对聊天 URL 配置，URL 必须含 `c=<chatroom_id>`。
- Socket.IO 的 `message:new` 是唯一实时主入站通道。`chatroom.getMessages` 仅在 Worker 启动、Socket 重连和固定补偿间隔执行，用于弥补实时事件遗漏，不能作为主消息通道。
- 普通出站消息走 `message:send`，且仅收到成功 ACK 后才记为已发送；发送失败不走其他路径自动重发。
- 仅支持文本消息和群聊；私聊、撤回、官方 Bot 长消息及 Webhook 不在第一期范围内。
- 首期唯一自动指令为精确文本 `签到`。每个群可单独启用签到和配置成功/重复模板，模板支持 `{name}`。

## 技术方案

### 方案选择

采用 Electron + React + TypeScript + Node Socket.IO + SQLite。

Electron 能让内嵌网页与 Worker 共用持久化 session，从当前认证页面安全取得短期 token 并调用已验证的 Socket.IO 协议。Tauri 虽然安装包更小，但嵌入式网页认证和 Socket.IO 协议复用成本更高；Electron 外壳配 Python Worker 会形成两个不应共用的浏览器会话。因此前者是第一期的最小可靠方案。

### 进程与数据流

```text
React 渲染进程
        │ IPC（受限白名单）
Electron 主进程 ─── SQLite
        │
        ├── DZMM 持久化 session（内嵌登录页）
        │        │
        │        └── /api/auth/token、tRPC 请求、Cookie
        │
        └── SocketWorker
                 ├── message:new → 入站处理、消息存储、签到
                 ├── message:send ← 手动发送、签到回复
                 └── chatroom.getMessages（补偿）
```

主进程拥有所有凭据、Socket 和数据库访问。渲染进程不得直接访问 Node、文件系统、Cookie 或 token；只可通过 `contextBridge` 暴露的最小 IPC 方法读写界面所需数据和控制 Worker。

### DZMM 会话与连接

使用名为 `persist:dzmm` 的 Electron session 打开 `DZMM_LOGIN_URL`，默认是 `https://www.aikda.com/sign-in`。登录后从同一 session 的活动页面调用 `GET /api/auth/token`，并从该 session 读取目标 origin 的 Cookie 头。

Worker 启动或重连时先调用 `user.getMe` 确认当前账号并获得自身平台 ID；随后以 token 连接 `<origin>` 的 Socket.IO 路径 `ws/matching`，认证载荷为 `{ token }`。连接并收到 `message:joined` 后，对每个启用目标群调用 `message:join-room({ chatroomId })`。

Worker 监听 `message:new`，只接收已启用群、文本内容、含平台消息 ID、发送者 ID 和发送时间的消息，并忽略自身平台 ID 发出的消息。断线、token 失效或认证失败会进入 `reconnecting` 或 `auth_required` 状态；重连成功后重新加入所有启用群并立即补偿。

### 历史补偿

补偿调用 `chatroom.getMessages({ chatroomId })`。它在下列时机运行：

1. Socket 完成首次连接并加入所有已启用群后；
2. 每次 Socket 重新连接并重新加入后；
3. Worker 运行期间按固定配置间隔执行，默认 5 秒。

每条历史或实时消息先写入 SQLite 的平台消息 ID 唯一索引；冲突时忽略。因此同一消息无论来自 Socket 还是补偿，最多处理一次。

### 用户资料适配器

用户资料查询封装在单独的 `DzmmUserDirectory` 中，调用已观察到的 `user.getChatroomUser` procedure，以群 ID 与平台用户 ID 查询。实际请求参数和昵称字段在开发时从已登录 DZMM 页面验证后写入适配器和测试 fixture，禁止依据猜测绑定字段。

签到不依赖资料查询成功。查询成功后缓存平台用户 ID、群 ID、昵称和更新时间；查询失败时记录不含凭据的 warning，并在模板中将 `{name}` 渲染为“这位成员”。

## 本地数据

SQLite 数据库位于应用数据目录。首期包含以下逻辑实体：

| 实体 | 关键字段 | 用途 |
| --- | --- | --- |
| `settings` | key, value | 补偿间隔等非敏感设置。 |
| `groups` | id, chatroom_id, chat_url, name, enabled | 多目标群配置；`chatroom_id` 唯一。 |
| `messages` | platform_message_id, group_id, sender_id, text, sent_at, direction | 实时监控与手动发送记录；平台消息 ID 唯一。 |
| `checkins` | group_id, platform_user_id, checkin_date | 每日签到记录；三字段唯一。 |
| `members` | group_id, platform_user_id, display_name, updated_at | 用户资料缓存。 |
| `group_checkin_settings` | group_id, enabled, success_template, duplicate_template | 每群签到开关与模板。 |
| `logs` | timestamp, level, scope, message | 可筛选、可导出的本机运行日志。 |

数据库不保存 Cookie、access token、账户密码或其他 DZMM 凭据。

## 签到

对每条已接受入站消息：

1. 仅当消息文本精确等于 `签到` 且所在群开启签到时继续；
2. 将群 ID、发送者平台 ID 与本地时区当天日期插入 `checkins`；
3. 插入成功时发送成功模板；唯一约束冲突时发送重复模板；
4. 模板中的 `{name}` 由资料适配器给出的昵称替换，缺失或查询失败则替换为“这位成员”；
5. 使用 `message:send` 发送回复并等待成功 ACK，结果写入消息和日志。

SQLite 的唯一约束是签到幂等的最终边界；Socket 重投或历史补偿不得造成重复成功签到。

## 界面

视觉采用 Linear 的低噪声高密度导航和 Sentry 的运行状态/事件信息层级，但不复制其品牌、图标或资产。默认深色主题，窄侧栏，页面顶部恒定展示登录和 Worker 状态。

### 总览

显示 DZMM 登录状态、Socket/Worker 状态、启用群数量、今日签到总数和最近错误。提供启动、停止和打开登录页操作。

### 消息

显示所有启用群的实时消息，提供群筛选和时间排序。手动发送时先选择一个已启用群；发送结果须明确显示成功或失败。消息页不显示 token 或 Cookie。

### 群聊

支持添加绝对 DZMM 聊天 URL、自动提取并校验 `c` 参数、命名、启用/停用和移除。新增、启停和移除在 Worker 运行中即时更新订阅；移除不删除历史消息和签到记录。

### 签到

按群配置启用开关、成功模板和重复模板，提供 `{name}` 模板说明。默认文本分别为 `{name} 签到成功` 与 `{name} 今天已经签到过了`。

### 日志

按信息、警告、错误筛选，实时显示 Worker、认证、Socket、补偿、发送和签到事件；支持导出当前筛选结果。日志不得含敏感凭据或完整 Cookie 值。

### 设置与登录

打开内嵌 DZMM 登录视图、展示当前账号的非敏感公开资料及登录状态、支持清除专用 session（操作前二次确认）。提供历史补偿间隔设置，允许值为 5 到 60 秒，默认 5 秒。

## 异常处理

- 登录页、token 请求或 `user.getMe` 失败：标记 `auth_required`，停止 Socket，保留本地数据，提示重新登录。
- Socket 断线：标记 `reconnecting`，使用退避重试；重连后再历史补偿。
- 历史补偿失败：保留 Socket 实时通道，记录 warning，并在下个周期重试。
- 入站、数据库或资料查询失败：记录不含敏感值的错误；单条消息的失败不能停止整个 Worker。
- Socket 发送无成功 ACK：显示失败，记录错误；不自动走 HTTP/浏览器 DOM/Bot API 发送。
- 群链接无效、不是绝对 URL、缺少 `c` 或与已有群重复：拒绝保存并在表单显示原因。

## 验收标准

1. macOS 和 Windows 都可安装并启动，重启后保留本机群配置、SQLite 数据和专用 DZMM 登录态。
2. 用户可在内嵌登录页完成 DZMM 登录；登录失效后总览明确显示需要登录，重新登录后 Worker 可恢复。
3. 添加并启用两条不同群链接后，两个群的 `message:new` 都实时进入消息页，且机器人自身消息不触发处理。
4. 断线期间的消息在重连补偿后出现一次；实时事件与历史补偿重复时只记录/处理一次。
5. 手动发送的 `message:send` 成功 ACK 后显示成功；失败时显示失败且不产生自动替代发送。
6. 开启签到的群中，同一用户当天第一次精确发送 `签到` 得到成功模板，第二次得到重复模板；次日可再次成功。
7. 签到回复优先显示资料接口取得的昵称；资料查询失败时仍正确签到并使用“这位成员”。
8. 页面、数据库和日志均不显示 DZMM Cookie、access token 或密码。

## 测试策略

- 单元测试覆盖聊天 URL 解析、Socket 入站过滤、去重、重连订阅、补偿时机、ACK 发送、签到唯一约束、模板渲染和资料查询降级。
- 主进程集成测试以伪 session、伪 Socket 与临时 SQLite 数据库验证多群、实时/补偿协作和 IPC 控制。
- 渲染进程组件测试覆盖状态展示、群表单校验、签到设置和消息/日志筛选。
- 在 macOS 与 Windows 打包前以测试群执行：登录、两群实时收消息、断网重连补偿、手动发送、首/重复签到、资料查询失败降级和日志导出。
