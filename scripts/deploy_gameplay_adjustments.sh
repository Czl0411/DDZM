#!/bin/bash
# 部署：玩法调整 —— 凿次数跨群合并 / 每日人气榜带总计 / 部门变更 24h CD（迁移 100）
# /我 未设置生日性别不显示 / 小游戏参与奖文案明确
# scp 清单与 cp 一一对应（勿删改，核对用）：
#   core_schema.py core_repository.py core_commands.py mig_100.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_schema.py     "$VENV/core/schema.py"
cp /tmp/core_repository.py "$VENV/core/repository.py"
cp /tmp/core_commands.py   "$VENV/core/commands.py"

cp /tmp/core_schema.py     "$CUR/src/dzmm_bot/core/schema.py"
cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"
cp /tmp/core_commands.py   "$CUR/src/dzmm_bot/core/commands.py"
cp /tmp/mig_100.py         "$CUR/migrations/versions/20261010_100_department_change_cooldown.py"

systemctl stop dzmm-core
set -a
source /etc/dzmm/dzmm.env
set +a
cd /opt/dzmm/current && /opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini upgrade head
systemctl start dzmm-core
sleep 3
systemctl restart dzmm-admin-web
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
/opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini current
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
