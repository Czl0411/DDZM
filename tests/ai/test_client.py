import json

import httpx


def test_minimax_client_sends_openai_compatible_request():
    from dzmm_bot.ai.client import MinimaxChatClient

    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": " 收到 "}}]},
        )

    client = MinimaxChatClient(
        "secret",
        "MiniMax-M2.5",
        client=httpx.Client(
            base_url="https://api.minimaxi.com/v1",
            transport=httpx.MockTransport(handle),
        ),
    )

    assert client.complete("system", "user", max_chars=20, timeout_seconds=10) == "收到"
    assert requests[0].url.path == "/v1/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert json.loads(requests[0].content)["reasoning_split"] is True


def test_minimax_client_rejects_an_empty_model_response():
    from dzmm_bot.ai.client import MinimaxCallError, MinimaxChatClient

    client = MinimaxChatClient(
        "secret",
        "MiniMax-M2.5",
        client=httpx.Client(
            base_url="https://api.minimaxi.com/v1",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": []})
            ),
        ),
    )

    try:
        client.complete("system", "user", max_chars=20, timeout_seconds=10)
    except MinimaxCallError as error:
        assert error.category == "invalid_response"
    else:
        raise AssertionError("expected an invalid model response to be rejected")
