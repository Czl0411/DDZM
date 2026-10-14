"""Public UID-trust HTTP/SSE interface; independent from employee accounts."""
import asyncio
import json
import re
from time import monotonic
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .mistrealm_repository import MistrealmError
from .mistrealm_state import FIELDS


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(Body):
    name: str = Field(min_length=1, max_length=40)
    avatar: str | None = Field(default=None, max_length=2048)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("请输入昵称")
        return value.strip()

    @field_validator("avatar")
    @classmethod
    def avatar_valid(cls, value):
        from urllib.parse import urlsplit
        if value and (urlsplit(value).scheme != "https" or not urlsplit(value).hostname):
            raise ValueError("头像必须是HTTPS地址")
        return value or None


class RequestBody(Body):
    request_id: UUID


class MatchTicket(Body):
    ticket: UUID


class Join(RequestBody):
    code: str = Field(pattern=r"^[0-9]{6}$")


class Action(RequestBody):
    match_id: UUID | None = None
    version: StrictInt = Field(ge=0)
    action: Literal["select_faction", "ready", "unready", "start", "mulligan",
                    "reserve", "play", "leader", "pass", "concede", "leave", "rematch"]
    payload: dict = Field(default_factory=dict)


def mistrealm_router(repository, clock):
    router = APIRouter(prefix="/api/mistrealm")

    def identity(value):
        if not value or not value.startswith("MistrealmUid "):
            raise HTTPException(401, "无法读取玩家身份")
        uid = value[len("MistrealmUid "):]
        if not re.fullmatch(r"[^\s\x00-\x1f\x7f]{1,255}", uid):
            raise HTTPException(401, "无法读取玩家身份")
        return uid

    def call(fn, *args):
        try:
            return fn(*args)
        except MistrealmError as error:
            raise HTTPException(error.status, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/players/me")
    def register(body: Profile, authorization: str | None = Header(None)):
        return call(repository.mistrealm_register, identity(authorization), body.name, body.avatar, clock())

    @router.get("/players/me")
    def me(authorization: str | None = Header(None)):
        return call(repository.mistrealm_me, identity(authorization), clock())

    @router.post("/rooms")
    def create(body: RequestBody, authorization: str | None = Header(None)):
        return call(repository.mistrealm_create, identity(authorization), body.request_id, clock())

    @router.post("/rooms/join")
    def join(body: Join, authorization: str | None = Header(None)):
        return call(repository.mistrealm_join, identity(authorization), body.code, body.request_id, clock())

    @router.post("/matchmaking")
    def match_start(authorization: str | None = Header(None)):
        return call(repository.mistrealm_matchmaking, identity(authorization), "start", None, clock())

    @router.post("/matchmaking/heartbeat")
    def match_heartbeat(body: MatchTicket, authorization: str | None = Header(None)):
        return call(repository.mistrealm_matchmaking, identity(authorization), "heartbeat", body.ticket, clock())

    @router.post("/matchmaking/cancel")
    def match_cancel(body: MatchTicket, authorization: str | None = Header(None)):
        return call(repository.mistrealm_matchmaking, identity(authorization), "cancel", body.ticket, clock())

    @router.get("/rooms/{room_id}")
    def view(room_id: UUID, authorization: str | None = Header(None)):
        return call(repository.mistrealm_view, room_id, identity(authorization), clock())

    @router.post("/rooms/{room_id}/actions")
    def action(room_id: UUID, body: Action, authorization: str | None = Header(None)):
        if set(body.payload) != FIELDS[body.action]:
            raise HTTPException(422, "操作参数不正确")
        return call(repository.mistrealm_action, room_id, identity(authorization), body.match_id,
                    body.version, body.request_id, body.action, body.payload, clock())

    @router.get("/rooms/{room_id}/events")
    async def events(room_id: UUID, request: Request, authorization: str | None = Header(None)):
        uid = identity(authorization)
        initial = await asyncio.to_thread(call, repository.mistrealm_view, room_id, uid, clock())

        async def stream():
            last, heartbeat, value = None, monotonic(), initial
            while not await request.is_disconnected():
                version = value["state"]["version"]
                if version != last:
                    yield "event: update\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n"
                    last, heartbeat = version, monotonic()
                elif monotonic()-heartbeat >= 15:
                    yield ": heartbeat\n\n"
                    heartbeat = monotonic()
                if value["state"]["phase"] == "closed":
                    return
                await asyncio.sleep(0.7)
                try:
                    value = await asyncio.to_thread(repository.mistrealm_view, room_id, uid, clock())
                except ValueError:
                    yield "event: unavailable\ndata: {}\n\n"
                    return

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    return router
