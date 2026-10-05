#!/bin/bash
set -e
V=/opt/dzmm/venv/lib/python3.12/site-packages/dzmm_bot
C=/opt/dzmm/current/src/dzmm_bot
for f in schema.py repository.py commands.py api_models.py core_client.py; do
  sudo cp /tmp/$f "$V/core/$f" 2>/dev/null || true
done
# core_client.py 属于 admin
sudo cp /tmp/core_client.py "$V/admin/core_client.py"
sudo cp /tmp/core_client.py "$C/admin/core_client.py"
for f in schema.py repository.py commands.py api_models.py; do
  sudo cp /tmp/$f "$C/core/$f"
done
sudo cp /tmp/core_app.py "$V/core/app.py"
sudo cp /tmp/core_app.py "$C/core/app.py"
sudo cp /tmp/admin_app.py "$V/admin/app.py"
sudo cp /tmp/admin_app.py "$C/admin/app.py"
sudo cp /tmp/admin.js "$V/admin/static/admin.js"
sudo cp /tmp/admin.js "$C/admin/static/admin.js"
sudo cp /tmp/index.html "$V/admin/templates/index.html"
sudo cp /tmp/index.html "$C/admin/templates/index.html"
sudo cp /tmp/20261003_85_allowance_settings.py /opt/dzmm/current/migrations/versions/
set -a
source /etc/dzmm/dzmm.env
set +a
cd /opt/dzmm/current
/opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini upgrade head
/opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini current
sudo systemctl restart dzmm-core
sleep 3
for u in dzmm-admin-web dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker; do
  sudo systemctl reset-failed "$u" 2>/dev/null || true
  sudo systemctl start "$u"
done
sleep 6
for u in dzmm-core dzmm-admin-web dzmm-browser-worker dzmm-ai-worker dzmm-ai-memory-worker; do
  echo "$u: $(systemctl is-active $u)"
done
