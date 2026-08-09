import json

import httpx
import pytest


def test_deepseek_client_sends_official_thinking_request():
    from dzmm_bot.ai.client import DeepSeekChatClient

    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": " 收到 ",
                            "reasoning_content": "不得发送的思考",
                        }
                    }
                ],
                "usage": {
                    "prompt_cache_hit_tokens": 10,
                    "prompt_cache_miss_tokens": 2,
                },
            },
        )

    client = DeepSeekChatClient(
        "secret",
        "deepseek-v4-flash",
        client=httpx.Client(
            base_url="https://api.deepseek.com",
            transport=httpx.MockTransport(handle),
        ),
    )

    assert client.complete("system", "user", max_chars=20, timeout_seconds=10) == "收到"
    assert requests[0].url.path == "/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert json.loads(requests[0].content) == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "thinking": {"type": "enabled"},
        "max_tokens": 20,
    }


def test_deepseek_client_rejects_an_empty_model_response():
    from dzmm_bot.ai.client import DeepSeekCallError, DeepSeekChatClient

    client = DeepSeekChatClient(
        "secret",
        "deepseek-v4-flash",
        client=httpx.Client(
            base_url="https://api.deepseek.com",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": []})
            ),
        ),
    )

    with pytest.raises(DeepSeekCallError, match="invalid_response") as captured:
        client.complete("system", "user", max_chars=20, timeout_seconds=10)

    assert captured.value.category == "invalid_response"
