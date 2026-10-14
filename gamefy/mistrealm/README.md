# 雾境：王冠与群鸦

独立公开双人 Gamefy 卡牌游戏。平台 UID 信任模式；玩家独立于员工、群聊和公司积分。后端权威处理发牌、隐藏信息、目标、计分与超时。

## 本地试玩

从仓库根目录运行（使用已安装项目依赖的 Python）：

```sh
PYTHONPATH=src python scripts/mistrealm_dev.py --port 18741
```

打开 http://127.0.0.1:18741/?player=local-a 和 http://127.0.0.1:18741/?player=local-b ，创建房间并复制六位房间码给另一页面。开发服务器只监听回环地址、使用临时 SQLite、仅在开发 HTML 中注入模拟 SDK；关闭服务器即清空本次试玩数据，线上 publish 不含模拟身份。

流程：首页 → 建房/加入 → 选阵营 → 准备 → 房主开始 → 换牌 → 预备牌 → 对战 → 结算 → 双方再战。

## 文件

- publish/client.js：SDK 身份、HTTP、SSE、失活超时和退避；断流后顺序读取快照，避免并行同步通道。
- publish/game.js：DOM 交互与按版本更新；错误动作不自动重放。
- publish/cards.json：从后端权威 CARDS 导出，由测试校验；不要单独修改数值。
- publish/assets：本次生成的独立插画、背景、卡背及矢量界面素材。
- tests：客户端、资源一致性和本地浏览器链路检查。
- scripts/mistrealm_dev.py：仓库根目录的本地测试服务器，不发布。

## 验证

```sh
PYTHONPATH=src python -m pytest tests/core/test_mistrealm_state.py tests/core/test_mistrealm_api.py tests/core/test_mistrealm_integration.py gamefy/mistrealm/tests/test_assets.py -q
node --test gamefy/mistrealm/tests/client.test.mjs
python gamefy/mistrealm/tests/browser_smoke.py
```

浏览器检查需要运行上述本地服务器，并安装 Playwright 与 Google Chrome。PostgreSQL 并发和迁移测试使用独立可丢弃数据库：

```sh
MISTREALM_TEST_DATABASE_URL=postgresql+psycopg://USER@127.0.0.1:PORT/mistrealm_test PYTHONPATH=src python -m pytest tests/core/test_mistrealm_postgres.py -q
```

该测试创建并删除 mistrealm 表，不要指向已有业务数据库。

## 平台绑定

新游戏卡 ID 尚未提供，因此没有写入 dzmm.json，也没有发布。绑定后在本目录使用 Gamefy CLI 初始化对应的新卡，保留本地 publish 文件，设置 publish/config.js 的公网 HTTPS API 根地址，再执行 gamefy check 和 gamefy deploy --dry-run。原始 PNG 美术包约 59 MB，最终上传预算和弱网加载表现需要随平台 dry-run/check 一起验收。

服务配置与迁移步骤见 ../../docs/mistrealm-deployment.md。不会使用现有三个游戏的 cardId。
