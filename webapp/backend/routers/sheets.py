# -*- coding: utf-8 -*-
"""表格数据路由：类 Excel 的行数据/自动计算/合并/填充/导出。

自动计算复用 framework.engine.CalcEngine；钻芯法/回弹钻芯修正法专属重算
使用 sheet_logic 中剥离 Qt 后的等价纯数据逻辑；导出复用 excel_exporter。
"""

import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Union

from deps import (get_controller, get_state, ok, ApiError,
                  export_workbook)
from utils.excel_import import ExcelImportError, import_sheet_rows
from sheet_apply import (apply_rows_to_sheet, clean_rows as _clean_rows,
                         run_calc as _run_calc)
import sheet_logic

router = APIRouter(tags=["sheets"])


class RowsBody(BaseModel):
    rows: List[list]
    force: bool = False  # 允许用空表覆盖已有数据（防止过期页面误清空）


class CalcBody(BaseModel):
    rows: Optional[List[list]] = None


class MergeBody(BaseModel):
    merges: List[dict]
    append: bool = False


class SmartMergeBody(BaseModel):
    # 0-based 全量列下标；None=沿用旧行为（所有候选分组列）
    columns: Optional[List[int]] = None


class RowEditBody(BaseModel):
    index: int
    count: int = 1


def _adjust_merges_after_insert(merges, index, count):
    """在 index 行前插入 count 行后调整合并区域。"""
    out = []
    for (r, c, rs, cs) in merges:
        if r >= index:
            out.append((r + count, c, rs, cs))
        elif r < index < r + rs:
            out.append((r, c, rs + count, cs))
        else:
            out.append((r, c, rs, cs))
    return out


def _adjust_merges_after_delete(merges, start, count):
    """删除 [start, start+count) 行后调整合并区域。"""
    end = start + count - 1
    out = []
    for (r, c, rs, cs) in merges:
        r_end = r + rs - 1
        if r_end < start:
            out.append((r, c, rs, cs))
        elif r > end:
            out.append((r - count, c, rs, cs))
        else:
            overlap_start = max(r, start)
            overlap_end = min(r_end, end)
            overlap = overlap_end - overlap_start + 1
            new_rs = rs - overlap
            if new_rs > 1:
                out.append((r if r < start else start, c, new_rs, cs))
    return out


def _shift_merge_formats(formats, index, count, delete=False):
    """调整 merge_formats 的锚点行坐标。"""
    out = {}
    for (r, c), fmt in (formats or {}).items():
        if delete:
            if r >= index + count:
                out[(r - count, c)] = fmt
            elif r < index:
                out[(r, c)] = fmt
        else:
            out[(r + count if r >= index else r, c)] = fmt
    return out


class FillDownBody(BaseModel):
    col_keys: List[Union[str, int]]
    row_from: int
    row_to: int


@router.put("/sheet/{sheet_key}/rows")
def put_rows(sheet_key: str, body: RowsBody):
    """覆盖保存工作表行数据，并立即重算自动计算列（桌面端编辑即算的等价实现）。"""
    try:
        state = get_state()
        rows = _clean_rows(body.rows)
        existing = state.sheet_data.get(sheet_key, [])
        has_new = any(str(v).strip() for r in rows for v in r)
        has_old = any(str(v).strip() for r in existing for v in r)
        if has_old and not has_new and not body.force:
            raise ApiError("拒绝用空表覆盖已有数据；如确需清空请传 force=true")
        state.sheet_data[sheet_key] = rows
        marks = []
        recalc_error = ""
        if has_new:
            try:
                rows, marks = _run_calc(sheet_key, rows)
                state.sheet_data[sheet_key] = rows
            except Exception as e:  # noqa: BLE001
                # 计算失败不能阻断保存，保留原始行并把错误返回给前端
                recalc_error = str(e)
                state.sheet_data[sheet_key] = rows
        if sheet_key not in state.checked_items:
            state.checked_items.append(sheet_key)
        return ok({
            "sheet_key": sheet_key,
            "rows": rows,
            "marks": marks,
            "merges": [list(m) for m in state.merges.get(sheet_key, [])],
            "recalc_error": recalc_error,
        }, f"已保存表格数据（{len(rows)} 行）")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存表格数据失败：{e}"}


@router.post("/sheet/{sheet_key}/import_excel")
async def import_excel(sheet_key: str, file: UploadFile = File(...),
                       append: bool = Form(False),
                       sheet_name: str = Form("")):
    """从 Excel 导入工作表行：表头自动匹配当前列，默认覆盖。"""
    tmp_dir = tempfile.mkdtemp(prefix="sheet_import_")
    try:
        name = os.path.basename(file.filename or "import.xlsx")
        if not name.lower().endswith((".xlsx", ".xlsm", ".csv", ".docx")):
            raise ApiError("仅支持 .xlsx / .xlsm / .csv / .docx 文件")
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as out:
            out.write(await file.read())
        controller = get_controller()
        columns = controller.get_columns(sheet_key)
        data = import_sheet_rows(path, columns, sheet_name or None,
                                  preferred_name=sheet_key)
        state = get_state()
        result = apply_rows_to_sheet(state, sheet_key,
                                     data.get("rows") or [], append=append)
        rows = result["rows"]
        recalc_error = result["recalc_error"]
        return ok({
            "sheet_key": sheet_key,
            "rows": len(rows),
            "imported": len(data.get("rows") or []),
            "matched_columns": data.get("matched"),
            "warnings": data.get("warnings") or [],
            "merges": [list(m) for m in state.merges.get(sheet_key, [])],
            "recalc_error": recalc_error,
        }, f"已导入 {len(data.get('rows') or [])} 行（{'追加' if append else '覆盖'}）")
    except ApiError:
        raise
    except ExcelImportError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"导入 Excel 失败：{e}"}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/sheet/{sheet_key}/calc")
def calc_sheet(sheet_key: str, body: CalcBody):
    """跑自动计算，返回自动计算列更新后的 rows。"""
    try:
        state = get_state()
        rows = _clean_rows(body.rows) if body.rows is not None \
            else _clean_rows(state.sheet_data.get(sheet_key, []))
        if not rows:
            return ok({"rows": [], "marks": []}, "表格没有数据行，无需计算")
        rows, marks = _run_calc(sheet_key, rows)
        state.sheet_data[sheet_key] = rows
        return ok({
            "rows": rows,
            "marks": marks,
            "merges": [list(m) for m in state.merges.get(sheet_key, [])],
        }, "自动计算完成")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"自动计算失败：{e}"}


@router.post("/sheet/{sheet_key}/merge")
def merge_sheet(sheet_key: str, body: MergeBody):
    """保存合并单元格。

    append=false：用 body.merges 整体替换（用于取消合并/批量重设）；
    append=true：把 body.merges 追加到现有合并（用于新增合并）。
    """
    try:
        state = get_state()
        rows = state.sheet_data.get(sheet_key)
        if rows is None:
            raise ApiError(f"工作表不存在：{sheet_key}，请先勾选检测项目")
        columns = get_controller().get_columns(sheet_key)
        n_rows = max(len(rows), 1)
        n_cols = max(len(columns), max((len(r) for r in rows), default=1))
        existing = [tuple(m) for m in state.merges.get(sheet_key, [])]
        if body.append:
            new_merges = sheet_logic.validate_merges(
                body.merges, n_rows, n_cols, existing=existing)
            merges = existing + new_merges
        else:
            merges = sheet_logic.validate_merges(body.merges, n_rows, n_cols)
        state.merges[sheet_key] = merges
        fmts = state.merge_formats.setdefault(sheet_key, {})
        for (r, c, _rs, _cs) in merges:
            fmts[(r, c)] = fmts.get((r, c), {"align": "center"})
        return ok({"merges": [list(m) for m in merges]},
                  f"已保存合并单元格（{len(merges)} 处）")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"合并单元格失败：{e}"}


@router.post("/sheet/{sheet_key}/smart_merge")
def smart_merge(sheet_key: str, body: Optional[SmartMergeBody] = None):
    """通用智能合并；砖回弹额外合并构件/批次统计列。

    body.columns 给定时只处理这些列，并清掉这些候选列上的旧自动合并，
    不会再把用户没选的列一起合并。
    """
    try:
        state = get_state()
        rows = state.sheet_data.get(sheet_key)
        if rows is None:
            raise ApiError(f"工作表不存在：{sheet_key}，请先勾选检测项目")
        base, _comp = get_controller().parse_sheet_key(sheet_key)
        columns = get_controller().get_columns(sheet_key)
        n_rows = max(len(rows), 1)
        n_cols = max(len(columns), max((len(r) for r in rows), default=1))
        requested = None
        if body is not None and body.columns is not None:
            requested = {int(c) for c in body.columns
                         if isinstance(c, int) or str(c).lstrip("-").isdigit()}
            requested = {c for c in requested if 0 <= c < n_cols}
        if base == "砖强度检测":
            all_cols = set(range(0, 4)) | set(range(12, 19))
            merge_cols = all_cols if requested is None else all_cols & requested
            new_merges = sheet_logic.smart_brick_component_merges(
                rows, only_columns=merge_cols)
            message = f"已按批次/构件智能合并（{len(new_merges)} 处）"
        else:
            all_cols = set(sheet_logic._generic_merge_columns(columns))
            merge_cols = all_cols if requested is None else all_cols & requested
            new_merges, _merge_cols_list = sheet_logic.smart_table_merges(
                rows, columns, only_columns=merge_cols)
            message = f"已智能合成分组列（{len(new_merges)} 处）"
        existing = [tuple(m) for m in state.merges.get(sheet_key, [])]
        # 关键：清掉所有候选列上的旧合并，包括本次未勾选的候选列，
        # 避免上一次“全列智能合并”的残留继续影响未选择的列。
        preserved = [m for m in existing
                     if len(m) >= 4 and int(m[1]) not in all_cols]

        def _merge_dict(m):
            if isinstance(m, dict):
                return m
            return {
                "start_row": int(m[0]), "start_col": int(m[1]),
                "end_row": int(m[0]) + int(m[2]) - 1,
                "end_col": int(m[1]) + int(m[3]) - 1,
            }

        merges = sheet_logic.validate_merges(
            [_merge_dict(m) for m in preserved + new_merges],
            n_rows, n_cols)
        state.merges[sheet_key] = merges
        fmts = state.merge_formats.setdefault(sheet_key, {})
        for (r, c, _rs, _cs) in merges:
            fmts[(r, c)] = fmts.get((r, c), {"align": "center"})
        return ok({
            "rows": rows,
            "merges": [list(m) for m in merges],
            "merged_columns": sorted(int(c) for c in merge_cols),
        }, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"智能合并失败：{e}"}


@router.post("/sheet/{sheet_key}/rows/insert")
def insert_rows(sheet_key: str, body: RowEditBody):
    """在指定行前插入空白行，并同步调整合并区域。"""
    try:
        state = get_state()
        rows = state.sheet_data.get(sheet_key)
        if rows is None:
            raise ApiError(f"工作表不存在：{sheet_key}，请先勾选检测项目")
        columns = get_controller().get_columns(sheet_key)
        index = max(0, min(int(body.index), len(rows)))
        count = max(1, min(int(body.count), 200))
        blank = [["" for _ in range(len(columns))] for _ in range(count)]
        rows[index:index] = blank
        state.sheet_data[sheet_key] = rows
        state.merges[sheet_key] = _adjust_merges_after_insert(
            [tuple(m) for m in state.merges.get(sheet_key, [])], index, count)
        state.merge_formats[sheet_key] = _shift_merge_formats(
            state.merge_formats.get(sheet_key, {}), index, count)
        return ok({
            "rows": rows,
            "merges": [list(m) for m in state.merges[sheet_key]],
        }, f"已在第 {index + 1} 行插入 {count} 行")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"插入行失败：{e}"}


@router.post("/sheet/{sheet_key}/rows/delete")
def delete_rows(sheet_key: str, body: RowEditBody):
    """删除指定行，并同步裁剪合并区域。"""
    try:
        state = get_state()
        rows = state.sheet_data.get(sheet_key)
        if rows is None:
            raise ApiError(f"工作表不存在：{sheet_key}，请先勾选检测项目")
        if not rows:
            raise ApiError("当前工作表没有数据行")
        start = max(0, min(int(body.index), len(rows) - 1))
        count = max(1, min(int(body.count), len(rows) - start))
        del rows[start:start + count]
        state.sheet_data[sheet_key] = rows
        state.merges[sheet_key] = _adjust_merges_after_delete(
            [tuple(m) for m in state.merges.get(sheet_key, [])], start, count)
        state.merge_formats[sheet_key] = _shift_merge_formats(
            state.merge_formats.get(sheet_key, {}), start, count, delete=True)
        return ok({
            "rows": rows,
            "merges": [list(m) for m in state.merges[sheet_key]],
        }, f"已删除第 {start + 1}~{start + count} 行")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"删除行失败：{e}"}


@router.post("/sheet/{sheet_key}/fill_down")
def fill_down(sheet_key: str, body: FillDownBody):
    """批量向下填充（Ctrl+D 语义）：把起始行指定列的值填充到结束行。"""
    try:
        state = get_state()
        rows = state.sheet_data.get(sheet_key)
        if rows is None:
            raise ApiError(f"工作表不存在：{sheet_key}，请先勾选检测项目")
        columns = get_controller().get_columns(sheet_key)
        indices = []
        for key in body.col_keys:
            if isinstance(key, int):
                indices.append(key)
            elif str(key) in columns:
                indices.append(columns.index(str(key)))
            else:
                raise ApiError(f"列不存在：{key}")
        if not indices:
            raise ApiError("未指定要填充的列")
        sheet_logic.fill_down(rows, indices, body.row_from, body.row_to)
        state.sheet_data[sheet_key] = rows
        return ok({"rows": rows},
                  f"已向下填充 {len(indices)} 列（第 {body.row_from + 1}~{body.row_to + 1} 行）")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"向下填充失败：{e}"}


@router.get("/project/export")
def export_project():
    """导出当前项目全部已勾选检测项目到一个 Excel 工作簿。"""
    try:
        state = get_state()
        controller = get_controller()
        keys = []
        for key in state.checked_items:
            if key in state.sheet_data and key not in keys:
                keys.append(key)
        if not keys:
            raise ApiError("当前没有已勾选的检测项目可导出")
        if not any(str(v).strip() for key in keys
                   for row in state.sheet_data.get(key, []) for v in row):
            raise ApiError("已勾选的检测项目还没有数据可导出")
        out_dir = tempfile.mkdtemp(prefix="export_project_")
        safe_name = "".join(
            ch for ch in (state.project_name or "检测项目")
            if ch not in '\\/:*?"<>|').strip() or "检测项目"
        filepath = os.path.join(out_dir, f"{safe_name}_检测数据.xlsx")
        rows_by_key = {key: state.sheet_data.get(key, []) for key in keys}
        columns_by_key = {key: controller.get_columns(key) for key in keys}
        export_workbook(
            state.project_name or "检测项目",
            rows_by_key,
            columns_by_key,
            filepath,
            cell_formats={key: state.cell_formats.get(key, {}) for key in keys},
            merge_formats={key: state.merge_formats.get(key, {}) for key in keys},
            merges={key: [tuple(m) for m in state.merges.get(key, [])]
                    for key in keys},
            checked_keys=keys,
        )
        return FileResponse(
            filepath, filename=os.path.basename(filepath),
            media_type="application/vnd.openxmlformats-officedocument"
                       ".spreadsheetml.sheet")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "data": None,
                             "message": f"导出 Excel 失败：{e}"}, status_code=500)


@router.get("/sheet/{sheet_key}/export")
def export_sheet(sheet_key: str):
    """导出单个工作表为 Excel 下载（复用 excel_exporter.export_workbook）。"""
    try:
        state = get_state()
        rows = state.sheet_data.get(sheet_key)
        if not rows:
            raise ApiError(f"工作表没有数据可导出：{sheet_key}")
        columns = get_controller().get_columns(sheet_key)
        out_dir = tempfile.mkdtemp(prefix="export_sheet_")
        filepath = os.path.join(out_dir, f"{sheet_key[:31]}.xlsx")
        export_workbook(
            state.project_name, {sheet_key: rows},
            {sheet_key: columns}, filepath,
            cell_formats={sheet_key: state.cell_formats.get(sheet_key, {})},
            merge_formats={sheet_key: state.merge_formats.get(sheet_key, {})},
            merges={sheet_key: [tuple(m) for m in state.merges.get(sheet_key, [])]},
            checked_keys=[sheet_key],
        )
        filename = os.path.basename(filepath)
        return FileResponse(
            filepath, filename=filename,
            media_type="application/vnd.openxmlformats-officedocument"
                       ".spreadsheetml.sheet")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "data": None,
                             "message": f"导出 Excel 失败：{e}"}, status_code=500)
