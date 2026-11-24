# -*- coding: utf-8 -*-
"""当前工程工作区：按工程聚合报告、原始记录、附件与快照。

不把源码目录当作工作区根：DSH 的 Files 页以会话 cwd 为根，而本产品的 cwd
是自身源码，直接展示会泄露代码。这里改用“当前检测工程”为语义根，只在
其产物范围内列出文件；文件树接口保留给兼容调用。
"""

import base64
import os
import re
import time
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from deps import ApiError, get_record_store, get_state, ok

router = APIRouter(tags=["workspace"])

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_EXCLUDE = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".dsh"}
_TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".html", ".css", ".scss", ".sql", ".ps1", ".bat", ".sh", ".ini", ".cfg",
}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
_MAX_TEXT = 200 * 1024


def _resolve(relative: str) -> str:
    relative = (relative or "").replace("\\", "/").strip("/")
    full = os.path.abspath(os.path.join(_ROOT, relative))
    if full != _ROOT and not full.startswith(_ROOT + os.sep):
        raise ApiError("路径越界", 403)
    return full


def _stamp(value, default=0):
    """把生成时间/时间戳统一成 epoch 秒，前端用 relativeTime 展示。"""
    if isinstance(value, (int, float)):
        number = float(value)
        return int(number / 1000) if number > 1e12 else int(number)
    text = str(value or "").strip()
    if not text:
        return int(default or 0)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(time.mktime(datetime.strptime(text[:19], fmt).timetuple()))
        except ValueError:
            continue
    return int(default or 0)


def _file_stamp(full):
    try:
        return int(os.path.getmtime(full)) if full and os.path.isfile(full) else 0
    except OSError:
        return 0


def _rel_path(full):
    if not full:
        return ""
    try:
        rel = os.path.relpath(os.path.abspath(full), _ROOT).replace("\\", "/")
    except ValueError:
        return ""
    if rel == "." or rel.startswith("../"):
        return ""
    return rel


def _preview_kind(full):
    ext = os.path.splitext(str(full or ""))[1].lower()
    if ext == ".docx":
        return "docx"
    if ext == ".pdf":
        return "pdf"
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _TEXT_EXT:
        return "text"
    return "none"


def _row_has_value(row):
    if isinstance(row, (list, tuple)):
        return any(str(v or "").strip() for v in row)
    if isinstance(row, dict):
        return any(str(v or "").strip() for v in row.values())
    return bool(str(row or "").strip())


def _where(full):
    """用父目录名区分同名的检测报告/原始记录（通常是导出时间戳）。"""
    parent = os.path.basename(os.path.dirname(str(full or "")))
    return "" if parent.lower() in ("", "exports", "uploads", "projects", "generated") else parent


def _item(kind, full, name, meta="", detail="", at=0, size=0, exists=None):
    full = os.path.abspath(full) if full else ""
    if exists is None:
        exists = bool(full and os.path.isfile(full))
    if exists and not size:
        try:
            size = os.path.getsize(full)
        except OSError:
            size = 0
    rel = _rel_path(full)
    stamp = _stamp(at or _file_stamp(full))
    return {
        "id": "%s:%s" % (kind, rel or full or name),
        "kind": kind,
        "name": name or os.path.basename(full) or "未命名文件",
        "path": rel,
        "filepath": full,
        "size": int(size or 0),
        "at": stamp,
        "exists": bool(exists),
        "preview": _preview_kind(full) if exists else "none",
        "downloadable": bool(exists and rel),
        "meta": meta,
        "detail": detail,
        "where": _where(full),
    }


def _project_summary(state):
    checked = list(getattr(state, "checked_items", None) or [])
    filled = 0
    total_rows = 0
    for key in checked:
        rows = [r for r in (getattr(state, "sheet_data", {}).get(key) or [])
                if _row_has_value(r)]
        total_rows += len(rows)
        if rows:
            filled += 1
    assessed = sum(
        1 for key in checked
        if (getattr(state, "assessment_results", {}).get(key) or {}).get("ok")
    )
    autosave = getattr(state, "autosave_path", "") or ""
    project_file = getattr(state, "filepath", "") or ""
    snapshot_path = project_file if project_file and os.path.isfile(project_file) else autosave
    return {
        "name": getattr(state, "project_name", "") or "未命名项目",
        "checked_count": len(checked),
        "filled_count": filled,
        "assessed_count": assessed,
        "total_rows": total_rows,
        "snapshot_at": _file_stamp(snapshot_path),
        "snapshot_name": os.path.basename(snapshot_path) if snapshot_path else "",
    }


@router.get("/workspace/overview")
def workspace_overview(q: str = "", limit: int = 60, include_missing: bool = False):
    """当前工程的产物清单：报告 / 原始记录 / 附件 / 工程快照。

    这是工作区面板的默认入口；它不遍历源码目录，只读取记录库和工程相关目录。
    """
    state = get_state()
    project = _project_summary(state)
    project_name = project["name"]
    query = str(q or "").strip()
    size = max(1, min(int(limit or 60), 200))

    report_items, original_items = [], []
    record_limit = 200
    try:
        records, _ = get_record_store().list_report_records(
            q=query, project=project_name, limit=record_limit)
        for rec in records:
            full = str(rec.get("filepath") or "")
            report_items.append(_item(
                "report", full,
                rec.get("filename") or os.path.basename(full),
                meta=(rec.get("report_no") or "未编号") + " · %s 项" % (rec.get("assessed_count") or 0),
                detail=rec.get("template_name") or "检测报告",
                at=rec.get("generated_at") or rec.get("created_at") or "",
                size=int(rec.get("file_size") or 0),
                exists=rec.get("exists"),
            ))
        originals, _ = get_record_store().list_original_records(
            q=query, project=project_name, limit=record_limit)
        for rec in originals:
            full = str(rec.get("filepath") or "")
            original_items.append(_item(
                "original", full,
                rec.get("filename") or os.path.basename(full),
                meta="%s 行" % (rec.get("rows_count") or 0),
                detail=rec.get("template_name") or rec.get("sheet_key") or "原始记录",
                at=rec.get("generated_at") or rec.get("created_at") or "",
                exists=rec.get("exists"),
            ))
    except Exception:  # noqa: BLE001 - 记录库异常不应让整个工作区空白
        report_items, original_items = [], []

    report_missing = sum(1 for item in report_items if not item["exists"])
    original_missing = sum(1 for item in original_items if not item["exists"])
    if not include_missing:
        report_items = [item for item in report_items if item["exists"]]
        original_items = [item for item in original_items if item["exists"]]

    upload_items = []
    upload_dir = os.path.join(_ROOT, "data", "uploads")
    try:
        names = sorted(
            (name for name in os.listdir(upload_dir)
             if os.path.isfile(os.path.join(upload_dir, name))),
            key=lambda name: os.path.getmtime(os.path.join(upload_dir, name)),
            reverse=True)
    except OSError:
        names = []
    for name in names:
        if query and query.lower() not in name.lower():
            continue
        full = os.path.join(upload_dir, name)
        display = re.sub(r"^\d{8}_\d{6}_", "", name) or name
        upload_items.append(_item(
            "upload", full, display,
            meta="本机上传", detail="对话附件"))

    snapshot_items = []
    seen = set()
    for role, full in (("工程文件", getattr(state, "filepath", "") or ""),
                       ("自动保存", getattr(state, "autosave_path", "") or "")):
        if not full or not os.path.isfile(full):
            continue
        key = os.path.abspath(full)
        if key in seen:
            continue
        seen.add(key)
        name = os.path.basename(full)
        if query and query.lower() not in name.lower():
            continue
        snapshot_items.append(_item(
            "snapshot", full, name,
            meta=role, detail="工程 JSON 快照"))
    snapshot_items.sort(key=lambda item: item["at"], reverse=True)

    sections = [
        {"key": "reports", "title": "检测报告", "items": report_items[:size], "total": len(report_items)},
        {"key": "originals", "title": "原始记录", "items": original_items[:size], "total": len(original_items)},
        {"key": "uploads", "title": "上传附件", "items": upload_items[:size], "total": len(upload_items)},
        {"key": "snapshots", "title": "工程快照", "items": snapshot_items[:size], "total": len(snapshot_items)},
    ]
    counts = {section["key"]: section["total"] for section in sections}
    missing = {
        "reports": report_missing,
        "originals": original_missing,
    }
    return ok({
        "project": project,
        "query": query,
        "limit": size,
        "counts": counts,
        "total": sum(counts.values()),
        "missing": missing,
        "missing_total": sum(missing.values()),
        "sections": sections,
    }, "工作区已按当前工程加载")


@router.get("/workspace/download")
def workspace_download(path: str):
    """下载工作区中的任意文件；路径仍限制在项目根内。"""
    full = _resolve(path)
    if not os.path.isfile(full):
        raise ApiError("文件不存在", 404)
    return FileResponse(full, filename=os.path.basename(full))


@router.get("/workspace/tree")
def workspace_tree(path: str = ""):
    base = _resolve(path)
    if not os.path.isdir(base):
        raise ApiError("目录不存在", 404)
    entries = []
    try:
        names = sorted(os.listdir(base), key=lambda item: (not os.path.isdir(os.path.join(base, item)), item.lower()))
    except OSError as exc:
        raise ApiError("读取目录失败：%s" % exc)
    for name in names:
        if name in _EXCLUDE or name.startswith("."):
            continue
        full = os.path.join(base, name)
        rel = os.path.relpath(full, _ROOT).replace("\\", "/")
        entries.append({
            "name": name,
            "path": rel,
            "type": "dir" if os.path.isdir(full) else "file",
            "size": 0 if os.path.isdir(full) else os.path.getsize(full),
        })
    rel_base = os.path.relpath(base, _ROOT).replace("\\", "/")
    return ok({"path": "" if rel_base == "." else rel_base, "entries": entries})


@router.get("/workspace/file")
def workspace_file(path: str):
    full = _resolve(path)
    if not os.path.isfile(full):
        raise ApiError("文件不存在", 404)
    ext = os.path.splitext(full)[1].lower()
    if ext in _IMAGE_EXT:
        return FileResponse(full)
    if ext in _TEXT_EXT:
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(_MAX_TEXT)
        except OSError as exc:
            raise ApiError("读取失败：%s" % exc)
        return ok({"path": path, "kind": "text", "content": text, "truncated": os.path.getsize(full) > _MAX_TEXT})
    return ok({"path": path, "kind": "binary", "size": os.path.getsize(full)})


class UploadBody(BaseModel):
    name: str
    data: str


@router.post("/workspace/upload")
def workspace_upload(body: UploadBody):
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", os.path.basename(body.name or "file"))
    if not name:
        raise ApiError("文件名无效")
    target_dir = os.path.join(_ROOT, "data", "uploads")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, "%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), name))
    try:
        payload = base64.b64decode(body.data.split(",")[-1])
    except Exception:  # noqa: BLE001
        raise ApiError("文件内容不是合法 base64")
    with open(target, "wb") as fh:
        fh.write(payload)
    rel = os.path.relpath(target, _ROOT).replace("\\", "/")
    return ok({"path": rel, "size": len(payload)}, "已上传：%s" % rel)
