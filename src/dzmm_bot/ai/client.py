import httpx


class MinimaxCallError(Exception):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class MinimaxChatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.minimax.io/v1",
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if client is not None:
            self._client.headers["Authorization"] = f"Bearer {api_key}"

    def complete(
        self,
        system_prompt: str,
        user_content: str,
        *,
        max_chars: int,
        timeout_seconds: int,
    ) -> str:
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "max_completion_tokens": max_chars,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise MinimaxCallError("timeout") from error
        except httpx.HTTPStatusError as error:
            raise MinimaxCallError("http_error") from error
        except httpx.HTTPError as error:
            raise MinimaxCallError("network") from error
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise MinimaxCallError("invalid_response") from error
        if not isinstance(content, str) or not (text := content.strip()):
            raise MinimaxCallError("invalid_response")
        return text[:max_chars]
