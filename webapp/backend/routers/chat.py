# -*- coding: utf-8 -*-
"""自研 Web 对话桥：浏览器 WebSocket ↔ DSH ACP（stdio JSON-RPC）。

- 会话列表 / 恢复（session/list、session/resume）
- 流式消息与工具轨迹（session/update）
- 权限确认（session/request_permission 转发到页面）
- 取消（session/cancel 通知）
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import chat_store

from deps import ApiError, ok
from routers.auth import COOKIE_NAME, _verify

router = APIRouter(tags=["chat"])

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_MCP_SERVER = os.path.join(_ROOT, "webapp", "mcp_server.py")
_PYTHON = os.environ.get("STRUCTURAL_PYTHON", r"C:\Program Files\python\python.exe")
# DSH ACP 内核：优先用桌面版提取出的完整运行时（data/dsh_runtime，普通 node 直接跑），
# 不可用时回退到 Electron exe（ELECTRON_RUN_AS_NODE=1 当 node 用）。
_DSH_JS = os.environ.get(
    "DSH_CLI_JS",
    os.path.join(_ROOT, "data", "dsh_runtime", "app", "dsh", "node_modules",
                 "@deepseek-ai", "dsh-desktop-host", "lib", "cli.js"))
_DSH_NODE = os.environ.get(
    "DSH_NODE_EXE",
    r"D:\新建文件夹\resources\runtime\primary-runtime\dependencies\node\bin\node.exe")
_DSH_EXE = os.environ.get("DSH_CLI_EXE", r"D:\新建文件夹\DeepSeek Harness.exe")

UpdateHandler = Callable[[dict], Awaitable[None]]
PermissionHandler = Callable[[dict], Awaitable[str]]
CloseHandler = Callable[[str], Awaitable[None]]

_STORE_PATH = os.path.join(_ROOT, "data", "chat_sessions.json")
_STORE_LOCK = threading.Lock()


def _load_meta() -> dict:
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_meta(data: dict) -> None:
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _STORE_PATH)


def _session_meta(session_id: str) -> dict:
    with _STORE_LOCK:
        return dict(_load_meta().get(session_id) or {})


def _update_session_meta(session_id: str, **fields) -> None:
    with _STORE_LOCK:
        data = _load_meta()
        entry = data.get(session_id) or {}
        entry.update(fields)
        entry["updatedAt"] = time.time()
        data[session_id] = entry
        _save_meta(data)


def _hide_session(session_id: str) -> None:
    _update_session_meta(session_id, hidden=True)


def _project_name() -> str:
    try:
        from deps import get_state
        return str(get_state().project_name or "")
    except Exception:  # noqa: BLE001
        return ""


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_ATTACHMENT_RE = re.compile(r"\[附件\]\s*([^\n\r]+)")
_OCR_CACHE: Dict[str, tuple] = {}
_OCR_CACHE_LOCK = threading.Lock()
_OCR_CACHE_MAX = 24


def _attachment_paths(text: str) -> list:
    """从一条用户消息中提取 [附件] 后的路径（图片/表格都可能有）。"""
    paths = []
    for match in _ATTACHMENT_RE.finditer(str(text or "")):
        raw = match.group(1).strip()
        raw = raw.split("[图片")[0].strip().strip("\u0060\"'")
        if raw:
            paths.append(raw)
    return paths


def _ocr_image_text(full_path: str) -> str:
    """同步 OCR 单张图片，按文件修改时间缓存，避免每轮重复识别。"""
    try:
        stat = os.stat(full_path)
        key = "%s|%s|%s" % (os.path.abspath(full_path), stat.st_mtime_ns, stat.st_size)
    except OSError as exc:
        return "（图片无法读取：%s）" % str(exc)[:200]
    with _OCR_CACHE_LOCK:
        cached = _OCR_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from report_generator.scan_recognition.ocr import ocr_file_detail
        result = ocr_file_detail(full_path)
        text = str((result or {}).get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001
        text = "（OCR 失败：%s）" % str(exc)[:300]
    if not text:
        text = "（OCR 未识别到可用文字）"
    with _OCR_CACHE_LOCK:
        _OCR_CACHE[key] = text
        if len(_OCR_CACHE) > _OCR_CACHE_MAX:
            _OCR_CACHE.pop(next(iter(_OCR_CACHE)))
    return text


async def _image_prompt_block(transcript: dict, current_text: str) -> str:
    """把最近图片附件的 OCR 文本注入本轮 prompt。

    仅在上传时识别图片是不够的：旧会话里用户消息只留下图片路径，恢复后
    模型仍会自作主张调用 read_image。这里在每轮发送前补齐 OCR 上下文，并
    明确要求不要读取图片本身。
    """
    texts = []
    for item in (transcript or {}).get("messages") or []:
        if item.get("role") == "user":
            texts.append(str(item.get("text") or ""))
    texts.append(str(current_text or ""))
    # 只取最近 12 条用户消息，按路径去重；标记过 OCR 的路径不重复识别。
    found: Dict[str, bool] = {}
    for text in texts[-12:]:
        marked = "[图片 OCR 文本" in text or "图片内容已由项目 OCR" in text
        for raw in _attachment_paths(text):
            ext = os.path.splitext(raw.split("?")[0])[1].lower()
            if ext not in _IMAGE_EXTS:
                continue
            found[raw] = bool(found.get(raw)) or marked
    if not found:
        return ""
    root = os.path.realpath(_ROOT)
    lines = [
        "【图片附件处理 · 系统自动注入】",
        "本会话包含图片附件。图片内容已经由项目 PaddleOCR 转成文字，请直接使用下面的文本。",
        "禁止调用 read_image，也不要再次读取或识别图片；旧消息中的图片读取错误是历史记录，可忽略。",
    ]
    loop = asyncio.get_running_loop()
    used = 0
    for raw, marked in list(found.items())[-3:]:
        full = raw if os.path.isabs(raw) else os.path.join(_ROOT, raw)
        full = os.path.realpath(full)
        if not (full == root or full.startswith(root + os.sep)):
            continue
        if marked:
            lines.append("图片：%s（消息中已附带 OCR 文本，直接使用该文本）" % raw)
            continue
        text = await loop.run_in_executor(None, _ocr_image_text, full)
        text = str(text or "").strip()
        if used + len(text) > 12000:
            text = text[:max(0, 12000 - used)]
        used += len(text)
        lines.append("图片：%s\n%s" % (raw, text))
    if len(lines) <= 3:
        return ""
    return "\n".join(lines)


class AcpError(RuntimeError):
    """ACP JSON-RPC 错误，保留 code/data 以便区分“会话已被占用”等可恢复情况。"""

    def __init__(self, message: str, code: Any = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class AcpClient:
    """Minimal ACP client over newline-delimited JSON-RPC on stdio."""

    def __init__(self, cwd: str, on_update: UpdateHandler,
                 on_permission: Optional[PermissionHandler] = None,
                 on_closed: Optional[CloseHandler] = None):
        self.cwd = cwd
        self.on_update = on_update
        self.on_permission = on_permission
        self.on_closed = on_closed
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._pending: dict[int, asyncio.Future] = {}
        self._reader: Optional[asyncio.Task] = None
        self._stderr: Optional[asyncio.Task] = None
        self._closed = False
        self.session_ids: Set[str] = set()

    async def start(self) -> None:
        env = os.environ.copy()
        env["ELECTRON_RUN_AS_NODE"] = "1"
        env.setdefault("OLLAMA_API_KEY", "ollama")
        if os.path.isfile(_DSH_NODE) and os.path.isfile(_DSH_JS):
            argv = [_DSH_NODE, _DSH_JS]
        else:
            argv = [_DSH_EXE, "--expose-internals", _DSH_JS]
        self.proc = await asyncio.create_subprocess_exec(
            *argv, "--profile", "acp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd, env=env,
        )
        self._reader = asyncio.create_task(self._read_loop())
        self._stderr = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                return
            sys.stderr.write("[acp] " + line.decode("utf-8", "replace"))
            sys.stderr.flush()

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if "id" in message and ("result" in message or "error" in message):
                future = self._pending.pop(int(message["id"]), None)
                if future and not future.done():
                    if "error" in message:
                        error = message.get("error") or {}
                        future.set_exception(AcpError(
                            str(error.get("message") or "ACP error"),
                            code=error.get("code"),
                            data=error.get("data"),
                        ))
                    else:
                        future.set_result(message.get("result"))
                continue
            method = message.get("method")
            if method == "session/update":
                try:
                    await self.on_update(message.get("params") or {})
                except Exception:  # noqa: BLE001
                    pass
            elif method == "session/request_permission":
                params = message.get("params") or {}
                option_id = "reject-once"
                if self.on_permission:
                    try:
                        option_id = await self.on_permission(params)
                    except Exception:  # noqa: BLE001
                        option_id = "reject-once"
                await self._reply(message["id"], {"outcome": {"outcome": "selected", "optionId": option_id}})
        # stdout 结束说明 ACP 进程已经退出；通知运行时，避免留下“假在线”的会话。
        if not self._closed:
            self._closed = True
            if self.on_closed:
                try:
                    await asyncio.wait_for(self.on_closed("对话进程已意外结束"), timeout=2.0)
                except Exception:  # noqa: BLE001
                    pass

    async def _reply(self, request_id: Any, result: dict) -> None:
        await self._send({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def _send(self, message: dict) -> None:
        if self._closed or self.proc is None or self.proc.stdin is None:
            raise RuntimeError("ACP 进程未启动")
        self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    async def request(self, method: str, params: dict, timeout: float = 120.0) -> Any:
        request_id = uuid.uuid4().int >> 96
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(future, timeout)

    async def notify(self, method: str, params: dict) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def close(self, reason: str = "") -> None:
        if reason and self.on_closed and not self._closed:
            try:
                await asyncio.wait_for(self.on_closed(reason), timeout=1.0)
            except Exception:  # noqa: BLE001
                pass
        self._closed = True
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=8)
            except Exception:  # noqa: BLE001
                try:
                    self.proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        for task in (self._reader, self._stderr):
            if task:
                task.cancel()


def _mcp_servers() -> list:
    return [{
        "name": "structural_inspection",
        "command": _PYTHON,
        "args": ["-u", _MCP_SERVER],
        "env": [
            {"name": "PYTHONIOENCODING", "value": "utf-8"},
            {"name": "PYTHONUTF8", "value": "1"},
            {"name": "STRUCTURAL_API_BASE", "value": "http://127.0.0.1:8765/api"},
        ],
    }]


# 同一后端进程内的 ACP 会话归属表。DSH 的 session 同一时刻只允许一个写句柄；
# 浏览器刷新/多标签会各自拉起一个 ACP 进程，恢复旧会话前必须先释放旧句柄。
_CLIENTS: Dict[int, AcpClient] = {}
_SESSION_OWNERS: Dict[str, AcpClient] = {}
_REGISTRY_LOCK: Optional[asyncio.Lock] = None


def _registry_lock() -> asyncio.Lock:
    global _REGISTRY_LOCK
    if _REGISTRY_LOCK is None:
        _REGISTRY_LOCK = asyncio.Lock()
    return _REGISTRY_LOCK


async def _claim_session(client: AcpClient, session_id: str) -> None:
    if not session_id:
        return
    async with _registry_lock():
        client.session_ids.add(session_id)
        _SESSION_OWNERS[session_id] = client
        _CLIENTS[id(client)] = client


async def _forget_session(client: AcpClient, session_id: str) -> None:
    if not session_id:
        return
    async with _registry_lock():
        client.session_ids.discard(session_id)
        if _SESSION_OWNERS.get(session_id) is client:
            _SESSION_OWNERS.pop(session_id, None)


async def _release_client(client: AcpClient) -> None:
    async with _registry_lock():
        for session_id in list(client.session_ids):
            if _SESSION_OWNERS.get(session_id) is client:
                _SESSION_OWNERS.pop(session_id, None)
        client.session_ids.clear()
        if _CLIENTS.get(id(client)) is client:
            _CLIENTS.pop(id(client), None)


def _error_text(exc: Exception) -> str:
    data = getattr(exc, "data", None)
    if data is not None:
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return str(data)
    return str(exc)


def _is_write_lock(exc: Exception) -> bool:
    return "active write handle" in _error_text(exc).lower()


def _resume_error_message(exc: Exception) -> str:
    if _is_write_lock(exc):
        return "该会话正在另一个窗口中使用，无法自动接管。请关闭其他标签页后重试。"
    return str(exc)


async def _takeover_session(client: AcpClient, session_id: str) -> bool:
    """若目标会话被本后端另一个 ACP 进程占用，关闭旧进程以释放写句柄。

    常驻 runtime 正在后台执行任务时不能抢占；否则会把用户已经启动的任务杀掉。
    """
    async with _registry_lock():
        owner = _SESSION_OWNERS.get(session_id)
    if not owner or owner is client:
        return False
    for runtime in list(_RUNTIMES.values()):
        if runtime.client is owner and runtime.busy:
            raise RuntimeError("该会话正在后台执行任务，暂不能接管；请等待完成或先停止。")
    target_runtime = next((rt for rt in list(_RUNTIMES.values()) if rt.client is owner), None)
    try:
        if target_runtime is not None:
            await target_runtime.broadcast({
                "type": "error",
                "message": "会话已被另一个窗口接管，请刷新页面",
            })
            await target_runtime.close()
        else:
            await owner.close(reason="会话已被另一个窗口接管，请刷新页面")
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(0.25)
    async with _registry_lock():
        if _SESSION_OWNERS.get(session_id) is owner:
            _SESSION_OWNERS.pop(session_id, None)
    return True


async def _resume_session(client: AcpClient, session_id: str) -> Any:
    params = {"sessionId": session_id, "cwd": _ROOT, "mcpServers": _mcp_servers()}
    try:
        result = await client.request("session/resume", params, timeout=120)
    except AcpError as exc:
        if not _is_write_lock(exc) or not await _takeover_session(client, session_id):
            raise
        # 旧进程退出后，DSH 释放会话句柄需要一点时间
        result = await client.request("session/resume", params, timeout=120)
    await _claim_session(client, session_id)
    return result


def _session_user(websocket: WebSocket) -> Optional[str]:
    token = websocket.cookies.get(COOKIE_NAME)
    return _verify(token) if token else None


def _package_version(profile: str, name: str) -> str:
    path = os.path.join(os.path.expanduser("~"), ".dsh", "profiles", profile,
                        "node_modules", *name.split("/"), "package.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("version") or "")
    except (OSError, json.JSONDecodeError):
        return ""


@router.get("/chat/plugins")
def chat_plugins():
    """当前产品使用的 DSH 插件 / bundle 只读清单。"""
    items = []
    home = os.path.join(os.path.expanduser("~"), ".dsh", "profiles")
    for profile in ("web", "acp"):
        pkg_path = os.path.join(home, profile, "package.json")
        try:
            with open(pkg_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        bundles = ((data.get("dsh") or {}).get("profile") or {}).get("bundles") or []
        for name in bundles:
            items.append({"name": name, "version": _package_version(profile, name),
                          "profile": profile, "kind": "bundle"})
        for name in (data.get("dependencies") or {}):
            if name in bundles:
                continue
            items.append({"name": name, "version": _package_version(profile, name),
                          "profile": profile, "kind": "插件"})
    return ok({
        "items": items,
        "mcp": {"name": "structural_inspection", "tools": 109},
    })


@router.get("/chat/memory")
def chat_memory():
    """当前工程的长期记忆：工程快照、最近报告、历史工作摘要。"""
    project = _project_name()
    payload = chat_store.memory_payload(project)
    return ok({"project": project, **(payload or {})})


# ── 常驻对话运行时：断线不中止，回合串行排队 ─────────────────────
#
# 页面只是订阅者；DSH 会话与 ACP 进程由本模块持有。浏览器刷新/切页时
# 只移除订阅，prompt 继续在后台执行，重新连接后用 transcript 续上。

_RUNTIMES: Dict[str, "ChatSessionRuntime"] = {}
_RUNTIME_LOCK: Optional[asyncio.Lock] = None
_CONNECT_LOCK: Optional[asyncio.Lock] = None


def _runtime_lock() -> asyncio.Lock:
    global _RUNTIME_LOCK
    if _RUNTIME_LOCK is None:
        _RUNTIME_LOCK = asyncio.Lock()
    return _RUNTIME_LOCK


def _connect_lock() -> asyncio.Lock:
    global _CONNECT_LOCK
    if _CONNECT_LOCK is None:
        _CONNECT_LOCK = asyncio.Lock()
    return _CONNECT_LOCK


def _epoch(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number / 1000.0 if number > 1e12 else number


def _find_runtime(session_id: str) -> Optional["ChatSessionRuntime"]:
    sid = str(session_id or "")
    runtime = _RUNTIMES.get(sid)
    if runtime is None or runtime.closed:
        return None
    return runtime


async def _register_runtime(runtime: "ChatSessionRuntime") -> None:
    async with _runtime_lock():
        current = _RUNTIMES.get(runtime.session_id)
        if current is not None and current is not runtime:
            raise RuntimeError("该会话已有正在运行的对话进程")
        _RUNTIMES[runtime.session_id] = runtime


async def _unregister_runtime(runtime: "ChatSessionRuntime") -> None:
    async with _runtime_lock():
        for sid, item in list(_RUNTIMES.items()):
            if item is runtime:
                _RUNTIMES.pop(sid, None)


async def _move_runtime(runtime: "ChatSessionRuntime", session_id: str) -> None:
    async with _runtime_lock():
        current = _RUNTIMES.get(session_id)
        if current is not None and current is not runtime:
            raise RuntimeError("该会话已有正在运行的对话进程")
        for sid, item in list(_RUNTIMES.items()):
            if item is runtime:
                _RUNTIMES.pop(sid, None)
        _RUNTIMES[session_id] = runtime


def _latest_session_local(project: str) -> str:
    """只读本地元数据选最近会话，避免为了“恢复”先启动一个 ACP 进程。"""
    if not project:
        return ""
    candidates = []
    meta = _load_meta()
    for sid, entry in meta.items():
        if not isinstance(entry, dict) or entry.get("hidden"):
            continue
        if str(entry.get("project") or "").strip() != project:
            continue
        transcript = chat_store.load_transcript(sid)
        if not (transcript.get("messages") or []):
            continue
        updated = max(_epoch(entry.get("updatedAt")), _epoch(transcript.get("updatedAt")))
        candidates.append((updated, sid))
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[0])[1]


class ChatSessionRuntime:
    """一个 DSH 会话的常驻运行时；WebSocket 断开不结束当前回合。"""

    def __init__(self, project: str):
        self.project = str(project or "未命名工程")
        self.session_id = ""
        self.client: Optional[AcpClient] = None
        self.config_options: list = []
        self.transcript: dict = {}
        self.turn: dict = {}
        self.subscribers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self.pending_permissions: Dict[str, dict] = {}
        self.queue: list = []
        self.usage: dict = {}
        self.prompt_task: Optional[asyncio.Task] = None
        self.current_job: Optional[dict] = None
        self.closed = False
        self.idle_task: Optional[asyncio.Task] = None
        self.is_new_session = True
        self.title_text = ""
        self.created_at = time.time()
        self.last_active = self.created_at
        self._op_lock = asyncio.Lock()

    # ── 基础状态 ──────────────────────────────────────────────
    @property
    def busy(self) -> bool:
        return bool(self.current_job) or bool(self.queue)

    @property
    def assistant_id(self) -> str:
        return str(self.turn.get("assistant_id") or "")

    def history_view(self) -> dict:
        data = self.transcript or chat_store.load_transcript(self.session_id)
        messages = []
        for item in (data.get("messages") or [])[-300:]:
            view = dict(item)
            view["text"] = str(view.get("text") or "")[:20000]
            messages.append(view)
        return {
            "messages": messages,
            "tools": (data.get("tools") or [])[-120:],
            "plan": (data.get("plan") or [])[-50:],
            "summary": data.get("summary") or "",
            "title": data.get("title") or self.title_text,
        }

    def memory_count(self) -> int:
        try:
            project = _project_name() or self.project
            return len(chat_store.load_memory(project).get("facts") or [])
        except Exception:  # noqa: BLE001
            return 0

    def snapshot(self) -> dict:
        self.transcript = self.transcript or chat_store.load_transcript(self.session_id)
        return {
            "sessionId": self.session_id,
            "title": self.title_text or str(_session_meta(self.session_id).get("title") or ""),
            "project": self.project,
            "configOptions": self.config_options,
            "resumed": not self.is_new_session,
            "history": self.history_view(),
            "memoryCount": self.memory_count(),
            "busy": self.busy,
            "queue": len(self.queue),
            "assistantId": self.assistant_id,
            "usage": self.usage,
        }

    # ── 订阅者 ────────────────────────────────────────────────
    async def _broadcast(self, payload: dict) -> None:
        items = list(self.subscribers.items())
        if not items:
            return

        async def one(token: str, sender: Callable[[dict], Awaitable[None]]) -> None:
            try:
                await asyncio.wait_for(sender(payload), timeout=8.0)
            except Exception:  # noqa: BLE001
                self.subscribers.pop(token, None)

        await asyncio.gather(*(one(token, sender) for token, sender in items))

    def attach(self, token: str, sender: Callable[[dict], Awaitable[None]]) -> None:
        self.subscribers[token] = sender
        self.last_active = time.time()
        if self.idle_task is not None:
            self.idle_task.cancel()
            self.idle_task = None

    def detach(self, token: str) -> None:
        self.subscribers.pop(token, None)
        self.last_active = time.time()
        if not self.subscribers and not self.busy:
            self._schedule_idle()

    async def replay_permissions(self, token: str) -> None:
        sender = self.subscribers.get(token)
        if sender is None:
            return
        for permission_id, item in list(self.pending_permissions.items()):
            try:
                await asyncio.wait_for(sender({
                    "type": "permission_request",
                    "id": permission_id,
                    "params": item.get("params") or {},
                }), timeout=5.0)
            except Exception:  # noqa: BLE001
                return

    def _schedule_idle(self, seconds: float = 120.0) -> None:
        if self.closed or self.busy or self.subscribers:
            return
        if self.idle_task is not None:
            self.idle_task.cancel()

        async def waiter() -> None:
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                return
            self.idle_task = None
            if not self.closed and not self.busy and not self.subscribers:
                await self.close()

        self.idle_task = asyncio.create_task(waiter())

    # ── 会话记录 ──────────────────────────────────────────────
    def _save_turn(self, force: bool = False) -> None:
        data = self.turn.get("transcript")
        if not data or not self.session_id:
            return
        now = time.time()
        if not force and now - float(self.turn.get("last_save") or 0) < 0.8:
            return
        self.turn["last_save"] = now
        try:
            chat_store.save_transcript(self.session_id, data)
        except Exception:  # noqa: BLE001
            pass

    def _ensure_assistant_message(self) -> str:
        data = self.turn.get("transcript")
        if not data:
            return ""
        message_id = str(self.turn.get("assistant_id") or "")
        if message_id and any(m.get("id") == message_id for m in data.get("messages") or []):
            return message_id
        message_id = "a-" + uuid.uuid4().hex[:12]
        data.setdefault("messages", []).append({
            "id": message_id,
            "role": "assistant",
            "text": "",
            "streaming": True,
            "at": time.time(),
        })
        self.turn["assistant_id"] = message_id
        return message_id

    def _update_assistant_text(self, text: str) -> None:
        data = self.turn.get("transcript")
        if not data or not text:
            return
        message_id = self._ensure_assistant_message()
        for item in data.get("messages") or []:
            if item.get("id") == message_id:
                item["text"] = str(item.get("text") or "") + text
                break
        self._save_turn()

    def _update_assistant_thinking(self, text: str) -> None:
        """思考过程与正文分开保存，恢复会话后仍能回看。"""
        data = self.turn.get("transcript")
        if not data or not text:
            return
        message_id = self._ensure_assistant_message()
        for item in data.get("messages") or []:
            if item.get("id") == message_id:
                item["thinking"] = str(item.get("thinking") or "") + text
                break
        self._save_turn()

    async def on_update(self, params: dict) -> None:
        update = (params or {}).get("update") or {}
        kind = update.get("sessionUpdate")
        data = self.turn.get("transcript")
        if data:
            if kind == "agent_message_chunk":
                content = update.get("content") or {}
                text = content.get("text") if isinstance(content, dict) else ""
                if isinstance(text, str):
                    self._update_assistant_text(text)
            elif kind == "agent_thought_chunk":
                content = update.get("content") or {}
                text = content.get("text") if isinstance(content, dict) else ""
                if isinstance(text, str):
                    self._update_assistant_thinking(text)
            elif kind == "usage_update":
                # 上下文用量：最新值留在运行时与快照里，断线重连后仍可见。
                try:
                    self.usage = {
                        "used": int(update.get("used") or 0),
                        "size": int(update.get("size") or 0),
                    }
                except (TypeError, ValueError):
                    pass
            elif kind in ("tool_call", "tool_call_update"):
                tool_id = str(update.get("toolCallId") or update.get("id") or "")
                if tool_id:
                    raw = update.get("rawInput")
                    if raw is None:
                        raw = update.get("rawOutput")
                    if raw is None:
                        raw = update.get("content")
                    detail = ""
                    if raw is not None:
                        try:
                            detail = json.dumps(raw, ensure_ascii=False)[:3000]
                        except Exception:  # noqa: BLE001
                            detail = str(raw)[:3000]
                    items = data.setdefault("tools", [])
                    target = next((x for x in items if x.get("id") == tool_id), None)
                    if target is None:
                        target = {"id": tool_id, "at": time.time()}
                        items.append(target)
                    target["title"] = update.get("title") or target.get("title") or "工具调用"
                    target["status"] = update.get("status") or target.get("status") or "pending"
                    target["kind"] = update.get("kind") or target.get("kind") or ""
                    if detail:
                        target["detail"] = detail
                    data["tools"] = items[-120:]
                    self._save_turn()
            elif kind == "plan":
                entries = update.get("entries")
                if isinstance(entries, list):
                    data["plan"] = entries
                    self._save_turn(force=True)
        await self._broadcast({"type": "update", "params": params})

    async def on_permission(self, params: dict) -> str:
        if self.closed:
            return "reject-once"
        permission_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending_permissions[permission_id] = {
            "future": future,
            "params": params,
            "at": time.time(),
        }
        await self._broadcast({
            "type": "permission_request",
            "id": permission_id,
            "params": params,
        })
        try:
            return await asyncio.wait_for(future, timeout=300)
        except Exception:  # noqa: BLE001
            return "reject-once"
        finally:
            self.pending_permissions.pop(permission_id, None)

    def answer_permission(self, permission_id: str, allow: bool) -> None:
        item = self.pending_permissions.get(str(permission_id or ""))
        if not item:
            return
        future = item.get("future")
        if future and not future.done():
            future.set_result("allow-once" if allow else "reject-once")

    async def on_closed(self, reason: str) -> None:
        if self.closed:
            return
        self.closed = True
        await self._unregister()
        message = str(reason or "对话进程已结束")
        await self._broadcast({"type": "error", "message": message})
        await self._broadcast({"type": "closed", "reason": message})

    async def _unregister(self) -> None:
        await _unregister_runtime(self)

    # ── 任务队列 ──────────────────────────────────────────────
    def _job_update(self, job: dict, **fields: Any) -> None:
        try:
            updated = chat_store.update_job(job.get("id", ""), **fields)
        except Exception:  # noqa: BLE001
            updated = None
        if updated:
            job.update(updated)

    def _ensure_worker(self) -> None:
        if self.closed:
            return
        if self.prompt_task is None or self.prompt_task.done():
            self.prompt_task = asyncio.create_task(self._drain())

    async def submit(self, text: str) -> dict:
        value = str(text or "").strip()
        if not value:
            raise RuntimeError("消息不能为空")
        if self.closed or self.client is None:
            raise RuntimeError("对话进程未就绪，请刷新页面重连")
        # 图片附件可能来自旧会话消息：发送前补齐 OCR 上下文，避免模型再次
        # 调用 read_image（文本模型会直接报错，视觉模型也可能长时间挂起）。
        try:
            base_transcript = self.transcript or chat_store.load_transcript(self.session_id)
            image_block = await _image_prompt_block(base_transcript, value)
        except Exception:  # noqa: BLE001
            image_block = ""
        async with self._op_lock:
            if len(self.queue) >= 20:
                raise RuntimeError("排队任务过多（最多 20 条），请等待当前任务完成")
            project = _project_name() or self.project
            self.project = project
            meta = _session_meta(self.session_id)
            title = str(meta.get("title") or "").strip() or value[:24]
            new_title = not str(meta.get("title") or "").strip()
            _update_session_meta(
                self.session_id, project=project, title=title, lastPrompt=value[:120])

            # 复用同一个 transcript 对象：当前回合尚未结束时新提交的消息
            # 也要写进这份对象，否则 finish_turn 保存时会覆盖掉排队消息。
            transcript = self.transcript or chat_store.load_transcript(self.session_id)
            transcript["project"] = project
            transcript["title"] = transcript.get("title") or title
            prompt_text = value
            injected = False
            prefix_parts = []
            if self.is_new_session and int(transcript.get("promptCount") or 0) == 0:
                try:
                    block = chat_store.context_block(project)
                except Exception:  # noqa: BLE001
                    block = ""
                if block:
                    prefix_parts.append(block)
            if image_block:
                prefix_parts.append(image_block)
            if prefix_parts:
                prompt_text = "\n\n".join(prefix_parts) + "\n\n【用户当前请求】\n" + value
                injected = True
            user_message = {
                "id": "u-" + uuid.uuid4().hex[:12],
                "role": "user",
                "text": value,
                "at": time.time(),
            }
            transcript.setdefault("messages", []).append(user_message)
            transcript["promptCount"] = int(transcript.get("promptCount") or 0) + 1
            transcript["summary"] = ""
            self.transcript = transcript
            self.title_text = title
            try:
                chat_store.save_transcript(self.session_id, transcript)
            except Exception:  # noqa: BLE001
                pass

            job = chat_store.create_job(self.session_id, project, value, title)
            item = {
                "job": job,
                "text": value,
                "prompt_text": prompt_text,
                "title": title,
                "injected": injected,
                "user_id": user_message["id"],
            }
            self.queue.append(item)
            self._job_update(job, queue=max(0, len(self.queue) - 1))
            self.is_new_session = False

        await self._broadcast({
            "type": "queued",
            "jobId": job["id"],
            "queue": len(self.queue),
            "title": title,
        })
        if new_title:
            await self._broadcast({
                "type": "session_title",
                "sessionId": self.session_id,
                "title": title,
            })
            asyncio.create_task(self.refresh_sessions())
        self._ensure_worker()
        return dict(job)

    async def _drain(self) -> None:
        while self.queue and not self.closed:
            item = self.queue.pop(0)
            job = item["job"]
            self.current_job = item
            self.transcript = self.transcript or chat_store.load_transcript(self.session_id)
            self.turn = {
                "active": True,
                "user": item["text"],
                "assistant_id": "",
                "transcript": self.transcript,
                "last_save": time.time(),
                "injected": item.get("injected", False),
                "started": time.time(),
            }
            self._job_update(
                job, status="running", started_at=time.time(),
                message="执行中", queue=len(self.queue))
            await self._broadcast({
                "type": "prompt_start",
                "jobId": job["id"],
                "title": item.get("title") or job.get("title") or "",
                "queue": len(self.queue),
            })
            await self.refresh_sessions()

            error = ""
            stop_reason = "end_turn"
            cancelled = False
            assistant_text = ""
            try:
                client = self.client
                if client is None:
                    raise RuntimeError("对话进程已结束")
                result = await client.request(
                    "session/prompt",
                    {"sessionId": self.session_id,
                     "prompt": [{"type": "text", "text": item["prompt_text"]}]},
                    timeout=1800,
                )
                stop_reason = str((result or {}).get("stopReason") or "end_turn")
                cancelled = stop_reason in ("cancelled", "canceled") or bool(item.get("cancel_requested"))
            except asyncio.CancelledError:
                error = "任务已取消"
                cancelled = True
            except Exception as exc:  # noqa: BLE001
                error = str(exc)[:2000]

            assistant_text = self.finish_turn(self.project, item.get("title") or "", error=error)
            now = time.time()
            if error and not cancelled:
                self._job_update(
                    job, status="failed", finished_at=now,
                    message=error, assistant=assistant_text[:1000])
                await self._broadcast({
                    "type": "error", "message": error,
                    "jobId": job["id"], "queue": len(self.queue),
                })
            else:
                status = "cancelled" if cancelled else "done"
                self._job_update(
                    job, status=status, finished_at=now,
                    message="已停止" if cancelled else "已完成",
                    assistant=assistant_text[:1000], queue=len(self.queue))
                await self._broadcast({
                    "type": "prompt_end",
                    "stopReason": "cancelled" if cancelled else stop_reason,
                    "memoryCount": self.memory_count(),
                    "jobId": job["id"],
                    "queue": len(self.queue),
                })

            self.current_job = None
            self.turn.clear()
            await self._broadcast({"type": "queue", "queue": len(self.queue)})
            await self.refresh_sessions()
            if cancelled and error == "任务已取消":
                # 强制取消后 DSH 可能仍持有写句柄，不再自动跑后续队列。
                for pending in list(self.queue):
                    self.queue.remove(pending)
                    notice = self._cancel_queued(pending)
                    await self._broadcast({
                        "type": "cancel_notice",
                        "jobId": str((pending.get("job") or {}).get("id") or ""),
                        "messageId": notice["id"],
                        "text": notice["text"],
                    })
                await self._broadcast({"type": "queue", "queue": 0})
                break
        if self.current_job is None:
            self._schedule_idle()

    def finish_turn(self, project: str, title: str, error: str = "") -> str:
        if not self.turn.get("active"):
            return ""
        data = self.turn.get("transcript") or {}
        assistant_text = ""
        message_id = str(self.turn.get("assistant_id") or "")
        if error:
            if not message_id:
                message_id = "a-" + uuid.uuid4().hex[:12]
                data.setdefault("messages", []).append({
                    "id": message_id,
                    "role": "assistant",
                    "text": "对话失败：" + error,
                    "error": True,
                    "at": time.time(),
                })
            else:
                for item in data.get("messages") or []:
                    if item.get("id") == message_id:
                        item["error"] = True
                        if not item.get("text"):
                            item["text"] = "对话失败：" + error
                        break
        for item in data.get("messages") or []:
            if item.get("id") == message_id:
                item["streaming"] = False
                assistant_text = str(item.get("text") or "")
                break
        try:
            chat_store.save_transcript(self.session_id, data)
        except Exception:  # noqa: BLE001
            pass
        try:
            chat_store.record_turn_memory(
                project, self.session_id, title,
                str(self.turn.get("user") or ""), assistant_text)
        except Exception:  # noqa: BLE001
            pass
        self.turn.clear()
        self.is_new_session = False
        return assistant_text

    def _cancel_queued(self, item: dict) -> dict:
        job = item.get("job") or {}
        now = time.time()
        self._job_update(
            job, status="cancelled", finished_at=now,
            message="已取消", queue=0)
        data = self.transcript or chat_store.load_transcript(self.session_id)
        notice = {
            "id": "a-" + uuid.uuid4().hex[:12],
            "role": "assistant",
            "text": "已取消",
            "at": now,
        }
        data.setdefault("messages", []).append(notice)
        try:
            chat_store.save_transcript(self.session_id, data)
        except Exception:  # noqa: BLE001
            pass
        return notice

    async def cancel(self, job_id: str = "") -> int:
        target = str(job_id or "")
        cancelled = 0
        current_hit = False
        async with self._op_lock:
            if target:
                for item in list(self.queue):
                    if str((item.get("job") or {}).get("id")) == target:
                        self.queue.remove(item)
                        notice = self._cancel_queued(item)
                        await self._broadcast({
                            "type": "cancel_notice",
                            "jobId": str(item["job"].get("id") or ""),
                            "messageId": notice["id"],
                            "text": notice["text"],
                        })
                        cancelled += 1
                if self.current_job and str(self.current_job["job"].get("id")) == target:
                    current_hit = True
            else:
                for item in list(self.queue):
                    self.queue.remove(item)
                    notice = self._cancel_queued(item)
                    await self._broadcast({
                        "type": "cancel_notice",
                        "jobId": str(item["job"].get("id") or ""),
                        "messageId": notice["id"],
                        "text": notice["text"],
                    })
                    cancelled += 1
                current_hit = bool(self.current_job)
            if current_hit and self.current_job:
                item = self.current_job
                item["cancel_requested"] = True
                self._job_update(item["job"], message="正在停止")
                try:
                    if self.client is not None:
                        await self.client.notify("session/cancel", {"sessionId": self.session_id})
                except Exception:  # noqa: BLE001
                    pass
                asyncio.create_task(self._force_cancel(str(item["job"].get("id") or ""), 20.0))
        await self._broadcast({
            "type": "queue", "queue": len(self.queue), "cancelled": cancelled,
            "busy": bool(self.current_job)})
        return cancelled + (1 if current_hit else 0)

    async def _force_cancel(self, job_id: str, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        current = self.current_job
        if (current and str(current["job"].get("id")) == str(job_id)
                and self.prompt_task is not None and not self.prompt_task.done()):
            self.prompt_task.cancel()

    async def set_model(self, value: Any) -> list:
        if self.client is None:
            raise RuntimeError("对话进程已结束")
        result = await self.client.request(
            "session/set_config_option",
            {"sessionId": self.session_id, "configId": "model", "value": value},
            timeout=60,
        )
        self.config_options = (result or {}).get("configOptions") or []
        await self._broadcast({
            "type": "config", "configOptions": self.config_options})
        return self.config_options

    async def refresh_sessions(self) -> None:
        client = self.client
        if client is None or self.closed:
            return
        try:
            result = await client.request("session/list", {"cwd": _ROOT}, timeout=30)
            items = []
            for item in (result or {}).get("sessions") or []:
                sid = str(item.get("sessionId") or "")
                meta = _session_meta(sid)
                if meta.get("hidden"):
                    continue
                live = _find_runtime(sid)
                items.append({
                    **item,
                    "title": meta.get("title") or "",
                    "project": meta.get("project") or "",
                    "updatedAt": meta.get("updatedAt") or item.get("updatedAt") or 0,
                    "busy": bool(live and live.busy),
                    "queue": len(live.queue) if live else 0,
                })
            # DSH 的 session/list 在回合取消/结束的瞬间偶尔会漏掉刚结束的会话，
            # 这里补回仍由本后端持有的运行时，避免左侧历史行短暂消失。
            seen = {str(item.get("sessionId") or "") for item in items}
            for sid, live in list(_RUNTIMES.items()):
                if sid in seen or live.closed:
                    continue
                meta = _session_meta(sid)
                items.append({
                    "sessionId": sid,
                    "title": meta.get("title") or "",
                    "project": meta.get("project") or "",
                    "updatedAt": meta.get("updatedAt") or 0,
                    "busy": bool(live.busy),
                    "queue": len(live.queue),
                })
            items.sort(key=lambda item: float(item.get("updatedAt") or 0), reverse=True)
            payload = {"type": "sessions", "items": items}
            # 会话列表是全局的：任何会话开始/结束都应通知所有已打开页面，
            # 否则用户切到 B 后，A 完成后左侧运行点不会消失。
            for runtime in list(_RUNTIMES.values()):
                await runtime._broadcast(payload)
        except Exception:  # noqa: BLE001
            pass

    # ── 切换会话 ──────────────────────────────────────────────
    async def new_session(self) -> dict:
        async with self._op_lock:
            if self.busy or self.closed or self.client is None:
                raise RuntimeError("当前回合尚未结束，请先停止或等待完成")
            client = self.client
            session = await client.request(
                "session/new", {"cwd": _ROOT, "mcpServers": _mcp_servers()}, timeout=120)
            session_id = str(session.get("sessionId") or "")
            if not session_id:
                raise RuntimeError("创建会话失败")
            await _claim_session(client, session_id)
            previous = self.session_id
            self.session_id = session_id
            self.is_new_session = True
            self.config_options = (session or {}).get("configOptions") or []
            self.transcript = chat_store.load_transcript(session_id)
            self.title_text = ""
            self.turn.clear()
            self.usage = {}
            await _move_runtime(self, session_id)
            if previous and previous != session_id:
                try:
                    await client.request("session/close", {"sessionId": previous}, timeout=10)
                except Exception:  # noqa: BLE001
                    pass
                await _forget_session(client, previous)
            if not _session_meta(session_id).get("project"):
                _update_session_meta(session_id, project=_project_name())
        return self.snapshot()

    async def resume_session(self, target: str) -> dict:
        target = str(target or "")
        if not target:
            raise RuntimeError("会话 ID 为空")
        async with self._op_lock:
            if self.busy or self.closed or self.client is None:
                raise RuntimeError("当前回合尚未结束，请先停止或等待完成")
            if target == self.session_id:
                return self.snapshot()
            client = self.client
            result = await _resume_session(client, target)
            previous = self.session_id
            self.session_id = target
            self.is_new_session = False
            self.config_options = (result or {}).get("configOptions") or []
            self.transcript = chat_store.load_transcript(target)
            self.title_text = str(_session_meta(target).get("title") or "")
            self.turn.clear()
            self.usage = {}
            await _move_runtime(self, target)
            if previous and previous != target:
                try:
                    await client.request("session/close", {"sessionId": previous}, timeout=10)
                except Exception:  # noqa: BLE001
                    pass
                await _forget_session(client, previous)
            _update_session_meta(target, project=_project_name())
        return self.snapshot()

    # ── 关闭 ──────────────────────────────────────────────────
    async def close(self) -> None:
        if self.closed and self.client is None:
            return
        self.closed = True
        if self.idle_task is not None:
            self.idle_task.cancel()
            self.idle_task = None
        for item in list(self.queue):
            self.queue.remove(item)
            self._cancel_queued(item)
        if self.current_job:
            self._job_update(
                self.current_job["job"], status="interrupted",
                finished_at=time.time(), message="对话进程已关闭")
            self.current_job = None
        if self.prompt_task is not None and not self.prompt_task.done():
            try:
                if self.client is not None:
                    await self.client.notify("session/cancel", {"sessionId": self.session_id})
            except Exception:  # noqa: BLE001
                pass
            self.prompt_task.cancel()
        for permission_id, item in list(self.pending_permissions.items()):
            future = item.get("future")
            if future and not future.done():
                future.set_result("reject-once")
            self.pending_permissions.pop(permission_id, None)
        client = self.client
        self.client = None
        await _unregister_runtime(self)
        if client is not None:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass
            await _release_client(client)
        await self._broadcast({"type": "closed", "reason": "对话进程已关闭"})


async def _create_runtime(project: str, target: str = "") -> ChatSessionRuntime:
    runtime = ChatSessionRuntime(project)
    client = AcpClient(_ROOT, runtime.on_update, runtime.on_permission,
                       on_closed=runtime.on_closed)
    runtime.client = client
    try:
        await client.start()
        await client.request(
            "initialize", {"protocolVersion": 1, "clientCapabilities": {}}, timeout=60)
        if target:
            result = await _resume_session(client, target)
            runtime.session_id = target
            runtime.is_new_session = False
            runtime.config_options = (result or {}).get("configOptions") or []
            _update_session_meta(target, project=project)
        else:
            session = await client.request(
                "session/new", {"cwd": _ROOT, "mcpServers": _mcp_servers()}, timeout=120)
            runtime.session_id = str(session.get("sessionId") or "")
            if not runtime.session_id:
                raise RuntimeError("创建会话失败")
            await _claim_session(client, runtime.session_id)
            runtime.is_new_session = True
            runtime.config_options = (session or {}).get("configOptions") or []
            if not _session_meta(runtime.session_id).get("project"):
                _update_session_meta(runtime.session_id, project=project)
        runtime.transcript = chat_store.load_transcript(runtime.session_id)
        runtime.title_text = str(_session_meta(runtime.session_id).get("title") or "")
        await _register_runtime(runtime)
        return runtime
    except Exception:
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            pass
        await _release_client(client)
        raise


async def _open_runtime(
        project: str, target: str = "", fallback: bool = True) -> ChatSessionRuntime:
    """取得目标会话的常驻 runtime；已有实例优先，避免重复拉起 ACP。

    切换会话时不再复用并关闭当前 runtime：旧 runtime 留在后台继续执行，
    新会话另起一个 runtime，因此不同会话可以并行。target 恢复失败时，
    自动恢复可以回退到新会话；手动切换传 fallback=False，保留当前对话。
    """
    async with _connect_lock():
        if target:
            existing = _find_runtime(target)
            if existing is not None:
                return existing
        try:
            return await _create_runtime(project, target)
        except Exception:
            if not target or not fallback:
                raise
            existing = _find_runtime(target)
            if existing is not None:
                return existing
            return await _create_runtime(project, "")


@router.get("/chat/jobs")
def chat_jobs(limit: int = 12):
    """对话任务记录；运行中的任务来自常驻 runtime，断线后仍可观察。"""
    try:
        size = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        size = 12
    items = chat_store.list_jobs(size)
    for item in items:
        runtime = _find_runtime(item.get("session_id") or "")
        if runtime is None:
            continue
        item["live"] = True
        item["queue"] = len(runtime.queue)
        current = runtime.current_job
        if current and str(current["job"].get("id")) == str(item.get("id")):
            item["status"] = "running"
            item["message"] = "执行中"
    return ok({"items": items, "total": len(items)})


@router.post("/chat/jobs/{job_id}/cancel")
async def cancel_chat_job(job_id: str):
    """停止一个对话任务：排队中的立即移除，执行中的向 DSH 发 session/cancel。"""
    job = chat_store.get_job(job_id)
    if not job:
        raise ApiError("对话任务不存在", 404)
    runtime = _find_runtime(job.get("session_id") or "")
    if runtime is not None:
        await runtime.cancel(job_id)
    elif job.get("status") in ("queued", "running"):
        chat_store.update_job(
            job_id, status="cancelled", message="已取消", finished_at=time.time())
    return ok(chat_store.get_job(job_id))


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket):
    username = _session_user(websocket)
    if not username:
        await websocket.close(code=1008)
        return
    await websocket.accept()

    send_lock = asyncio.Lock()
    token = uuid.uuid4().hex
    runtime: Optional[ChatSessionRuntime] = None

    async def send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def send_ready(target: ChatSessionRuntime, kind: str = "ready") -> None:
        payload = target.snapshot()
        payload.update({"type": kind, "user": username})
        await send(payload)

    try:
        project = _project_name()
        auto_resume = str(websocket.query_params.get("resume") or "1") != "0"
        target = str(websocket.query_params.get("session") or "").strip()
        if not target and auto_resume:
            target = _latest_session_local(project)

        runtime = await _open_runtime(project, target)

        runtime.attach(token, send)
        await send_ready(runtime, "resumed" if target and not runtime.is_new_session else "ready")
        await runtime.replay_permissions(token)
        await runtime.refresh_sessions()

        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind == "prompt":
                text = str(message.get("text") or "").strip()
                if not text:
                    continue
                try:
                    await runtime.submit(text)
                except Exception as exc:  # noqa: BLE001
                    await send({"type": "error", "message": str(exc)})
            elif kind == "cancel":
                try:
                    await runtime.cancel()
                except Exception:  # noqa: BLE001
                    pass
            elif kind == "permission_response":
                runtime.answer_permission(
                    str(message.get("id") or ""), bool(message.get("allow")))
            elif kind == "set_model":
                try:
                    await runtime.set_model(message.get("value"))
                except Exception as exc:  # noqa: BLE001
                    await send({"type": "error", "message": str(exc)})
            elif kind == "list_sessions":
                await runtime.refresh_sessions()
            elif kind == "new_session":
                try:
                    fresh = await _open_runtime(project, "")
                    runtime.detach(token)
                    runtime = fresh
                    runtime.attach(token, send)
                    await send_ready(runtime, "ready")
                    await runtime.refresh_sessions()
                except Exception as exc:  # noqa: BLE001
                    await send({"type": "error", "message": "新建会话失败：" + str(exc)})
            elif kind == "rename_session":
                target_id = str(message.get("sessionId") or "")
                title = str(message.get("title") or "").strip()
                if target_id and title:
                    _update_session_meta(target_id, title=title[:40])
                    await send({"type": "session_title", "sessionId": target_id, "title": title[:40]})
                    await runtime.refresh_sessions()
            elif kind == "delete_session":
                target_id = str(message.get("sessionId") or "")
                if not target_id:
                    continue
                if target_id == runtime.session_id:
                    await send({"type": "error", "message": "不能删除当前正在使用的会话"})
                    continue
                other = _find_runtime(target_id)
                if other is not None and other.busy:
                    await send({"type": "error", "message": "该会话正在后台执行任务，暂不能删除"})
                    continue
                if other is not None:
                    await other.close()
                _hide_session(target_id)
                await runtime.refresh_sessions()
            elif kind == "resume":
                target_id = str(message.get("sessionId") or "")
                if not target_id:
                    continue
                if target_id == runtime.session_id:
                    await send_ready(runtime, "resumed")
                    continue
                existing = _find_runtime(target_id)
                if existing is not None:
                    if existing is not runtime:
                        runtime.detach(token)
                        runtime = existing
                        runtime.attach(token, send)
                    await send_ready(runtime, "resumed")
                    await runtime.replay_permissions(token)
                    await runtime.refresh_sessions()
                    continue
                try:
                    # 不复用当前 runtime：旧会话留在后台继续跑，目标会话另起进程。
                    target_runtime = await _open_runtime(
                        project, target_id, fallback=False)
                    runtime.detach(token)
                    runtime = target_runtime
                    runtime.attach(token, send)
                    await send_ready(
                        runtime, "resumed" if not runtime.is_new_session else "ready")
                    await runtime.replay_permissions(token)
                    await runtime.refresh_sessions()
                except Exception as exc:  # noqa: BLE001
                    await send({
                        "type": "error",
                        "message": "恢复会话失败：" + _resume_error_message(exc),
                    })
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            await send({"type": "error", "message": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        if runtime is not None:
            runtime.detach(token)
