# -*- coding: utf-8 -*-
"""工程检测harness — Web 版后端入口。

FastAPI 应用：复用 report_generator 现有业务层（插件化检测项目、SQLite 存储、
报告生成、规范问答、批量审查、扫描识别），不重写业务逻辑，禁止引入 PyQt5/Qt。

启动（cwd=webapp/backend）：
    python -m uvicorn main:app --host 127.0.0.1 --port 8765
"""

import os
import sys
import time

# ── sys.path 引导（必须在导入任何业务模块之前）──────────────────────
_BACKEND = os.path.dirname(os.path.abspath(__file__))
_WEBAPP = os.path.dirname(_BACKEND)
_ROOT = os.path.dirname(_WEBAPP)
_REPORT_GEN = os.path.join(_ROOT, "report_generator")
_LIBS = os.path.join(_REPORT_GEN, "libs")
for _p in (_LIBS, _REPORT_GEN, _ROOT, _WEBAPP):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI, Request                    # noqa: E402
from fastapi.middleware.cors import CORSMiddleware      # noqa: E402
from fastapi.responses import JSONResponse              # noqa: E402
from fastapi.staticfiles import StaticFiles             # noqa: E402
from fastapi.exceptions import RequestValidationError   # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

try:
    from structural_config import get as _cfg_get
except ImportError:  # pragma: no cover
    def _cfg_get(section, key, default=None):
        return default

APP_VERSION = str(_cfg_get("app", "version", "1.0.0"))

from request_log import log_request, new_request_id       # noqa: E402
from deps import ApiError, get_state                     # noqa: E402
import scan_jobs                                         # noqa: E402
from routers import (assessment as assessment_router,
                     auth as auth_router,
                     chat as chat_router,
                     config as config_router,
                     workspace as workspace_router,
                     dsh_plugins as dsh_plugins_router,
                     equipment as equipment_router,
                     ingest as ingest_router,
                     libraries as libraries_router,
                     normqa as normqa_router,
                     original_record as original_record_router,
                     plugins as plugins_router,
                     personnel as personnel_router,
                     project as project_router,
                     records as records_router,
                     report as report_router,
                     report_edit as report_edit_router,
                     review as review_router,
                     scan as scan_router,
                     sheets as sheets_router,
                     tasks as tasks_router,
                     templates as templates_router,
                     utils as utils_router,
                     wiki as wiki_router,
                     workflow as workflow_router)

app = FastAPI(
    title="工程检测harness API",
    version=APP_VERSION,
    description="Web 版后端：复用 report_generator 业务层（FastAPI）",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

# 扫描识别作业持久化：重启后保留最近 50 条，进行中的作业标记为 interrupted。
scan_jobs.configure(os.path.join(_ROOT, "data", "scan_jobs.json"))

# ── CORS：Vite 开发服务器 + 本机 DSH Web（插件从 DSH 页面读工程上下文）──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 自动保存：任何写请求成功后落盘 data/projects/autosave.json ──────
@app.middleware("http")
async def autosave_project_state(request: Request, call_next):
    response = await call_next(request)
    if (request.method in ("POST", "PUT", "PATCH", "DELETE")
            and request.url.path.startswith("/api/")
            and response.status_code < 500):
        try:
            get_state().autosave()
        except Exception:  # noqa: BLE001 - 自动保存失败不影响主请求
            pass
    return response


# ── 统一响应包装的异常处理 ─────────────────────────────────────────


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    """业务异常：返回中文消息。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "data": None, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc):
    """请求体校验失败：返回中文提示。"""
    return JSONResponse(
        status_code=400,
        content={"ok": False, "data": None,
                 "message": f"请求参数不正确：{exc.errors()[:1]}"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """未捕获异常兜底：统一返回 {"ok": false, "message": 中文}。"""
    return JSONResponse(
        status_code=500,
        content={"ok": False, "data": None,
                 "message": f"服务器内部错误：{type(exc).__name__}: {exc}"})


# ── 注册路由（统一 /api 前缀）──────────────────────────────────────
app.include_router(auth_router.router, prefix="/api")
app.include_router(chat_router.router, prefix="/api")
app.include_router(workspace_router.router, prefix="/api")
app.include_router(plugins_router.router, prefix="/api")
app.include_router(personnel_router.router, prefix="/api")
app.include_router(equipment_router.router, prefix="/api")
app.include_router(dsh_plugins_router.router, prefix="/api")
app.include_router(project_router.router, prefix="/api")
app.include_router(assessment_router.router, prefix="/api")
app.include_router(tasks_router.router, prefix="/api")
app.include_router(sheets_router.router, prefix="/api")
app.include_router(report_router.router, prefix="/api")
app.include_router(report_edit_router.router, prefix="/api")
app.include_router(templates_router.router, prefix="/api")
app.include_router(original_record_router.router, prefix="/api")
app.include_router(normqa_router.router, prefix="/api")
app.include_router(review_router.router, prefix="/api")
app.include_router(scan_router.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")
app.include_router(utils_router.router, prefix="/api")
app.include_router(workflow_router.router, prefix="/api")
app.include_router(wiki_router.router, prefix="/api")
app.include_router(records_router.router, prefix="/api")
app.include_router(libraries_router.router, prefix="/api")
app.include_router(ingest_router.router, prefix="/api")


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """给每个请求分配/透传 X-Request-ID，并把 /api 请求写入结构化日志。"""
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    started = time.time()
    is_api = request.url.path.startswith("/api/")
    query_keys = [key for key, _value in request.query_params.multi_items()]
    try:
        response = await call_next(request)
    except Exception:
        if is_api:
            log_request(request.method, request.url.path, 500,
                        (time.time() - started) * 1000, request_id=request_id,
                        client=request.client.host if request.client else "",
                        query_keys=query_keys)
        raise
    response.headers["X-Request-ID"] = request_id
    if is_api:
        project_name = ""
        try:
            project_name = str(getattr(get_state(), "project_name", ""))
        except Exception:  # noqa: BLE001
            project_name = ""
        log_request(request.method, request.url.path, response.status_code,
                    (time.time() - started) * 1000, request_id=request_id,
                    client=request.client.host if request.client else "",
                    query_keys=query_keys, project_name=project_name)
    return response


@app.get("/api/health", tags=["system"])
def health():
    """健康检查（含版本号）。"""
    return {"ok": True, "data": {"status": "running", "version": APP_VERSION},
            "message": "服务运行中"}


@app.get("/api/system/dsh", tags=["system"])
def dsh_status():
    """探测 DSH GUI 是否可达、是否要求登录（401）。

    前端 /harness 用它在嵌入 iframe 前给出「可达 / 需登录 / 未启动」提示。
    """
    try:
        from structural_config import get as cfg_get
    except ImportError:  # pragma: no cover
        def cfg_get(section, key, default=None):
            return default
    url = str(cfg_get("dsh", "gui_url", "http://127.0.0.1:3642")).rstrip("/")
    import requests
    try:
        response = requests.get(url + "/", timeout=3, allow_redirects=False)
        return {"ok": True, "data": {
            "url": url,
            "reachable": True,
            "status": response.status_code,
            "auth_required": response.status_code in (301, 302, 303, 401),
        }, "message": "DSH 状态读取成功"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "data": {
            "url": url,
            "reachable": False,
            "status": 0,
            "auth_required": False,
            "error": str(exc)[:200],
        }, "message": "DSH 未启动或不可达"}


@app.get("/api/system/info", tags=["system"])
def system_info():
    """系统信息：智能体入口（DSH GUI）、MCP 服务名与后端版本。

    P0 后应用内不再提供智能体对话，Vue 端只展示状态与跳转链接。
    """
    try:
        from structural_config import get as cfg_get
    except ImportError:  # pragma: no cover
        def cfg_get(section, key, default=None):
            return default
    return {
        "ok": True,
        "data": {
            "backend": "running",
            "version": APP_VERSION,
            "agent_surface": "dsh",
            "dsh_gui_url": cfg_get("dsh", "gui_url", "http://127.0.0.1:6567"),
            "mcp_server_name": cfg_get("dsh", "mcp_server_name",
                                       "structural_inspection"),
            "architecture_doc": "docs/HARNESS_AGENT_ARCHITECTURE.md",
        },
        "message": "系统信息读取成功",
    }


# ── 生产模式：托管前端构建产物 webapp/frontend/dist ─────────────────
class SPAStaticFiles(StaticFiles):
    """静态文件 + Vue history 路由回退（/templates、/report-edit 刷新不 404）。"""

    @staticmethod
    def _no_cache_html(response):
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    async def get_response(self, path, scope):
        # 未命中的 /api/* 必须返回 404：否则被删除的端点会退回 index.html，
        # 客户端会误以为接口仍然存在（P0 删桥接后尤其需要这条护栏）。
        raw_path = str(scope.get("path") or path or "")
        if raw_path.startswith("/api/"):
            raise StarletteHTTPException(status_code=404)
        clean = str(path or "").lstrip("/")
        is_spa_route = (not clean.startswith("api/")
                        and "." not in os.path.basename(clean))
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not is_spa_route:
                raise
            response = await super().get_response("index.html", scope)
            return self._no_cache_html(response)
        if response.status_code != 404 or not is_spa_route:
            return self._no_cache_html(response)
        response = await super().get_response("index.html", scope)
        return self._no_cache_html(response)


_DIST = os.path.join(_WEBAPP, "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", SPAStaticFiles(directory=_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
