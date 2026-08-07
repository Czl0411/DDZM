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
    assert "systemctl restart dzmm-core.service dzmm-admin-web.service dzmm-browser-worker.service" in deploy


def test_weekly_attendance_migration_preserves_custom_me_templates():
    migration = (ROOT / "migrations/versions/20260806_11_weekly_attendance.py").read_text()

    assert "weekly_attendance_settlements" in migration
    assert "连续打卡：{连续打卡天数} 天。" in migration


def test_hide_and_seek_migration_creates_game_tables():
    migration = (ROOT / "migrations/versions/20260806_13_hide_and_seek.py").read_text()

    assert 'down_revision: str | None = "20260806_12"' in migration
    assert "hide_and_seek_settings" in migration
    assert "hide_and_seek_scenes" in migration
    assert "hide_and_seek_daily_plays" in migration
    assert "hide_and_seek_games" in migration
    assert "ux_hide_and_seek_one_selecting_user" in migration


def test_hide_and_seek_command_migration_preserves_custom_templates():
    migration = (ROOT / "migrations/versions/20260806_14_hide_and_seek_commands.py").read_text()

    assert 'down_revision: str | None = "20260806_13"' in migration
    assert "old_started_template" in migration
    assert "old_found_template" in migration
    assert "/开始摸鱼躲藏" in migration


def test_hide_and_seek_penalty_timing_migration_preserves_custom_start_copy():
    migration = (ROOT / "migrations/versions/20260806_15_hide_and_seek_penalty_timing.py").read_text()

    assert 'down_revision: str | None = "20260806_14"' in migration
    assert "old_started_template" in migration
    assert "old_expired_template" in migration
    assert "开局不扣除" in migration


def test_hide_and_seek_two_round_patrol_migration_updates_default_templates_only():
    migration = (ROOT / "migrations/versions/20260806_16_hide_and_seek_two_round_patrol.py").read_text()

    assert 'down_revision: str | None = "20260806_15"' in migration
    assert "old_found_template" in migration
    assert 'new_found_template = "{巡查过程}' in migration


def test_ordered_multi_reply_migration_removes_single_reply_constraint():
    migration = (ROOT / "migrations/versions/20260806_17_ordered_multi_replies.py").read_text()

    assert 'down_revision: str | None = "20260806_16"' in migration
    assert "outbound_messages_inbound_message_id_key" in migration
    assert 'sa.Column("reply_index", sa.Integer()' in migration


def test_separate_patrol_template_migration_adds_first_round_scenarios():
    migration = (
        ROOT / "migrations/versions/20260806_18_hide_and_seek_patrol_reply_templates.py"
    ).read_text()

    assert 'down_revision: str | None = "20260806_17"' in migration
    assert '"first_round_missed"' in migration
    assert '"found_first_round"' in migration
    assert '"created_at"' in migration
    assert '"updated_at"' in migration


def test_memory_assessment_migration_creates_game_tables():
    migration = (ROOT / "migrations/versions/20260806_19_memory_assessment.py").read_text()

    assert 'down_revision: str | None = "20260806_18"' in migration
    assert "memory_assessment_settings" in migration
    assert "memory_assessment_level_rules" in migration
    assert "memory_assessment_daily_plays" in migration
    assert "memory_assessment_games" in migration
    assert "memory_assessment_participants" in migration
    assert "memory_assessment_rounds" in migration


def test_memory_assessment_recall_migration_links_rounds_to_outbound_messages():
    migration = (ROOT / "migrations/versions/20260806_20_memory_assessment_recall.py").read_text()

    assert 'down_revision: str | None = "20260806_19"' in migration
    assert '"count"' in migration
    assert "recall_after_seconds" in migration
    assert "outbound_message_id" in migration


def test_random_event_command_gate_migration_adds_safe_defaults():
    migration = (ROOT / "migrations/versions/20260807_21_random_event_command_gate.py").read_text()

    assert 'down_revision: str | None = "20260806_20"' in migration
    assert "signup_allowed_commands" in migration
    assert "in_progress_allowed_commands" in migration
    assert "blocked_message" in migration
