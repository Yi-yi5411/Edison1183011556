# -*- coding: utf-8 -*-
"""API 访问日志：每个 /api 请求写一行 JSON（含 X-Request-ID、耗时、状态）。

- 路径：默认 data/logs/backend.jsonl，可用 STRUCTURAL_LOG_DIR 覆盖；
- 关闭：STRUCTURAL_ACCESS_LOG=off；
- 轮转：超过 10MB 改名为 .1（只留一份历史）；
- 隐私：只记录路径与查询参数名，不记录参数值。
"""
import json
import os
import time
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MAX_BYTES = 10 * 1024 * 1024


def log_dir():
    return os.environ.get("STRUCTURAL_LOG_DIR") or os.path.join(
        _ROOT, "data", "logs")


def log_file():
    return os.path.join(log_dir(), "backend.jsonl")


def enabled():
    return str(os.environ.get("STRUCTURAL_ACCESS_LOG", "")).lower() not in (
        "off", "0", "false")


def new_request_id():
    return uuid.uuid4().hex[:12]


def _rotate(path):
    try:
        if os.path.isfile(path) and os.path.getsize(path) > MAX_BYTES:
            os.replace(path, path + ".1")
    except OSError:
        pass


def write_entry(entry):
    """追加一行 JSON；失败静默（日志不能影响业务）。"""
    try:
        path = log_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _rotate(path)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def log_request(method, path, status, duration_ms, request_id="",
                client="", query_keys=None, project_name=""):
    """记录一次 API 请求。path 不含查询串；query_keys 只记参数名。"""
    if not enabled():
        return None
    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "request_id": request_id or new_request_id(),
        "method": str(method or "").upper(),
        "path": str(path or ""),
        "query_keys": sorted(set(query_keys or [])),
        "status": int(status or 0),
        "duration_ms": int(duration_ms or 0),
        "client": str(client or ""),
        "project": str(project_name or ""),
    }
    write_entry(entry)
    return entry
