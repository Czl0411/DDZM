# 斗地主发布检查单

目前是本地实现，不代表已创建平台游戏卡或上线。首版无摸鱼币、无付费 AI，独立于象棋。

## 配置与入口

取得用户上线授权后创建独立 Gamefy 草稿，记录真实 ID；不能使用象棋 3761638。按现有 Gamefy CLI 文档生成 `gamefy/doudizhu/dzmm.json`，发布目录为 `publish`，入口 `index.html`。开发密钥仅由本地环境提供，不写入文件或命令日志。

服务器环境需要四项配置，缺省不开放：

- `DZMM_DOUDIZHU_GAME_ID`：独立游戏卡 ID。
- `DZMM_DOUDIZHU_GAME_URL`：对应站点的 HTTPS 游戏入口。
- `DZMM_DOUDIZHU_PUBLIC_API_URL`：公开 HTTPS 后端地址。
- `DZMM_DOUDIZHU_CHATROOM_ID`：先指定测试群；验收后经批准再改小游戏群 `4fc4a2fd-465a-4436-9884-dbb5e60c6af2`。

`publish/config.js` 的 `apiBase` 填相同的公开 HTTPS 后端地址（不包含 `/api/doudizhu`）。它不是秘密。客户端从平台 SDK 读取 UID，以 `Authorization: DoudizhuUid <uid>` 请求；无 JWT。**这不防冒充 UID**，不得据此接入资产结算。

群内 `/斗地主` 分别发送 character 分享卡和入座码文字。另两名已入职用户输入四位码入座，三人准备开始。文字未送达不能加入。等待十分钟到期关闭。已入职身份是全局员工登记，不限定原群成员。

## 安全部署顺序

1. 记录当前服务版本和数据库迁移版本。备份数据库、环境配置、当前发布目录及 Caddy 配置，并验证备份可读取；不将备份提交 Git。
2. 在生产数据库的隔离副本验证升级。新增迁移 `20261013_109` 接 `20261013_108`，只创建四张斗地主表。不要通过 `stamp` 跳过实际缺失的既有迁移。
3. 安装新代码，执行已核验的迁移，填上面的四项配置。沿用既有 `/internal/daily-jobs/run` 维护入口推进倒计时；确认 worker 正常调用，否则超时不能推进。
4. 合并 `deploy/caddy/dzmm-chess-ip.Caddyfile` 新增的 `/api/doudizhu/*` 流式代理，保留象棋代理和默认 404。先在服务器执行 `caddy validate --config <实际配置路径> --adapter caddyfile`，成功后再重载。此处本地测试仅检查模板，未代替真实 Caddy 校验。
5. 仅重启受影响的后端/worker。确认内部健康检查、HTTPS 证书、跨域预检和未授权请求行为；不要扩大内部管理 API 的公网代理范围。
6. 配置并通过 Gamefy CLI 校验新卡，再上传独立草稿。需公开审核时单独提交；预览可用不等于普通玩家可用。不能覆盖象棋卡。

## 验收

三名真实账号从测试群开局，第四账号观战。覆盖入座竞争、准备、叫分、提示/滑选/出牌/不出、聊天、关闭重开、超时托管、取消托管、中文群结算和再来一局。核对观众无手牌、没有币流水、结算只发一次，象棋及群消息时延不受影响。

自动测试：

```sh
.venv/bin/python -m pytest tests/core/test_doudizhu*.py tests/core/test_chess*.py tests/deploy/test_doudizhu*.py tests/deploy/test_chess_migration.py tests/runtime/test_settings.py -q
node --test gamefy/doudizhu/tests/*.test.mjs
.venv/bin/python -m pytest gamefy/doudizhu/tests/test_doudizhu_sandbox.py -q
```

真实 PostgreSQL 并发测试使用独立测试库，通过 `DOUDIZHU_TEST_DATABASE_URL` 指定，禁止填生产库。测试创建并删除自己的随机 schema。未设置时该测试跳过，不能声称已验证数据库锁。

本次全项目回归（排除需额外数据库配置的 `scripts/test_estrus_rank.py`）有 57 项既有迁移测试失败；在改动前 `b067c82` 的独立代码副本重跑 `tests/deploy`，同样 57 项失败且清单一致。不能将全项目报告成全绿，也不顺带修改旧迁移。

最后一次完整回归结果为 **2330 通过、59 失败、18 跳过**。除上述 57 项外，指令清单测试遗漏新增 `/斗地主`，现已更新预期并复测通过；另一个 Socket 并发测试要求耗时低于 180ms，本次为 186ms，未修改生产逻辑，单独复测通过。这两项复测为 2/2 通过，之后没有再次运行完整 2407 项，不能将分项结果拼成一次全量通过。

本地审查后验证：144 项 Python 测试通过（含象棋回归、真实 PostgreSQL 抢座/准备/手动操作与超时竞态、320/390/1280px 沙箱及跨房间导航），另 6 项 Node 测试通过。审查发现的旧账号残留、象棋帮助异常、旧导航覆盖新房间、续局空位无法补人均补了失败回归并修复。

续局仅限原三人；准备阶段任何人退出都会结束房间，按钮明确显示“退出并结束房间”。换人请重新 `/斗地主`。

暂缓的轻微问题：上一轮准备阶段聊天可能在续局准备页重新出现；滑选只验证了单指，多指重叠触碰可能重复切换选牌。出牌仍需要显式点击按钮，服务端仍校验牌型与归属。

## 回滚

先关闭新开局入口并通知测试人员，保存斗地主数据备份，再恢复前一代码、配置和 Caddy 配置；增量表可保留，避免丢失记录。只有确认不再需要任何斗地主数据且备份可恢复时才考虑降级到 108，降级会删除这四张表。不要在线上执行未经验证的整库恢复或清理。
