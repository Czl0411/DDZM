# 雾境服务接入

## 范围

使用现有 FastAPI / SQLAlchemy / PostgreSQL。独立 mistrealm_players、mistrealm_rooms、mistrealm_seats、mistrealm_requests；没有员工、群或奖励表外键。游戏路径 /api/mistrealm，身份头 Authorization: MistrealmUid <uid>。

开关 DZMM_MISTREALM_ENABLED 默认 false。设为 true 后启用接口、CORS 和现有后台 tick 的超时推进。路由响应 no-store，SSE 心跳15秒，客户端30秒失活后重连。读取及写入也推进到期状态，刷新不会重置时间。

## 待发布时的步骤

1. 备份目标数据库，确认当前迁移链。测试新增迁移 20261015_111（上游20261014_110），再按项目部署流程升级。
2. 服务环境设置 DZMM_MISTREALM_ENABLED=true，重启现有 core 服务。
3. 仓库 deploy/caddy/dzmm-chess-ip.Caddyfile 已增加精确 /api/mistrealm/* 代理，保持 flush_interval -1，未开放管理路径。实际加载配置前需在目标服务器验证证书、语法和进程配置。
4. gamefy/mistrealm/publish/config.js 填写可供平台访问的 HTTPS API 根地址。默认为同源，仅供本地服务器。
5. 用户创建新游戏卡并提供 ID 后，用该卡初始化专属 dzmm.json；不得复用其他游戏 ID。先 check（含 reload/slow）和 deploy --dry-run，确认资源预算，再经用户授权发布。
6. 用两个普通平台账号验证完整流程、刷新、网络切换、同阵营对战和手机竖屏；发布代码与公开上架审核是两个步骤。

当前未执行生产迁移、生产部署或平台发布。

## 规则与恢复

每套20张，开局9张，最多换2张并选1张预备牌；第三局取回预备牌。每行6单位，护甲不计战力；双方停手结算，最多三局。等待与结算房间30分钟到期，换牌45秒，预备30秒，行动45秒，局间5秒。连续两次准备或行动超时判负，双方同时达到则取消。主动提交清零超时计数。

请求包含 request_id、version、match_id。重复请求返回原回执，版本冲突要求刷新；不会自动重放新出牌。限流保存在独立玩家表，在独立事务中计数，失败尝试同样占用额度。房间和玩家行锁及唯一席位约束在 PostgreSQL 上校验。

## 本地验收边界

scripts/mistrealm_dev.py 只监听127.0.0.1，使用临时SQLite和模拟平台UID。它用于查看界面、操作和双客户端同步，不证明真实 Gamefy SDK、平台资源加载或公网网络已通过验收。真实 PostgreSQL 的并发和迁移用独立测试数据库验证，不依赖SQLite推断。
