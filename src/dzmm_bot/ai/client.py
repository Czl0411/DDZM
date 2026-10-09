import httpx


class DeepSeekCallError(Exception):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class DeepSeekChatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.deepseek.com",
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
        history_messages=(),
        max_chars: int,
        timeout_seconds: int,
        temperature: float | None = None,
    ) -> str:
        text, _ = self.complete_with_reason(
            system_prompt,
            user_content,
            history_messages=history_messages,
            max_chars=max_chars,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
        )
        return text

    def complete_with_reason(
        self,
        system_prompt: str,
        user_content: str,
        *,
        history_messages=(),
        max_chars: int,
        timeout_seconds: int,
        temperature: float | None = None,
        thinking_enabled: bool = True,
        max_tokens: int | None = None,
    ) -> tuple[str, str]:
        """返回 (正文, finish_reason)。

        - `thinking_enabled=False` 关掉思考模式：token 预算全留给正文，
          长文更快出、更不容易被掐断（dzmm_nuo 的高潮/场景生成就是这么调的）。
        - `max_tokens` 不传就沿用旧口径（= max_chars）。
        - `finish_reason == "length"` 表示被 max_tokens 截断，调用方可以接着续写。
        """
        request_body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *(
                    {"role": message.role, "content": message.content}
                    for message in history_messages
                ),
                {"role": "user", "content": user_content},
            ],
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
            "max_tokens": int(max_tokens or max_chars),
        }
        if temperature is not None:
            request_body["temperature"] = temperature
        try:
            response = self._client.post(
                "/chat/completions",
                json=request_body,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise DeepSeekCallError("timeout") from error
        except httpx.HTTPStatusError as error:
            raise DeepSeekCallError("http_error") from error
        except httpx.HTTPError as error:
            raise DeepSeekCallError("network") from error
        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise DeepSeekCallError("invalid_response") from error
        if not isinstance(content, str) or not (text := content.strip()):
            raise DeepSeekCallError("invalid_response")
        reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return text[:max_chars], str(reason or "")
