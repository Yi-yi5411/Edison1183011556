# -*- coding: utf-8 -*-
"""设备库 API：对接检测设备管理系统（验证码登录 + 设备分页查询）并维护本地库。"""
import base64
import json
import os
import ssl
import time
import urllib3
from datetime import datetime
from typing import Optional

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from deps import ApiError, get_state, ok, ROOT
from utils.equipment_store import (
    count_equipment,
    delete_equipment,
    list_equipment,
    preview_equipment_detail,
    preview_equipment_for_report,
    set_selected,
    upsert_equipment,
)

router = APIRouter(tags=["equipment"])
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_CONFIG_PATH = os.path.join(ROOT, "data", "equipment", "config.json")
_DEFAULT = {
    "base_url": "https://em.hbsjyy.net:3000/jeecg-boot",
    "username": "06055",
    "password": "0b98Vzrs~",
}
_TOKEN = {"token": "", "exp": 0, "username": "", "login_at": ""}


def _load_config():
    cfg = dict(_DEFAULT)
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in cfg:
                if data.get(k):
                    cfg[k] = str(data[k]).strip()
    except Exception:
        pass
    cfg["base_url"] = os.environ.get("EQUIPMENT_API_BASE", cfg["base_url"]).rstrip("/")
    cfg["username"] = os.environ.get("EQUIPMENT_API_USERNAME", cfg["username"])
    cfg["password"] = os.environ.get("EQUIPMENT_API_PASSWORD", cfg["password"])
    return cfg


def _session():
    s = requests.Session()
    s.trust_env = False          # 本机代理环境变量不可用时也能直连
    s.verify = False
    s.headers.update({"Accept": "application/json"})
    return s


def _decode_exp(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return int(data.get("exp") or 0)
    except Exception:
        return 0


def _token_valid():
    return bool(_TOKEN.get("token")) and (not _TOKEN.get("exp") or _TOKEN["exp"] > time.time() + 30)


def _clear_token():
    _TOKEN.update({"token": "", "exp": 0, "username": "", "login_at": ""})


def _api_error(resp, prefix):
    try:
        data = resp.json()
        msg = data.get("message") or data.get("msg") or str(data)[:200]
    except Exception:
        msg = (resp.text or "")[:200]
    raise ApiError("%s：%s" % (prefix, msg), 502)


def _status_payload():
    cfg = _load_config()
    return {
        "base_url": cfg["base_url"],
        "username": _TOKEN.get("username") or cfg["username"],
        "logged_in": _token_valid(),
        "expires_at": (datetime.fromtimestamp(_TOKEN["exp"]).strftime("%Y-%m-%d %H:%M:%S")
                       if _TOKEN.get("exp") else ""),
        "local_count": count_equipment(),
    }


@router.get("/equipment/status")
def equipment_status():
    return ok(_status_payload(), "设备系统状态")


@router.get("/equipment/captcha")
def equipment_captcha():
    cfg = _load_config()
    key = "eq" + str(int(time.time() * 1000))
    try:
        with _session() as s:
            resp = s.get(cfg["base_url"] + "/sys/randomImage/" + key, timeout=20)
        if resp.status_code != 200:
            _api_error(resp, "获取验证码失败")
        data = resp.json()
        image = str(data.get("result") or "")
        if not image:
            raise ApiError("设备系统未返回验证码图片", 502)
        return ok({"key": key, "image": image}, "验证码获取成功")
    except ApiError:
        raise
    except Exception as e:
        raise ApiError("无法连接设备管理系统：%s" % e, 502)


class LoginBody(BaseModel):
    username: Optional[str] = ""
    password: Optional[str] = ""
    captcha: Optional[str] = ""
    check_key: Optional[str] = ""


@router.post("/equipment/login")
def equipment_login(body: LoginBody):
    cfg = _load_config()
    username = (body.username or cfg["username"]).strip()
    password = body.password or cfg["password"]
    captcha = (body.captcha or "").strip()
    key = (body.check_key or "").strip()
    if not captcha or not key:
        raise ApiError("请输入验证码并刷新验证码图片")
    try:
        with _session() as s:
            resp = s.post(cfg["base_url"] + "/sys/login", json={
                "username": username, "password": password,
                "captcha": captcha, "checkKey": key,
            }, timeout=30)
        if resp.status_code != 200:
            _api_error(resp, "登录失败")
        data = resp.json()
        if not data.get("success"):
            raise ApiError("登录失败：%s" % (data.get("message") or "账号、密码或验证码错误"))
        token = str((data.get("result") or {}).get("token") or "")
        if not token:
            raise ApiError("登录成功但设备系统未返回 token", 502)
        _TOKEN.update({
            "token": token,
            "exp": _decode_exp(token),
            "username": username,
            "login_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return ok(_status_payload(), "设备管理系统登录成功")
    except ApiError:
        raise
    except Exception as e:
        raise ApiError("登录设备管理系统失败：%s" % e, 502)


@router.post("/equipment/logout")
def equipment_logout():
    _clear_token()
    return ok(_status_payload(), "已退出设备管理系统")


def _require_token():
    if not _token_valid():
        _clear_token()
        raise ApiError("设备管理系统登录已失效，请重新登录", 401)
    return _TOKEN["token"]


def _remote_list(page_no=1, page_size=20, keyword="", status="", department=""):
    cfg = _load_config()
    params = {"pageNo": max(1, int(page_no)), "pageSize": min(100, max(1, int(page_size)))}
    if keyword:
        # 设备系统按 Jeecg 查询生成器解析 * 通配；默认做包含匹配
        params["equipmentName"] = keyword if "*" in keyword else "*%s*" % keyword
    if status:
        params["equipmentId5"] = status
    if department:
        params["equipmentPlace2"] = department
    try:
        with _session() as s:
            resp = s.get(cfg["base_url"] + "/standing/standing/list",
                         params=params,
                         headers={"X-Access-Token": _require_token()},
                         timeout=30)
        if resp.status_code == 401:
            _clear_token()
            raise ApiError("设备管理系统登录已失效，请重新登录", 401)
        if resp.status_code != 200:
            _api_error(resp, "查询设备失败")
        data = resp.json()
        if not data.get("success"):
            msg = data.get("message") or "查询失败"
            if "Token" in msg or "登录" in msg:
                _clear_token()
                raise ApiError("设备管理系统登录已失效，请重新登录", 401)
            raise ApiError("查询设备失败：%s" % msg, 502)
        result = data.get("result") or {}
        records = result.get("records") or []
        return {
            "records": records,
            "total": int(result.get("total") or 0),
            "page_no": int(result.get("current") or page_no),
            "page_size": int(result.get("size") or page_size),
        }
    except ApiError:
        raise
    except Exception as e:
        raise ApiError("查询设备管理系统失败：%s" % e, 502)


@router.get("/equipment/remote")
def equipment_remote(page_no: int = 1, page_size: int = 20,
                     keyword: str = "", status: str = "", department: str = ""):
    data = _remote_list(page_no, page_size, keyword, status, department)
    return ok(data, "远程设备查询成功")


def _fetch_remote_ids(ids):
    wanted = {str(x) for x in (ids or []) if str(x).strip()}
    if not wanted:
        return []
    found = []
    page = 1
    while page <= 100:
        data = _remote_list(page, 100)
        for rec in data["records"]:
            if str(rec.get("id") or "") in wanted:
                found.append(rec)
        if len(found) >= len(wanted) or page * 100 >= data["total"]:
            break
        page += 1
    return found


class SyncBody(BaseModel):
    ids: list = []
    all: bool = False


@router.post("/equipment/sync")
def equipment_sync(body: SyncBody):
    if body.all:
        records = []
        page = 1
        while page <= 100:
            data = _remote_list(page, 100)
            records.extend(data["records"])
            if page * 100 >= data["total"]:
                break
            page += 1
    else:
        records = _fetch_remote_ids(body.ids)
    if not records:
        raise ApiError("没有可同步的设备，请先勾选远程设备")
    # 勾选同步的设备默认选入报告；全量同步不自动全选，避免报告误用无关设备
    count = upsert_equipment(records, selected=not body.all)
    return ok({"synced": count, "local_count": count_equipment()},
              "已同步 %d 台设备到本地库" % count)


@router.get("/equipment/library")
def equipment_library(keyword: str = "", selected_only: bool = False):
    rows = list_equipment(keyword, selected_only=selected_only)
    total = count_equipment() if not str(keyword or "").strip() else len(rows)
    return ok({"records": rows, "total": total}, "设备库读取成功")


class SelectBody(BaseModel):
    ids: list = []
    selected: bool = True


@router.post("/equipment/library/select")
def equipment_select(body: SelectBody):
    count = set_selected(body.ids, body.selected)
    return ok({"updated": count}, "报告选用状态已更新")


class DeleteBody(BaseModel):
    ids: list = []


@router.post("/equipment/library/delete")
def equipment_delete(body: DeleteBody):
    count = delete_equipment(body.ids)
    return ok({"deleted": count}, "已删除 %d 台设备" % count)


@router.get("/equipment/recommend")
def equipment_recommend(limit: int = 20):
    """只读：按已勾选检测项目推荐在用设备（当天使用次数、是否选用）。

    复用 equipment_store.preview_equipment_for_report，不占用当日使用次数。
    """
    try:
        state = get_state()
        checked = [k for k in (state.checked_items or [])
                   if k in (state.sheet_data or {})]
        limit = max(1, min(int(limit or 20), 100))
        rows = preview_equipment_for_report(checked, limit=limit)
        detail = preview_equipment_detail(checked, limit=limit)
        covered = sum(1 for item in detail if item.get("covered"))
        return ok({
            "checked_items": checked,
            "equipment": rows,
            "items": detail,
            "count": len(rows),
            "covered_items": covered,
            "daily_limit": 10,
        }, "已为 %d 个检测项目推荐 %d 台设备（%d 项有可用仪器）"
                  % (len(checked), len(rows), covered))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"推荐设备失败：{e}"}
