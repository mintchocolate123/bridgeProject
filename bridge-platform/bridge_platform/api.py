"""平台的 HTTP API。

啟動(在 bridge-platform 目錄下):
    python -m bridge_platform

端點說明見 docs/api-design.md。本檔只負責 HTTP 的部分:解析請求、驗證
token、頻率限制、把錯誤轉成統一格式。所有遊戲邏輯都在 manager 與 room。
"""

import asyncio
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from bridge_platform import config
from bridge_platform.errors import ApiError, Forbidden, NotFound, TooManyRequests, Unauthorized
from bridge_platform.filters import events_since
from bridge_platform.manager import Manager
from bridge_platform.room import find_room, hash_token
from bridge_platform.store import Store

log = logging.getLogger("bridge_platform")


# ---------------------------------------------------------------------------
# 請求格式
# ---------------------------------------------------------------------------

class JoinRequest(BaseModel):
    name: str
    room_code: Optional[str] = None
    seat: Optional[str] = None
    options: Optional[dict[str, Any]] = None


class ActionRequest(BaseModel):
    turn_id: str
    action: str


class AdminCreateRequest(BaseModel):
    boards: Optional[list[dict[str, Any]]] = None      # PBN 牌局
    options: Optional[dict[str, Any]] = None           # 或是依種子產生


class AbortRequest(BaseModel):
    reason: str = Field(default="aborted by admin", max_length=200)


# ---------------------------------------------------------------------------
# 頻率限制
# ---------------------------------------------------------------------------

class RateLimiter:
    """每個鍵每秒最多 rate 次。滑動一秒的計數,簡單夠用。"""

    def __init__(self, rate):
        self.rate = rate
        self.hits = defaultdict(list)

    def check(self, key):
        now = time.monotonic()
        hits = [t for t in self.hits[key] if now - t < 1.0]
        if len(hits) >= self.rate:
            self.hits[key] = hits
            raise TooManyRequests(f"more than {self.rate} requests per second")
        hits.append(now)
        self.hits[key] = hits


# ---------------------------------------------------------------------------
# 應用程式
# ---------------------------------------------------------------------------

def create_app(manager=None, admin_key=config.ADMIN_KEY, tick_interval=0.5,
               rate_limit=config.RATE_LIMIT_PER_SECOND,
               max_streams_per_ip=config.MAX_STREAMS_PER_IP,
               keepalive=config.STREAM_KEEPALIVE_S,
               ui_dist=config.UI_DIST):
    limiter = RateLimiter(rate_limit)
    open_streams = defaultdict(int)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal manager
        if manager is None:
            manager = Manager(Store(config.DB_PATH))
            restored = manager.restore()
            log.info("restored %d rooms from %s", restored, config.DB_PATH)
        app.state.manager = manager

        async def ticker():
            while True:
                await asyncio.sleep(tick_interval)
                try:
                    manager.tick()
                except Exception:
                    log.exception("tick failed")

        task = asyncio.create_task(ticker())
        yield
        task.cancel()

    app = FastAPI(title="Bridge platform", version="0.1", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                       allow_methods=["*"], allow_headers=["*"])

    # -- 錯誤格式 -----------------------------------------------------------

    @app.exception_handler(ApiError)
    async def _api_error(request, exc):
        headers = {"Retry-After": "1"} if exc.status == 429 else None
        return JSONResponse(exc.to_dict(), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request, exc):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else "invalid request"
        return JSONResponse({"error": {"code": "invalid_request", "message": message}},
                            status_code=422)

    # -- 共用 ---------------------------------------------------------------

    def bearer(request):
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        return value.strip() if scheme.lower() == "bearer" else None

    def player(request, room_code):
        """驗證 token,並確認它屬於路徑上的房間。回傳 (room, seat)。"""
        token = bearer(request)
        room, seat = manager.authenticate(token)
        if room.code != room_code.upper():
            raise Unauthorized("token does not belong to this room")
        limiter.check(hash_token(token))
        return room, seat

    def admin(request):
        if admin_key is None:
            raise Forbidden("admin endpoints are disabled; set BRIDGE_ADMIN_KEY", code="admin_disabled")
        token = bearer(request) or ""
        if not secrets.compare_digest(token.encode(), admin_key.encode()):
            raise Unauthorized("invalid admin key", code="invalid_admin_key")

    def client_ip(request):
        return request.client.host if request.client else "unknown"

    def stream(request, room, viewer):
        """某個視角的事件串流。支援 Last-Event-ID 與 ?since= 重連。"""
        ip = client_ip(request)
        if open_streams[ip] >= max_streams_per_ip:
            raise TooManyRequests(f"at most {max_streams_per_ip} streams per IP")

        last_id = request.headers.get("last-event-id", "")
        if last_id.isdigit():
            start = int(last_id) + 1
        else:
            try:
                start = max(int(request.query_params.get("since", 0)), 0)
            except ValueError:
                start = 0

        async def generate():
            open_streams[ip] += 1
            cursor = start
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    batch = events_since(room, cursor, viewer)
                    for event in batch:
                        yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    cursor += len(batch)

                    if room.ended and cursor >= len(room.events):
                        yield 'data: {"type": "stream_end"}\n\n'
                        return
                    if not batch:
                        before = len(room.events)
                        await manager.wait_for_change(room, cursor, keepalive)
                        if len(room.events) == before:
                            yield ": keep-alive\n\n"
            finally:
                open_streams[ip] -= 1

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # -- 玩家 ---------------------------------------------------------------

    @app.post("/api/v1/rooms/join", status_code=201)
    async def join(body: JoinRequest, request: Request):
        limiter.check("join:" + client_ip(request))
        room, seat, token = manager.join(body.room_code, body.name, body.seat, body.options)
        return {"room_code": room.code, "seat": seat, "player_token": token,
                "room": room.summary()}

    @app.delete("/api/v1/rooms/{room_code}/seat")
    async def leave(room_code: str, request: Request):
        room, seat = player(request, room_code)
        manager.leave(room, seat)
        return room.summary()

    @app.get("/api/v1/rooms/{room_code}/state")
    async def player_state(room_code: str, request: Request):
        room, seat = player(request, room_code)
        return {"seat": seat, **room.state(seat)}

    @app.get("/api/v1/rooms/{room_code}/stream")
    async def player_stream(room_code: str, request: Request):
        room, seat = player(request, room_code)
        return stream(request, room, seat)

    @app.post("/api/v1/rooms/{room_code}/action")
    async def act(room_code: str, body: ActionRequest, request: Request):
        room, seat = player(request, room_code)
        return manager.act(room, seat, body.turn_id, body.action)

    # -- 觀戰 ---------------------------------------------------------------

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "rooms": len(manager.rooms)}

    @app.get("/api/v1/rooms")
    async def list_rooms(status: Optional[str] = None):
        return manager.list_rooms(status)

    @app.get("/api/v1/rooms/{room_code}")
    async def public_state(room_code: str):
        return find_room(manager.rooms, room_code).state("public")

    @app.get("/api/v1/rooms/{room_code}/spectate")
    async def spectate(room_code: str, request: Request):
        return stream(request, find_room(manager.rooms, room_code), "public")

    @app.get("/api/v1/rooms/{room_code}/record")
    async def record(room_code: str):
        return find_room(manager.rooms, room_code).record()

    @app.get("/api/v1/rooms/{room_code}/replay/{index}")
    async def replay(room_code: str, index: int):
        return find_room(manager.rooms, room_code).frames(index)

    # -- 主辦方 -------------------------------------------------------------

    @app.post("/api/v1/admin/rooms", status_code=201)
    async def admin_create(body: AdminCreateRequest, request: Request):
        admin(request)
        if body.boards is not None:
            room = manager.create_from_pbn(body.boards)
        else:
            room = manager.create_from_options(body.options or {}, created_by="admin")
        return room.summary()

    @app.get("/api/v1/admin/rooms/{room_code}")
    async def admin_state(room_code: str, request: Request):
        admin(request)
        return find_room(manager.rooms, room_code).state("all")

    @app.get("/api/v1/admin/rooms/{room_code}/stream")
    async def admin_stream(room_code: str, request: Request):
        admin(request)
        return stream(request, find_room(manager.rooms, room_code), "all")

    @app.post("/api/v1/admin/rooms/{room_code}/abort")
    async def admin_abort(room_code: str, body: AbortRequest, request: Request):
        admin(request)
        room = find_room(manager.rooms, room_code)
        manager.abort(room, body.reason)
        return room.summary()

    # -- 前端 ---------------------------------------------------------------

    if ui_dist and os.path.isfile(os.path.join(ui_dist, "index.html")):
        mount_ui(app, ui_dist)
    else:
        log.info("no built UI at %s; serving API only", ui_dist)

    return app


def mount_ui(app, dist):
    """提供 build 好的前端。找不到檔案就回 index.html,讓前端路由處理。"""
    root = os.path.realpath(dist)
    index = os.path.join(root, "index.html")

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
                   include_in_schema=False)
    async def _api_not_found(rest: str):
        # 打錯的 API 路徑要回 JSON 404,不可以回網頁
        raise NotFound(f"no endpoint /api/{rest}", code="not_found")

    @app.get("/{path:path}", include_in_schema=False)
    async def _ui(path: str):
        target = os.path.realpath(os.path.join(root, path))
        if target.startswith(root + os.sep) and os.path.isfile(target):
            # 檔名含雜湊的資源可以長期快取,index.html 不行
            cache = "public, max-age=31536000, immutable" if "/assets/" in target.replace(os.sep, "/") else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
