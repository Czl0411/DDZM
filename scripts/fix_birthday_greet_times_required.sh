#!/bin/bash
# 修复：后台保存生日祝福一直 422 —— admin required 清单仍是旧字段 greet_time，
# 而 greet_times 改版（迁移 89/一天三次广播）后未同步。仅替换 admin/app.py。
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current
cp /tmp/admin_app.py "$VENV/admin/app.py"
cp /tmp/admin_app.py "$CUR/src/dzmm_bot/admin/app.py"
systemctl restart dzmm-admin-web
sleep 2
systemctl is-active dzmm-core dzmm-admin-web
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
