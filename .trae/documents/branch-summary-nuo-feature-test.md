# nuo/feature-test 分支工作总结

> 更新时间：2026-10-04
> 分支：`nuo/feature-test`（基于 `main`，领先 33 个提交；最终目标：稳定后合回 main 一并 PR 给原仓库）
> 生产环境：43.153.194.94（5 服务 active，alembic 已升级至 `20261003_89`）
> 测试规模：全仓 1768 个测试用例

本分支围绕「摸鱼公司」群聊玩法做了一整轮功能扩张：从生日祝福起步，陆续加入大话骰子、部门津贴体系、拉新归因、商店分类限购、真心换真心、风纪罚款、/凿 与发情值八大模块，并把所有可调参数暴露到后台管理界面。以下按模块总结。

---

## 一、生日祝福（迁移 76 + 89）

### 功能
- **设置与查询**：`/设置生日 月 日`、`/我的生日`、`/本月生日`；生日信息带可见性（public / private，private 不播报但特权照发）；每人每年可改次数有限（默认 1 次）。
- **前一天预告**：`preview_time`（默认 20:00）播报【生日预告】，每人每年只播一次。
- **当天祝福**：默认在 **09:00 / 12:00 / 17:00 三次公告**（迁移 89，原为单时刻）；【生日祝福】列出当天全部寿星、入职工龄、礼金到账与特权说明。
- **礼金与特权**：礼金默认 20 币（0-999 可调）；当天打卡倍率（默认 ×2）、商店折扣（默认 8 折）、购彩前 N 注免单、随机事件奖励加成（默认 +50%）、入职周年祝福。
- **随礼**：祝福公告发出后开放 `/随礼 金额`（回复寿星消息或 @），窗口分钟数可调（0 = 到当天 24:00），单次上限可调；窗口关闭后播报随礼汇总。
- **幂等与补发**：礼金每人每年一次（`birthday_greetings` 唯一约束）；`same_day_backfill` 控制错过后是否当天补发；后台名单有「试跑」（只渲染文案）和「补发」（真发钱+公告）按钮。

### 三次公告改造（迁移 89，@63df3b8）
- `birthday_settings.greet_time`（单值）→ `greet_times`（JSON 列表，最多 10 个、去重、按分钟排序）；默认 `["09:00", "12:00", "17:00"]`。
- 新表 `birthday_greet_announcements`（announce_date + slot 唯一）：每个公告时刻每天只广播一次，机器人每秒轮询也不会重发。
- **礼金仍一年只发一次**：在第一个到达的时刻发放；后续时刻对已祝福寿星重复公告。
- 后台「祝福时刻」输入框改为逗号分隔多值。

### 后台
- 「游戏运营 / 生日祝福」面板：总开关（默认关）、预告开关、当天补发开关、随礼开关、入职周年开关、全部参数与文案模板（支持 `{寿星}` 占位）、群开关列表、生日名单（试跑/补发）。

---

## 二、大话骰子（迁移 77 + 87）

- 从 dzmm_nuo 移植的群聊骰子游戏：`/大话骰子` 开局 → `/加入` → `/开始` → 私聊收骰 → 群内轮流报「N 个 X」→ `/开骰` 全场明牌判负 → `/继续` 开下一轮（从开局者下一位开始）。
- 万能点机制、报名超时、中途退出处理。
- **生涯总战绩**（@0fb7a73）：`/大话骰子数据` 分「本局」与「总战绩」——开牌、败露、拆穿、受罚四个榜单按群跨局累计；自动结束（人数不足）的局也计入。
- 后台参数面板（迁移 87）：`liar_dice_settings` 按群存储回合超时秒数（30-600，默认 120），替换原硬编码常量。
- 共享指令 `/开始 /加入 /退出 /结束游戏 /继续` 走 active_gameplay_summary 路由。

---

## 三、部门津贴体系（迁移 78 + 85 + 86）

### 津贴规则（7 类，绑定部门后生效）
| kind | 动作词 | 触发 |
|---|---|---|
| checkin | 打卡奖励 | 打卡成功 |
| event | 演出奖励 | 随机事件 completed / 公演 |
| game（host/play） | 开局奖励 / 参与奖励 | 真正开局（begin_*）给发起人；每满计局步长给全员 |
| submission | 投稿奖励 | 随机事件投稿过审（走私聊，因无群上下文） |
| chat | 水群掉落 | 摸鱼吃瓜部成员聊天按概率掉落（默认 10%），同人冷却默认 0（0-86400 可调） |
| referral | 拉新奖励 | 通过邀请链接进群，发给邀请人 |
| discipline | （无津贴，仅执法权标记） | 见风纪罚款 |

- **每人每日 5 币封顶**（daily_cap 可调）：实发后恰好满 → 通知追加「（今日津贴已满 N 币）」；已满后静默。
- `/部门` 列表动态显示各部门津贴说明（含 referral 文案修复 @df7f024）。
- **到账通知**（@d1ddb7e）：`_grant_department_allowance` 统一出口，消息驱动用消息所在群、游戏结算用对局群、无群场景走私聊兜底；批量场景逐人头发送。

### 参数全可配（迁移 85）
- `department_allowance_settings` 单行：6 类面额、计局步长 game_play_step（默认 5）、水群概率 chat_drop_percent（默认 10）、referral 面额、daily_cap（默认 5）。
- 后台侧边栏新分组「部门津贴」：津贴设置 + 风纪罚款两个面板。
- `/罚款` 抽成同样走设置（执法者抽成计入 dept_fine kind，共享封顶）。

### /我的津贴（@ce08390）
- 群内指令：当日津贴按 kind 分组明细（复用标签字典 + dept_fine→罚款抽成）+ 合计（标注已封顶）；未入职/无入账各有文案。

---

## 四、拉新自动归因（迁移 79）

- **归因来源**：平台向群消息流注入 type=system 入群消息——「X 通过 Y 的链接加入了群聊」（可归因）/「X 加入了群聊」（无邀请人）。
- **链路**：aikda_socket 放行 system 消息并解析名字 → worker 主循环（Playwright 线程）经 member_directory（getMembers，60s TTL）把名字换 uid 塞进 metadata → core `record_referral_from_system` 归因发奖。
- **两个关键修复**：
  - @17e3a1b：消息 handler 跑在 socket.io 回调线程，直接查 Playwright 会 greenlet 崩溃——改为挂 `_pending_referrals` 队列由主循环解析，`referral_resolved` 标记防重；名字未命中强制刷新缓存。
  - @9a46cbd：传输层 payload 丢失 content_type/metadata 导致归因静默失败——补齐透传。
- **防刷**：`referral_records.platform_message_id` 唯一（防重放）+ `newcomer_platform_id` 唯一（防退群重进刷）；封顶/未绑定/解析失败以 amount=0 留痕。
- 规则：只发邀请人、占每日 5 币封顶、仅 allowance_kind=referral 绑定部门（次元外联部）。

---

## 五、商店分类与每日限购（迁移 80）

- `items` 新增 `category`（String32）与 `daily_purchase_limit`；限购桶按「分类」共享（同分类商品共用当日额度），无分类按单商品计。
- `/商店` 按分类分区展示（礼物 → 刮刮乐 → 功能 → 成人 → 自定义 → 其他）。
- 迁移回填 22 个系统商品分类，并重命名旧限购桶（gift→礼物赠送、scratch→刮刮乐）保留当日已购连续性。
- 后台商品列表卡片式 + 分类筛选。

---

## 六、真心换真心（迁移 81 + 87）

- 群聊问答游戏：`/真心换真心` 开局 → `/问题 内容`（@谁谁答，主指令 `/问`，别名 `/问吧` `/问题`）→ 被点名者 `/真心 内容` 回答（别名 `/答` `/真心` `/huida` `/da`；跳过=弃提问轮，拒答=不答）→ `/继续` 开下一轮 → `/当前游戏` 查名单与总人数 → `/真心换真心数据` 查总战绩。
- 5 张表：settings（按群）、games（settled_rounds 防重计局）、players（position 序号）、questions（required_player_count 快照）、answers（四态）。
- 中途加入：position=max+1、免答当前正在收集的问题；剩余不足 2 人自动结束；提问 300s / 回答 600s 懒超时公告。
- 津贴挂钩：开局奖（发起人）+ 每轮结算参与者计局。
- 后台参数面板（迁移 87）：提问超时（30-3600）、回答超时（30-3600）、最少开局人数（2-10）。
- 设计决策（用户拍板）：无轮末/终局排行（顺序发言无意义，@1c3817f）。

---

## 七、风纪罚款（迁移 82 + 83 + 84）

- **指令**：`/罚款`（别名 `/罚`）——引用回复形态引用优先且 payload 全作理由；名字形态首 token 为名、其余为附言。`/我的罚款` 私聊查询（_DIRECT_COMMANDS 白名单）。
- **流程**：罚款即销毁（余额不足扣到 0）→ 执法者抽成 = 实扣 × kickback_percent（默认 20%，向下取整）计 `dept_fine` 津贴（迁移 82 更新了 CHECK 约束放行）→ 与每日 5 币封顶共享 → 不发标准津贴通知（私聊回执含封顶提示）。
- **约束**：禁罚自己 / 执法部门（allowance_kind=discipline）内成员 / 未入职者；冷却按 DB max(created_at)；撤销退款但不追回抽成。
- **执法权绑定**（迁移 83→84 演进，用户拍板不设独立勾选框）：部门津贴下拉选 `discipline` 即获得执法权，可多部门绑定。
- **职级配额**：rank_quotas 显式配置优先（按 rank_id UUID 为键）；否则按 sort_order 默认表（1:0, 2:1, 3:2, 4-5:3, 6-7:5, 8-9:8, 10:10, 11:20）。
- 三个新 balance source：discipline_fine / discipline_fine_refund / fine_kickback；异议提示 `_FINE_FEEDBACK_HINT`。
- 后台「风纪罚款」卡片（设置 + 记录列表 + 撤销按钮）。

---

## 八、/凿 与发情值系统（迁移 88 + 本轮 v2 增强）

### 玩法
- `/凿 目标 [附言]` 或引用消息 `/凿 [附言]`：被凿者发情值随机 +0/+1/+2、获得摸鱼币 0/1/2——两套三档概率分布（默认 50/30/20）后台可调。
- 发情值攒满阈值（默认 100，10-1000 可调）触发**高潮长文**；触发后清零、计「今日第 N 次 / 总第 M 次」。
- 发币走 `estrus_gain` source，**不占每日 5 币封顶**（用户拍板）。
- 凿者冷却可调（默认 0 = 无限制）；`/允许被凿` `/拒绝被凿` 开关——拒绝后他人再凿，公开提示「XX 拒绝了 YY 的凿，并且给了 YY 一杵子。」。
- `/我的发情值`：当前发情值 X/100、被凿次数、高潮 今 N 次/总 M 次、状态。
- `/发情值排名`：前 5 名，排序 = 今日高潮 > 总高潮 > 发情值 > 被凿次数；**定时推送跟随收益榜时刻**（12:00 / 16:00 / 20:00 / 23:59），幂等同链路。
- 数据：`estrus_states`（按群×用户，跨天懒重置今日次数）+ `estrus_chops` 日志 + `estrus_settings` 单行；users.gender 列（male/female/unknown）。
- 目标解析 display_name → platform_nickname（重名返回工号列表让凿者消歧）。

### 高潮文字 v2（@9cf43fb + @d60960b）
- **三条口径**（用户拍板）：主角永远是被凿者；最后一凿的人可以出场互动（按住、掐下巴、命令、调教）但镜头不转移；prompt 不带群聊上下文。
- **性别分路**：男/女/未知三套 prompt 与身体词汇（男：性器/后穴/前液…；女：穴口/花心/乳尖…；未知：中性词汇，不写器官）。
- **调教库 + 词库**：`DIAOJIAO_LIBRARY`（动作 12 条 / 道具 10 种 / 命令 9 条）+ `LEXICON`（声音/身体反应/神态/体液/顶点），同时喂给 AI prompt（当素材）和兜底组装（当槽位文案），改词只改 estrus.py。
- **篇幅与形态**：250-400 字、**整段单条发送**（prompt 禁止换行 + runtime `re.sub` 兜底合并）；`CLIMAX_MAX_CHARS` 600→1000（600 曾在 300+ 字处硬截断，实测教训）。
- **AI 链路**：core 直调 DeepSeekChatClient（DP_API_KEY 同源），20s 超时；失败/超时/空结果 → 兜底文案按槽位随机组装（开场→动作→互动→现场细节→反应→余韵→顶点→收尾），互动槽位只在有凿者名时插入，`_SafeDict` 防占位符炸段——保证任何情况下都有输出且与 AI 版同一量级。
- **实测效果**（生产 21:57）：female 词库、凿者互动（按后颈/反扣手腕/命令「自己动」/数到十）、单段 400 字、回执 100/100 全部生效。

### 性别来源（@d60960b，参考 dzmm_nuo `_gender_of` 档案回写模式）
1. 用户 `/设置性别 男|女`（`/修改性别` 别名归一；私聊可用）——**显式档案永远优先**。
2. 平台推断：worker 每 6 小时拉 getMembers（`member_genders`，10 分钟 TTL），把非空 gender 推给 core `/internal/users/platform-gender-sync`；core **只回填 unknown 用户**。探针已确认平台返回体有 gender 字段（当前群友全为 null，平台侧设置后自动流入）。
3. 兜底 unknown 中性文案。

---

## 九、后台管理改进汇总

| 面板 | 位置 | 内容 |
|---|---|---|
| 生日祝福 | 游戏运营 | 全参数 + 名单试跑/补发 + 群开关 |
| 大话骰子 | 游戏运营 | 回合超时秒数（按群） |
| 真心换真心 | 游戏运营 | 提问/回答超时、最少人数（按群） |
| 凿与发情值 | 游戏运营 | 开关/阈值/两套概率分布/冷却 |
| 津贴设置 | 部门津贴 | 6 类面额 + 步长 + 水群概率/冷却 + referral + 封顶 |
| 风纪罚款 | 部门津贴 | 金额/抽成/配额/冷却/上限 + 记录撤销 |

- **群编辑弹窗修复**（@8b0ba6a、@1a7fa44）：admin.js `groupGameOptions` 硬编码列表漏游戏导致保存刷掉 enabled_game_types；仅补 JS 列表不补复选框元素导致弹窗 JS 抛异常——两个坑都已修，新增群游戏必须同步补这两处。
- **生日面板修复**（@91d0dcb、@da42142）：`/api/group-chats` 返回 `{items, version}` 包装需解包 + 把 version 写入全局 configurationVersion 供 If-Match 用。
- 群设置保存 / 静态 JS 热修 / If-Match 并发控制等机制均已验证。

---

## 十、迁移清单（本分支 76 → 89）

| # | 名称 | 内容 |
|---|---|---|
| 76 | birthday_blessing | 生日祝福全套表 |
| 77 | liar_dice | 大话骰子表 |
| 78 | department_allowance | 部门津贴台账 + 绑定 |
| 79 | referral | 拉新归因记录（防重约束） |
| 80 | shop_category_limit | 商品分类 + 每日限购（batch_alter_table 改列宽） |
| 81 | truth_trade | 真心换真心 5 表 |
| 82 | discipline_fine | 罚款设置/记录（CHECK 放行 dept_fine） |
| 83 | department_fine_binding | 执法权绑定演进 |
| 84 | drop_fine_enabled | 删独立勾选框列（batch drop） |
| 85 | allowance_settings | department_allowance_settings 单行 |
| 86 | chat_drop_cooldown | 水群冷却参数化（默认 0） |
| 87 | liar_dice_settings | 大话骰子按群设置 |
| 88 | estrus_chop | 凿三表 + users.gender（曾漏 created_at/updated_at，已修 @5ad3b53） |
| 89 | birthday_greet_times | greet_times 列 + 公告幂等表 |

---

## 十一、新增指令清单

- **生日**：`/设置生日` `/我的生日` `/本月生日` `/随礼`
- **大话骰子**：`/大话骰子` `/开骰` `/大话骰子数据`（+ 共享 `/加入 /开始 /退出 /结束游戏 /继续`）
- **真心换真心**：`/真心换真心` `/问题`（别名 /问 /问吧）`/真心`（别名 /答 /huida /da）`/当前游戏` `/真心换真心数据`
- **津贴**：`/我的津贴`
- **罚款**：`/罚款`（别名 `/罚`）`/我的罚款`
- **凿**：`/凿` `/允许被凿` `/拒绝被凿` `/我的发情值` `/发情值排名` `/设置性别`（别名 `/修改性别`）

---

## 十二、测试与运维

### 测试
- 全仓 1768 个用例；每个功能模块配套测试文件（如 `test_estrus_chop.py` 13 个、`test_birthday_jobs.py` 含三时刻公告幂等用例、`test_discipline_fine.py`、`test_truth_trade.py` 等）。
- 测试固定随机源（`_SeqRandom`）验证概率分布、幂等、跨天重置、私聊白名单、422 校验等。
- **本地既有失败**（与分支改动无关，勿再排查）：admin auth_desktop 17 个（os.getpgid Windows 无）、tests/runtime（DZMM_BROWSER_PROFILE）、test_service（WinError32 文件锁）、tests/deploy 43 个（enabled_game_types 等表缺失）、test_group_commands 打卡经济 1 个、test_repository tip 2 个、tests/admin 需装 websockets。
- **重要教训**：本地 SQLite 用 `Base.metadata.create_all()` 建表、生产 PG 走 alembic——迁移文件漏列时测试全过但生产 500（迁移 88 created_at 事故），改表结构必须同时核对 ORM 与迁移。

### 运维脚本（scripts/）
- **部署**：`deploy_estrus_chop.sh`、`deploy_estrus_v2.sh`、`deploy_gender_sync.sh`、`deploy_birthday_greet_times.sh`、`deploy_game_settings_panels.sh`、`deploy_allowance*.sh`、`deploy_my_allowance.sh`——scp 清单与 cp 一一对应，含重启清单（core → admin-web → 三 worker reset-failed+start）与 healthz 验证。
- **排查**：`debug_estrus.sh`、`debug_estrus_gender.sh`、`debug_chat_drop.sh`、`debug_my_allowance.sh`、`debug_submission_allowance.sh`、`debug_worker_state.sh`。
- **验证**：`verify_estrus.sh`、`verify_game_settings.sh`、`verify_birthday_greet_times.sh`；干跑测试 `test_estrus_rank.py`（发情值排名不发包验证）、`check_latest_climax.sh`。
- **运维动作**：`set_nuonuo_heat.sh`、`set_persona_gender.sh`、`clear_xiaoxiaonuo_allowance.sh`。
- **平台探针**：`probe_member_directory.py`、`probe_member_gender.py`（worker Chromium CDP 127.0.0.1:19222 + context.request 共享 cookie 直调 tRPC；勿新开页面防 WAF，请求过多 418 限流）。

### 部署铁律（血泪教训）
1. core/app.py 与 admin/app.py 同名，scp 到 /tmp 会相互覆盖——**必须改名**（core_app.py / admin_app.py）再传。
2. scp 清单漏传的文件，/tmp 里的同名旧文件会被脚本照常 cp 上去——每条 cp 都要核对本次清单；上传后 **md5 校验**。
3. 部署脚本整体 `sudo bash` 执行（/etc/dzmm/dzmm.env 仅 root 可读；source 需 `set -a` 导出）。
4. 单独重启 dzmm-core 会连崩 browser-worker / ai-worker / ai-memory-worker（Connection refused + systemd 放弃重启）——重启 core 后必须 `reset-failed + start` 三 worker（完整 deploy.sh healthz 后会自动做）。
5. 静态 JS 热修要补到运行时目录 `/opt/dzmm/venv/.../admin/static/`（FileResponse 读包副本，每请求读盘 + no-store，刷新即生效）。
6. SQLAlchemy Row 陷阱：`session.execute(select(A, B))` 返回 Row 元组，属性访问会炸——必须解包或 `.scalars()`。
7. SQLite 跑 `op.alter_column`/`drop_column` 报语法错误——迁移一律用 `batch_alter_table`（PG 无碍但保证本地迁移测试可跑）。

---

## 十三、当前状态与后续路线

- **已全部上线生产**：迁移 76-89 全部执行完毕，5 服务 active，核心功能均经群内实测（含高潮文字 v2 的真实 AI 输出验证）。
- **本地领先 fork/nuo/feature-test 19 个提交**，未 push。
- **待办**：
  1. push 到 fork；
  2. 稳定后合回 main，一并 PR 给原仓库；
  3. 后台员工编辑弹窗补性别设置（方案文档承诺过，未实现；现阶段用 `/设置性别` 或 SQL）；
  4. 平台 gender 字段当前全员为空，等平台侧有人设置后回填链路自动生效。
- **分支文档索引**：本目录下 `estrus-chop.md`（/凿）、`birthday` 相关 plan、`department-allowance.md`、`discipline-fine.md`、`liar-dice-port.md`、`shop-optimization.md`、`truth-trade-game.md` 各功能详细方案。
