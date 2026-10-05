# 商店优化：后台管理能力补齐 + 分类

## 目标

后台对**所有商品**（系统目录商品 + 后台自建商品）具备完整管理能力：上架/下架（已有）、**改价**、**每日限购**、**分类**；玩家侧 /商店 按分类分区展示、/购买 按商品限购校验。

不在本次范围：自建商品开放效果类型（保持收藏品定位）、刮奖奖励可配、系统目录双向同步。

## 一、数据模型（迁移 80）

`items` 表加两列：

- `category: String(32) | None` — 分类名，自由文本；NULL = 未分类
- `daily_purchase_limit: Integer | None` — 每人每日限购次数；NULL = 不限

迁移时对 `system_key` 非空的系统商品回填默认值：

| 分类 | 商品 | daily_purchase_limit |
|---|---|---|
| 礼物赠送 | gift_basic/intermediate/advanced/platinum（effect_type=gift） | 2（迁移现有硬编码行为） |
| 刮刮乐 | scratch_a/b/c（scratch） | 3（同上） |
| 功能道具 | ai_quota、multiplayer_quota | NULL（不限） |
| 成人内容 | adult_m/adult_scene/adult_common ×10 | NULL（不限，仍受群 adult_shop_enabled 控制） |
| （不设） | 自建商品（system_key 为空） | NULL |

`_ensure_shop_catalog` 补缺时同步写入 category 与 daily_purchase_limit 默认值（只补缺、不覆盖手改值的行为不变）。

## 二、后台

### 2.1 商品列表布局重构

现状：每个商品一横排挤 6 个控件（价格、启用、无限库存、无标签的库存框、职位长下拉、保存），可读性差。改为卡片式两区布局（复用现有 command-card 的样式体系）：

- **头部行**：`#编号 商品名` + 状态徽章（已上架/已下架）+ 分类徽章 + 系统效果徽章（系统商品显示 effect_type，自建显示"收藏品"）
- **编辑区网格**（两行对齐，每项带标签）：
  - 第一行：价格｜库存｜无限库存（勾选后库存框禁用）
  - 第二行：分类｜每日限购（空=不限）｜最低职位
  - 右下角：保存按钮

### 2.2 编辑能力

- 创建/编辑商品支持：**价格**（编辑态开放修改）、**分类**（datalist 建议：礼物赠送/刮刮乐/功能道具/成人内容/收藏，可自由输入）、**每日限购**（数字，空=不限）
- `CreateItemRequest` / `UpdateItemRequest` 加 `category`、`daily_purchase_limit`；Update 加 `price`
- `update_shop_item` / `add_item` 支持新字段（`daily_purchase_limit=0` 视为不限）
- 商品列表增加**分类筛选下拉**（选项来自现有商品的 distinct category），与名称搜索叠加

## 三、玩家侧

- **/商店 分区展示**：按 category 分组，组序固定：礼物赠送 → 刮刮乐 → 功能道具 → 成人内容 → 其他（未分类归此）。组头如「◆ 礼物赠送」，行格式保持现有「#编号 名称 价格 库存 LV门槛 说明」。成人组行仍仅在群开启成人商店时展示。
- **/购买 限购校验**：把 gift 2 次 / scratch 3 次的硬编码改为读 `item.daily_purchase_limit`；当日已购次数达上限返回「今日限购」提示（复用 ShopPurchaseDailyUsageRecord 表与 reply_templates 新增 no_more_purchase 模板）。NULL = 不限，行为与现在一致。
- 折扣价结算逻辑不变（生日折扣）。

## 四、测试

- 迁移：新列存在、系统商品回填正确
- 限购：达到上限第 N+1 次被拒；NULL 不限；跨天重置
- 后台：改价/分类/限购编辑生效并影响玩家侧 /商店 与 /购买
- /商店：分组渲染、未分类归"其他"、成人组开关

## 五、交付

迁移 80 + 代码，本地测试通过后按常规流程部署（备份 → deploy.sh → 重启验证）。
