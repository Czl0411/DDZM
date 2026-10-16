import base64
import re
from io import BytesIO
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import HTTPException, Path as ApiPath, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from dzmm_bot.core.workstation import WORKSTATION_LAYERS
from dzmm_bot.core.gamefy import WorkstationShareRequest
from dzmm_bot.browser.workstation_image import render_workstation_image


ROOT = Path(__file__).parent
VIEW_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, nofollow",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'",
}


def install_workstation_routes(app, core):
    gamefy_path = "/api/gamefy/workstation"
    gamefy_headers = {
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",
        "X-Content-Type-Options": "nosniff",
    }

    @app.options(gamefy_path)
    @app.options(gamefy_path + "/lobby")
    @app.options(gamefy_path + "/employees/{employee_number}")
    @app.options(gamefy_path + "/employees/{employee_number}/image")
    @app.options(gamefy_path + "/share")
    @app.options(gamefy_path + "/shares/{request_id}")
    def gamefy_preflight():
        return JSONResponse({}, headers={
            **gamefy_headers,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Max-Age": "600",
        })

    def gamefy_response(request, operation):
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer ") or not 0 < len(authorization[7:]) <= 8192:
            return JSONResponse({"detail": "请先登录 DZMM，再打开工位游戏。"}, status_code=401, headers=gamefy_headers)
        try:
            return JSONResponse(operation(authorization[7:]), headers=gamefy_headers)
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            messages = {
                401: "玩家身份无效或已过期，请刷新游戏重新登录。",
                404: "未找到员工档案或工位，请返回大厅刷新；尚未入职请在群里发送 /入职 名字。",
                403: "请先在目标群发送 /我的工位，再刷新本页；发图入口有效期为24小时。",
                409: "这次发送已选择其他群，请刷新后重试。",
                429: "发送过于频繁，请在一分钟后再试。",
            }
            return JSONResponse(
                {"detail": messages.get(status_code, "工位暂时无法加载，请稍后刷新重试。")},
                status_code=status_code if status_code in messages else 503,
                headers=gamefy_headers,
            )
        except httpx.RequestError:
            return JSONResponse({"detail": "工位暂时无法加载，请稍后刷新重试。"}, status_code=503, headers=gamefy_headers)

    @app.get(gamefy_path)
    def gamefy_workstation(request: Request):
        return gamefy_response(request, core.get_gamefy_workstation)

    @app.get(gamefy_path + "/lobby")
    def workstation_lobby(request: Request, query: str = Query("", max_length=64), page: int = Query(1, ge=1, le=1000000)):
        return gamefy_response(request, lambda token: core.list_gamefy_workstations(token, query, page))

    @app.get(gamefy_path + "/employees/{employee_number}")
    def employee_workstation(request: Request, employee_number: int = ApiPath(ge=1, le=2147483647)):
        return gamefy_response(request, lambda token: core.get_gamefy_employee_workstation(token, employee_number))

    @app.get(gamefy_path + "/employees/{employee_number}/image")
    def employee_workstation_image(request: Request, employee_number: int = ApiPath(ge=1, le=2147483647)):
        def image_data(token):
            workstation = core.get_gamefy_employee_workstation(token, employee_number)
            image = BytesIO()
            render_workstation_image(workstation, image)
            return {"data_url": "data:image/png;base64," + base64.b64encode(image.getvalue()).decode("ascii")}

        return gamefy_response(request, image_data)

    @app.post(gamefy_path + "/share")
    def share_gamefy_workstation(request: Request, payload: WorkstationShareRequest):
        return gamefy_response(request, lambda token: core.share_gamefy_workstation(token, payload.model_dump(mode="json")))

    @app.get(gamefy_path + "/shares/{request_id}")
    def gamefy_share_status(request: Request, request_id: UUID):
        return gamefy_response(request, lambda token: core.gamefy_workstation_share_status(token, str(request_id)))

    def read_workstation(token):
        if not re.fullmatch(r"[0-9a-f]{32}\.[0-9a-f]{64}", token):
            raise HTTPException(404, "工位链接无效或已失效，请在群里重新发送 /我的工位。")
        try:
            return core.get_workstation(token)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                raise HTTPException(404, "工位链接无效或已失效，请在群里重新发送 /我的工位。") from error
            raise HTTPException(503, "工位暂时无法加载，请稍后重试。") from error
        except httpx.RequestError as error:
            raise HTTPException(503, "工位暂时无法加载，请稍后重试。") from error

    @app.get("/workstation/{token}")
    def workstation_page(token: str):
        try:
            read_workstation(token)
        except HTTPException as error:
            return HTMLResponse(
                '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>工位暂不可用</title><h1>工位暂不可用</h1>'
                f'<p>{error.detail}</p></html>',
                status_code=error.status_code, headers=VIEW_HEADERS,
            )
        return FileResponse(ROOT / "templates" / "workstation.html", headers=VIEW_HEADERS)

    @app.get("/api/workstations/{token}")
    def workstation_data(token: str):
        return JSONResponse(read_workstation(token), headers=VIEW_HEADERS)

    @app.get("/static/workstation/{filename}")
    def workstation_asset(filename: str):
        allowed = {"core-base.png", *(f"{key}-layer.png" for key in WORKSTATION_LAYERS)}
        if filename not in allowed:
            raise HTTPException(404, "not found")
        return FileResponse(
            ROOT / "static" / "workstation" / filename,
            media_type="image/png", headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/static/workstation.js")
    def workstation_script():
        return FileResponse(ROOT / "static" / "workstation.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/static/workstation.css")
    def workstation_styles():
        return FileResponse(ROOT / "static" / "workstation.css", media_type="text/css", headers={"Cache-Control": "no-cache"})
