import asyncio
import json
import signal

import pytest


class FakeProcess:
    def __init__(self, pid):
        self.pid = pid


class ProcessFactory:
    def __init__(self):
        self.calls = []

    async def __call__(self, *command, **kwargs):
        self.calls.append((command, kwargs))
        return FakeProcess(3000 + len(self.calls))


def make_controller(tmp_path, process_factory, **overrides):
    from dzmm_bot.auth_desktop import AuthDesktopController

    options = {
        "runtime_dir": tmp_path / "runtime",
        "profile_dir": tmp_path / "profile",
        "login_url": "https://chat.example/login",
        "login_state": lambda: "auth_required",
        "browser_stopped": lambda: True,
        "process_factory": process_factory,
        "getpgid": lambda pid: pid + 100,
        "killpg": lambda pgid, sig: None,
    }
    options.update(overrides)
    return AuthDesktopController(**options)


def test_start_requires_auth_required_and_stopped_browser(tmp_path):
    factory = ProcessFactory()
    wrong_state = make_controller(
        tmp_path, factory, login_state=lambda: "ready"
    )
    running_browser = make_controller(
        tmp_path, factory, browser_stopped=lambda: False
    )

    with pytest.raises(RuntimeError, match="auth_required"):
        wrong_state.start()
    with pytest.raises(RuntimeError, match="stopped"):
        running_browser.start()

    assert factory.calls == []


def test_start_spawns_isolated_desktop_and_loopback_novnc(tmp_path):
    factory = ProcessFactory()
    controller = make_controller(tmp_path, factory)

    controller.start()

    commands = [call[0] for call in factory.calls]
    assert [command[0] for command in commands] == [
        "Xvfb",
        "fluxbox",
        "google-chrome",
        "x11vnc",
        "websockify",
    ]
    assert all(call[1]["start_new_session"] is True for call in factory.calls)
    chrome = commands[2]
    assert f"--user-data-dir={tmp_path / 'profile'}" in chrome
    assert "https://chat.example/login" in chrome
    x11vnc = commands[3]
    assert "-localhost" in x11vnc
    novnc = commands[4]
    assert "127.0.0.1:16080" in novnc
    assert "127.0.0.1:15900" in novnc

    pid_data = json.loads((tmp_path / "runtime" / "auth-desktop.json").read_text())
    assert pid_data == {
        "process_groups": [3101, 3102, 3103, 3104, 3105],
        "pids": [3001, 3002, 3003, 3004, 3005],
    }


def test_stop_signals_only_recorded_process_groups_and_removes_pid_file(tmp_path):
    factory = ProcessFactory()
    signals = []
    controller = make_controller(
        tmp_path,
        factory,
        killpg=lambda pgid, sig: signals.append((pgid, sig)),
        login_state=lambda: "auth_in_progress",
    )
    pid_file = tmp_path / "runtime" / "auth-desktop.json"
    pid_file.parent.mkdir()
    pid_file.write_text(
        json.dumps({"pids": [10, 20], "process_groups": [110, 120]})
    )

    controller.stop()

    assert signals == [(120, signal.SIGTERM), (110, signal.SIGTERM)]
    assert not pid_file.exists()
    assert factory.calls == []


def test_start_rejects_an_existing_desktop_pid_file(tmp_path):
    factory = ProcessFactory()
    controller = make_controller(tmp_path, factory)
    pid_file = tmp_path / "runtime" / "auth-desktop.json"
    pid_file.parent.mkdir()
    pid_file.write_text(json.dumps({"pids": [10], "process_groups": [110]}))

    with pytest.raises(RuntimeError, match="already active"):
        controller.start()

    assert factory.calls == []


def test_controller_exposes_one_asyncio_lock_for_lifecycle(tmp_path):
    factory = ProcessFactory()
    controller = make_controller(tmp_path, factory)

    assert isinstance(controller.lock, asyncio.Lock)


def test_controller_satisfies_the_browser_workers_synchronous_desktop_port(
    tmp_path,
):
    factory = ProcessFactory()
    controller = make_controller(tmp_path, factory)

    result = controller.start()

    assert result is None
    assert len(factory.calls) == 5
