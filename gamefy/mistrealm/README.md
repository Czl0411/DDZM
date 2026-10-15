# 雾境：王冠与群鸦

独立公开双人 Gamefy 卡牌游戏。平台 UID 信任模式；玩家独立于员工、群聊和公司积分。后端权威处理发牌、隐藏信息、目标、计分与超时。

## Classic 120 开发预览（2026-10-15）

新版入口为 `/classic/`，API 为 `/api/mistrealm/classic`。它使用独立的 `rules_version=2`，已有线上 v1 入口和房间继续使用原引擎。本节描述新版；下文固定预组、两排等内容是 v1 的历史说明。经典版已于2026-10-15更新至游戏卡3769848，版本1792031142598；尚未提交公开上架。

```sh
PYTHONPATH=src python scripts/mistrealm_dev.py --port 18744
```

打开 http://127.0.0.1:18744/classic/?player=classic-local-a 和 http://127.0.0.1:18744/classic/?player=classic-local-b 。两个页面可通过快速匹配或房间码对战；这是临时 SQLite 和模拟身份，重启清空数据。

新版提供120种卡牌（102单位、10领袖、8特殊）和2种变身形态、5阵营、10套可编辑初始牌组。至少22单位、最多10特殊，同阵营加中立；双方锁定前隐藏对方阵营与领袖，锁定后揭晓。匹配使用入队时的牌组副本，编辑保存不会改变正在匹配的牌组。

采用三排、10张起手、最多换2张、跨局不自动补牌和两颗生命宝石。服务器结算间谍、医师连锁、召集、同袍、鼓舞、号角、天气、焚阵、诱饵、仪式变身及阵营能力；点击场上卡牌可查看当前战力的计算来源。玩家头像和昵称沿用平台资料，支持刷新恢复选择和对局。

122张卡面已逐张检查并接入，前端资源约19.36MiB。

少数原作数字版边界仍有资料冲突，见[规则核验记录](../../docs/superpowers/specs/2026-10-15-mistrealm-classic-120.md)。已完成单账号真实平台启动、建房和刷新验收；不宣称原作边界逐项复核或真实平台双账号完整对局已完成。

```sh
PYTHONPATH=src python -m pytest tests/core/test_mistrealm* -q
node --test gamefy/mistrealm/tests/*test.mjs
python3 gamefy/mistrealm/tests/test_classic_assets.py
PYTHONPATH=src python gamefy/mistrealm/tests/classic_browser.py
PYTHONPATH=src python gamefy/mistrealm/tests/classic_e2e.py
PYTHONPATH=src python gamefy/mistrealm/tests/classic_recovery_browser.py
```

资源检查需要 Pillow；浏览器检查需要 Playwright 与 Chrome，`classic_browser.py` 连接上面的18744本地服务，`classic_e2e.py` 自行创建隔离服务。规则和卡表从 `src/dzmm_bot/core/mistrealm_classic_*` 导出，运行 `PYTHONPATH=src python scripts/export_mistrealm_classic.py` 更新前端目录。原创PNG、生成提示词和审核记录分别保存在 `source-art/classic` 与 `art-updates/classic-120-manifest.json`。

## 平台构建与更新

不要把源目录 `publish/` 原样当作新版根入口上传。它保留本地 v1 入口；平台构建会加入保留 SDK 的版本选择器，新玩家默认 Classic，已有 v1/v2 房间和队列按原版本恢复。

```sh
python3 scripts/build_mistrealm_platform.py .superpowers/classic-deploy/game
cd .superpowers/classic-deploy/game
gamefy deploy --dry-run
gamefy check --reload --slow
gamefy deploy --yes --verify --label mistrealm-2.0.0-classic-120
```

生产数据库要求迁移113及兼容后端，详见部署记录。构建设置两个版本的 HTTPS API，保留 `legacy.html` 与旧版资源；源目录 `/classic/` 仍可同源本地预览。

## 本地试玩

从仓库根目录运行（使用已安装项目依赖的 Python）：

```sh
PYTHONPATH=src python scripts/mistrealm_dev.py --port 18741
```

打开 http://127.0.0.1:18741/?player=local-a 和 http://127.0.0.1:18741/?player=local-b ，创建房间并复制六位房间码给另一页面。开发服务器只监听回环地址、使用临时 SQLite、仅在开发 HTML 中注入模拟 SDK；关闭服务器即清空本次试玩数据，线上 publish 不含模拟身份。

也可在两个入口同时点击“快速匹配”，系统自动配对，仍由双方选择阵营、准备后开局。匹配不加段位或积分；等待时可取消，刷新会恢复有效队列。停止心跳20秒后会退出候选队列。

流程：首页 → 快速匹配或建房/加入 → 选阵营 → 准备 → 房主开始 → 换牌 → 对战 → 结算 → 双方再战。

## 重制预组（2026-10-15）

仍为每套20张：6种中立牌加4种阵营牌，各2张，另配1位领袖。沿用现有美术。开局10张、最多换2张，随后直接对战；不设预备牌，行动和后续小局均不自动补牌。每方2颗生命宝石，小局败者扣1颗，平局双方各扣1颗；归零即败，双方同时归零则整场平局。未打出的手牌跨局保留。这是首轮可试玩数值，尚未进行大样本胜率平衡。

- 黑鸦：弩手/骑士制造伤口 → 刺客追击或猎手增益 → 引路人回收受伤单位或部署牌，择机再次使用。回收会丢失当前场上点数，不能无代价重复技能。
- 烬冠：王旗先落阵 → 同列单位持续获得额外增益 → 守卫保护王旗，统领与动员补充阵型收益。王旗本身低战力，先出有风险，后出则少收益。
- 中立医师提供跨局资源，但只能复活基础战力≤5的非医师单位，复活不触发部署或王旗。复活出的持续技能仍会响应之后的手牌部署。任意战列单位优先前列，满则后列；无可用位置时不可选。
- 破甲弩矢清除增益与护甲后造成3伤害，用来反制高增益目标；不会把受伤单位恢复至基础战力。
- 回收、复活允许不选目标直接部署；有目标的伤害或保护部署技能仍须选目标。医师/引路人不会凭空抽新牌。

| 卡牌 | 基础战力 | 效果 |
|---|---:|---|
| 荒境佣兵 | 7 | 无部署效果。 |
| 铁盾卫士 | 5 | 部署：自身获得3护甲。 |
| 山隘弩手 | 4 | 部署：对一个敌人造成3伤害。 |
| 随军医师 | 2 | 部署：可复活弃牌堆中一个基础战力不超过5的非医师单位。恢复基础战力，不触发部署；任意战列单位优先进入前列。 |
| 战地动员 | — | 使至多两个不同友军各获得3增益。 |
| 破甲弩矢 | — | 移除一个敌人的全部护甲与高于基础战力的增益，再造成3伤害。 |
| 雾鸦骑士 | 7 | 部署：对一个敌人造成2伤害。 |
| 灰羽猎手 | 5 | 部署：存在受伤敌人时，自身获得3增益。 |
| 断誓刺客 | 4 | 部署：对一个敌人造成2伤害；目标已受伤则改为4。 |
| 鸦群引路人 | 3 | 部署：可将一个其他友军收回手牌，移除其增益、伤害与护甲。再次打出时可触发部署技能。 |
| 烬冠步兵 | 5 | 部署：本列有其他友军时，自身获得3增益。 |
| 王旗执掌者 | 3 | 持续：每当你从手牌向本列部署其他单位，使该单位获得1增益。复活不触发；多面王旗可叠加。 |
| 誓约守卫 | 6 | 部署：使一个其他友军获得2增益及2护甲。 |
| 灰烬统领 | 5 | 部署：本列至少有两个其他友军时，使其中两个各获得2增益。 |
| 无冠鸦王 | — | 整场一次：对一个敌人造成3伤害，消耗行动。 |
| 余烬摄政 | — | 整场一次：使一个友军获得3增益及2护甲，消耗行动。 |

## 当前规则范围

本次对齐《巫师3》的起手、跨局资源与生命宝石规则；仍保留自定义20张双阵营预组、前后两列、技能效果、首局先手首个单位+2补偿及45秒行动计时，并非逐项复刻原作。

## 文件

- publish/client.js：SDK 身份、HTTP、SSE、失活超时和退避；断流后顺序读取快照，避免并行同步通道。
- publish/game.js：DOM 交互与按版本更新；错误动作不自动重放。
- publish/layout.css：按已确认的首页、房间、战场参考图恢复主要构图，并适配手机；在基础style.css之后加载。
- publish/cards.json：从后端权威 CARDS 导出，由测试校验；不要单独修改数值。
- publish/assets：本次生成的独立插画、背景、卡背及矢量界面素材。
- tests：客户端、资源一致性和本地浏览器链路检查。
- scripts/mistrealm_dev.py：仓库根目录的本地测试服务器，不发布。

## 验证

```sh
PYTHONPATH=src python -m pytest tests/core/test_mistrealm_state.py tests/core/test_mistrealm_api.py tests/core/test_mistrealm_integration.py gamefy/mistrealm/tests/test_assets.py -q
PYTHONPATH=src python -m pytest tests/core/test_mistrealm_deck_rework.py -q
node --test gamefy/mistrealm/tests/client.test.mjs
PYTHONPATH=src MISTREALM_DEV_URL=http://127.0.0.1:18741 python gamefy/mistrealm/tests/deck_rework_browser.py
python gamefy/mistrealm/tests/browser_smoke.py
MISTREALM_DEV_URL=http://127.0.0.1:18741 python gamefy/mistrealm/tests/matchmaking_browser.py
```

浏览器检查需要运行上述本地服务器，并安装 Playwright 与 Google Chrome。PostgreSQL 并发和迁移测试使用独立可丢弃数据库：

```sh
MISTREALM_TEST_DATABASE_URL=postgresql+psycopg://USER@127.0.0.1:PORT/mistrealm_test PYTHONPATH=src python -m pytest tests/core/test_mistrealm_postgres.py -q
```

该测试创建并删除 mistrealm 表，不要指向已有业务数据库。

## 平台绑定

游戏卡 ID 为 3769848，已发布版本 1792002374478，公网 API 为 https://49.234.20.159。封面、简介及横屏设置已保存；公开上架因 VIP1 每日 2 次额度用完被拒绝，尚未公开。发布包使用同尺寸 WebP，约 9.2 MiB；PNG 原图保存在 source-art/，不上传。

服务配置与迁移步骤见 ../../docs/mistrealm-deployment.md。不会使用现有三个游戏的 cardId。
