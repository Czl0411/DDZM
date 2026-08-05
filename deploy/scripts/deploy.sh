#!/usr/bin/env bash
set -euo pipefail
dzmm_release_dir=${1:-}
[ -n "$dzmm_release_dir" ] && [ -f "$dzmm_release_dir/pyproject.toml" ] || {
  echo 'usage: deploy.sh RELEASE_DIRECTORY' >&2
  exit 2
}
install -d -o dzmm -g dzmm /opt/dzmm/current
rsync -a --delete --exclude .git --exclude .venv "$dzmm_release_dir/" /opt/dzmm/current/
chown -R dzmm:dzmm /opt/dzmm/current
python3 -m venv /opt/dzmm/venv
/opt/dzmm/venv/bin/pip install --upgrade pip
/opt/dzmm/venv/bin/pip install /opt/dzmm/current
runuser -u dzmm -- /opt/dzmm/venv/bin/playwright install chromium
set -a
source /etc/dzmm/dzmm.env
set +a
cd /opt/dzmm/current
/opt/dzmm/venv/bin/alembic -c /opt/dzmm/current/alembic.ini upgrade head
install -m 644 /opt/dzmm/current/deploy/systemd/dzmm-*.service /etc/systemd/system/
systemctl daemon-reload
