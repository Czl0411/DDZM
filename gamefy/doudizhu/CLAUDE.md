<!-- gamefy:begin -->
<!-- 由 gamefy CLI 维护：pull / docs 会更新这一段，段外内容不会被改动。 -->
# DZMM Gamefy 游戏项目

游戏 ID 3763357 · 站点 https://www.aikda.com · gamefy CLI 0.2.3

用 `gamefy` CLI 在本地开发，游戏跑在平台的 iframe 沙箱里。上次同步的版本与来源在 `.dzmm/lock.json`。
开发者密钥只存在 CLI 里（`~/.config/dzmm/`）：不要向作者索要密钥，也不要把它写进项目。未登录时运行
`gamefy auth login`，把终端显示的网址和代码转告作者，由作者在自己的浏览器里授权。

## 资料在哪

- 工作指南（规则、配方、模板、示例游戏）：`gamefy skills` 装到 `.claude/skills/dzmm-gamefy/`，先读 `SKILL.md`。
  做新游戏、或者作者只给了一个模糊点子时，先读同目录的 `game-design.md`，定下核心循环再写代码。
- 平台完整参考：`gamefy docs` 写到 `.gamefy/docs.md`（约 5k 行）。按任务查对应章节，不必通读；
  但用到某个 `dzmm.*` / `ctx.*` 接口前，必须先查到它的真实签名和返回结构，不要凭常识猜。

## 目录

- `publish/` — 玩家看到的静态文件，`index.html` 是入口
- `functions/` — 服务端函数，一文件一函数，**不能 import 任何东西**；多个操作用 `request.body.op` 分发
- `dzmm.json` 与 `.dzmm/` — 项目配置与发布基线，都要提交，不要 gitignore

## 必须遵守

1. AI 对话没有 `system` role，只有 `user` 和 `assistant`；流式回调拿到的是累计全文，不是增量。
2. 持久化只用 `dzmm.kv`：`get()` 返回信封 `{ value, updated_at }`；`put` 默认防抖，手动存档要 `{ flush: true }` 并 await。
   游戏 iframe 没有同源权限，localStorage / sessionStorage / IndexedDB / Cookie 都会抛 SecurityError——这是平台固定的安全设计，
   改代码用 `dzmm.kv`，不要建议作者去改沙箱或要平台加接口。来源是 `chrome-extension://` 的报错来自浏览器扩展，与游戏无关。
3. 页面随时可能被重新加载（切到后台被系统回收、离开较久后回来）：有进度的游戏每次重要状态变化就 `dzmm.kv.put` 存档，
   页面变为 hidden / pagehide 时把内存里未保存的状态 put 出去，启动时先恢复上次进度；
   不要只靠手动存档按钮。防抖写入在页面关掉时未必送得出，一局结束、拿到奖励等关键节点用 `{ flush: true }`。
4. 启动加载：主脚本一开始就调用 `dzmm.loading.progress({ phase: 'start' })`，加载资源时按真实进度上报；
   首个可交互画面渲染出来后才调用 `dzmm.loading.ready()`；失败时调用 `dzmm.loading.error(code, message)`
   并在页面里显示可重试的错误。不要提前 `ready()`，也不要用假进度掩盖卡住——线上冷启动会被判为启动超时。
5. 玩家展示资料（`dzmm.user.info()` 的昵称、头像）只用于显示；需要信任的判定（分数、货币、归属）放到服务端函数，
   用 `ctx.user` 与 `ctx.kv`。所有资料字段都可能为空，要有兜底显示。
6. 可选能力先查 `dzmm.capabilities.get()`，缺失按 false 处理并准备降级路径。
7. 调试用 `dzmm.log.info/warn/error()`，不用 `console.log`：前者在 `gamefy dev` 控制台里看得到，发布后 `gamefy logs` 也查得到。

## 说“完成”之前

- 没有浏览器也要看到游戏：运行 `gamefy check --tap "<开始按钮>" --play "<目标元素>" --reload`（用本机 Chrome/Edge 无头打开，手机竖屏；
  `--play` 会在一局时间内持续点目标，走完开局→交分→排行榜整条链路；加 `--slow` 看弱网启动），
  **亲自打开 `.gamefy/check/` 里的截图看**：首屏、按下开始后的画面、刷新后的画面是否正确。它报告启动时序、脚本错误、资源加载失败；
  有 error 时退出码为 1。截图看不出问题不等于没问题，但没看截图就不能说“验证过画面”。
- 在 `gamefy dev` 里实际跑过改动的功能（Agent shell 里用 `nohup gamefy dev --no-open > .gamefy/dev.log 2>&1 &` 后台启动，
  否则命令结束时进程会被一起终止；地址写在 `.gamefy/dev.json`，`--port` 可固定端口），并切到手机竖屏看布局；玩到一半刷新页面，确认进度能恢复；
  至少走一遍出错路径（AI 调用失败、额度用尽、资源加载失败）。
- 服务端调用失败的路径要真的走一次：临时让开局 / 交分函数 `throw`，再跑一次 `gamefy check --tap … --play …` 看截图，
  确认玩家当场看到提示、按钮可以重试，而不是玩完一整局才发现成绩没记上。开局请求要 await，失败就停在菜单。
- 多人功能（排行榜、共享数据）用 `gamefy dev --player 2`（2 到 8）再开一个测试玩家：服务端 `ctx.user` 与浏览器 `dzmm.kv` 都与作者本人分开，
  两个窗口对照看隔离与交互。测试玩家没有头像，真实玩家之间的表现仍要向作者说明还没验证。
- 本地和线上不同的能力（`capabilities.get()` 在本地为 false 的项目）要确认降级路径真的能走通。

## 发布

- 发布前先 `gamefy deploy --dry-run`（只检查不发布：大小限制、版本冲突、上架状态）；发布用 `gamefy deploy --yes --verify`
  （发布后逐文件回读比对），可加 `--label 1.2.0` 给这个版本起名（平台记录，logs/status 和网页工作台都显示）。
- 只用 `gamefy deploy` 发布（或网页「上传本地项目」），不要自己写脚本调发布接口。
  Agent 的 shell 没有终端交互，需要 `--yes`；只在作者要求发布时执行。
- 报 `revision_conflict` 时先保住本地成果（git commit 或复制整个项目），再到另一个空目录 `gamefy pull` 线上版本比较、合并后重新发布。
  `pull` 会整体替换 `publish/` 和 `functions/`，不是合并；不要默认加 `--force`。
- 代码发布成功不等于玩家能玩到：还要有名称、简介、封面并提交上架审核。作者要求“上线”时先 `gamefy status` 看还缺什么，
  再用 `gamefy profile --name … --intro … --cover <图片>` 补齐、`gamefy listing submit` 提交审核（与网页作品页同一套检查），
  `gamefy status --wait` 跟进审核结果。封面、简介、名称要作者确认过再提交，不要自己编。
- 发布后查线上问题：`gamefy logs --json`（默认最近 7 天，包含这段时间内的所有发布版本）与 `gamefy health --json`。
<!-- gamefy:end -->
