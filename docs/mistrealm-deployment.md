# 雾境服务接入

## 范围

使用现有 FastAPI / SQLAlchemy / PostgreSQL。独立 mistrealm_players、mistrealm_rooms、mistrealm_seats、mistrealm_requests；没有员工、群或奖励表外键。游戏路径 /api/mistrealm，身份头 Authorization: MistrealmUid <uid>。

开关 DZMM_MISTREALM_ENABLED 默认 false。设为 true 后启用接口、CORS 和现有后台 tick 的超时推进。路由响应 no-store，SSE 心跳15秒，客户端30秒失活后重连。读取及写入也推进到期状态，刷新不会重置时间。

## 待发布时的步骤

1. 备份目标数据库，确认当前迁移链。测试新增迁移 20261015_111（基础表）与20261015_112（匹配队列字段，上游20261015_111），再按项目部署流程升级。
2. 服务环境设置 DZMM_MISTREALM_ENABLED=true，重启现有 core 服务。
3. 仓库 deploy/caddy/dzmm-chess-ip.Caddyfile 已增加精确 /api/mistrealm/* 代理，保持 flush_interval -1，未开放管理路径。实际加载配置前需在目标服务器验证证书、语法和进程配置。
4. gamefy/mistrealm/publish/config.js 填写可供平台访问的 HTTPS API 根地址。当前为 https://49.234.20.159。
5. 独立游戏卡 ID 为 3769848，已配置于 gamefy/mistrealm/dzmm.json；不得复用其他游戏 ID。先 check（含 reload/slow）和 deploy --dry-run，确认资源预算，再经用户授权发布。
6. 用两个普通平台账号验证完整流程、刷新、网络切换、同阵营对战和手机竖屏；发布代码与公开上架审核是两个步骤。

2026-10-15 已完成生产迁移、后端部署及平台代码发布；公开上架因账号每日额度用完被拒绝，尚未公开。

### 2026-10-15 发布记录

- 游戏卡 3769848 已保存名称「雾境：王冠与群鸦」、玩法简介、双阵营封面与横屏设置；版本为 1792002374478（mistrealm-1.0.0），78 个发布文件已逐一回读一致。
- 服务器备份位于 /var/backups/dzmm/mistrealm-20261015，包含数据库 dump、代码、已安装包、环境和 Caddy 配置；备份目录仅 root 可读。已验证数据库备份目录及文件校验和。
- 生产数据库副本完成 110 → 112 → 110 → 112 迁移演练后删除。正式数据库迁移至 20261015_112，4 张新表 owner 均为 dzmm。
- 基于线上源文件应用雾境补丁，保留其他功能线上改动。更新源码及已安装 Python 包；Core 新增 mistrealm.conf 开关并重启，Caddy 校验后重载。首次因探测路径写错触发回滚，修正为 /api/mistrealm/players/me 后部署通过。
- 公网 API 为 https://49.234.20.159，身份接口匿名请求返回 401，跨域预检返回 200；原象棋、斗地主、你画我猜 rooms 接口仍返回 401。Core、Admin、Browser、Caddy 均 active。AI worker 在部署前已处于 failed，本次未改变。
- 50 项规则/API/集成/资源测试、8 项客户端测试通过；线上源文件应用补丁后的 48 项核心测试通过。公网后端双浏览器测试通过完整对局、刷新、再战、三种屏宽及不透明 iframe；使用模拟 UID，不等同两名真实平台用户验收。
- 真实 SDK 平台弱网首开、建房、刷新恢复通过。WebP 版本弱网 ready 约 3.0–3.6 秒；手机真机和复杂断网情形尚需人工验收。
- 首次 59.5 MiB 上传被网关以 HTTP 413 拒绝。发布目录 20 张 PNG 改为同尺寸 quality=90 WebP，包降至 9.2 MiB；原图保存在 gamefy/mistrealm/source-art，未重新生成画面。资源一致性及双浏览器流程复验通过。
- listing submit 被平台拒绝：VIP1 会员每日上架限制 2 次，已达上限。当前 isPublic=false、publishStatus=none，额度恢复后需要再次提交上架。

## 规则与恢复

每套20张，开局10张，最多换2张，双方确认后直接对战；没有预备牌，行动和后续小局均不自动补牌，剩余手牌跨局保留。每行6单位，护甲不计战力；双方停手结算。每方2颗生命宝石，小局败者扣1颗、平局双方各扣1颗；归零即败，双方同时归零则整场平局，最多三局。等待与结算房间30分钟到期，换牌45秒，行动45秒，局间5秒。换牌超时保留全部，首次行动超时停手，连续第二次超时直接判负，不再扣减本小局宝石。主动提交清零超时计数。

新规则状态以lives替代scores，并移除reserve字段/阶段/动作。首次发布使用新建房间；若存在旧规则试玩房间，更新前结束旧房间后再开新局，不在对局中途切换规则。本地开发服重启会清空其临时数据库。

请求包含 request_id、version、match_id。重复请求返回原回执，版本冲突要求刷新；不会自动重放新出牌。限流保存在独立玩家表，在独立事务中计数，失败尝试同样占用额度。房间和玩家行锁及唯一席位约束在 PostgreSQL 上校验。

## 本地验收边界

scripts/mistrealm_dev.py 只监听127.0.0.1，使用临时SQLite和模拟平台UID。它用于查看界面、操作和双客户端同步，不证明真实 Gamefy SDK、平台资源加载或公网网络已通过验收。真实 PostgreSQL 的并发和迁移用独立测试数据库验证，不依赖SQLite推断。


## 快速匹配

独立玩家表新增 queue_ticket、queued_at、queue_expires_at 及租期索引，无员工关联。POST /matchmaking 进入/恢复；POST /matchmaking/heartbeat 和 /matchmaking/cancel 携带 ticket。首页每2秒续租，服务端20秒过期。过期票据不被心跳复活，旧取消不清除新票据。

只在有效等待玩家之间配对，不扫描自定义房间。玩家行锁、候选 SKIP LOCKED、两席唯一约束保证并发入座；双方同时进入而互相跳过时，后续心跳会完成配对。取消与配对竞争时，以先提交事务为准：已配对则返回房间，不假装已取消。

## 2026-10-15 匹配计时修复

版本 mistrealm-1.0.1-clock / 1792002782024：服务器返回 elapsed_ms，页面使用 performance.now() 累加，避免设备时钟落后导致已等待长期显示 0。心跳返回和刷新均恢复服务器累计等待时长，不修改配对条件。服务器与本机观察到约 1 分钟时差，未修改系统时钟。

新增回归测试先复现旧版失败，再验证修复：9 项匹配测试、8 项客户端测试通过；浏览器模拟 Date.now() 固定为 0，仍能计时、心跳、刷新恢复及取消。隔离本地队列复验双人配对、准备开局和延迟心跳取消保护通过，未将合成测试玩家放入线上公开匹配队列。线上已安装后端时长返回校验通过，Core active、无重启循环；本次无数据库迁移。后端备份 /var/backups/dzmm/mistrealm-clock-20261015。
