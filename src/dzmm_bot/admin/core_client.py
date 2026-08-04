from typing import Protocol

import httpx


class AdminCorePort(Protocol):
    def status(self) -> dict: ...

    def login_state(self) -> str | None: ...

    def enqueue_command(self, command: str) -> dict: ...


class CoreClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"X-Core-Token": token},
            timeout=10,
        )

    def status(self) -> dict:
        health = self._get("/healthz")
        heartbeat = self._get("/internal/login-state")
        return {
            "state": "healthy" if health["database_available"] else "unhealthy",
            "last_heartbeat": None if heartbeat is None else heartbeat["recorded_at"],
            "queue_counts": {},
        }

    def login_state(self) -> str | None:
        heartbeat = self._get("/internal/login-state")
        return None if heartbeat is None else heartbeat["login_state"]

    def enqueue_command(self, command: str) -> dict:
        response = self._client.post(
            "/internal/worker-commands", json={"command": command}
        )
        response.raise_for_status()
        return response.json()

    def _get(self, path: str):
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()


class NoVNCClient:
    def __init__(
        self,
        port: int = 16080,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=10
        )

    def get(self, path: str) -> httpx.Response:
        return self._client.get(path)
