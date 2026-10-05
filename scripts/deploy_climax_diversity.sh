#!/bin/bash
# 部署：高潮文案去重 —— 素材抽样+禁原句、风格随机化、temperature 1.3、AI失败日志、
# 兜底库扩容（每槽位 3-4 句 → 8 句）。无迁移。
# scp 清单与 cp 一一对应（勿删改，核对用）：core_estrus.py ai_client.py core_repository.py
set -e
VENV=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
CUR=/opt/dzmm/current

cp /tmp/core_estrus.py     "$VENV/core/estrus.py"
cp /tmp/ai_client.py       "$VENV/ai/client.py"
cp /tmp/core_repository.py "$VENV/core/repository.py"

cp /tmp/core_estrus.py     "$CUR/src/dzmm_bot/core/estrus.py"
cp /tmp/ai_client.py       "$CUR/src/dzmm_bot/ai/client.py"
cp /tmp/core_repository.py "$CUR/src/dzmm_bot/core/repository.py"

systemctl restart dzmm-core
sleep 3
systemctl reset-failed dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
systemctl start dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker 2>/dev/null || true
sleep 2
curl -sf http://127.0.0.1:18120/healthz && echo " core healthz OK"
systemctl list-units 'dzmm-*' --no-pager --plain | grep dzmm
