"""UID-trust API for the independent draw-and-guess game."""

import asyncio
import json
from time import monotonic
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .drawguess_repository import DrawguessRateLimitError


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: StrictInt = Field(ge=0)
    version: StrictInt = Field(ge=0)
    request_id: UUID
    action: Literal["claim", "ready", "unready", "leave", "start", "choose", "guess", "rematch"]
    payload: dict = Field(default_factory=dict)


class StrokePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: StrictInt = Field(ge=0)
    request_id: UUID
    operations: list[dict] = Field(min_length=1)


class ChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: StrictInt = Field(ge=0)
    request_id: UUID
    text: str = Field(min_length=1, max_length=100)


class CreateRoomPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_type: Literal["casual", "coin"] = "casual"
    stake: Literal[0, 5, 10, 20] = 0


async def room_events(repository, room_id, uid, after, clock, request):
    cursor = after
    last_version = None
    last_chat_version = None
    heartbeat_at = monotonic()
    first = True
    while not await request.is_disconnected():
        try:
            value = await asyncio.to_thread(repository.drawguess_events, room_id, uid, cursor, clock())
        except ValueError:
            yield "event: unavailable\ndata: {}\n\n"
            return
        version = value["version"]
        chat_version = value.get("chat_version", 0)
        if "snapshot" not in value and (
            first or version != last_version or chat_version != last_chat_version
        ):
            snapshot = await asyncio.to_thread(repository.drawguess_view, room_id, uid, clock())
            value = {
                **value, "cursor": snapshot["cursor"], "reset": True,
                "events": [], "snapshot": snapshot,
            }
            version = snapshot["state"]["version"]
        if (
            first or value["events"] or value["cursor"] != cursor
            or version != last_version or chat_version != last_chat_version
        ):
            yield "event: update\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n"
            heartbeat_at = monotonic()
            first = False
        elif monotonic() - heartbeat_at >= 15:
            yield ": heartbeat\n\n"
            heartbeat_at = monotonic()
        cursor = value["cursor"]
        last_version = version
        last_chat_version = chat_version
        await asyncio.sleep(0.2)


def drawguess_router(repository, clock):
    router = APIRouter(prefix="/api/drawguess")

    def player_uid(authorization):
        if not authorization or not authorization.startswith("DrawguessUid "):
            raise HTTPException(401, "无法读取玩家身份")
        uid = authorization[len("DrawguessUid "):]
        if not uid or len(uid) > 255 or any(char.isspace() for char in uid):
            raise HTTPException(401, "无法读取玩家身份")
        return uid

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DrawguessRateLimitError as error:
            raise HTTPException(429, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/rooms")
    def rooms(authorization: str | None = Header(None)):
        return call(repository.list_drawguess_rooms, player_uid(authorization), clock())

    @router.post("/rooms")
    def create_room(body: CreateRoomPayload, authorization: str | None = Header(None)):
        return call(
            repository.create_drawguess_room,
            player_uid(authorization), None, None, clock(),
            room_type=body.room_type, stake=body.stake,
        )

    @router.get("/rooms/{room_id}")
    def snapshot(room_id: UUID, authorization: str | None = Header(None)):
        return call(repository.drawguess_view, room_id, player_uid(authorization), clock())

    @router.post("/rooms/{room_id}/actions")
    def action(room_id: UUID, body: ActionPayload, authorization: str | None = Header(None)):
        fields = {"choose": {"word_id"}, "guess": {"text"}}.get(body.action, set())
        valid = set(body.payload) in (set(), {"code"}) if body.action == "claim" else set(body.payload) == fields
        if not valid:
            raise HTTPException(422, "操作参数不正确")
        return call(
            repository.drawguess_action, room_id, player_uid(authorization), body.turn_id,
            body.version, body.request_id, body.action, body.payload, clock(),
        )

    @router.post("/rooms/{room_id}/strokes")
    def strokes(room_id: UUID, body: StrokePayload, authorization: str | None = Header(None)):
        return call(
            repository.drawguess_strokes, room_id, player_uid(authorization), body.turn_id,
            body.request_id, body.operations, clock(),
        )

    @router.post("/rooms/{room_id}/chat")
    def chat(room_id: UUID, body: ChatPayload, authorization: str | None = Header(None)):
        if not body.text.strip():
            raise HTTPException(422, "请输入消息")
        return call(
            repository.drawguess_chat, room_id, player_uid(authorization), body.turn_id,
            body.request_id, body.text, clock(),
        )

    @router.get("/rooms/{room_id}/events")
    async def events(room_id: UUID, request: Request, after: int = Query(0, ge=0),
                     authorization: str | None = Header(None)):
        uid = player_uid(authorization)
        await asyncio.to_thread(call, repository.drawguess_view, room_id, uid, clock())
        return StreamingResponse(
            room_events(repository, room_id, uid, after, clock, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
