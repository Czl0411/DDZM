# 雾境经典版（120 卡）开发验收

日期：2026-10-15。实现基线 `22d4ee6`，独立工作区 `codex/mistrealm`。以下是本次经典版记录；文末保留旧版验收历史。

## 本次实现与验证

- 120 张可构筑卡（102 单位、10 领袖、8 特殊牌）、2 张变身形态；5 阵营、10 套可编辑预组。卡面共 122 张，13 张保留经检查的原创画面、109 张新生成；逐张检查并保留原 PNG、提示词、映射记录。
- 三排战场、起手 10 张、至多换 2 张、跨局保留手牌、无常规回合/局间补牌、两颗生命；间谍、医师连锁、召集、同袍、天气、号角、灼烧、诱饵与仪式效果已实现。下列原作边界规则仍是发布门槛。
- 独立牌组保存、冻结排队/开局牌组、按规则版本分池配对；锁定前隐藏对方阵营/领袖，开局后仍隐藏手牌和牌库顺序。头像/昵称使用 SDK，UID 信任方式沿用用户确认边界。
- 最终相关 Python 回归：**247 passed、3 skipped**（可选 PostgreSQL 环境项）；Node 客户端 **12 passed**。100 组预组交叉对局检查结束条件、JSON 持久化、隐私投影、卡牌守恒、再战重置。
- PostgreSQL 单独使用本机一次性库验证：110→112→113、113→112→113；四人同时排队形成两个房间、四个唯一席位，通过。未连接生产数据库做迁移测试。
- 资源门槛 **2 passed**：122 张独立 WebP 的 PNG/WebP 解码、尺寸与哈希完整，16 个原创 SVG 图标通过；前端发布目录 **19.36 MiB**，单卡低于 800 KiB。
- 本地 Chromium：双人建房/加入、隐藏阵营、同时锁定、换牌、六条战列；编辑牌组查看详情并返回后草稿保留、保存/刷新；1366、844 横屏、390 竖屏，无页面横向溢出。
- 大场面：50 单位横向战列、医师选择时刷新、连锁结算、战力来源查看、长昵称/头像失败、离线恢复；场面没有人为 9 单位限制。
- 慢网：500 kbps / 250 ms，设备 Date.now=0，匹配计时、刷新、取消、重排和真实本地配对。

## 最终独立审查处理

一次独立审查发现 3 个实质问题，均以回归验证后修复，不追加第二轮审查：

1. 第三局开场医师选择结束后未重置先手计时，会导致先手被自动停手。新增 8 个先手/手动/超时/嵌套组合，先失败后通过；整条开场链完成才开始正常 60 秒回合，不切换指定先手。
2. 旧入口恢复新版房间会按旧卡数据渲染并报错。两个入口现在按活动房间/队列版本跳转，保留 UID 查询参数、房间与排队票据。
3. 取消匹配请求失败会停掉心跳。失败后恢复同票据轮询，能收敛到等待、已匹配或空闲；恢复时保留等待时长，消除每次心跳短暂显示 0 秒。

审查测试限制：审查者首次旧入口复现遗漏覆盖旧 HTTPS 配置，启动超时后停止；不能确认那次资料读取请求完全留在本地，未执行匹配或部署。之后复现及最终浏览器回归均显式拦截非本地请求并覆盖测试配置。

## 仍未作为已完成发布宣称的内容

- 原作数字版边界证据：兽群保留英雄资格、第三局复活目标及触发、变身离场重置、天气减半取整、平局后先手、诱饵留场占位；当前开发规则及冲突来源见设计规格核验表。尚不能宣称逐项完全复刻原作。
- 本地交付时尚未执行平台与生产步骤；随后用户授权部署，已完成真实Gamefy上传、生产迁移与单账号验收（见下方补记）。两名真实平台用户联调与手机真机验收仍未完成。
- 全项目 tests/ 较早运行 2502 passed、21 skipped、58 failed；这 58 个失败均在未改动的 `22d4ee6` 基线逐项复现，属于既有历史迁移/命令清单问题。没有用本次相关测试通过冒充全项目全绿。直接 pytest 另有 scripts/test_estrus_rank.py 收集时的数据库环境依赖。

## 执行裁定记录

- 未核实的数字版边界使用显式开发规则并保留发布门槛；若证据改变，须调整对应实现及测试。
- 紧密关联的目录/引擎/API/UI 在一个实现检查点提交，完整卡图另行提交；代价是单次代码差异较大。
- 项目没有根 README，说明写入现有 `gamefy/mistrealm/README.md`。
- 保留 v1 根入口与现有房间，新版 `/classic/` 隔离预览；尚未进行生产切换。
- 审查没有提出纯样式 Minor 项。

---

# 雾境本地验收记录

日期：2026-10-15。基线：c148977。所有操作仅在独立工作区和临时数据库执行。

## 已验证

- 受影响 Python / 游戏沙箱测试：218 passed、3 skipped。跳过项是可选环境用例；雾境 PostgreSQL 用例另行显式运行通过。
- 四个游戏的 Node 测试：33 passed。
- 本地 PostgreSQL 14：新增迁移升级、回退、再次升级及清理通过；并发争抢最后席位仅一人成功，同 UID 并发建房仅生成一个活动房间。
- Chrome 双客户端：首页、创建/加入、阵营选择、准备、换牌、预备牌、真实单位部署、三局结束、再战、刷新恢复通过。
- 1366×768、390×844、844×390 界面检查通过，无横向页面溢出；手机操作栏不覆盖手牌。
- 不含 allow-forms / allow-same-origin 的 allow-scripts 沙箱中，模拟 SDK 启动、创建房间、离开通过。
- 独立审查的准备超时计数、双方超时取消、关闭房间返回首页、SSE半开连接恢复已修复；另补充截止推进不能随版本冲突回滚的测试。
- 新游戏不读取员工表，陌生 UID 可直接登记；对手手牌、预备牌和牌库顺序不会出现在快照。
- git diff --check 和 JS 语法检查通过。

## 全项目测试的既有失败

直接 pytest 在收集 scripts/test_estrus_rank.py 时要求 DZMM_DATABASE_URL；未配置生产环境变量来绕过。
随后运行 pytest tests，结果2400 passed、19 skipped、60 failed。其中2个代理测试在开发中先更新断言、后更新配置，最终相关测试已通过；其余58项全部在 git archive c148977 的干净快照中逐项复现（58 failed），属于既有命令清单/历史迁移问题，未越界修复。

逐项复现的失败：
- `tests/core/test_app.py::test_game_management_lists_commands_employees_and_shop_items`
- `tests/deploy/test_ai_trigger_prefixes_migration.py::test_ai_trigger_prefixes_migration_defaults_existing_settings`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_creates_every_table`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_adds_the_group_switch_for_existing_rows`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_adds_the_unique_anchors`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_lays_out_the_settings_columns`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_downgrades_cleanly`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_round_trips_after_downgrade`
- `tests/deploy/test_birthday_migration.py::test_birthday_migration_tracks_the_yearly_edit_quota`
- `tests/deploy/test_black_history_migration.py::test_delete_draft_migration_upgrades_database_already_at_revision_81`
- `tests/deploy/test_company_lottery_migration.py::test_company_lottery_migration_creates_tables`
- `tests/deploy/test_company_lottery_migration.py::test_company_lottery_migration_adds_round_rule_snapshots`
- `tests/deploy/test_company_lottery_migration.py::test_company_lottery_migration_seeds_pool_and_settings`
- `tests/deploy/test_company_lottery_migration.py::test_company_lottery_migration_creates_indexes`
- `tests/deploy/test_company_lottery_migration.py::test_company_lottery_migration_keeps_the_economy_global`
- `tests/deploy/test_company_lottery_migration.py::test_company_lottery_migration_downgrades_cleanly`
- `tests/deploy/test_company_story_novel_migration.py::test_company_story_novel_migration_adds_nullable_setting_column`
- `tests/deploy/test_dark_market_commands_migration.py::test_dark_market_command_migration_seeds_without_overwriting_custom_template`
- `tests/deploy/test_dark_market_complaint_review_migration.py::test_dark_market_complaint_review_migration_adds_review_state_and_audit_fields`
- `tests/deploy/test_dark_market_complaint_review_migration.py::test_dark_market_balance_audit_migration_upgrades_existing_revision_58`
- `tests/deploy/test_dark_market_migration.py::test_dark_market_migration_creates_defaults_and_rank_limits`
- `tests/deploy/test_dark_market_migration.py::test_disclosure_duration_migration_preserves_existing_settings`
- `tests/deploy/test_dark_market_receipt_migration.py::test_dark_market_receipt_migration_preserves_history_and_command_customization`
- `tests/deploy/test_department_allowance_migration.py::test_department_allowance_migration_creates_every_table`
- `tests/deploy/test_group_game_types_migration.py::test_group_game_types_migration_enables_every_game_for_existing_groups`
- `tests/deploy/test_ivorune_node_migration.py::test_ivorune_node_migration_rewrites_persisted_platform_urls`
- `tests/deploy/test_king_game_migration.py::test_king_game_migration_creates_persistent_game_tables`
- `tests/deploy/test_liar_dice_migration.py::test_liar_dice_migration_creates_every_table`
- `tests/deploy/test_liar_dice_migration.py::test_liar_dice_migration_enables_game_for_existing_groups`
- `tests/deploy/test_liar_dice_migration.py::test_liar_dice_migration_does_not_duplicate_the_type`
- `tests/deploy/test_memory_assessment_single_timeouts_migration.py::test_memory_assessment_single_timeouts_migration_upgrades_revision_64`
- `tests/deploy/test_memory_guild_match_migration.py::test_memory_guild_match_migration_upgrades_existing_revision_61`
- `tests/deploy/test_multi_group_chat_migration.py::test_multi_group_migration_backfills_legacy_group_rows`
- `tests/deploy/test_never_have_i_ever_hearts_migration.py::test_never_have_i_ever_hearts_migration_removes_fixed_upper_bound`
- `tests/deploy/test_never_have_i_ever_migration.py::test_never_have_i_ever_migration_upgrades_revision_63`
- `tests/deploy/test_number_bomb_points_tournament_migration.py::test_number_bomb_points_tournament_migration_preserves_existing_games`
- `tests/deploy/test_outbound_submission_migrations.py::test_outbound_reference_and_submission_migrations_round_trip`
- `tests/deploy/test_performance_never_have_i_ever_knowledge_cards_migration.py::test_performance_and_never_have_i_ever_knowledge_cards_migration`
- `tests/deploy/test_pr5_backfill_migration.py::test_pr6_migrations_merge_into_deployed_main_chain_without_second_head`
- `tests/deploy/test_random_event_ad_slot_migration.py::test_ad_slot_migration_creates_tables`
- `tests/deploy/test_random_event_ad_slot_migration.py::test_ad_slot_migration_links_author_work_and_poll`
- `tests/deploy/test_random_event_ad_slot_migration.py::test_ad_slot_migration_keeps_one_draft_per_author`
- `tests/deploy/test_random_event_ad_slot_migration.py::test_ad_slot_migration_downgrades_cleanly`
- `tests/deploy/test_random_event_global_completion_reward_migration.py::test_random_event_global_completion_reward_migration_defaults_existing_settings`
- `tests/deploy/test_random_event_signup_notice_migration.py::test_random_event_signup_notice_migration_upgrades_existing_revision_62`
- `tests/deploy/test_random_event_tipping_migration.py::test_random_event_tipping_migration_resolves_names_and_round_trips`
- `tests/deploy/test_random_event_vote_gate_migration.py::test_gate_migration_appends_the_vote_command`
- `tests/deploy/test_random_event_vote_gate_migration.py::test_gate_migration_is_idempotent`
- `tests/deploy/test_random_event_vote_gate_migration.py::test_gate_migration_downgrades_cleanly`
- `tests/deploy/test_random_event_vote_migration.py::test_random_event_vote_migration_creates_tables`
- `tests/deploy/test_random_event_vote_migration.py::test_random_event_vote_migration_adds_settings_columns`
- `tests/deploy/test_random_event_vote_migration.py::test_random_event_vote_migration_is_global`
- `tests/deploy/test_random_event_vote_migration.py::test_random_event_vote_migration_allows_only_one_vote_per_employee`
- `tests/deploy/test_random_event_vote_migration.py::test_random_event_vote_migration_keeps_one_poll_per_schedule`
- `tests/deploy/test_random_event_vote_migration.py::test_random_event_vote_migration_downgrades_cleanly`
- `tests/deploy/test_shop_cards_migration.py::test_shop_card_migration_numbers_legacy_items_and_seeds_catalog`
- `tests/deploy/test_texas_holdem_migration.py::test_texas_holdem_migration_adds_group_scoped_tables_and_defaults`
- `tests/deploy/test_worker_account_display_name_migration.py::test_worker_account_display_name_migration_round_trips`

## 尚待平台验收

新游戏卡 ID 未提供，gamefy deploy --dry-run 因没有该卡的 dzmm.json 停止。未运行真实平台双账号 check、发布、上架或生产迁移。发布目录含原始 PNG 约59 MB，平台绑定后需要核对上传预算并做 slow 检查，必要时另做发布资源压缩。

当前本地试玩使用 scripts/mistrealm_dev.py 的模拟 SDK / 临时 SQLite；它不能替代真实 Gamefy SDK 和公网部署验收。


## 快速匹配增量验收

- 62项受影响Python测试通过；2项PostgreSQL环境用例在常规命令中跳过，随后在独立PostgreSQL库显式执行，2项均通过。
- 8项客户端测试通过；独立审查未发现确定性高/中优先级缺陷。
- PostgreSQL验证4人并发配对仅生成2个房间、4个唯一席位，取消与配对竞争、手动建房与入队竞争，迁移112升降级通过。
- 浏览器验证匹配、等待时刷新、取消后忽略迟到心跳、双人自动入房、准备开局及390px等待界面无横向溢出。
- 平台绑定/发布仍未执行。

## 固定预组重制（2026-10-15）

- 保留20张固定预组、三局争点、跨局补牌与预备牌；改造医师复活、引路人回收、王旗持续同列增益，以及弩矢清除增益/护甲。沿用既有美术。
- `pytest tests/core/test_mistrealm*.py gamefy/mistrealm/tests/test_assets.py -q`：54通过，2项PostgreSQL测试因未配置专用数据库跳过；本次无数据库结构改动。
- 客户端Node测试8通过；新增浏览器场景使用确定状态和实际Python结算规则，验证弃牌目标过滤、复活不触发部署、回收再部署伤害、前列王旗配合与390px布局。
- 更新后的18742本地服务通过原有双客户端完整对局、刷新、三局结算、再战、三个尺寸及隔离iframe检查。
- 本轮验证规则正确性与操作链路；数值仍是首轮试玩方案，未声称已完成竞争性胜率平衡。

## 对齐已确认的界面构图（2026-10-15）

- 对照原素材包 reference/home.png、room.png、battle.png，恢复首页左侧纵向主菜单/右侧领袖、房间双阵营肖像/卡组预览/中央VS，以及战场领袖/战列/操作三栏。继续保留快速匹配和新版卡组交互。
- 接入原素材包按钮、卡框、阵营标记与预备牌卡背；修正SVG按钮缩放，桌面战列保持卡牌纵向比例。新增layout.css承载这次布局修正。
- 扩展浏览器检查：首页和房间390px无横向溢出；桌面战场三栏不重叠。完整双客户端对局/三局结算/再战/iframe通过；新卡组的复活选择与回收操作通过。截图分别检查桌面首页、房间、战场以及手机房间和战场。
- 本次按既有素材重建主要构图；生成参考图中的部分复杂雕花与字形不等同于可复用UI素材，未宣称逐像素复刻。

## 起手与生命宝石规则更新（2026-10-15）

本节替代前文历史验证中有关预备牌、开局9张、跨局补3张和局分的描述。

- 开局10张、最多换2张；双方换牌确认后直接进入首局，删除预备牌阶段、字段与API动作。
- 行动与后续小局不自动抽牌，剩余手牌保留，场上单位进入弃牌堆。现有复活与回收效果仍可用。
- 初始生命[2,2]；小局败者扣1，平局双方扣1；任一方归零结束，双方同时归零整场平局。结果页和领袖面板显示剩余宝石，替换局分。
- 规则/API/资源测试58通过，2项PostgreSQL测试因未配置数据库跳过。本次未改数据库结构。覆盖连续平局、胜后平局、两连胜、各胜一局后第三局决胜、跨局无补牌、拒绝旧预备牌动作和再战重置生命。
- 浏览器验证10张换牌直接开局、双人完整结算/刷新/再战、390px与横屏布局、iframe，以及新卡组复活和回收组合通过。客户端8项测试通过。
- 此轮只对齐起手、跨局资源与生命判胜；20张预组、前后两列、技能、首局+2补偿与行动计时仍为自定义规则。

- 补充第二次连续超时优先判负的回归：不先执行停手、扣宝石，再覆盖零生命结算，保证终局原因与剩余生命一致。


## Classic 120 授权部署补记（2026-10-15）

正式数据库已升级113，平台已发布版本1792031142598。新增平台构建测试1 passed；不透明SDK iframe的五类新旧入口恢复、刷新与组牌通过。真实平台弱网首开6.72秒、刷新6.23秒，无平台检查findings；本人账号建房、刷新恢复与离开通过。Node12项再次通过，基于现场线上源码合并后的后端247项通过/3可选跳过。生产备份副本迁移升级/回退/再次升级通过。原作证据、双真实账号完整对局与手机真机限制仍保留，未提交公开上架。

发布回读：224/224文件一致、0函数；公开上架状态仍isPublic=false/publishStatus=none。构建测试先复现缺失构建入口，再通过；不透明iframe回归在修正本机测试网络环境后，旧入口无法找到新版首页按钮，发布入口五种模式均通过。
