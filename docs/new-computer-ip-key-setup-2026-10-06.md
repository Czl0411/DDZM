# 换电脑拉取项目：IP、密钥与运行配置说明

更新时间：2026-10-06。本文面向从 GitHub 拉取当前功能分支、在另一台电脑继续开发或搭建新环境的使用者。所有密钥均使用占位符，不包含生产真实凭据。

## 1. 先决定新电脑用来做什么

| 使用方式 | IP 怎么处理 | 密钥怎么处理 | 是否迁移数据库 |
| --- | --- | --- | --- |
| 新电脑只写代码，仍部署到现服务器 | 保留 `43.153.194.94` | 使用获授权的 SSH 登录凭据；生产环境文件仍留服务器 | 不需要 |
| 新电脑运行独立开发环境 | Core、管理端和本地数据库用 `127.0.0.1` | 为本地环境新建 Core、Admin、Integration Token；按需配置自己的平台与 AI Key | 新建测试库，或恢复经过处理的测试备份 |
| 完整机器人迁到新 Ubuntu 服务器 | SSH、域名、外部 API 地址改为新服务器；同机服务间保留 `127.0.0.1` | 配置新服务器环境文件，按计划保留或轮换授权凭据并同步调用方 | 要保留员工、余额、称号等业务数据时必须迁移 |

**仅换开发电脑，不需要更换生产服务器 IP，也不需要把生产密钥复制到本地。** 新环境建议使用独立测试数据库、测试群和机器人账号。

现服务器：`ubuntu@43.153.194.94`，SSH 端口 22。`43.134.78.52` 已废弃，不要使用。

## 2. 从 GitHub 获取正确版本

当前功能分支在你的仓库，使用以下命令。GitHub CLI 或 Git 的身份验证由新电脑自行完成：

```bash
git clone --branch nuo/feature-test --single-branch https://github.com/niuerhaizaishan/DDZM.git
cd DDZM
git branch --show-current
git log -1 --oneline
```

已向原仓库 `Czl0411/DDZM` 提交 [PR #4](https://github.com/Czl0411/DDZM/pull/4)。在确认 PR 已合并前，不要假设原仓库 `main` 包含此分支更新。本文依据功能提交 `5c66d7f` 的代码整理；后续更新以实际拉取版本为准。

GitHub 只提供代码、迁移、测试、模板和文档，不包含以下内容：

- 服务器 `/etc/dzmm/dzmm.env` 中的真实凭据。
- PostgreSQL 内的员工、余额、流水、群配置、商品及称号记录。
- 浏览器 Profile、平台登录 Cookie 和会话。
- 新电脑的 SSH 登录密钥、Python 虚拟环境及本地配置。
- 本地 `tmp_deploy_staging/` 中的历史备份、模拟数据和发布包。

因此，拉取代码不会自动恢复生产数据，也不会自动取得平台登录状态。

## 3. 哪些地址需要修改

| 地址或配置 | 用途 | 处理方式 |
| --- | --- | --- |
| `ubuntu@43.153.194.94:22` | 现服务器 SSH | 继续用现服务器时不变；迁服时替换用户名、IP 和端口 |
| `127.0.0.1:18120` | Core 内部 API | 表示服务所在机器自身；Core 与 Worker、管理端同机时保留 |
| `127.0.0.1:18090` | 管理端、本机集成接口 | 新电脑本地启动时直接使用；访问远程服务时改为服务器地址或授权域名 |
| `127.0.0.1:19222` | Chromium CDP | 同机浏览器控制地址，通常不改，也不作为公网 API 使用 |
| `127.0.0.1:16080` | 登录控制台代理 | Linux 登录桌面使用，通常不改 |
| `DZMM_DATABASE_URL` | 数据库主机、端口、库名、账号密码 | 改为新环境数据库；本地库通常为 `127.0.0.1:5432` |
| `DZMM_LOGIN_URL` | 平台登录网页 | 使用实际平台登录地址，不是部署服务器 IP |
| `DZMM_CHAT_URL` | 平台聊天入口与主群初始化 | 使用自己的目标群链接；测试环境使用测试群 |
| `DZMM_DEEPSEEK_BASE_URL` | AI 服务入口 | 默认 `https://api.deepseek.com`；仅使用其他兼容入口时修改 |
| `DZMM_BROWSER_PROFILE` | 浏览器数据目录 | 换成新机器的绝对路径，并确保运行账号可读写 |

管理端和 Worker 当前通过 `http://127.0.0.1:{DZMM_CORE_API_PORT}` 连接 Core，不能只填一个“远程 Core IP”就把它们拆到不同机器。本文按服务同机运行说明。

### 仓库中与现 IP 有关的位置

- `.trae/documents/integration-api.md`：API 基地址及调用示例有 `43.153.194.94:18090`；迁服后调用方改成新的授权入口。
- `docs/superpowers/plans/2026-08-06-random-event-templates-and-details.md`：SSH 部署和状态检查示例。
- `docs/branch-update-nuo-feature-test-2026-10-06.md` 第 14.2 节：当前环境记录。
- `.trae/documents/branch-summary-nuo-feature-test.md`、`department-allowance.md`、`liar-dice-port.md`：历史部署说明。
- 你在新电脑实际执行的 `ssh`、`scp`、外部 API 请求，以及仓库外的 DNS、反向代理和防火墙配置。

历史记录中的 IP 不影响程序启动；真正决定连接目标的是当前执行命令、环境变量和调用方配置。不要把所有 `127.0.0.1` 全局替换成公网 IP。

## 4. 所有 Key、Token 的用途与来源

| 配置项 | 用途 | 如何获得 | 是否必须 |
| --- | --- | --- | --- |
| `DZMM_DATABASE_URL` | PostgreSQL 连接串，含数据库密码 | 创建或获得新环境数据库账号 | Core、管理端及迁移必须 |
| `DZMM_CORE_TOKEN` | 管理端、Worker 调用 Core 的内部凭据 | 自己生成随机值，同一套环境各服务使用相同值 | 必须 |
| `DZMM_ADMIN_TOKEN` | 管理后台凭据 | 自己生成独立随机值 | 启动管理端必须 |
| `DZMM_INTEGRATION_API_KEY` | 新增 `/api/integration` 接口的 `X-Api-Key` | 自己生成独立随机值，并交给授权调用方 | 集成接口启用时必须 |
| `DZMM_BOT_API_TOKEN` | 平台官方 Bot 发消息 | 从实际平台的 Bot 管理入口获取 | 可选，启用 Bot 发送时需要 |
| `DZMM_BOT_ID` | 平台官方 Bot 身份 ID | 从平台获取，与 Bot Token 对应 | 使用后台“添加长消息 Bot”时需要 |
| `DP_API_KEY` | DeepSeek AI 调用 | 从 DeepSeek 或所用兼容服务的账号取得 | AI Worker、记忆 Worker 必须；部分生成文案也使用它 |
| SSH 私钥或其他授权登录方式 | 新电脑连接服务器 | 为新电脑配置获授权的 SSH 登录方式 | 需要远程部署时使用 |

注意：`DP_API_KEY` 名称以实际代码为准，不是 `DZMM_DEEPSEEK_API_KEY`。官方 Bot Token、AI Key 由对应平台签发，不能用本地随机生成值代替。

普通账号的网页 Access Token 和 Cookie 由浏览器登录流程取得，不能拿来代替以上三类自建 Token。它们不是需要手工长期填入环境文件的固定 Key。

### 自建 Token 怎么生成

Linux / Ubuntu：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Windows PowerShell：

```powershell
py -3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

每运行一次得到一个新的 32 字节随机值，URL-safe 编码通常为 43 个字符。为 Core、Admin、Integration 分别运行一次，三个值不要相同。不要使用 `CHANGE_ME`、示例字符串或旧历史中的密钥。

生成命令会显示新值，保存到受限配置或密钥管理工具，不粘贴进文档、PR 或公开日志。当前集成 API 是一个共享 Key，没有自动过期、刷新接口、JWT 或每调用方独立 Key 管理。

此前硬编码集成 Key 已从本次推送历史清理，但删除历史不会让运行中的旧 Key 失效。之前仅完成代码与历史清理，没有实际轮换生产 Key；若尚未另行轮换，应同步服务器和所有调用方停用旧值。

## 5. 环境文件模板

仓库模板是 `deploy/env/dzmm.example.env`，目前没有列出集成 Key 和全部端口项。下面补齐常用项目，仅供填写，不能直接以占位符启动：

```dotenv
DZMM_DATABASE_URL='postgresql+psycopg://dzmm:<URL编码后的数据库密码>@127.0.0.1:5432/dzmm'
DZMM_CORE_TOKEN='<独立随机CoreToken>'
DZMM_ADMIN_TOKEN='<独立随机AdminToken>'
DZMM_INTEGRATION_API_KEY='<独立随机IntegrationToken>'

DZMM_BROWSER_PROFILE='/var/lib/dzmm-browser/profile'
DZMM_LOGIN_URL='<实际平台登录URL>'
DZMM_CHAT_URL='<实际测试群或正式群URL>'

DZMM_CORE_API_PORT=18120
DZMM_ADMIN_WEB_PORT=18090
DZMM_BROWSER_CDP_PORT=19222
DZMM_NOVNC_PORT=16080
DZMM_OUTBOUND_CONCURRENCY=4

DZMM_BOT_API_TOKEN=''
DZMM_BOT_ID=''
DP_API_KEY=''
DZMM_DEEPSEEK_MODEL='deepseek-v4-flash'
DZMM_DEEPSEEK_BASE_URL='https://api.deepseek.com'
```

数据库密码包含 `@`、`:`、`/`、`#`、`%` 等字符时，连接串中的密码需 URL 编码；给整条连接串加引号只解决 Shell 解析，不代替 URL 编码。

不用集成接口时删除 `DZMM_INTEGRATION_API_KEY` 整行，不要赋空字符串：当前该变量“缺省”表示未启用，“已设置但为空”会导致配置加载失败。Bot 与 AI 的空值则会按未配置处理；未配置 `DP_API_KEY` 时不要启动两种 AI Worker。

程序读取的是进程环境变量，**不会自动加载仓库里的 `.env`**。Linux systemd 会读取指定环境文件；手工启动需先加载；Windows 按下文导入到当前 PowerShell。

### Linux 保存位置

```bash
sudo install -d -m 700 -o root -g root /etc/dzmm
sudoedit /etc/dzmm/dzmm.env
sudo chown root:root /etc/dzmm/dzmm.env
sudo chmod 600 /etc/dzmm/dzmm.env
```

将填好的真实配置保存到该文件，同名变量保留一项。五个 systemd 服务均从此处读取。手工迁移或验收需以 `sudo bash` 整体执行，在其中 `source` 文件。

### Windows 保存位置

推荐使用仓库外的 `%USERPROFILE%\.dzmm\dzmm.env`，只允许自己的账户及必要管理员读取。将 Profile 改为本机绝对路径，例如 `C:/DZMMBot/browser_profile`；该路径只是示例。

```powershell
$dzmmConfigDirectory = Join-Path $env:USERPROFILE '.dzmm'
New-Item -ItemType Directory -Force -Path $dzmmConfigDirectory | Out-Null
notepad (Join-Path $dzmmConfigDirectory 'dzmm.env')
```

填好配置后，每个准备启动服务的 PowerShell 窗口先执行以下导入。仅支持模板使用的单行 `名称=值`，去除首尾成对引号，不执行配置中的代码，也不打印真实值：

```powershell
$dzmmConfigPath = Join-Path $env:USERPROFILE '.dzmm\dzmm.env'
foreach ($dzmmLine in Get-Content -LiteralPath $dzmmConfigPath -Encoding UTF8) {
    $dzmmLine = $dzmmLine.Trim()
    if (-not $dzmmLine -or $dzmmLine.StartsWith('#')) { continue }
    if ($dzmmLine -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        throw '环境文件格式错误，请检查名称=值格式。'
    }
    $dzmmName = $Matches[1]
    $dzmmValue = $Matches[2].Trim()
    if ($dzmmValue.Length -ge 2 -and (
        ($dzmmValue.StartsWith("'") -and $dzmmValue.EndsWith("'")) -or
        ($dzmmValue.StartsWith('"') -and $dzmmValue.EndsWith('"'))
    )) {
        $dzmmValue = $dzmmValue.Substring(1, $dzmmValue.Length - 2)
    }
    if ($dzmmValue.Length -eq 0) {
        Remove-Item -LiteralPath "Env:$dzmmName" -ErrorAction SilentlyContinue
    } else {
        Set-Item -LiteralPath "Env:$dzmmName" -Value $dzmmValue
    }
}
```

导入仅作用于当前窗口及之后启动的子进程。新的窗口要再次导入，已启动服务要重启才能读到新值。若从文件删除某变量，当前窗口原有的同名环境变量不会自动消失，需要手动移除或换新窗口。

不要把真实配置写入 `deploy/env/dzmm.example.env`。当前 `.gitignore` 没有通用 `.env` 忽略项，因此不能仅凭文件名判断安全；使用仓库外路径最直接。

## 6. 新电脑最小本地开发流程（Windows）

需要 Git、Python 3.12 或更新版本、可用 PostgreSQL。项目生产迁移使用 PostgreSQL JSONB 等能力，不要用 SQLite 替代完整迁移。准备一个自己的开发数据库，并将连接串填入本地配置。

在仓库目录执行：

```powershell
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e '.[test]'
& .\.venv\Scripts\python.exe -m pip install tzdata
```

Windows 通常需要额外的 `tzdata` 来支持代码中的 `ZoneInfo('Asia/Shanghai')`。每个服务窗口先按第 5 节加载环境变量，再执行对应命令：

```powershell
& .\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
& .\.venv\Scripts\python.exe -m alembic -c alembic.ini current
```

迁移作用于 `DZMM_DATABASE_URL` 指向的数据库，运行前确认它是开发库。本文版本最终 revision 为 `20261006_100`，后续以拉取版本的 `head` 为准。

终端一启动 Core：

```powershell
& .\.venv\Scripts\python.exe -m uvicorn dzmm_bot.core.app:create_app_from_environment --factory --host 127.0.0.1 --port 18120
```

终端二启动管理端：

```powershell
& .\.venv\Scripts\python.exe -m uvicorn dzmm_bot.admin.app:create_app_from_environment --factory --host 127.0.0.1 --port 18090
```

访问 `http://127.0.0.1:18090`，使用本地配置的 `DZMM_ADMIN_TOKEN`。若修改端口，应同步环境变量和上述启动参数；Linux systemd 的端口也固定写在服务文件中，不能只修改环境变量。

**Windows 此流程用于 Core 与后台开发，不等于完整机器人运行验收。** Browser Worker 当前依赖 Linux 浏览器路径、`os.getpgid`、Xvfb、noVNC 等机制；完整收发与登录桌面建议在 Ubuntu 或 WSL2 的 Linux 环境运行，WSL2 的 systemd、显示依赖和服务安装仍需单独配置。

只启动 Core 和后台时，Worker 离线、AI 无心跳、登录控制台不可用属于预期情况。空数据库还需要完成管理员验证、员工及群初始化等业务配置；只出现页面或健康检查通过不代表群聊功能就绪。

## 7. 仍部署到现服务器：新电脑需要什么

保留现服务器配置即可；新电脑只需项目代码、GitHub 身份验证和获授权的 SSH 登录方式。先验证连接：

```bash
ssh -p 22 ubuntu@43.153.194.94
```

如果使用指定私钥，在自己的 SSH 命令或 SSH 配置里指定；不要把私钥复制到项目目录。若新电脑用新公钥，需要有权限的维护人在服务器授权，克隆项目不会自动授予 SSH 权限。

生产 `/etc/dzmm/dzmm.env` 继续留在服务器，部署脚本在服务器整体通过 `sudo bash` 执行。新电脑仅开发代码时，不要以生产连接串启动本地 Core、迁移或数据库脚本。

## 8. 如需完整迁到新 Ubuntu 服务器

迁移顺序：准备 Linux 运行环境 → 备份旧环境 → 配置新数据库和凭据 → 安装服务与代码 → 恢复业务数据并迁移 → 平台重新登录 → 验收 → 切换调用方和监听。

- Python 版本需满足 `>=3.12`；安装 PostgreSQL、rsync、Python venv、Chromium 的系统依赖及登录桌面依赖。`deploy/scripts/provision.sh` 不安装 PostgreSQL，也不代替全部依赖和数据库准备。
- 使用 `sudo bash deploy/scripts/provision.sh --apply` 建立服务账号与基础目录；按第 5 节建立 `/etc/dzmm/dzmm.env`。
- 源码运行目录为 `/opt/dzmm/current`，虚拟环境为 `/opt/dzmm/venv`，浏览器 Profile 目录由环境文件指定，并由 `dzmm` 用户读写。
- 标准发布命令为 `sudo bash /path/to/release/deploy/scripts/deploy.sh /path/to/release`，其中 release 是含 `pyproject.toml` 的独立发布目录；不要把它误写为不存在的目录。
- 发布脚本会执行数据库迁移并启动五个服务。完整发布前准备有效的 `DP_API_KEY`，否则 AI 和记忆 Worker 会退出；测试阶段仅运行必要服务时需另行安排启动范围。
- 保留业务数据必须安全导出与恢复 PostgreSQL；群列表、商品、配置、称号和余额在数据库中，不是只迁移源码。
- 新浏览器 Profile 建议人工重新登录专用平台账号，核对目标群、Bot 加群权限及可访问私聊。不要把旧 Profile 提交进 Git。
- 正式切换前暂停旧实例监听，避免两套机器人同时消费同一正式群消息。恢复的数据库可能包含待发任务，应先核对队列和测试群，避免旧消息重放。
- 更新外部 API 调用方、域名和代理。代码里同机 Core、CDP 和登录代理的回环地址保持不变。

服务清单及配置变化后的重启范围：

| 变更 | 应处理的服务或调用方 |
| --- | --- |
| `DZMM_INTEGRATION_API_KEY` | 重启 `dzmm-admin-web`，同步所有外部调用方 |
| `DZMM_ADMIN_TOKEN` | 重启 `dzmm-admin-web`，更新管理员使用的凭据 |
| `DZMM_CORE_TOKEN` | Core、管理端和三个 Worker 保持一致；先 Core 健康，再恢复管理端及 Worker |
| 数据库连接串 | 重启 Core、管理端；整体环境迁移时检查全部服务 |
| `DP_API_KEY`、AI 模型或入口 | 重启 `dzmm-ai-worker`、`dzmm-ai-memory-worker`，以及使用生成文案客户端的 `dzmm-core` |
| Bot Token、Bot ID、登录 URL、Profile | 重启 `dzmm-browser-worker`；Bot 发送配置变化也核对 Core 的长消息保留行为 |

单独重启 Core 后，等待健康，再恢复三个 Worker：

```bash
sudo systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker
sudo systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker
```

这两个命令用于 Core 已健康后的恢复，不替代先停止并重启服务以加载新环境变量。

## 9. 新增集成 API 的使用与验收

API 基路径为管理端的 `/api/integration`，不是 Core 的公网接口。调用方使用受限配置中的集成 Key，通过请求头传入：

```http
X-Api-Key: <DZMM_INTEGRATION_API_KEY的真实值>
```

本机基地址：`http://127.0.0.1:18090/api/integration`。远程调用使用实际授权的 HTTPS 入口；Token 不放进 URL、浏览器前端代码或仓库。

| HTTP 状态 | 含义 |
| --- | --- |
| 200 | 请求成功；只读余额查询需要真实有效员工平台 ID |
| 401 | 未带 Key 或 Key 错误 |
| 404 | 对应员工不存在等资源未找到 |
| 429 | 超过当前进程每分钟 60 次集成调用限制 |
| 503 | 未配置集成 Key，或接口依赖暂时不可用，结合响应内容排查 |

只读验收方法见 [PR 说明的 API Token 章节](pr-description-nuo-feature-test-2026-10-06.md)。如果该说明文件不在你的克隆版本中，也可在 [PR #4](https://github.com/Czl0411/DDZM/pull/4) 正文查看。`scripts/smoke_integration_api.sh` 包含真实发扣币操作，不把它当只读连通检查。

轮换 Key：重新生成 → 更新服务环境文件 → 重启管理端 → 同步全部调用方。当前只有一个共享 Key，没有新旧 Key 并存过渡期；重启生效后旧值立即失效。

## 10. 不要直接照搬的文件和数据

| 项目 | 新环境需要核对 |
| --- | --- |
| `config.example.json` | 是 `dzmm-read` 只读工具的配置模板，不代替正式服务环境变量；如使用，复制为已忽略的 `config.local.json` 并填自己的群 URL、Profile |
| `scripts/smoke_game_quota.sh` | 使用了特定员工平台 ID，需要改成测试员工 |
| `scripts/set_nuonuo_heat.sh` | 使用了特定员工和群 ID，并修改发情值 |
| `scripts/set_persona_gender.sh` | 面向特定人员修改档案数据，执行前核对目标 |
| `scripts/clear_xiaoxiaonuo_allowance.sh` | 会删除特定员工津贴记录，不是初始化步骤 |
| `src/dzmm_bot/core/repository.py` 的 `_CHOP_BOT_ACCOUNT_NAMES` | 指定机器人昵称保护规则，换机器人账号时核对 |
| 数据库中的群 ID、管理员、统计群与公告群 | 全部按新环境实际账号和群配置 |
| 浏览器 Profile、Cookie、SSH 私钥、真实环境文件 | 不随源码提交或上传 GitHub |

`dzmm-read` 是独立的读取工具，不是启动五个生产服务的命令。Windows 跑完整 Browser Worker 的限制也不会因填写 `config.local.json` 而消失。

## 11. 常见问题速查

| 问题 | 首先检查 |
| --- | --- |
| 提示 `DZMM_DATABASE_URL` 或 `DZMM_CORE_TOKEN` 未设置 | 是否在启动服务的同一终端加载环境变量 |
| 管理端提示 `DZMM_ADMIN_TOKEN` 未设置 | 是否配置管理 Token，重新加载并重启 |
| 集成 API 提示 disabled / 503 | 是否补充了模板未列出的 `DZMM_INTEGRATION_API_KEY` 并重启管理端 |
| 内部 API 或集成 API 返回 401 | 是否混用 Core、Admin、Integration Token，或者调用方仍使用旧 Key |
| 数据库连接失败 | 是否连接正确主机，账号与密码是否正确，密码是否 URL 编码 |
| 新电脑页面有了，员工和称号没了 | 是否只克隆代码却没有迁移数据库 |
| Worker 在 Windows 启动报系统属性或浏览器路径错误 | 使用 Linux / WSL2 完整环境，Windows 本地只先运行 Core 与管理端 |
| Core 健康但部分业务不可用 | 是否完成群和员工初始化、管理员验证，Worker 是否在线 |
| 群里重复回复 | 是否新旧两个实例同时监听正式群 |
| 只改配置文件却没有生效 | 进程是否重新加载环境并重启；已运行进程不会自动读取文件 |

建议默认采用“新电脑独立开发库 + 测试群，生产服务器保持现状”的方式；需要正式迁服时，再单独迁移数据、账号登录态和调用方配置。
