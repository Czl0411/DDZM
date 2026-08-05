from typing import Callable, Protocol

import httpx
import websockets


class AdminCorePort(Protocol):
    def status(self) -> dict: ...

    def login_state(self) -> str | None: ...

    def enqueue_command(self, command: str) -> dict: ...

    def list_game_commands(self) -> list[dict]: ...

    def set_game_command_enabled(self, command: str, enabled: bool) -> dict: ...

    def set_game_command_template(
        self, command: str, scenario: str, template: str
    ) -> dict: ...

    def list_game_users(self) -> list[dict]: ...

    def list_game_items(self) -> list[dict]: ...

    def create_game_item(self, item: dict) -> dict: ...

    def get_game_settings(self) -> dict: ...

    def set_game_settings(self, settings: dict) -> dict: ...

    def get_activity_settings(self) -> dict: ...

    def set_activity_settings(self, settings: dict) -> dict: ...


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
        return self._get("/internal/status")

    def login_state(self) -> str | None:
        heartbeat = self._get("/internal/login-state")
        return None if heartbeat is None else heartbeat["login_state"]

    def enqueue_command(self, command: str) -> dict:
        response = self._client.post(
            "/internal/worker-commands", json={"command": command}
        )
        response.raise_for_status()
        return response.json()

    def list_game_commands(self) -> list[dict]:
        return self._get("/internal/game/commands")

    def set_game_command_enabled(self, command: str, enabled: bool) -> dict:
        response = self._client.patch(
            "/internal/game/commands", json={"command": command, "enabled": enabled}
        )
        response.raise_for_status()
        return response.json()

    def set_game_command_template(
        self, command: str, scenario: str, template: str
    ) -> dict:
        response = self._client.patch(
            "/internal/game/command-templates",
            json={"command": command, "scenario": scenario, "template": template},
        )
        response.raise_for_status()
        return response.json()

    def list_game_users(self) -> list[dict]:
        return self._get("/internal/game/users")

    def list_game_items(self) -> list[dict]:
        return self._get("/internal/game/items")

    def create_game_item(self, item: dict) -> dict:
        response = self._client.post("/internal/game/items", json=item)
        response.raise_for_status()
        return response.json()

    def get_game_settings(self) -> dict:
        return self._get("/internal/game/settings")

    def set_game_settings(self, settings: dict) -> dict:
        response = self._client.patch("/internal/game/settings", json=settings)
        response.raise_for_status()
        return response.json()

    def get_activity_settings(self) -> dict:
        return self._get("/internal/game/activity-settings")

    def set_activity_settings(self, settings: dict) -> dict:
        response = self._client.patch("/internal/game/activity-settings", json=settings)
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


class NoVNCWebSocketConnector:
    def __init__(
        self,
        port: int = 16080,
        *,
        connect: Callable = websockets.connect,
    ) -> None:
        self._base_url = f"ws://127.0.0.1:{port}"
        self._connect = connect

    def __call__(self, path: str, *, subprotocols: list[str] | None = None):
        return self._connect(
            f"{self._base_url}{path}", subprotocols=subprotocols
        )
