# DeepSeek 模型供应商替换设计

## 目标

将 AI 总监事和玩家记忆提炼使用的模型供应商从 MiniMax 完整替换为 DeepSeek，同时保持现有业务触发、额度、队列、超时、失败回退、回复长度和出站发送流程不变。

## 范围

- 将运行代码中的 MiniMax 客户端、错误类型和配置名称改为 DeepSeek 语义。
- 从 `DP_API_KEY` 读取 DeepSeek API 密钥。
- 默认使用 `deepseek-v4-flash` 和 `https://api.deepseek.com`。
- 更新 AI Worker 启动入口、部署环境示例和相关自动化测试。
- 保留已经应用的迁移文件和历史设计/实施文档中的 MiniMax 名称，避免改写项目历史。
- 不引入通用多供应商抽象，不改变数据库结构、管理端配置或核心业务 API。

## DeepSeek 请求

客户端继续使用现有 `httpx`，向 `{base_url}/chat/completions` 发送 OpenAI 兼容请求。请求包含：

- `model`: 默认 `deepseek-v4-flash`；
- `messages`: 现有 system 和 user 两条消息；
- `thinking`: `{ "type": "disabled" }`，降低群聊回复和记忆提炼的延迟；
- `max_tokens`: 使用现有调用方传入的回复上限值。

响应只读取 `choices[0].message.content`。即使供应商响应包含 `reasoning_content`，也不会保存或发送给玩家。模型文本去除首尾空白后，继续按现有 `max_chars` 做字符截断，保持平台回复长度行为不变。

## 上下文缓存

DeepSeek 的上下文硬盘缓存由服务端默认启用，不需要客户端传递缓存开关。当前请求中稳定、重复的系统提示词前缀可以自动产生部分缓存命中；玩家资料、记忆和本轮消息等动态内容通常不会命中。缓存属于尽力而为，不保证每次请求命中。

响应 `usage` 中的 `prompt_cache_hit_tokens` 和 `prompt_cache_miss_tokens` 可用于后续观测。本次替换不新增日志或费用统计，也不改变响应解析路径，避免扩大范围或记录额外的请求元数据。

## 配置与命名

运行设置改为：

- `deepseek_api_key`：从 `DP_API_KEY` 读取，空字符串视为未配置；
- `deepseek_model`：从 `DZMM_DEEPSEEK_MODEL` 读取，默认 `deepseek-v4-flash`；
- `deepseek_base_url`：从 `DZMM_DEEPSEEK_BASE_URL` 读取，默认 `https://api.deepseek.com`。

AI Worker 缺少密钥时明确报告 `DP_API_KEY must be set and nonempty`。不再读取 `DZMM_MINIMAX_API_KEY`、`DZMM_MINIMAX_MODEL`、`DZMM_MINIMAX_BASE_URL` 或通用 `API_KEY`，防止继续误用旧供应商密钥。

活动代码中的类型改为 `DeepSeekChatClient` 和 `DeepSeekCallError`。AI Worker 捕获新的错误类型，但提交给核心服务的错误分类继续使用现有稳定值：`timeout`、`http_error`、`network` 和 `invalid_response`。

## 文件边界

- `src/dzmm_bot/ai/client.py`：DeepSeek HTTP 客户端与错误分类。
- `src/dzmm_bot/ai/main.py`：读取 DeepSeek 设置并构造客户端。
- `src/dzmm_bot/ai/worker.py`：捕获 DeepSeek 客户端错误。
- `src/dzmm_bot/ai/__init__.py`：更新包说明。
- `src/dzmm_bot/runtime/settings.py`：DeepSeek 环境配置。
- `deploy/env/dzmm.example.env`：DeepSeek 部署示例。
- `tests/ai/test_client.py`、`tests/ai/test_worker.py`、`tests/runtime/test_settings.py`：验证新客户端、错误映射和配置读取。

`runtime/settings.py`、`tests/runtime/test_settings.py` 和部署环境示例已有其他未提交修改。实现必须保留这些修改，只局部替换 MiniMax 相关行。

## 错误与安全

- HTTP 超时映射为 `timeout`。
- 非成功 HTTP 状态映射为 `http_error`。
- 其他 HTTP 传输异常映射为 `network`。
- 缺少、类型错误或空白的最终内容映射为 `invalid_response`。
- 不记录或返回 API 密钥、Authorization 请求头、完整提示词或供应商原始响应。
- `.env` 保持未跟踪状态，不加入提交。

## 验证标准

1. 客户端向 `https://api.deepseek.com/chat/completions` 发送 Bearer 认证请求。
2. 请求模型为 `deepseek-v4-flash`，包含禁用思考模式的官方字段，并使用 `max_tokens`。
3. 最终回复只来自 `message.content`，去除首尾空白并遵守字符上限。
4. 空响应与 DeepSeek 调用错误继续触发现有失败回退路径。
5. `Settings.from_environment()` 从 `DP_API_KEY` 读取密钥，并提供正确的模型和地址默认值。
6. 活动代码和部署示例不再依赖 MiniMax 配置或类型。
7. AI、运行设置以及完整测试套件通过，且当前工作区的既有未提交改动保持不丢失。
