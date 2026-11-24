# -*- coding: utf-8 -*-
"""DSH Host API 客户端：通过 /api Typert RPC 管理 DSH 插件。

DSH 的浏览器会话使用 launch token 换 HttpOnly cookie。本模块保存用户从
DSH 启动 URL 复制的 token，先 GET /?token=... 换 cookie，再调用
/api/pluginMarket/* 与 /api/pluginManager/*。token 只在服务端保存，不回传前端。
"""
import json
import os
import uuid

import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG = os.path.join(_ROOT, "data", "dsh_host.json")


class DshHostError(RuntimeError):
    pass


def _load_config():
    try:
        with open(_CONFIG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(data):
    os.makedirs(os.path.dirname(_CONFIG), exist_ok=True)
    tmp = _CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _CONFIG)


def _default_base():
    try:
        from structural_config import get as cfg_get
        return str(cfg_get("dsh", "gui_url", "http://127.0.0.1:3642")).rstrip("/")
    except Exception:  # noqa: BLE001
        return "http://127.0.0.1:3642"


class DshHost:
    def __init__(self):
        cfg = _load_config()
        self.base_url = str(cfg.get("base_url") or _default_base()).rstrip("/")
        self.token = str(cfg.get("token") or "")
        self._session = requests.Session()
        self._session.trust_env = False
        self._authed = False
        self._last_error = ""

    def public_status(self):
        return {
            "base_url": self.base_url,
            "token_configured": bool(self.token),
            "authed": self._authed,
            "last_error": self._last_error,
        }

    def configure(self, base_url=None, token=None):
        if base_url is not None and str(base_url).strip():
            self.base_url = str(base_url).strip().rstrip("/")
        if token is not None and str(token).strip():
            raw = str(token).strip()
            # 允许直接粘贴 DSH 启动 URL，而不是裸 token
            if "token=" in raw:
                from urllib.parse import parse_qs, urlparse
                query = parse_qs(urlparse(raw).query)
                raw = (query.get("token") or [raw])[0]
            if raw.startswith("http"):
                from urllib.parse import parse_qs, urlparse
                query = parse_qs(urlparse(raw).query)
                raw = (query.get("token") or [""])[0]
            self.token = raw
        self._authed = False
        _save_config({"base_url": self.base_url, "token": self.token})
        return self.public_status()

    def _authenticate(self):
        if self._authed:
            return
        if not self.token:
            raise DshHostError("尚未配置 DSH Host token，请从 DSH 启动 URL 复制 token")
        response = self._session.get(
            self.base_url + "/",
            params={"token": self.token},
            allow_redirects=False,
            timeout=8,
        )
        if response.status_code not in (200, 301, 302, 303, 401):
            raise DshHostError(
                "DSH token 换取 cookie 失败：HTTP %s" % response.status_code)
        # 303 会 Set-Cookie；部分部署 200 直接返回页面
        self._authed = True

    def call(self, method, args=None):
        """调用一个 Typert Remote 方法，返回 result.value。"""
        self._authenticate()
        rpc_id = str(uuid.uuid4())
        body = {
            "type": "client-request",
            "rpcId": rpc_id,
            "method": method,
            "payload": {"args": dict(args or {})},
        }
        response = self._session.post(
            self.base_url + "/api/" + method.lstrip("/"),
            json=body,
            timeout=600,
        )
        if response.status_code == 401:
            self._authed = False
            self._authenticate()
            response = self._session.post(
                self.base_url + "/api/" + method.lstrip("/"),
                json=body,
                timeout=600,
            )
        if response.status_code != 200:
            raise DshHostError(
                "DSH Host API HTTP %s：%s" % (response.status_code, response.text[:300]))
        try:
            data = response.json()
        except ValueError:
            raise DshHostError("DSH Host API 返回非 JSON")
        result = data.get("result") or {}
        if not result.get("ok"):
            error = result.get("error") or {}
            raise DshHostError(
                str(error.get("message") or error.get("code") or "DSH Host API 调用失败"))
        return result.get("value")

    # ── 插件市场 ──
    def list_indexes(self):
        return self.call("pluginMarket/listIndexes", {})

    def set_indexes(self, urls):
        return self.call("pluginMarket/setIndexes", {"urls": list(urls or [])})

    def search(self, url, text="", limit=30):
        return self.call("pluginMarket/search", {
            "url": url,
            "query": {
                "text": text,
                "sort": {"kind": "relevance"},
                "offset": 0,
                "limit": max(1, min(100, int(limit))),
            },
        })

    # ── 插件管理 ──
    def list_bundles(self):
        return self.call("pluginManager/listBundles", {})

    def inspect(self, spec):
        return self.call("pluginManager/inspect", {"spec": spec, "options": {}})

    def install(self, spec, expected=None, enabled=True):
        options = {"enabled": bool(enabled), "saveExact": True}
        if expected:
            options["expected"] = expected
        return self.call("pluginManager/installBundle", {"spec": spec, "options": options})

    def set_bundle_enabled(self, name, enabled):
        return self.call("pluginManager/setBundleEnabled",
                         {"name": name, "enabled": bool(enabled)})

    def remove(self, name):
        return self.call("pluginManager/removeBundle", {"name": name})


def get_host():
    return DshHost()


def configure_host(base_url=None, token=None):
    return DshHost().configure(base_url, token)
