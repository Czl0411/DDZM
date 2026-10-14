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
