# Gamefy 你画我猜

独立的 3～8 人群聊游戏前端。发布目录是 `publish/`，入口是 `index.html`。后端接口位于 `/api/drawguess`，群聊入口是 `/你画我猜`。

## 本地检查

```sh
node --test gamefy/drawguess/tests/*.test.mjs
.venv/bin/python -m pytest gamefy/drawguess/tests/test_drawguess_sandbox.py -q
.venv/bin/python -m pytest tests/core/test_drawguess_*.py tests/deploy/test_drawguess_*.py -q
```

前端只使用 Gamefy SDK 的 `user.info()`、`kv.get/put()`、`loading` 和 `log`。不使用 localStorage、sessionStorage、URL hash 或平台 token。KV 只保存当前 UID 最近进入的房间 ID；失败时仍可从大厅进入。

## 游戏卡

游戏卡 ID 为 `3767285`，本目录的 `dzmm.json` 已指向该独立草稿；不复用象棋 `3761638` 或斗地主 `3763357`。

卡片封面保存在 `assets/cover-v1.png`。线上简介为：

> 3～8人轮流作画，系统随机出题，其他人限时抢答。猜中得分，画手也能获得协作分；两轮结束按总分排名，支持观战与断线重连。

1. 先阅读新草稿生成的本地开发说明，并确认 `dzmm.json` 的发布目录仍指向 `publish`。
2. 确认 `publish/config.js` 的 `apiBase` 指向公开 HTTPS API 根地址。
3. 使用本机开发密钥完成 CLI 校验和草稿上传；密钥不得写入仓库。
4. 先在测试群进行三人真机联调。普通群成员可用后，再单独提交审核和开放正式群。

完整的迁移、配置、验收和回滚步骤见 `docs/drawguess-deployment.md`。
