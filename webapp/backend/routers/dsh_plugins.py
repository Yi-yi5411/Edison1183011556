# -*- coding: utf-8 -*-
"""DSH 原生能力/插件清单：把 Harness 的 bundle、能力与插件市场入口暴露给插件中心。"""
import json
import os

from fastapi import APIRouter

router = APIRouter(tags=["plugins"])

PROFILE_IDS = ("web", "acp")

CAPABILITIES = [
    {"key": "agent_loop", "title": "Agent 循环", "module": "dsh-agent-loop",
     "desc": "会话内的自主规划、工具调用与回合推进", "surface": "DSH ACP"},
    {"key": "subagent", "title": "子智能体", "module": "dsh-agent-team",
     "desc": "委派并行子任务、汇总结果", "surface": "DSH 原生"},
    {"key": "web_search", "title": "网页搜索", "module": "dsh-tool-web",
     "desc": "联网检索并引用来源", "surface": "DSH Web/ACP"},
    {"key": "web_fetch", "title": "网页获取", "module": "dsh-web-fetch-http",
     "desc": "抓取指定 URL 的正文内容", "surface": "DSH 原生"},
    {"key": "terminal", "title": "终端", "module": "dsh-tool-terminal",
     "desc": "受权限控制的 shell 命令执行", "surface": "DSH 原生"},
    {"key": "voice", "title": "语音输入", "module": "dsh-experimental-voice-input-bundle",
     "desc": "语音转文字输入（需 DSH Web 前端）", "surface": "DSH Web"},
    {"key": "plugin_market", "title": "插件市场", "module": "dsh-plugin-market",
     "desc": "DSH 原生插件索引与外部安装", "surface": "DSH Web"},
    {"key": "authorization", "title": "自动授权审查", "module": "dsh-authorization",
     "desc": "权限预设、逐次确认与自动审查", "surface": "DSH 原生"},
    {"key": "worktree", "title": "工作树 / 变更请求", "module": "dsh-workspace-changes",
     "desc": "代码工作树与变更审阅", "surface": "DSH 代码工作区"},
]


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _profile_record(home, profile_id):
    base = os.path.join(home, ".dsh", "profiles", profile_id)
    pkg = _read_json(os.path.join(base, "package.json"))
    meta = (pkg.get("dsh") or {}).get("profile") or {}
    bundles = list(meta.get("bundles") or [])
    deps = dict(pkg.get("dependencies") or {})
    return {
        "id": profile_id,
        "name": pkg.get("name") or ("dsh-profile-" + profile_id),
        "path": base,
        "exists": os.path.isdir(base),
        "bundles": bundles,
        "dependencies": deps,
        "cordis_path": os.path.join(base, "cordis.patch.yml"),
        "cordis_exists": os.path.isfile(os.path.join(base, "cordis.patch.yml")),
    }


@router.get("/plugins/dsh")
def dsh_plugins():
    """DSH 原生能力清单、profile bundle、插件市场入口与可达性。"""
    try:
        from structural_config import get as cfg_get
    except ImportError:  # pragma: no cover
        def cfg_get(section, key, default=None):
            return default
    home = os.path.expanduser("~")
    profiles = [_profile_record(home, pid) for pid in PROFILE_IDS]
    gui_url = str(cfg_get("dsh", "gui_url", "http://127.0.0.1:3642")).rstrip("/")
    installed_bundles = sorted({b for p in profiles for b in p["bundles"]})
    capabilities = []
    for cap in CAPABILITIES:
        capabilities.append({
            **cap,
            "available": True,
            "source": "DSH",
            "note": "由 DSH 原生提供；在 DSH 工作台配置/使用",
        })
    return {
        "ok": True,
        "data": {
            "gui_url": gui_url,
            "profiles": profiles,
            "bundles": installed_bundles,
            "capabilities": capabilities,
            "plugin_dir": os.path.join(home, ".dsh", "plugins"),
            "market_hint": "插件市场与外部安装使用 DSH 原生插件管理器；本页只做入口和状态展示。",
            "agent_surface": "dsh",
        },
        "message": "DSH 能力清单读取成功",
    }


@router.get("/plugins/dsh/status")
def dsh_status():
    """DSH 是否可达（复用 /api/system/dsh 的探测逻辑）。"""
    try:
        import requests
        try:
            from structural_config import get as cfg_get
        except ImportError:  # pragma: no cover
            def cfg_get(section, key, default=None):
                return default
        url = str(cfg_get("dsh", "gui_url", "http://127.0.0.1:3642")).rstrip("/")
        response = requests.get(url + "/", timeout=3, allow_redirects=False)
        return {"ok": True, "data": {
            "url": url,
            "reachable": True,
            "status": response.status_code,
            "auth_required": response.status_code in (301, 302, 303, 401),
        }, "message": "DSH 状态读取成功"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "data": {
            "url": str(cfg_get("dsh", "gui_url", "http://127.0.0.1:3642")),
            "reachable": False,
            "status": 0,
            "error": str(exc)[:200],
        }, "message": "DSH 未启动或不可达"}


# ── DSH Host API：真实插件市场/插件管理 ──────────────────────────────

from pydantic import BaseModel  # noqa: E402

from deps import ok  # noqa: E402


class HostConfigBody(BaseModel):
    base_url: str = ""
    token: str = ""


class IndexesBody(BaseModel):
    urls: list = []


class SearchBody(BaseModel):
    url: str
    text: str = ""
    limit: int = 30


class InspectBody(BaseModel):
    spec: str


class InstallBody(BaseModel):
    spec: str
    name: str = ""
    version: str = ""
    confirm: bool = False


class ToggleBody(BaseModel):
    name: str
    enabled: bool
    confirm: bool = False


class RemoveBody(BaseModel):
    name: str
    confirm: bool = False
    confirm_delete: bool = False


def _host():
    from dsh_host import DshHost
    return DshHost()


@router.get("/plugins/dsh/host")
def dsh_host_status():
    try:
        host = _host()
        return ok(host.public_status(), "DSH Host 配置读取成功")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": str(exc)}


@router.put("/plugins/dsh/host")
def dsh_host_configure(body: HostConfigBody):
    try:
        host = _host()
        status = host.configure(body.base_url, body.token)
        try:
            bundles = host.list_bundles()
        except Exception as exc:  # noqa: BLE001
            status["last_error"] = str(exc)
            return {"ok": False, "data": status,
                    "message": "DSH Host 连接失败：%s" % exc}
        return ok({"status": host.public_status(),
                   "bundle_count": len(bundles or [])},
                  "DSH Host 连接成功")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "保存 DSH Host 配置失败：%s" % exc}


@router.get("/plugins/dsh/host/indexes")
def dsh_host_indexes():
    try:
        return ok(_host().list_indexes(), "DSH 插件索引读取成功")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": str(exc)}


@router.put("/plugins/dsh/host/indexes")
def dsh_host_set_indexes(body: IndexesBody):
    try:
        host = _host()
        host.set_indexes(body.urls)
        return ok(host.list_indexes(), "DSH 插件索引已保存")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "保存 DSH 插件索引失败：%s" % exc}


@router.get("/plugins/dsh/host/bundles")
def dsh_host_bundles():
    try:
        return ok(_host().list_bundles(), "DSH 已安装插件读取成功")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": str(exc)}


@router.post("/plugins/dsh/host/search")
def dsh_host_search(body: SearchBody):
    try:
        return ok(_host().search(body.url, body.text, body.limit), "DSH 插件搜索成功")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "DSH 插件搜索失败：%s" % exc}


@router.post("/plugins/dsh/host/inspect")
def dsh_host_inspect(body: InspectBody):
    try:
        return ok(_host().inspect(body.spec), "DSH 插件检查完成")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "DSH 插件检查失败：%s" % exc}


@router.post("/plugins/dsh/host/install")
def dsh_host_install(body: InstallBody):
    if not body.confirm:
        return {"ok": False, "data": None, "message": "安装插件需要 confirm=true"}
    try:
        expected = None
        if body.name and body.version:
            expected = {"name": body.name, "version": body.version}
        return ok(_host().install(body.spec, expected), "DSH 插件安装完成")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "DSH 插件安装失败：%s" % exc}


@router.post("/plugins/dsh/host/toggle")
def dsh_host_toggle(body: ToggleBody):
    if not body.confirm:
        return {"ok": False, "data": None, "message": "启用/停用插件需要 confirm=true"}
    try:
        return ok(_host().set_bundle_enabled(body.name, body.enabled),
                  "DSH 插件状态已更新")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "更新 DSH 插件状态失败：%s" % exc}


@router.post("/plugins/dsh/host/remove")
def dsh_host_remove(body: RemoveBody):
    if not body.confirm or not body.confirm_delete:
        return {"ok": False, "data": None, "message": "删除插件需要二次确认"}
    try:
        return ok(_host().remove(body.name), "DSH 插件已删除")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "message": "删除 DSH 插件失败：%s" % exc}
