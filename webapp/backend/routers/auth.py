# -*- coding: utf-8 -*-
"""Web 端登录：复用桌面端 auth.db 账号（admin/admin123，或手机号）。"""

import base64
import hashlib
import hmac
import os
import secrets
import sys
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from deps import ok, ApiError

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from desktop.auth_db import AuthDatabase  # noqa: E402

router = APIRouter(tags=["auth"])

COOKIE_NAME = "structural_session"
SESSION_HOURS = 12
_SECRET_PATH = os.path.join(_ROOT, "data", ".auth_secret")


def _secret() -> bytes:
    try:
        with open(_SECRET_PATH, "rb") as fh:
            raw = fh.read().strip()
        if len(raw) >= 32:
            return raw
    except OSError:
        pass
    raw = secrets.token_hex(32).encode("ascii")
    os.makedirs(os.path.dirname(_SECRET_PATH), exist_ok=True)
    with open(_SECRET_PATH, "wb") as fh:
        fh.write(raw)
    return raw


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _issue(username: str) -> str:
    payload = "%s|%d" % (username, int(time.time()) + SESSION_HOURS * 3600)
    token = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return token + "." + _sign(payload)


def _verify(token: str):
    try:
        encoded, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        username, expires = payload.rsplit("|", 1)
        if int(expires) < time.time():
            return None
        return username
    except Exception:  # noqa: BLE001
        return None


def _db() -> AuthDatabase:
    return AuthDatabase(os.path.join(_ROOT, "desktop", "auth.db"))


def _public(user):
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "real_name": user.get("real_name") or user.get("username"),
        "department": user.get("department") or "",
        "role": user.get("role") or "user",
    }


class LoginBody(BaseModel):
    login_id: str
    password: str


@router.post("/auth/login")
def login(body: LoginBody, response: Response):
    login_id = (body.login_id or "").strip()
    if not login_id or not body.password:
        raise ApiError("请输入用户名和密码")
    ok_flag, user, message = _db().authenticate(login_id, body.password)
    if not ok_flag or user is None:
        raise ApiError(message or "用户名或密码错误", 401)
    response.set_cookie(
        COOKIE_NAME, _issue(user["username"]), max_age=SESSION_HOURS * 3600,
        httponly=True, samesite="lax", path="/")
    return ok(_public(user), "登录成功")


@router.get("/auth/me")
def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError("未登录", 401)
    username = _verify(token)
    if not username:
        raise ApiError("登录已过期", 401)
    users = _db().get_user_list()
    user = next((item for item in users if item.get("username") == username), None)
    if user is None:
        raise ApiError("用户不存在", 401)
    return ok(_public(user), "已登录")


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return ok(None, "已退出")
