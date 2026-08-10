from types import SimpleNamespace

import pytest


def test_ai_main_builds_the_deepseek_client(monkeypatch):
    import dzmm_bot.ai.main as module

    settings = SimpleNamespace(
        core_api_port=18120,
        core_token="core-token",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        deepseek_base_url="https://api.deepseek.com",
    )
    captured = {}

    class FakeDeepSeekClient:
        def __init__(self, api_key, model, *, base_url):
            captured["client"] = (api_key, model, base_url)

    class StopWorker:
        def __init__(self, worker_id, core, client):
            captured["worker_id"] = worker_id

        def run_once(self):
            raise StopIteration

    monkeypatch.setattr(
        module.Settings, "from_environment", staticmethod(lambda: settings)
    )
    monkeypatch.setattr(module, "DeepSeekChatClient", FakeDeepSeekClient)
    monkeypatch.setattr(module, "AICoreClient", lambda *args: object())
    monkeypatch.setattr(module, "AIWorker", StopWorker)

    with pytest.raises(StopIteration):
        module.main()

    assert captured == {
        "client": (
            "deepseek-secret",
            "deepseek-v4-flash",
            "https://api.deepseek.com",
        ),
        "worker_id": "ai-worker-1",
    }


def test_ai_main_requires_the_deepseek_key(monkeypatch):
    import dzmm_bot.ai.main as module

    settings = SimpleNamespace(deepseek_api_key=None)
    monkeypatch.setattr(
        module.Settings, "from_environment", staticmethod(lambda: settings)
    )

    with pytest.raises(ValueError, match="DP_API_KEY must be set and nonempty"):
        module.main()


def test_memory_main_builds_an_isolated_worker(monkeypatch):
    import dzmm_bot.ai.memory_main as module

    settings = SimpleNamespace(
        core_api_port=18120,
        core_token="core-token",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        deepseek_base_url="https://api.deepseek.com",
    )
    captured = {}

    class FakeDeepSeekClient:
        def __init__(self, api_key, model, *, base_url):
            captured["client"] = (api_key, model, base_url)

    class StopWorker:
        def __init__(self, worker_id, core, client):
            captured["worker_id"] = worker_id

        def run_once(self):
            raise StopIteration

    monkeypatch.setattr(
        module.Settings, "from_environment", staticmethod(lambda: settings)
    )
    monkeypatch.setattr(module, "DeepSeekChatClient", FakeDeepSeekClient)
    monkeypatch.setattr(module, "AICoreClient", lambda *args: object())
    monkeypatch.setattr(module, "AIMemoryWorker", StopWorker)

    with pytest.raises(StopIteration):
        module.main()

    assert captured == {
        "client": (
            "deepseek-secret",
            "deepseek-v4-flash",
            "https://api.deepseek.com",
        ),
        "worker_id": "ai-memory-worker-1",
    }
