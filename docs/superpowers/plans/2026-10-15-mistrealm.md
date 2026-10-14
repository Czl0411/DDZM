# Mistrealm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 实现公开、UID 信任模式的双人雾境卡牌游戏。
**Architecture:** 独立纯规则引擎，SQLAlchemy 事务房间存储，FastAPI HTTP/SSE，静态 Gamefy 前端。只扩展现有挂载、配置及迁移入口。
**Tech Stack:** Python / pytest / SQLAlchemy / FastAPI / 原生 JavaScript / CSS。
**Spec:** docs/superpowers/specs/2026-10-14-mistrealm-public-game-design.md

## Global Constraints
- 不读取员工表，不校验 token，不关联群或公司积分。
- 首版 14 种牌、2 领袖、每套 20 张、双方任意阵营。
- 动态文字与数值，图片只作插画；无浏览器持久存储。
- 不部署生产、不运行生产迁移；平台 ID 待提供。
- 保留现有游戏和用户未提交改动。

## Review Focus
- bool 冒充整数、重复目标、过期动作必须原子拒绝（Task 1/2）。
- 重试建房不得产生第二个房间（Task 2）。
- 一方断线不应改变对方隐藏信息或重置截止时间（Task 1/2/3）。
- 页面切换后旧 SSE 不得覆盖新页面（Task 3）。
- 资源加载失败仍保留可读牌名及重试入口（Task 3）。

### Task 1: 卡池与纯状态
Files: src/dzmm_bot/core/mistrealm_cards.py, mistrealm_state.py; tests/core/test_mistrealm_state.py。
Interfaces: CARDS / deck(faction, seat); new_state(host, now_ms); apply_action(state, seat, action, payload, now_ms, rng); advance(state, now_ms, rng); project(state, seat)。
- [x] 先写卡池、换牌、预备、逐卡效果、战列限制、领袖、停手、计分、超时、隐藏信息测试并运行观察失败。
- [x] 实现不可变输入转换与受控随机输入，使用设计中的 45/30/45 秒及 5 秒局间值。
- [x] pytest tests/core/test_mistrealm_state.py -q 全通过。

### Task 2: 独立房间持久化与接口
Files: mistrealm_repository.py, mistrealm_api.py, schema.py, repository.py, migrations/versions/20261015_111_mistrealm.py; tests/core/test_mistrealm_api.py。
Interfaces: repository.mistrealm_register(uid, name, avatar, now), mistrealm_me(uid, now), mistrealm_create/join/action/view; router(repository, clock)。
- [x] 测试陌生 UID 登记建房、第二人加入、第三人拒绝、幂等、版本冲突、非成员隔离、回滚。
- [x] 新增独立 Player/Room/Seat/Request；玩家锁再房间锁，活动席位唯一，数据库共享限流。
- [x] 新增 HTTP/SSE 及错误映射；pytest tests/core/test_mistrealm_api.py -q。
- [x] 使用本地 PostgreSQL 验证迁移和并发；若不可用明确记录未验证项。

### Task 3: Gamefy 页面
Files: gamefy/mistrealm/publish/{index.html,style.css,game.js,client.js,config.js,cards.json,assets/}, tests/client.test.mjs, README.md。
Interfaces: MistrealmClient 使用 Task 2 接口及 project 快照。
- [x] 编写请求、身份、重连、过期快照和错误恢复测试，观察失败。
- [x] 实现首页、建房加入、准备、换牌预备、战列目标选择、停手、结算再战、图鉴规则设置。
- [x] 使用本次美术包，动态渲染技能、战力与护甲；图像按需加载。
- [x] node --test gamefy/mistrealm/tests/*.test.mjs；双客户端及 390×844、844×390、1366×768 检查。

### Task 4: 服务接入与发布说明
Files: core/app.py, runtime/settings.py, tests/runtime/test_settings.py, docs/mistrealm-deployment.md。
- [x] 测试默认关闭与启用路由、后台截止推进及 CORS。
- [x] 新增 DZMM_MISTREALM_ENABLED，独立部署配置说明，禁止填用其他游戏 ID。
- [x] 运行受影响 tests/core tests/runtime tests/deploy 及三游戏回归；基线失败和未具备的平台验收条件记录在 docs/mistrealm-validation.md。

### Task 5: 最终验收
- [x] 对照 spec 检查完整链路、隐藏信息、幂等、超时、断线恢复。
- [x] 独立代码审查，修复重要问题后复测。
- [x] 保存工作区与验证记录，交付本地启动说明，不自动部署或发布。

