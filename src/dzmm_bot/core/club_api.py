"""UID-scoped API for the unified Club and its mahjong table."""

import asyncio
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .mahjong_repository import MahjongRateLimitError


class CreateRoomPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    room_type: Literal["casual", "coin"] = "coin"
    match_mode: Literal["east", "south"] = "east"


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=0)
    request_id: UUID
    action: Literal[
        "claim", "ready", "unready", "leave", "start",
        "discard", "riichi", "tsumo", "ron", "pass", "chi", "pon", "kan",
        "ankan", "kakan", "kyuushu",
    ]
    payload: dict = Field(default_factory=dict)


class ChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    text: str = Field(min_length=1, max_length=300)


def _uid(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("ClubUid "):
        raise HTTPException(401, "无法读取玩家身份")
    value = authorization[len("ClubUid "):]
    if not value or len(value) > 255 or any(char.isspace() for char in value):
        raise HTTPException(401, "无法读取玩家身份")
    return value


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except MahjongRateLimitError as error:
        raise HTTPException(429, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


async def mahjong_events(repository, room_id, uid, clock, request):
    previous = None
    while not await request.is_disconnected():
        try:
            value = await asyncio.to_thread(repository.mahjong_view, room_id, uid, clock())
        except ValueError:
            yield "event: unavailable\ndata: {}\n\n"
            return
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if encoded != previous:
            yield f"event: snapshot\ndata: {encoded}\n\n"
            previous = encoded
        else:
            yield ": heartbeat\n\n"
        await asyncio.sleep(1)


def club_router(repository, clock):
    router = APIRouter(prefix="/api/club")

    @router.get("/mahjong/rooms")
    def rooms(authorization: str | None = Header(None)):
        return _call(repository.list_mahjong_rooms, _uid(authorization), clock())

    @router.post("/mahjong/rooms")
    def create(body: CreateRoomPayload, authorization: str | None = Header(None)):
        return _call(
            repository.create_mahjong_room,
            _uid(authorization),
            clock(),
            room_type=body.room_type,
            match_mode=body.match_mode,
            request_id=body.request_id,
        )

    @router.get("/mahjong/rooms/{room_id}")
    def snapshot(room_id: UUID, authorization: str | None = Header(None)):
        return _call(repository.mahjong_view, room_id, _uid(authorization), clock())

    @router.post("/mahjong/rooms/{room_id}/actions")
    def action(room_id: UUID, body: ActionPayload, authorization: str | None = Header(None)):
        expected = {
            "claim": {"code"},
            "discard": {"tile"},
            "riichi": {"tile"},
            "chi": {"tiles"},
            "pon": {"tiles"},
            "kan": {"tiles"},
            "ankan": {"tile_type"},
            "kakan": {"meld_index"},
        }.get(body.action, set())
        if set(body.payload) != expected:
            raise HTTPException(422, "操作参数不正确")
        return _call(
            repository.mahjong_action,
            room_id,
            _uid(authorization),
            body.version,
            body.request_id,
            body.action,
            body.payload,
            clock(),
        )

    @router.post("/mahjong/rooms/{room_id}/chat")
    def chat(room_id: UUID, body: ChatPayload, authorization: str | None = Header(None)):
        if not body.text.strip():
            raise HTTPException(422, "请输入消息")
        return _call(
            repository.mahjong_chat,
            room_id,
            _uid(authorization),
            body.request_id,
            body.text,
            clock(),
        )

    @router.get("/mahjong/rooms/{room_id}/events")
    async def events(room_id: UUID, request: Request, authorization: str | None = Header(None)):
        uid = _uid(authorization)
        await asyncio.to_thread(_call, repository.mahjong_view, room_id, uid, clock())
        return StreamingResponse(
            mahjong_events(repository, room_id, uid, clock, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
