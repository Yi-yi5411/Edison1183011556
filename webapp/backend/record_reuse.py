# -*- coding: utf-8 -*-
"""历史原始记录快照 → 当前工程的复用（只做数据搬运，不重算业务口径）。

复用规则：
- 行按当前列名对齐：同名列重排、当前多出的列补空、历史独有列丢弃并告警；
- 默认覆盖目标表；append=True 追加；
- 覆盖时一并恢复当时的钻芯参数（影响表格结构与重算）与评定原始输入；
- 写库统一走 sheet_apply.apply_rows_to_sheet，与导入/粘贴同一份实现。
"""
from deps import get_controller, get_record_store, get_state
from sheet_apply import apply_rows_to_sheet
from utils.record_search import (align_rows, compare_columns, extract_sheet,
                                 sheet_summary)


class ReuseError(Exception):
    """可读的复用错误（路由层转 400）。"""


def _load_snapshot(record_id):
    record = get_record_store().get_original_record(record_id,
                                                    with_snapshot=True)
    if not record:
        raise ReuseError("原始记录不存在：%s" % record_id)
    snapshot = record.get("snapshot") or {}
    if not record.get("has_snapshot") or not snapshot:
        raise ReuseError("该原始记录没有保存工程快照，无法复用")
    return record, snapshot


def list_record_sheets(record_id):
    """列出快照里可复用的表，并与当前列定义比对兼容性。"""
    record, snapshot = _load_snapshot(record_id)
    controller = get_controller()
    sheets = []
    for sheet in sheet_summary(snapshot):
        key = sheet.get("sheet_key") or ""
        current = controller.get_columns(key) if key else []
        comparison = compare_columns(sheet.get("columns") or [], current)
        sheets.append(dict(sheet, current_columns=current,
                           compatibility=comparison))
    return {
        "record_id": record_id,
        "project_name": record.get("project_name") or "",
        "generated_at": record.get("generated_at") or "",
        "sheet_key": record.get("sheet_key") or "",
        "template_name": record.get("template_name") or "",
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def reuse_record(record_id, sheet_key=None, append=False):
    """把快照里的某张表写进当前工程，返回应用摘要。"""
    record, snapshot = _load_snapshot(record_id)
    try:
        sheet = extract_sheet(snapshot, sheet_key)
    except ValueError as e:
        raise ReuseError(str(e))

    key = sheet.get("sheet_key") or ""
    if not key:
        raise ReuseError("快照里没有工作表键，无法定位目标表")
    controller = get_controller()
    current = controller.get_columns(key)
    if not current:
        raise ReuseError("当前系统里没有工作表定义：%s（检测项目可能已移除）" % key)

    comparison = compare_columns(sheet.get("columns") or [], current)
    rows = sheet.get("rows") or []
    warnings = []
    if comparison["missing_columns"]:
        warnings.append("历史列在当前列定义中不存在，已忽略：%s"
                        % "、".join(comparison["missing_columns"][:5]))
    if comparison["extra_columns"]:
        warnings.append("当前新增列已留空：%s"
                        % "、".join(comparison["extra_columns"][:5]))
    if not comparison["same_order"] or comparison["missing_columns"]:
        rows = align_rows(rows, sheet.get("columns") or [], current)
        warnings.append("已按当前列顺序重排行数据")

    state = get_state()
    result = apply_rows_to_sheet(state, key, rows, append=bool(append))

    params_restored = False
    if sheet.get("params") and not append:
        state.cd_params[key] = dict(sheet["params"])
        params_restored = True
    input_restored = False
    if sheet.get("assessment_input") is not None and not append:
        state.assessment_inputs[key] = sheet["assessment_input"]
        input_restored = True

    return {
        "record_id": record_id,
        "source_project": record.get("project_name") or "",
        "source_generated_at": record.get("generated_at") or "",
        "sheet_key": key,
        "rows": result["total"],
        "appended": bool(append),
        "columns_reordered": not comparison["same_order"],
        "missing_columns": comparison["missing_columns"],
        "extra_columns": comparison["extra_columns"],
        "params_restored": params_restored,
        "assessment_input_restored": input_restored,
        "recalc_error": result["recalc_error"],
        "warnings": warnings,
    }
