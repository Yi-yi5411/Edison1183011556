# -*- coding: utf-8 -*-
"""数据库状态路由：报告模板 / 原始记录模板 / 设备 / 记录库 / Wiki / 规范。"""
from fastapi import APIRouter

from deps import (get_record_store, get_state, get_template_library,
                  get_wiki_store, ok)
from utils import equipment_store
from utils.equipment_store import count_equipment, list_equipment
from utils.norm_qa import db_status
from utils import personnel_store

router = APIRouter(tags=["libraries"])


def _has_value(row):
    if isinstance(row, (list, tuple)):
        return any(str(v or "").strip() for v in row)
    if isinstance(row, dict):
        return any(str(v or "").strip() for v in row.values())
    return bool(str(row or "").strip())


def _safe(fn, fallback):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        data = dict(fallback)
        data["error"] = str(e)
        return data


def build_libraries_status():
    """统一状态字典（Harness 启动预演与记录库页面共用）。"""
    state = get_state()
    checked = list(state.checked_items or [])
    total_rows = 0
    filled = 0
    for key in checked:
        rows = [r for r in (state.sheet_data.get(key) or []) if _has_value(r)]
        total_rows += len(rows)
        if rows:
            filled += 1
    assessed = sum(
        1 for key in checked
        if (state.assessment_results.get(key) or {}).get("ok"))

    def _templates():
        lib = get_template_library()
        reports = lib.list_report_templates()
        originals = lib.list_original_templates()
        default_id = lib.default_report_template_id()
        default_name = ""
        for item in reports:
            if item.get("id") == default_id:
                default_name = item.get("name") or ""
                break
        return {
            "report_templates": len(reports),
            "original_templates": len(originals),
            "default_report_template": default_name,
            "db_path": str(getattr(lib, "db_path", "")),
        }

    def _equipment():
        selected = list_equipment(selected_only=True, limit=1000)
        return {
            "total": count_equipment(),
            "selected": len(selected),
            "db_path": str(equipment_store._DB_PATH),
        }

    def _records():
        return get_record_store().stats()

    def _wiki():
        return get_wiki_store().status()

    def _personnel():
        return personnel_store.status()

    def _norms():
        info = db_status()
        return {"total": info.get("total", 0),
                "codes": len(info.get("codes") or []),
                "db_path": info.get("db_path", "")}

    return {
        "project": {
            "name": state.project_name or "未命名项目",
            "checked_items": len(checked),
            "filled_items": filled,
            "total_rows": total_rows,
            "assessed_items": assessed,
            "autosave_path": getattr(state, "autosave_path", ""),
        },
        "templates": _safe(_templates, {
            "report_templates": 0, "original_templates": 0,
            "default_report_template": "", "db_path": ""}),
        "equipment": _safe(_equipment, {
            "total": 0, "selected": 0, "db_path": ""}),
        "records": _safe(_records, {
            "report": {"total": 0, "this_month": 0},
            "original": {"total": 0, "this_month": 0, "with_snapshot": 0},
            "latest": "", "db_path": ""}),
        "wiki": _safe(_wiki, {
            "pages": 0, "categories": 0, "db_path": "", "exists": False}),
        "personnel": _safe(_personnel, {
            "total": 0, "active": 0, "roles": {}, "db_path": ""}),
        "norms": _safe(_norms, {
            "total": 0, "codes": 0, "db_path": ""}),
    }


@router.get("/libraries/status")
def libraries_status():
    try:
        return ok(build_libraries_status(), "数据库状态读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取数据库状态失败：{e}"}
