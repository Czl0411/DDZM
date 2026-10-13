"""UID-trust API. A UID is an asserted identity, not proof of authentication."""
import asyncio
from dataclasses import asdict
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .doudizhu_repository import DoudizhuRateLimitError
from .doudizhu_rules import Pattern, legal_plays


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    round_id: UUID | None
    version: StrictInt = Field(ge=0)
    request_id: UUID
    action: Literal['claim', 'ready', 'unready', 'leave', 'bid', 'play', 'pass', 'takeover', 'resume', 'rematch']
    payload: dict = Field(default_factory=dict)


class ChatPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    round_id: UUID | None
    request_id: UUID
    text: str = Field(min_length=1, max_length=300)


async def room_events(repository, room_id, uid, clock, request):
    while not await request.is_disconnected():
        try:
            value = await asyncio.to_thread(repository.doudizhu_view, room_id, uid, clock())
        except ValueError:
            yield 'event: unavailable\ndata: {}\n\n'
            return
        yield 'event: snapshot\ndata: ' + json.dumps(value, ensure_ascii=False) + '\n\n'
        await asyncio.sleep(1)


def doudizhu_router(repository, clock):
    router = APIRouter(prefix='/api/doudizhu')

    def employee(authorization):
        if not authorization or not authorization.startswith('DoudizhuUid '):
            raise HTTPException(401, '无法读取玩家身份')
        uid = authorization[len('DoudizhuUid '):]
        if not uid or len(uid) > 255 or any(c.isspace() for c in uid):
            raise HTTPException(401, '无法读取玩家身份')
        if repository.find_user(uid) is None:
            raise HTTPException(403, '请先入职')
        return uid

    def call(fn, *args):
        try:
            return fn(*args)
        except DoudizhuRateLimitError as error:
            raise HTTPException(429, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get('/rooms')
    def rooms(authorization: str | None = Header(None)):
        return call(repository.list_doudizhu_rooms, employee(authorization), clock())

    @router.get('/rooms/{room_id}')
    def snapshot(room_id: UUID, authorization: str | None = Header(None)):
        return call(repository.doudizhu_view, room_id, employee(authorization), clock())

    @router.post('/rooms/{room_id}/actions')
    def action(room_id: UUID, body: ActionPayload, authorization: str | None = Header(None)):
        uid = employee(authorization)
        fields = {'claim': {'code'}, 'bid': {'score'}, 'play': {'cards'}}.get(body.action, set())
        if set(body.payload) != fields:
            raise HTTPException(422, '操作参数不正确')
        return call(repository.doudizhu_action, room_id, uid, body.round_id, body.version,
                    body.request_id, body.action, body.payload, clock())

    @router.post('/rooms/{room_id}/chat')
    def chat(room_id: UUID, body: ChatPayload, authorization: str | None = Header(None)):
        if not body.text.strip():
            raise HTTPException(422, '请输入消息')
        return call(repository.doudizhu_chat, room_id, employee(authorization), body.round_id,
                    body.request_id, body.text, clock())

    @router.get('/rooms/{room_id}/suggestions')
    def suggestions(room_id: UUID, authorization: str | None = Header(None)):
        value = call(repository.doudizhu_view, room_id, employee(authorization), clock())
        if value['phase'] != 'playing' or value['seat'] is None or value['turn'] != value['seat']:
            raise HTTPException(409, '当前不能提示出牌')
        previous = value['previous']
        previous = Pattern(**{**previous, 'cards': tuple(previous['cards'])}) if previous else None
        return [asdict(play) for play in legal_plays(tuple(value['hand']), previous)]

    @router.get('/rooms/{room_id}/events')
    async def events(room_id: UUID, request: Request, authorization: str | None = Header(None)):
        uid = employee(authorization)
        await asyncio.to_thread(call, repository.doudizhu_view, room_id, uid, clock())
        return StreamingResponse(room_events(repository, room_id, uid, clock, request),
                                 media_type='text/event-stream', headers={'Cache-Control': 'no-store'})
    return router
