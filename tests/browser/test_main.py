from pathlib import Path


def test_playwright_chromium_executable_uses_the_installed_browser_cache(
    monkeypatch, tmp_path
):
    from dzmm_bot.browser import main

    executable = (
        tmp_path
        / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
    )
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(main.Path, "home", lambda: tmp_path)

    assert main._playwright_chromium_executable() == str(executable)
