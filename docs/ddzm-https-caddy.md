# DDZM：Caddy 与自动 HTTPS

## 当前部署

部署日期：2026-10-15（北京时间）。

- HTTPS 后台入口：[https://43.153.194.94/](https://43.153.194.94/)。
- `http://43.153.194.94/` 自动以 308 跳转到 HTTPS。
- Caddy `2.11.7` 转发到现有 `127.0.0.1:18090`，支持 WebSocket。
- 证书由 Let's Encrypt 的 `shortlived` ACME profile 签发，是浏览器可信的公网 IP 证书，SAN 为 `43.153.194.94`。没有使用自签名证书。
- IP 证书有效期约 160 小时，由 Caddy 持续管理与自动续期，无需额外定时脚本。自动续期已启用，尚未跨完整续期周期观察。
- 首张证书到期时间：2026-10-22 08:43:50（北京时间）。这只是初始部署记录，实际到期时间会随续期变化。

本次增加代理和 TLS 入口，没有更新 DDZM 的应用代码、执行数据库迁移或重启原有五个应用服务。

## 配置文件

仓库中的文件：

| 文件 | 用途 |
| --- | --- |
| `deploy/caddy/Caddyfile` | 站点、ACME profile 与反向代理 |
| `deploy/caddy/caddy.service` | 独立 caddy 用户运行的 systemd 服务 |
| `deploy/scripts/deploy_caddy_https.sh` | 校验官方二进制哈希、备份、安装、配置校验与启用 |

服务器上的文件：

| 路径 | 用途 |
| --- | --- |
| `/usr/local/bin/caddy` | 固定版本官方 Linux amd64 二进制 |
| `/etc/caddy/Caddyfile` | 生效配置；root 所有，caddy 组可读 |
| `/etc/systemd/system/caddy.service` | 服务定义，已启用开机启动 |
| `/var/lib/caddy/` | 持久化证书、ACME 账号和自动续期状态；归 caddy 用户管理 |
| `/opt/dzmm/https-deploy/deploy/` | 本次部署脚本和配置副本 |
| `/var/backups/dzmm-https/20261015T094214Z/` | 部署前配置与 UFW 状态备份 |

配置中的 `default_sni 43.153.194.94` 用来支持通过 IP 访问、不发送 SNI 的客户端，并适配云服务器公网 IP 到内网 IP 的映射。缺少它时，即使证书签发成功，也可能在 TLS 握手时找不到正确证书。

Caddy 不读取 `/etc/dzmm/dzmm.env`，也不需要任何 DDZM 管理密钥、Bot token、开发者密钥或数据库凭证。不要把这些配置复制到 Caddyfile。

## 网络要求

服务器 UFW 已放行 TCP 80、443。用户已在腾讯云控制台放行公网 443，随后公网验证通过。

- TCP 443：HTTPS 访问。
- TCP 80：自动跳转及 HTTP-01 证书验证。需要持续保留，供后续续期使用。
- 如果迁移到新实例，同时核对腾讯云安全组或轻量服务器防火墙；只修改服务器 UFW 不足以让公网访问。

原 `http://43.153.194.94:18090` 入口仍可使用，未自动关闭，以免影响已有调用方。迁移调用方到 HTTPS 后，可另行收紧此端口。Core 的 18120 端口和 Caddy 的 2019 管理端口仍仅本机监听。

## 运维

所有服务器变更命令整体通过 `sudo bash` 执行。例如检查配置并平滑加载：

```bash
sudo bash -c 'set -e; /usr/local/bin/caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; systemctl reload caddy'
```

查看状态和日志：

```bash
sudo bash -c 'systemctl status caddy --no-pager; journalctl -u caddy -n 60 --no-pager'
```

不要删除 `/var/lib/caddy`，其中包含续期必需的私钥和 ACME 账号；备份应按私密凭证处理，不进入仓库。服务以 caddy 用户运行，数据目录权限为 0750。

二进制版本固定为 `2.11.7`，下载来源为 Caddy 官方 GitHub Release，归档 SHA-256 已校验。更新 Caddy 本身时需要同步更新部署脚本的版本和官方发布哈希；证书续期不依赖重新运行部署脚本。

如需撤销新增 HTTPS 入口，可停止并禁用 Caddy，原 18090 服务继续运行：

```bash
sudo bash -c 'systemctl disable --now caddy'
```

如需恢复被覆盖的旧文件，先检查上述备份目录中的实际文件；本次服务器此前没有安装 Caddy。不要将旧防火墙备份整份恢复而覆盖后续新增规则。

## 已验证内容

- Caddy 配置验证成功，服务处于 active，开机启动已启用。
- Let's Encrypt 已完成 HTTP-01 验证并签发公网 IP 证书。
- 本机 Python 使用系统信任库完成公网 HTTPS 校验，返回 HTTP 200。
- 实际浏览器打开 HTTPS 后台，正常显示登录页，没有证书警告。
- HTTP 80 返回 308，并跳转到相同 IP 的 HTTPS 地址。
- 未登录访问 `/api/status` 返回 401；`/internal/status` 返回 404，未将 core 内部路由转发到公网。
- `dzmm-core`、`dzmm-admin-web`、`dzmm-browser-worker`、`dzmm-ai-worker`、`dzmm-ai-memory-worker` 均为 active。

## 与工位 Gamefy 接入的关系

现在已有可用的 HTTPS 服务器基址 `https://43.153.194.94`，不再需要为这一步单独准备域名。

仅增加 Caddy 不会使工位功能自动上线。2026-10-15 后续已单独部署装备商城、工位网页和 Gamefy JWT 接口，执行 `20261015_104` 迁移，并将草稿的数据地址设置为此 HTTPS 基址。应用部署及平台联调记录见 [工位 Gamefy 发布说明](gamefy-workstation-publishing.md)。游戏发布和上架仍为后续独立步骤。

## 官方依据

- [Caddy TLS issuer 与 ACME profile](https://caddyserver.com/docs/caddyfile/directives/tls)
- [Caddy default_sni](https://caddyserver.com/docs/caddyfile/options#default-sni)
- [Let's Encrypt 公网 IP 与短期证书正式可用](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/)
