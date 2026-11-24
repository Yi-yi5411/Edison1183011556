# -*- coding: utf-8 -*-
"""工作表行应用与自动计算的共享实现（不依赖 FastAPI）。

routers/sheets.py 的导入/保存路由与 ingest.py 的统一采集入口共用这一份逻辑，
避免「导入后怎么落库、什么时候重算、合并要不要保留」出现两套实现。
"""
import sheet_logic
from deps import CALC_RULES, CalcEngine, get_controller, get_state


def clean_rows(rows):
    """清洗行数据：None→""，保证为 list[list]。"""
    out = []
    for row in rows or []:
        out.append(["" if v is None else v for v in list(row)])
    return out


def pad_rows(rows, column_count):
    """行数据补齐到指定列数。"""
    for r in rows:
        if len(r) < column_count:
            r.extend([""] * (column_count - len(r)))
    return rows


def resolve_calc_item(key):
    """解析工作表键对应的计算规则键名（等价桌面版键名归一化）。"""
    controller = get_controller()
    base, _comp = controller.parse_sheet_key(key)
    base = controller.resolve_item_name(base)
    item = base or key
    return CalcEngine.get_item_name_for_calc(item, CALC_RULES)


def run_calc(key, rows):
    """对工作表跑自动计算：CalcEngine 规则 + 钻芯法专属逻辑。

    返回 (rows, marks)；marks 为 [(row, col, bool)] 计算异常标记（桌面版标红）。
    """
    controller = get_controller()
    base, _comp = controller.parse_sheet_key(key)
    base = controller.resolve_item_name(base)

    if base == "钻芯法检测":
        params = get_state().cd_params.get(key, {})
        rows, merges, merge_formats = sheet_logic.recalc_core_drilling(
            rows, params, get_state().merges.get(key, []))
        get_state().merges[key] = list(merges)
        get_state().merge_formats[key] = dict(merge_formats)
        return rows, []

    if base == "回弹钻芯修正法检测":
        params = get_state().cd_params.get(key, {})
        rows = sheet_logic.recalc_rebound_core_drilling(rows, params)
        return rows, []

    # 通用规则计算（CalcEngine，数据驱动）
    marks = []
    column_count = len(controller.get_columns(key)) or None
    rows = pad_rows(rows, column_count or 0) if column_count else rows
    row_count = len(rows)
    item_name = resolve_calc_item(key)
    if item_name:
        engine = CalcEngine(
            get_cell_func=lambda r, c: (rows[r][c] if 0 <= r < len(rows)
                                        and 0 <= c < len(rows[r]) else None),
            set_cell_func=lambda r, c, text: rows[r].__setitem__(c, text),
            set_font_func=lambda r, c, fail_mark: marks.append(
                (r, c, bool(fail_mark))),
        )
        for i in range(row_count):
            engine.apply_calc_rules(i, item_name, column_count,
                                    CALC_RULES, row_count=row_count)
    return rows, marks


def apply_rows_to_sheet(state, sheet_key, rows, append=False):
    """把导入/粘贴得到的行写进工程并立即重算。

    - append=True 追加，否则覆盖；
    - 钻芯法/回弹钻芯修正法的表格结构由参数生成：同结构回导时保留原有合并；
    - 写完后自动加入勾选项，避免「有数据但不在报告里」。
    返回 {rows, total, recalc_error, merges}。
    """
    rows = clean_rows(rows)
    if append:
        rows = list(state.sheet_data.get(sheet_key, [])) + rows
    else:
        old_count = len(state.sheet_data.get(sheet_key, []))
        old_merges = list(state.merges.get(sheet_key, []))
        old_merge_formats = dict(state.merge_formats.get(sheet_key, {}))
        if state.cd_params.get(sheet_key) and len(rows) == old_count:
            state.merges[sheet_key] = old_merges
            state.merge_formats[sheet_key] = old_merge_formats
        else:
            state.merges[sheet_key] = []
            state.merge_formats[sheet_key] = {}
        state.cell_formats[sheet_key] = {}
    state.sheet_data[sheet_key] = rows
    if sheet_key not in state.checked_items:
        state.checked_items.append(sheet_key)
    recalc_error = ""
    if any(str(v).strip() for r in rows for v in r):
        try:
            rows, _marks = run_calc(sheet_key, rows)
            state.sheet_data[sheet_key] = rows
        except Exception as e:  # noqa: BLE001
            recalc_error = str(e)
    return {
        "rows": rows,
        "total": len(rows),
        "recalc_error": recalc_error,
        "merges": [list(m) for m in state.merges.get(sheet_key, [])],
    }
