# -*- coding: utf-8 -*-
"""原始记录生成路由：按检测项选择模板并生成 DOCX，附生成历史。"""
import json
import os
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from deps import (ApiError, ROOT, fill_imported_record, generate_native_record,
                  get_controller, get_record_store, get_state,
                  get_template_library, ok)

router = APIRouter(tags=["original-record"])

HISTORY_FILE = os.path.join(ROOT, "data", "original_record_history.json")
HISTORY_LIMIT = 50


def _load_history_json():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _save_history(items):
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(items[:HISTORY_LIMIT], f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def _append_history_json(entry):
    items = _load_history_json()
    items.insert(0, entry)
    _save_history(items)


def _append_history(entry):
    """写入原始记录库；数据库不可用时回退旧 JSON。返回记录 ID 或 None。"""
    try:
        return get_record_store().add_original_record(entry)
    except Exception:  # noqa: BLE001
        _append_history_json(entry)
        return None


def _load_history():
    try:
        items, _total = get_record_store().list_original_records(limit=500)
        for item in items:
            # 兼容旧 /original-record/history 契约字段 rows
            item.setdefault("rows", item.get("rows_count", 0))
        return items
    except Exception:  # noqa: BLE001
        return _load_history_json()


def _history_view(items):
    out = []
    for item in items:
        view = dict(item)
        view["exists"] = os.path.isfile(str(item.get("filepath") or ""))
        out.append(view)
    return out


def _has_data(rows):
    for row in rows or []:
        if any(str(v).strip() for v in row):
            return True
    return False


class GenerateBody(BaseModel):
    sheet_keys: List[str] = []
    template_map: Dict[str, str] = {}


@router.post("/original-record/generate")
def generate_original_records(body: GenerateBody):
    """按检测项目生成原始记录（每项一个 .docx）。"""
    try:
        state = get_state()
        lib = get_template_library()
        controller = get_controller()

        requested = [str(k) for k in (body.sheet_keys or []) if str(k).strip()]
        keys = requested or [k for k in state.checked_items
                             if k in state.sheet_data]
        if not keys:
            raise ApiError("请先勾选检测项目并录入数据")

        info = dict(state.report_info or {})
        if not str(info.get("project_name") or "").strip():
            info["project_name"] = state.project_name or ""
        project_map = dict((state.template_selection or {}).get(
            "original_template_map") or {})
        for key, template_id in (body.template_map or {}).items():
            key = str(key or "").strip()
            template_id = str(template_id or "").strip()
            if key and template_id:
                project_map[key] = template_id

        files = []
        warnings = []
        for key in keys:
            rows = state.sheet_data.get(key) or []
            if not _has_data(rows):
                warnings.append("%s：没有数据行，未生成原始记录" % key)
                continue
            columns = controller.get_columns(key)
            base, _comp = controller.parse_sheet_key(key)
            template_id = project_map.get(key) or lib.default_template_id_for_item(base)
            view = lib.resolve_original_template(base, template_id)
            if not view:
                warnings.append("%s：未找到可用的原始记录模板，已跳过" % key)
                continue
            if not view.get("fillable"):
                warnings.append(
                    "%s：模板“%s”为 .doc 存档，请另存为 .docx 后使用"
                    % (key, view.get("name") or view.get("id")))
                continue
            try:
                if view.get("engine") == "native_docx":
                    path, item_warnings = generate_native_record(
                        view.get("config") or {}, key, columns, rows, info)
                else:
                    template_path = lib.get_original_file_path(view["id"])
                    path, item_warnings = fill_imported_record(
                        template_path, key, columns, rows, info)
            except Exception as e:  # noqa: BLE001 - 单项失败不中断其它项
                warnings.append("%s：生成失败（%s）" % (key, e))
                continue
            warnings.extend(item_warnings)
            rows_count = len([r for r in rows
                              if any(str(v).strip() for v in r)])
            snapshot = {
                "sheet_key": key,
                "base_item": base,
                "project_name": state.project_name or "",
                "columns": columns,
                "rows": rows,
                "params": state.cd_params.get(key, {}),
                "assessment_input": state.assessment_inputs.get(key),
                "assessment_result": state.assessment_results.get(key),
                "report_info": info,
            }
            record_id = None
            try:
                record_id = _append_history({
                    "filepath": path,
                    "sheet_key": key,
                    "base_item": base,
                    "template_id": view.get("id"),
                    "template_name": view.get("name"),
                    "rows": rows_count,
                    "warnings": item_warnings,
                    "snapshot": snapshot,
                    "project_name": state.project_name or "",
                    "generated_at": datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"),
                })
            except Exception:  # noqa: BLE001
                pass
            files.append({
                "sheet_key": key,
                "template_id": view.get("id"),
                "template_name": view.get("name"),
                "filepath": path,
                "warnings": item_warnings,
                "record_id": record_id,
            })

        if not files:
            detail = "；".join(warnings[:5]) if warnings else "没有可生成的数据"
            raise ApiError("未生成原始记录：%s" % detail)
        message = "原始记录生成完成：%d 个文件" % len(files)
        if warnings:
            message += "（%d 条提示）" % len(warnings)
        return ok({"files": files, "warnings": warnings}, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"生成原始记录失败：{e}"}


@router.get("/original-record/history")
def get_original_record_history():
    try:
        data = _history_view(_load_history())
        return ok(data, "原始记录历史读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取原始记录历史失败：{e}"}


@router.post("/original-record/history/clear")
def clear_original_record_history():
    try:
        try:
            get_record_store().clear_original_records()
        except Exception:  # noqa: BLE001
            _save_history([])
        return ok(True, "原始记录历史已清空")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"清空原始记录历史失败：{e}"}
