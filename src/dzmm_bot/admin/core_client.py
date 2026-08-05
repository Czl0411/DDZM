from typing import Callable, Protocol

import httpx
import websockets


class AdminCorePort(Protocol):
    def status(self) -> dict: ...

    def login_state(self) -> str | None: ...

    def get_manual_login_lease(self) -> dict | None: ...

    def start_manual_login(self, operator_id: str, operator_name: str) -> dict: ...

    def finish_manual_login(self, operator_id: str, operator_name: str) -> dict: ...

    def cancel_manual_login(self) -> dict: ...

    def enqueue_command(self, command: str) -> dict: ...

    def list_game_commands(self) -> list[dict]: ...

    def set_game_command_enabled(self, command: str, enabled: bool) -> dict: ...

    def set_game_command_template(
        self, command: str, scenario: str, template: str
    ) -> dict: ...

    def list_game_users(self, page: int, page_size: int) -> dict: ...

    def list_game_items(self, page: int, page_size: int) -> dict: ...

    def create_game_item(self, item: dict) -> dict: ...

    def get_game_settings(self) -> dict: ...

    def set_game_settings(self, settings: dict) -> dict: ...

    def get_activity_settings(self) -> dict: ...

    def set_activity_settings(self, settings: dict) -> dict: ...

    def get_random_event_settings(self) -> dict: ...

    def set_random_event_settings(self, settings: dict) -> dict: ...

    def list_random_event_scenes(self, page: int, page_size: int) -> dict: ...

    def create_random_event_scene(self, scene: dict) -> dict: ...

    def update_random_event_scene(self, scene_id: str, scene: dict) -> dict: ...

    def delete_random_event_scene(self, scene_id: str) -> dict: ...

    def list_today_random_events(self) -> list[dict]: ...

    def reschedule_random_event(self, schedule_id: str, scheduled_at: str) -> dict: ...


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

    def get_manual_login_lease(self) -> dict | None:
        return self._get("/internal/admin/login/lease")

    def start_manual_login(self, operator_id: str, operator_name: str) -> dict:
        return self._post_manual_login("start", operator_id, operator_name)

    def finish_manual_login(self, operator_id: str, operator_name: str) -> dict:
        return self._post_manual_login("finish", operator_id, operator_name)

    def cancel_manual_login(self) -> dict:
        response = self._client.post("/internal/admin/login/cancel")
        response.raise_for_status()
        return response.json()

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

    def list_game_users(self, page: int, page_size: int) -> dict:
        return self._get(
            "/internal/game/users", params={"page": page, "page_size": page_size}
        )

    def list_game_items(self, page: int, page_size: int) -> dict:
        return self._get(
            "/internal/game/items", params={"page": page, "page_size": page_size}
        )

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

    def get_random_event_settings(self) -> dict:
        return self._get("/internal/game/random-events/settings")

    def set_random_event_settings(self, settings: dict) -> dict:
        response = self._client.patch(
            "/internal/game/random-events/settings", json=settings
        )
        response.raise_for_status()
        return response.json()

    def list_random_event_scenes(self, page: int, page_size: int) -> dict:
        return self._get(
            "/internal/game/random-events/scenes",
            params={"page": page, "page_size": page_size},
        )

    def create_random_event_scene(self, scene: dict) -> dict:
        response = self._client.post(
            "/internal/game/random-events/scenes", json=scene
        )
        response.raise_for_status()
        return response.json()

    def update_random_event_scene(self, scene_id: str, scene: dict) -> dict:
        response = self._client.put(
            f"/internal/game/random-events/scenes/{scene_id}", json=scene
        )
        response.raise_for_status()
        return response.json()

    def delete_random_event_scene(self, scene_id: str) -> dict:
        response = self._client.delete(
            f"/internal/game/random-events/scenes/{scene_id}"
        )
        response.raise_for_status()
        return response.json()

    def list_today_random_events(self) -> list[dict]:
        return self._get("/internal/game/random-events/today")

    def reschedule_random_event(self, schedule_id: str, scheduled_at: str) -> dict:
        response = self._client.patch(
            f"/internal/game/random-events/today/{schedule_id}",
            json={"scheduled_at": scheduled_at},
        )
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: dict | None = None):
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def _post_manual_login(
        self, action: str, operator_id: str, operator_name: str
    ) -> dict:
        response = self._client.post(
            f"/internal/admin/login/{action}",
            json={"operator_id": operator_id, "operator_name": operator_name},
        )
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
