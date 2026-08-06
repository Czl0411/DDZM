# 连续打卡与周全勤奖实施计划

> **执行说明：** 用户已确认需求并要求立即实施；在当前工作树内按本计划执行。

**目标：** 在北京时间自然周完成后自动结算周全勤奖，支持后台配置奖励，并在 `/我` 中显示连续打卡天数。

**架构：** 复用每日打卡和余额账本。周结算记录以“用户 + 周一日期”唯一，先原子创建结算记录，成功后在同一事务写入余额交易，确保补跑与并发调用不重复奖励。连续打卡只由现有每日打卡记录计算。

**技术栈：** Python、SQLAlchemy、Alembic、FastAPI、原生管理端 JavaScript、pytest。

---

### 任务 1：增加周全勤持久化和仓储结算

**文件：**
- 修改：`src/dzmm_bot/core/schema.py`
- 修改：`src/dzmm_bot/core/repository.py`
- 新增：`migrations/versions/20260806_11_weekly_attendance.py`
- 修改：`tests/core/test_repository.py`

1. 先写测试：完整七天在周一结算、缺一天不结算、同一周不能重复结算、奖励账本来源正确。
2. 运行：`.venv/bin/python -m pytest tests/core/test_repository.py -q`，确认新增断言先失败。
3. 新增周结算表和迁移，为经济设置增加周全勤奖字段，默认值为 5。
4. 在每日任务中按北京时间周一结算上一自然周；用唯一记录和事务保证幂等。
5. 重跑同一测试文件，确认通过。

### 任务 2：实现连续打卡和机器人/API 读取

**文件：**
- 修改：`src/dzmm_bot/core/repository.py`
- 修改：`src/dzmm_bot/core/reply_templates.py`
- 修改：`src/dzmm_bot/core/commands.py`
- 修改：`src/dzmm_bot/core/api_models.py`
- 修改：`src/dzmm_bot/core/app.py`
- 修改：`tests/core/test_group_commands.py`
- 修改：`tests/core/test_app.py`

1. 先补充 `/我` 的连续打卡变量和配置 API 的失败测试。
2. 运行：`.venv/bin/python -m pytest tests/core/test_group_commands.py tests/core/test_app.py -q`，确认新增断言先失败。
3. 以北京时间今日（未打卡时从昨天）向前计算连续打卡天数。
4. 给 `/我` 默认模板与变量上下文增加 `{连续打卡天数}`；扩展游戏设置读写 API。
5. 重跑两个测试文件，确认通过。

### 任务 3：接入管理端配置并回归部署

**文件：**
- 修改：`src/dzmm_bot/admin/app.py`
- 修改：`src/dzmm_bot/admin/templates/index.html`
- 修改：`src/dzmm_bot/admin/static/admin.js`
- 修改：`tests/admin/test_app.py`
- 修改：相关迁移测试（如存在）

1. 先补充管理端设置请求中携带周全勤奖的测试。
2. 运行：`.venv/bin/python -m pytest tests/admin/test_app.py -q`，确认新增断言先失败。
3. 在经济设置概览和编辑弹窗显示、编辑“每周全勤奖”，复用既有保存、忙碌和刷新机制。
4. 运行：`.venv/bin/python -m pytest`，确认全量测试通过。
5. 复核迁移头、提交变更，部署到服务器并检查三个服务均为 active。
