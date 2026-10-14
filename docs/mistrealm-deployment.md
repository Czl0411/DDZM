# 雾境服务接入

## 范围

使用现有 FastAPI / SQLAlchemy / PostgreSQL。独立 mistrealm_players、mistrealm_rooms、mistrealm_seats、mistrealm_requests；没有员工、群或奖励表外键。游戏路径 /api/mistrealm，身份头 Authorization: MistrealmUid <uid>。

开关 DZMM_MISTREALM_ENABLED 默认 false。设为 true 后启用接口、CORS 和现有后台 tick 的超时推进。路由响应 no-store，SSE 心跳15秒，客户端30秒失活后重连。读取及写入也推进到期状态，刷新不会重置时间。

## 待发布时的步骤

1. 备份目标数据库，确认当前迁移链。测试新增迁移 20261015_111（基础表）与20261015_112（匹配队列字段，上游20261015_111），再按项目部署流程升级。
2. 服务环境设置 DZMM_MISTREALM_ENABLED=true，重启现有 core 服务。
3. 仓库 deploy/caddy/dzmm-chess-ip.Caddyfile 已增加精确 /api/mistrealm/* 代理，保持 flush_interval -1，未开放管理路径。实际加载配置前需在目标服务器验证证书、语法和进程配置。
4. gamefy/mistrealm/publish/config.js 填写可供平台访问的 HTTPS API 根地址。默认为同源，仅供本地服务器。
5. 独立游戏卡 ID 为 3769848，已配置于 gamefy/mistrealm/dzmm.json；不得复用其他游戏 ID。先 check（含 reload/slow）和 deploy --dry-run，确认资源预算，再经用户授权发布。
6. 用两个普通平台账号验证完整流程、刷新、网络切换、同阵营对战和手机竖屏；发布代码与公开上架审核是两个步骤。

当前未执行生产迁移、生产部署或平台发布。

### 2026-10-15 发布准备记录

- 游戏卡 3769848 已保存名称「雾境：王冠与群鸦」、玩法简介、双阵营封面与横屏设置；平台回读确认 hasCover/hasIntro 为 true。
- 已在隔离目录拉取平台初始工作区，并保留 .dzmm/lock.json 发布基线；未覆盖本地游戏素材与代码。
- deploy --dry-run 通过：78 个文件、59.5 MiB，低于 100 MiB 总限制，版本基线一致。
- 本轮规则、API、集成、卡组和资源测试 50 项通过，客户端测试 8 项通过。
- 公网目标为 https://49.234.20.159；雾境接口目前返回 404。临时配置该地址运行平台弱网首开/刷新检查，因 Failed to fetch 启动失败，未发布代码或提交上架。检查后恢复同源配置，保持本地试玩可用。
- SSH ubuntu@49.234.20.159 的现有密钥登录被拒绝；待用户建立 /tmp/dzmm-new-ssh 控制连接后继续备份、迁移、部署后端、设置公网 API 地址、复验及发布。

## 规则与恢复

每套20张，开局10张，最多换2张，双方确认后直接对战；没有预备牌，行动和后续小局均不自动补牌，剩余手牌跨局保留。每行6单位，护甲不计战力；双方停手结算。每方2颗生命宝石，小局败者扣1颗、平局双方各扣1颗；归零即败，双方同时归零则整场平局，最多三局。等待与结算房间30分钟到期，换牌45秒，行动45秒，局间5秒。换牌超时保留全部，首次行动超时停手，连续第二次超时直接判负，不再扣减本小局宝石。主动提交清零超时计数。

新规则状态以lives替代scores，并移除reserve字段/阶段/动作。首次发布使用新建房间；若存在旧规则试玩房间，更新前结束旧房间后再开新局，不在对局中途切换规则。本地开发服重启会清空其临时数据库。

请求包含 request_id、version、match_id。重复请求返回原回执，版本冲突要求刷新；不会自动重放新出牌。限流保存在独立玩家表，在独立事务中计数，失败尝试同样占用额度。房间和玩家行锁及唯一席位约束在 PostgreSQL 上校验。

## 本地验收边界

scripts/mistrealm_dev.py 只监听127.0.0.1，使用临时SQLite和模拟平台UID。它用于查看界面、操作和双客户端同步，不证明真实 Gamefy SDK、平台资源加载或公网网络已通过验收。真实 PostgreSQL 的并发和迁移用独立测试数据库验证，不依赖SQLite推断。


## 快速匹配

独立玩家表新增 queue_ticket、queued_at、queue_expires_at 及租期索引，无员工关联。POST /matchmaking 进入/恢复；POST /matchmaking/heartbeat 和 /matchmaking/cancel 携带 ticket。首页每2秒续租，服务端20秒过期。过期票据不被心跳复活，旧取消不清除新票据。

只在有效等待玩家之间配对，不扫描自定义房间。玩家行锁、候选 SKIP LOCKED、两席唯一约束保证并发入座；双方同时进入而互相跳过时，后续心跳会完成配对。取消与配对竞争时，以先提交事务为准：已配对则返回房间，不假装已取消。
