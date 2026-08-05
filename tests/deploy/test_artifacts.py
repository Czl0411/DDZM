from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_systemd_units_use_environment_factories_and_isolated_ports():
    core = (ROOT / "deploy/systemd/dzmm-core.service").read_text()
    admin = (ROOT / "deploy/systemd/dzmm-admin-web.service").read_text()
    worker = (ROOT / "deploy/systemd/dzmm-browser-worker.service").read_text()

    assert "dzmm_bot.core.app:create_app_from_environment --factory" in core
    assert "--host 127.0.0.1 --port 18120" in core
    assert "dzmm_bot.admin.app:create_app_from_environment --factory" in admin
    assert "--host 0.0.0.0 --port 18090" in admin
    assert "-m dzmm_bot.browser.main" in worker
    assert "9222" not in core + admin + worker


def test_deployment_runs_migrations_with_the_private_environment():
    deploy = (ROOT / "deploy/scripts/deploy.sh").read_text()
    migration_env = (ROOT / "migrations/env.py").read_text()

    assert "source /etc/dzmm/dzmm.env" in deploy
    assert "cd /opt/dzmm/current" in deploy
    assert "alembic -c /opt/dzmm/current/alembic.ini upgrade head" in deploy
    assert 'os.environ.get("DZMM_DATABASE_URL")' in migration_env
    assert 'usage: deploy.sh RELEASE_DIRECTORY' in deploy
    assert 'rsync -a --delete --exclude .git --exclude .venv "$dzmm_release_dir/"' in deploy
    assert "chown -R dzmm:dzmm /opt/dzmm/current" in deploy
    assert "runuser -u dzmm -- /opt/dzmm/venv/bin/playwright install chromium" in deploy
