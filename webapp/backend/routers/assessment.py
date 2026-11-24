# -*- coding: utf-8 -*-
"""检测评定路由：规则查询、原始数据保存、运行评定、批量评定。"""
import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from typing import Dict, List, Optional

from deps import (ApiError, assess, get_controller, get_spec, get_state,
                  list_specs, ok)
from utils.excel_import import ExcelImportError, import_assessment_input

router = APIRouter(tags=["assessment"])


class InputBody(BaseModel):
    input: Optional[dict] = None
    options: Optional[dict] = None


class RunAllBody(BaseModel):
    sheet_keys: List[str] = []


def _clean_options(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "no_drawing": bool(raw.get("no_drawing")),
        "table_no": str(raw.get("table_no") or "1").strip() or "1",
        "include_component_stats": bool(raw.get("include_component_stats")),
    }


def _resolve(sheet_key):
    state = get_state()
    key = str(sheet_key or "").strip()
    if not key:
        raise ApiError("缺少 sheet_key")
    if key not in state.sheet_data:
        raise ApiError(f"工作表不存在：{key}，请先勾选检测项目")
    controller = get_controller()
    base, comp = controller.parse_sheet_key(key)
    base = controller.resolve_item_name(base) or base
    spec = get_spec(base)
    if spec is None:
        raise ApiError(f"未找到“{base}”的评定规则")
    columns = controller.get_columns(key)
    rows = state.sheet_data.get(key) or []
    return state, key, base, comp, spec, columns, rows


def _run_one(state, key, base, comp, spec, columns, rows, input_data, options):
    merged_options = dict(state.assessment_options.get(key) or {})
    merged_options.update(_clean_options(options))
    if input_data is None:
        input_data = state.assessment_inputs.get(key)
    result = assess(key, base, comp, columns, rows,
                    options=merged_options, raw_input=input_data)
    state.assessment_options[key] = merged_options
    if input_data is not None:
        state.assessment_inputs[key] = input_data
    state.assessment_results[key] = result
    return result


@router.get("/assessment/specs")
def assessment_specs():
    """全部评定规则摘要（13 份提示词的机器可读版本）。"""
    try:
        return ok({"specs": list_specs()}, "评定规则读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取评定规则失败：{e}"}


@router.get("/assessment/{sheet_key}")
def assessment_detail(sheet_key: str):
    """当前工作表的评定规则、已保存原始数据/选项/结果。"""
    try:
        state, key, base, comp, spec, columns, rows = _resolve(sheet_key)
        public_spec = {k: v for k, v in spec.items() if k != "templates"}
        return ok({
            "sheet_key": key,
            "base_item": base,
            "component": comp,
            "spec": public_spec,
            "options": _clean_options(state.assessment_options.get(key) or {}),
            "input": state.assessment_inputs.get(key),
            "result": state.assessment_results.get(key),
            "columns": columns,
            "row_count": len([r for r in rows if any(str(v).strip() for v in r)]),
        }, "评定信息读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取评定信息失败：{e}"}


@router.put("/assessment/{sheet_key}/input")
def save_assessment_input(sheet_key: str, body: InputBody):
    """保存原始数据/选项（不执行评定）。"""
    try:
        state, key, _base, _comp, _spec, _columns, _rows = _resolve(sheet_key)
        if body.input is not None:
            if not isinstance(body.input, dict):
                raise ApiError("input 必须是对象")
            state.assessment_inputs[key] = body.input
        if body.options is not None:
            state.assessment_options[key] = _clean_options(body.options)
        return ok({
            "input": state.assessment_inputs.get(key),
            "options": _clean_options(state.assessment_options.get(key) or {}),
        }, "评定原始数据已保存")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存评定原始数据失败：{e}"}


@router.post("/assessment/{sheet_key}/import_excel")
async def import_assessment_excel(sheet_key: str, file: UploadFile = File(...),
                                  sheet_name: str = Form("")):
    """导入回弹法/回弹钻芯修正法的原始数据 Excel（不自动执行评定）。"""
    tmp_dir = tempfile.mkdtemp(prefix="assessment_import_")
    try:
        state, key, _base, _comp, spec, _columns, _rows = _resolve(sheet_key)
        family = spec.get("family")
        if family not in ("rebound", "rebound_core"):
            raise ApiError("该检测项不使用原始数据 Excel 导入，请用工作表导入")
        name = os.path.basename(file.filename or "import.xlsx")
        if not name.lower().endswith((".xlsx", ".xlsm", ".csv", ".docx")):
            raise ApiError("仅支持 .xlsx / .xlsm / .csv / .docx 文件")
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as out:
            out.write(await file.read())
        data = import_assessment_input(path, family, sheet_name or None)
        state.assessment_inputs[key] = data["input"]
        return ok({
            "sheet_key": key,
            "input": data["input"],
            "components": data.get("components"),
            "warnings": data.get("warnings") or [],
        }, "原始数据 Excel 导入成功，请核对后运行评定")
    except ApiError:
        raise
    except ExcelImportError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"导入原始数据失败：{e}"}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/assessment/{sheet_key}/run")
def run_assessment(sheet_key: str, body: InputBody):
    """执行当前工作表的评定；结果保存在项目状态中。"""
    try:
        state, key, base, comp, spec, columns, rows = _resolve(sheet_key)
        result = _run_one(state, key, base, comp, spec, columns, rows,
                          body.input, body.options)
        if result.get("ok"):
            message = "评定完成：%s" % result.get("conclusion")
        else:
            message = "评定未通过：%s" % "；".join(result.get("errors") or [])
        return ok(result, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"执行评定失败：{e}"}


@router.get("/assessment/{sheet_key}/result")
def assessment_result(sheet_key: str):
    """读取当前工作表最近一次评定结果。"""
    try:
        state, key, _base, _comp, _spec, _columns, _rows = _resolve(sheet_key)
        return ok(state.assessment_results.get(key), "评定结果读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取评定结果失败：{e}"}


@router.post("/assessment/run_all")
def run_all_assessments(body: RunAllBody):
    """批量评定已勾选检测项（未实现的规则会返回错误项，不中断其它项）。"""
    try:
        state = get_state()
        keys = [str(k) for k in (body.sheet_keys or []) if str(k).strip()]
        if not keys:
            keys = [k for k in state.checked_items if k in state.sheet_data]
        if not keys:
            raise ApiError("没有可评定的检测项目")
        results = {}
        warnings = []
        for key in keys:
            try:
                _state, _key, base, comp, spec, columns, rows = _resolve(key)
                results[key] = _run_one(
                    state, key, base, comp, spec, columns, rows,
                    state.assessment_inputs.get(key),
                    state.assessment_options.get(key))
            except Exception as e:  # noqa: BLE001 - 单项失败不中断
                warnings.append("%s：%s" % (key, e))
        ok_count = sum(1 for r in results.values() if r.get("ok"))
        return ok({"results": results, "warnings": warnings},
                  "批量评定完成：成功 %d/%d 项" % (ok_count, len(results)))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"批量评定失败：{e}"}
