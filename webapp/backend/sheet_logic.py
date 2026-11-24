# -*- coding: utf-8 -*-
"""表格纯数据逻辑（从桌面版 GUI Mixin 中剥离 Qt 后的等价实现）。

包含：
  - 钻芯法/回弹钻芯修正法 工作表构建（等价 CoreDrillingMixin._build_*_sheet）
  - 钻芯法/回弹钻芯修正法 自动重算（测试强度/推定值/批评定值/批均值）
  - 合并单元格校验（等价 MergeOpsMixin._merge_cells 的数据校验部分）
  - 批量向下填充（Ctrl+D 语义）

本模块禁止 import PyQt5 / 任何 Qt。
"""

import math

from deps import (ITEM_COLUMNS, ApiError, batch_assess)

# 测试荷载(kN) → 测试强度(MPa) 的单位换算因子（与桌面版 handlers.py 一致）
LOAD_TO_STRENGTH_FACTOR = 1000.0

# ── 钻芯法检测列索引（13 列，与 modules/concrete_strength/handlers.py 一致）──
CD_COL_BUILDING = 0    # 楼栋
CD_COL_BATCH = 1       # 批次
CD_COL_COMP_NO = 2     # 构件编号
CD_COL_COMP_NAME = 3   # 构件位置及名称
CD_COL_AXIS = 4        # 轴线编号
CD_COL_SAMPLE_NO = 5   # 序号
CD_COL_DIAMETER = 6    # 芯样直径(mm)
CD_COL_AREA = 7        # 截面积(mm²)
CD_COL_LOAD = 8        # 测试荷载(kN)
CD_COL_STRENGTH = 9    # 测试强度(MPa)
CD_COL_INFERRED = 10   # 推定值(MPa)
CD_COL_CRITIC = 11     # 批评定值(MPa)
CD_COL_GRADE = 12      # 设计等级

# ── 回弹钻芯修正法检测列索引（12 列）────────────────────────────────
RCD_COL_BUILDING = 0
RCD_COL_BATCH = 1
RCD_COL_COMP_NO = 2
RCD_COL_COMP_NAME = 3
RCD_COL_AXIS = 4
RCD_COL_ZONE = 5       # 钻芯测区
RCD_COL_DIAMETER = 6
RCD_COL_AREA = 7
RCD_COL_LOAD = 8
RCD_COL_STRENGTH = 9
RCD_COL_GRADE = 10     # 设计强度等级
RCD_COL_MEAN = 11      # 芯样强度均值(MPa)


def _to_float(value):
    """安全转 float；空/非法返回 None（等价桌面版 _to_float）。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_brick_rebound(params):
    """构建砖回弹法工作表：构件数 × 每构件测区数，预填批次/构件号/测区号。"""
    params = params if isinstance(params, dict) else {}
    cols = ITEM_COLUMNS.get("砖强度检测", [])
    batch = str(params.get("batch") or "1").strip() or "1"
    components = max(1, min(int(params.get("components", 10) or 10), 200))
    zones = max(1, min(int(params.get("zones_per_component", 10) or 10), 50))
    rows = []
    for comp_no in range(1, components + 1):
        for zone_no in range(1, zones + 1):
            row = ["" for _ in range(len(cols))]
            if len(row) > 4:
                row[0] = batch
                row[1] = str(comp_no)
                row[4] = str(zone_no)
            rows.append(row)
    merges = smart_brick_component_merges(rows)
    merge_formats = {(m[0], m[1]): {"align": "center"} for m in merges}
    return rows, merges, merge_formats, {
        "kind": "brick_rebound",
        "batch": batch,
        "components": components,
        "zones_per_component": zones,
    }


def smart_brick_component_merges(rows, only_columns=None):
    """按构件生成砖回弹表的纵向合并（only_columns 限定参与合并的列）。

    - 批次列：同一批次跨全部构件合并一次；
    - 构件编号、构件位置、轴号、构件平均强度：同一构件合并；
    - 批次平均值、方差、标准差、变异系数、强度标准值、评定等级：
      在同一构件的 10 行内合并，便于逐构件查看；
    - 只合并组内值完全一致的列，避免把不同值误合并。
    """
    merges = []
    if not rows:
        return merges
    merge_cols = (1, 2, 3, 12, 13, 14, 15, 16, 17, 18)
    allowed = None if only_columns is None else {int(c) for c in only_columns}
    if allowed is not None:
        merge_cols = tuple(c for c in merge_cols if c in allowed)
    batch_enabled = allowed is None or 0 in allowed
    key_cols = (0, 1, 2, 3)

    def cell(row, col):
        return str(row[col]).strip() if col < len(row) else ""

    # 组首行有值、后续行留空：先还原逐行有效值
    key_rows = []
    value_rows = []
    last_key = {}
    last_value = {}
    prev_component = ""
    for row in rows:
        raw_component = cell(row, 1)
        component_changed = bool(raw_component and prev_component
                                 and raw_component != prev_component)
        if raw_component:
            prev_component = raw_component
        key_vals = {}
        for col in key_cols:
            raw = cell(row, col)
            if raw:
                last_key[col] = raw
            key_vals[col] = last_key.get(col, "")
        value_vals = {}
        value_cols = tuple(merge_cols) + ((0,) if batch_enabled else ())
        for col in value_cols:
            raw = cell(row, col)
            if raw:
                last_value[col] = raw
            elif component_changed and col != 0:
                # 新构件首行没有明细值时，不沿用上一个构件的轴线/位置
                last_value[col] = ""
            value_vals[col] = last_value.get(col, "")
        key_rows.append(tuple(key_vals[c] for c in key_cols))
        value_rows.append(value_vals)

    start = 0
    while start < len(rows):
        end = start + 1
        group_key = key_rows[start]
        while end < len(rows) and key_rows[end] == group_key:
            end += 1
        span = end - start
        if span > 1 and any(group_key[1:]):
            for col in merge_cols:
                values = {value_rows[r].get(col, "") for r in range(start, end)}
                if len(values) == 1:
                    merges.append([start, col, span, 1])
        start = end

    # 批次列：同一批次跨全部构件合并（Excel 中批次通常只写一次）
    if batch_enabled:
        start = 0
        while start < len(rows):
            batch = value_rows[start].get(0, "")
            end = start + 1
            while end < len(rows) and value_rows[end].get(0, "") == batch:
                end += 1
            if batch and end - start > 1:
                merges.append([start, 0, end - start, 1])
            start = end
    return merges


def _generic_merge_columns(columns):
    """通用智能合并候选列：楼栋/楼层/批次/构件/轴线/检测部位等分组列。"""
    keywords = ("楼栋", "楼层", "批次", "构件编号", "构件位置", "构件名称",
                "轴线", "轴号", "检测部位", "构件类型", "部位")
    excluded = ("备注", "结论", "序号")
    selected = []
    for index, name in enumerate(columns or []):
        text = str(name or "").strip()
        if not text or any(word in text for word in excluded):
            continue
        if any(word in text for word in keywords):
            selected.append(index)
    return selected


def _is_component_detail(label):
    text = str(label or "")
    if "构件位置" in text:
        return False
    return (("轴线" in text) or ("轴号" in text)
            or (("构件名称" in text) and "位置" not in text))


def _effective_rows(rows, columns):
    """把“只有组首行有值、后续行留空”的表格还原为逐行有效值。

    智能合并直接比较原始单元格时，批次/构件位置/轴线这类只有首行有值的列
    会因为空值而被跳过。这里做有限下填：
    - 后续空单元格沿用同列上一个非空值；
    - 构件编号变化时，轴线/构件名称等构件明细列不沿用上一个构件，
      避免把不同构件的轴线误合并；
    - 批次、楼层、楼栋、构件位置等分组列允许跨构件沿用。
    """
    n_cols = len(columns or [])
    component_col = next((i for i, name in enumerate(columns or [])
                          if "构件编号" in str(name or "")), None)
    last = [""] * n_cols
    prev_component = ""
    result = []
    for row in rows or []:
        raw_component = ""
        if component_col is not None and component_col < len(row):
            raw_component = str(row[component_col] or "").strip()
        component_changed = bool(raw_component and prev_component
                                 and raw_component != prev_component)
        if raw_component:
            prev_component = raw_component
        effective = []
        for col in range(n_cols):
            raw = str(row[col] or "").strip() if col < len(row) else ""
            if raw:
                last[col] = raw
                effective.append(raw)
                continue
            label = str(columns[col] or "") if col < n_cols else ""
            if component_changed and _is_component_detail(label):
                last[col] = ""
            effective.append(last[col])
        result.append(effective)
    return result


def smart_table_merges(rows, columns, only_columns=None):
    """通用表格智能合并：连续相同的分组列纵向合并（only_columns 限定列）。

    返回 (merges, merge_columns)。空值、备注、结论和序号列不会合并；
    只处理分组描述列，数值/计算列保持原样。

    轴线/轴号列额外要求“楼栋 + 楼层 + 构件位置/名称”上下文一致，
    避免把不同楼层但轴线编号相同的单元格误合并。
    """
    merges = []
    merge_cols = _generic_merge_columns(columns)
    if only_columns is not None:
        allowed = {int(c) for c in only_columns}
        merge_cols = [c for c in merge_cols if c in allowed]
    if not rows or not merge_cols:
        return merges, merge_cols

    effective = _effective_rows(rows, columns)

    def cell(row, col):
        return row[col] if col < len(row) else ""

    axis_cols = {
        index for index, name in enumerate(columns or [])
        if "轴线" in str(name or "") or "轴号" in str(name or "")
    }
    context_cols = [
        index for index, name in enumerate(columns or [])
        if any(word in str(name or "") for word in
               ("楼栋", "楼层", "构件位置", "构件名称", "构件编号"))
    ]

    def context(row, exclude):
        return tuple(cell(row, col) for col in context_cols if col != exclude)

    for col in merge_cols:
        start = 0
        while start < len(effective):
            value = cell(effective[start], col)
            ctx = context(effective[start], col) if col in axis_cols else None
            end = start + 1
            while end < len(effective):
                if cell(effective[end], col) != value:
                    break
                if col in axis_cols and context(effective[end], col) != ctx:
                    break
                end += 1
            if value and end - start > 1:
                merges.append([start, col, end - start, 1])
            start = end
    return merges, merge_cols


def _ensure_width(rows, width):
    """把每行补齐到指定列数。"""
    for r in rows:
        if len(r) < width:
            r.extend([""] * (width - len(r)))
    return rows


def parse_design_value(grade_text):
    """解析设计强度等级字符串为数值 (MPa)："C40"→40.0；空/非法→None。"""
    if not grade_text:
        return None
    digits = ""
    for ch in str(grade_text).strip():
        if ch.isdigit() or ch == ".":
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


# ═════════════════════════════════════════════════════════════════
#  钻芯法检测：工作表构建（等价 _build_core_drilling_sheet 纯数据部分）
# ═════════════════════════════════════════════════════════════════

def build_core_drilling(params):
    """根据参数构建钻芯法检测工作表。

    params: 楼栋/构件数/芯样数/起始编号/设计等级/直径（+method/batches）
    返回 (rows, merges, merge_formats, cd_params)。
    """
    try:
        building = str(params.get("building", ""))
        n_components = int(params.get("components") or 0)
        samples_per = int(params.get("samples_per_component") or 2)
        sample_start = int(params.get("sample_start") or 1)
        grade = str(params.get("grade", ""))
        diameter = float(params.get("diameter") or 100.0)
    except (TypeError, ValueError):
        raise ApiError("钻芯法参数格式不正确（楼栋/构件数/芯样数/起始编号/设计等级/直径）")
    if n_components < 1 or samples_per < 1:
        raise ApiError("构件数与每构件芯样数必须至少为 1")
    method = params.get("method", "batch")
    batches = int(params.get("batches", 1) or 1)
    if batches < 1:
        batches = 1
    batch_size = math.ceil(n_components / batches) if n_components else 1

    total_rows = n_components * samples_per
    cols = ITEM_COLUMNS.get("钻芯法检测", [])
    rows = [["" for _ in range(len(cols))] for _ in range(total_rows)]

    # 截面积: π × (d/2)²
    area = math.pi * (diameter / 2) ** 2

    for comp_idx in range(n_components):
        comp_row_start = comp_idx * samples_per
        if method == "batch":
            comp_no = str(comp_idx % batch_size + 1)
        else:
            comp_no = str(comp_idx + 1)
        if method == "batch" and comp_idx % batch_size == 0:
            batch_no = min(batches, comp_idx // batch_size + 1)
            rows[comp_row_start][CD_COL_BATCH] = str(batch_no)
        for s in range(samples_per):
            row = comp_row_start + s
            rows[row][CD_COL_BUILDING] = building
            rows[row][CD_COL_COMP_NO] = comp_no
            rows[row][CD_COL_SAMPLE_NO] = str(sample_start + s)
            rows[row][CD_COL_DIAMETER] = f"{diameter:.1f}"
            rows[row][CD_COL_AREA] = f"{area:.2f}"
            rows[row][CD_COL_GRADE] = grade

    # 合并信息：楼栋/设计等级全表合并 + 每构件内部合并
    merges = []
    if total_rows > 1:
        merges.append((0, CD_COL_BUILDING, total_rows, 1))
        merges.append((0, CD_COL_GRADE, total_rows, 1))
    for comp_idx in range(n_components):
        r_start = comp_idx * samples_per
        if samples_per > 1:
            for c in (CD_COL_COMP_NO, CD_COL_COMP_NAME, CD_COL_AXIS,
                      CD_COL_DIAMETER, CD_COL_AREA, CD_COL_INFERRED):
                merges.append((r_start, c, samples_per, 1))
    # 批模式：批次列按批组合并
    if method == "batch":
        for batch_idx in range(batches):
            start_comp = batch_idx * batch_size
            end_comp = min(n_components, (batch_idx + 1) * batch_size)
            if end_comp <= start_comp:
                continue
            r_start = start_comp * samples_per
            row_span = (end_comp - start_comp) * samples_per
            if row_span > 1:
                merges.append((r_start, CD_COL_BATCH, row_span, 1))

    merge_formats = {(0, CD_COL_BUILDING): {"align": "center"},
                     (0, CD_COL_GRADE): {"align": "center", "bold": True}}
    for comp_idx in range(n_components):
        r_start = comp_idx * samples_per
        for c in (CD_COL_COMP_NO, CD_COL_COMP_NAME, CD_COL_AXIS,
                  CD_COL_DIAMETER, CD_COL_AREA, CD_COL_INFERRED):
            merge_formats[(r_start, c)] = {"align": "center"}
    if method == "batch":
        for batch_idx in range(batches):
            start_comp = batch_idx * batch_size
            end_comp = min(n_components, (batch_idx + 1) * batch_size)
            if end_comp <= start_comp:
                continue
            merge_formats[(start_comp * samples_per, CD_COL_BATCH)] = \
                {"align": "center"}

    cd_params = {"samples_per": samples_per, "diameter": diameter,
                 "grade": grade, "method": method, "batches": batches,
                 "building": building, "components": n_components,
                 "sample_start": sample_start}
    return rows, merges, merge_formats, cd_params


# ═════════════════════════════════════════════════════════════════
#  回弹钻芯修正法检测：工作表构建（等价 _build_rebound_core_drilling_sheet）
# ═════════════════════════════════════════════════════════════════

def build_rebound_core_drilling(params):
    """根据参数构建回弹钻芯修正法检测工作表。返回 (rows, merges, merge_formats, cd_params)。"""
    building = str(params.get("building", ""))
    batch_count = int(params.get("batches", 1) or 1)
    comps_per_batch = int(params.get("components_per_batch", 5) or 5)
    zones_per_component = int(params.get("zones_per_component", 3) or 3)
    grade = str(params.get("grade", "C40"))
    diameter = float(params.get("diameter", 100.0) or 100.0)
    if batch_count < 1 or comps_per_batch < 1 or zones_per_component < 1:
        raise ApiError("批数/每批构件数/每构件测区数必须至少为 1")

    total_rows = batch_count * comps_per_batch * zones_per_component
    cols = ITEM_COLUMNS.get("回弹钻芯修正法检测", [])
    area = math.pi * (diameter / 2) ** 2
    rows_per_batch = comps_per_batch * zones_per_component

    rows = [["" for _ in range(len(cols))] for _ in range(total_rows)]
    for b in range(batch_count):
        batch_no = str(b + 1)
        batch_start = b * rows_per_batch
        for comp_idx in range(comps_per_batch):
            comp_start = batch_start + comp_idx * zones_per_component
            comp_no = str(comp_idx + 1)
            for z in range(zones_per_component):
                row = comp_start + z
                rows[row][RCD_COL_BUILDING] = building
                rows[row][RCD_COL_BATCH] = batch_no
                rows[row][RCD_COL_COMP_NO] = comp_no
                rows[row][RCD_COL_ZONE] = str(z + 1)
                rows[row][RCD_COL_DIAMETER] = f"{diameter:.1f}"
                rows[row][RCD_COL_AREA] = f"{area:.2f}"
                rows[row][RCD_COL_GRADE] = grade

    merges = []
    if total_rows > 1:
        merges.append((0, RCD_COL_BUILDING, total_rows, 1))
    for b in range(batch_count):
        batch_start = b * rows_per_batch
        if rows_per_batch > 1:
            merges.append((batch_start, RCD_COL_BATCH, rows_per_batch, 1))
            merges.append((batch_start, RCD_COL_GRADE, rows_per_batch, 1))
            merges.append((batch_start, RCD_COL_MEAN, rows_per_batch, 1))
        for comp_idx in range(comps_per_batch):
            comp_start = batch_start + comp_idx * zones_per_component
            if zones_per_component > 1:
                merges.append((comp_start, RCD_COL_COMP_NO, zones_per_component, 1))
                merges.append((comp_start, RCD_COL_COMP_NAME, zones_per_component, 1))
                merges.append((comp_start, RCD_COL_AXIS, zones_per_component, 1))

    merge_formats = {(0, RCD_COL_BUILDING): {"align": "center"}}
    for b in range(batch_count):
        batch_start = b * rows_per_batch
        merge_formats[(batch_start, RCD_COL_BATCH)] = {"align": "center"}
        merge_formats[(batch_start, RCD_COL_GRADE)] = {"align": "center", "bold": True}
        merge_formats[(batch_start, RCD_COL_MEAN)] = {"align": "center", "bold": True}
        for comp_idx in range(comps_per_batch):
            comp_start = batch_start + comp_idx * zones_per_component
            for c in (RCD_COL_COMP_NO, RCD_COL_COMP_NAME, RCD_COL_AXIS):
                merge_formats[(comp_start, c)] = {"align": "center"}

    cd_params = {"building": building, "batches": batch_count,
                 "components_per_batch": comps_per_batch,
                 "zones_per_component": zones_per_component,
                 "grade": grade, "diameter": diameter}
    return rows, merges, merge_formats, cd_params


# ═════════════════════════════════════════════════════════════════
#  钻芯法检测：自动重算（等价 _recalc_core_drilling_row + 批评定值）
# ═════════════════════════════════════════════════════════════════

def _collect_component_strengths(rows, comp_start, samples_per):
    """收集一个构件（samples_per 行）的有效测试强度值。"""
    values = []
    for r in range(comp_start, min(comp_start + samples_per, len(rows))):
        v = _to_float(rows[r][CD_COL_STRENGTH])
        if v is not None and v > 0:
            values.append(v)
    return values


def recalc_core_drilling(rows, params, merges):
    """钻芯法全表重算：测试强度/推定值/批评定值 + 批次/批评定值列合并刷新。

    返回 (rows, merges, merge_formats)。
    """
    rows = _ensure_width(rows, CD_COL_GRADE + 1)
    samples_per = max(1, int(params.get("samples_per", 2) or 2))
    method = params.get("method", "batch")

    total = len(rows)
    # 1) 每行测试强度 + 每构件推定值
    for comp_start in range(0, total, samples_per):
        for r in range(comp_start, min(comp_start + samples_per, total)):
            area_val = _to_float(rows[r][CD_COL_AREA])
            load_val = _to_float(rows[r][CD_COL_LOAD])
            if area_val and area_val > 0 and load_val:
                strength = load_val / area_val * LOAD_TO_STRENGTH_FACTOR
                rows[r][CD_COL_STRENGTH] = f"{strength:.1f}"
            else:
                rows[r][CD_COL_STRENGTH] = ""
        strength_values = _collect_component_strengths(rows, comp_start, samples_per)
        inferred = min(strength_values) if strength_values else None
        # 推定值写入构件首行（合并锚点）
        if method == "batch":
            rows[comp_start][CD_COL_INFERRED] = "/"
        elif inferred is not None:
            rows[comp_start][CD_COL_INFERRED] = f"{inferred:.1f}"
        else:
            rows[comp_start][CD_COL_INFERRED] = ""

    # 2) 批次分组：批次列通常只在批首行写一次，后续构件为空，
    #    这里按构件顺序下填，避免把整批误拆成“只有第一个构件”。
    def batch_raw(r):
        return str(rows[r][CD_COL_BATCH] or "").strip()

    component_batches = []
    last_batch = ""
    for comp_start in range(0, total, samples_per):
        raw = batch_raw(comp_start)
        if raw:
            last_batch = raw
        component_batches.append((comp_start, last_batch))

    groups = []
    index = 0
    while index < len(component_batches):
        comp_start, raw = component_batches[index]
        if not raw:
            index += 1
            continue
        run_start = comp_start
        run_end = min(comp_start + samples_per - 1, total - 1)
        values = _collect_component_strengths(rows, comp_start, samples_per)
        index += 1
        while index < len(component_batches) and component_batches[index][1] == raw:
            next_start = component_batches[index][0]
            values.extend(_collect_component_strengths(rows, next_start, samples_per))
            run_end = min(next_start + samples_per - 1, total - 1)
            index += 1
        value = _to_float(raw)
        numeric = value is not None and math.isfinite(value) and value > 0
        token = (str(int(value)) if value == int(value) else raw) if numeric else raw
        groups.append({"token": token, "start": run_start, "end": run_end,
                       "values": values, "numeric": numeric})

    # 3) 批评定值（批模式）：按数字批次运行段计算
    for r in range(total):
        rows[r][CD_COL_CRITIC] = ""
    if method == "batch" and groups:
        D = _to_float(rows[0][CD_COL_DIAMETER])
        if D is None or D <= 0:
            D = params.get("diameter")
        design_value = parse_design_value(rows[0][CD_COL_GRADE]) \
            or parse_design_value(params.get("grade"))
        for g in groups:
            if not g["numeric"] or not g["values"]:
                continue
            try:
                result = batch_assess(D, g["values"], design_value, mode="batch")
            except Exception:
                result = {"error": "计算失败"}
            f_cu_e = result.get("f_cu_e")
            if result.get("error") or f_cu_e is None:
                continue
            if result.get("valid") is False or result.get("insufficient"):
                rows[g["start"]][CD_COL_CRITIC] = f"{f_cu_e:.1f} ⚠"
            else:
                rows[g["start"]][CD_COL_CRITIC] = f"{f_cu_e:.1f}"

    # 4) 合并刷新：重建批次列与批评定值列的合并
    kept = [m for m in merges if m[1] not in (CD_COL_BATCH, CD_COL_CRITIC)]
    merge_formats = {}
    for g in groups:
        if g["end"] - g["start"] + 1 > 1:
            kept.append((g["start"], CD_COL_BATCH, g["end"] - g["start"] + 1, 1))
        merge_formats[(g["start"], CD_COL_BATCH)] = {"align": "center"}
    for g in groups:
        if g["numeric"] and g["end"] - g["start"] + 1 > 1:
            kept.append((g["start"], CD_COL_CRITIC, g["end"] - g["start"] + 1, 1))
        if g["numeric"]:
            merge_formats[(g["start"], CD_COL_CRITIC)] = \
                {"align": "center", "bold": True}
    return rows, kept, merge_formats


# ═════════════════════════════════════════════════════════════════
#  回弹钻芯修正法检测：自动重算（测试强度 + 批均值）
# ═════════════════════════════════════════════════════════════════

def recalc_rebound_core_drilling(rows, params):
    """回弹钻芯修正法全表重算：测试强度 + 每批次芯样强度均值。返回 rows。"""
    rows = _ensure_width(rows, RCD_COL_MEAN + 1)
    total = len(rows)
    for r in range(total):
        area_val = _to_float(rows[r][RCD_COL_AREA])
        load_val = _to_float(rows[r][RCD_COL_LOAD])
        if area_val and area_val > 0 and load_val:
            strength = load_val / area_val * LOAD_TO_STRENGTH_FACTOR
            rows[r][RCD_COL_STRENGTH] = f"{strength:.1f}"
        else:
            rows[r][RCD_COL_STRENGTH] = ""

    batch_count = int(params.get("batches", 1) or 1)
    comps_per_batch = int(params.get("components_per_batch", 5) or 5)
    zones_per_component = int(params.get("zones_per_component", 3) or 3)
    rows_per_batch = comps_per_batch * zones_per_component
    for b in range(batch_count):
        batch_start = b * rows_per_batch
        batch_end = min(batch_start + rows_per_batch, total)
        values = []
        for r in range(batch_start, batch_end):
            v = _to_float(rows[r][RCD_COL_STRENGTH])
            if v is not None and v > 0:
                values.append(v)
        if batch_start < total:
            rows[batch_start][RCD_COL_MEAN] = \
                f"{sum(values) / len(values):.1f}" if values else ""
    return rows


# ═════════════════════════════════════════════════════════════════
#  合并单元格校验（等价 MergeOpsMixin._merge_cells 数据校验部分）
# ═════════════════════════════════════════════════════════════════

def validate_merges(merges, n_rows, n_cols, existing=()):
    """校验合并区域列表：越界/倒置/互相重叠均报 400。

    merges: [{start_row, end_row, start_col, end_col}, ...]
    返回 [(r, c, row_span, col_span), ...]。
    """
    def _rects_overlap(a, b):
        return (a[0] <= b[1] and b[0] <= a[1]
                and a[2] <= b[3] and b[2] <= a[3])

    checked = []
    for m in merges or []:
        try:
            r1 = int(m.get("start_row", 0))
            r2 = int(m.get("end_row", 0))
            c1 = int(m.get("start_col", 0))
            c2 = int(m.get("end_col", 0))
        except (TypeError, ValueError):
            raise ApiError("合并区域格式不正确（需要 start_row/end_row/start_col/end_col）")
        if r1 > r2 or c1 > c2:
            raise ApiError(f"合并区域起止坐标倒置（行{r1 + 1}-{r2 + 1}，列{c1 + 1}-{c2 + 1}）")
        if r1 < 0 or c1 < 0 or r2 >= n_rows or c2 >= n_cols:
            raise ApiError(
                f"合并区域越界（行{r1 + 1}-{r2 + 1}，列{c1 + 1}-{c2 + 1}，"
                f"当前表 {n_rows} 行 × {n_cols} 列）")
        rect = (r1, r2, c1, c2)
        for e in checked:
            if _rects_overlap(rect, e):
                raise ApiError(
                    f"合并区域重叠（行{r1 + 1}-{r2 + 1}，列{c1 + 1}-{c2 + 1} 与已有区域冲突）")
        for e in existing:
            e_rect = (e[0], e[0] + e[2] - 1, e[1], e[1] + e[3] - 1)
            if _rects_overlap(rect, e_rect):
                raise ApiError(
                    f"合并区域与已有合并重叠（行{r1 + 1}-{r2 + 1}，列{c1 + 1}-{c2 + 1}），"
                    f"请先取消该区域的合并")
        checked.append(rect)
    return [(r1, c1, r2 - r1 + 1, c2 - c1 + 1)
            for (r1, r2, c1, c2) in checked]


# ═════════════════════════════════════════════════════════════════
#  批量向下填充（Ctrl+D 语义）
# ═════════════════════════════════════════════════════════════════

def fill_down(rows, col_indices, row_from, row_to):
    """把 row_from 行指定列的值向下填充到 row_to 行（含）。原地修改 rows。"""
    if not rows:
        raise ApiError("当前工作表没有数据行")
    if row_from < 0 or row_from >= len(rows):
        raise ApiError(f"起始行号越界（1~{len(rows)}）")
    if row_to < row_from or row_to >= len(rows):
        raise ApiError(f"结束行号越界（{row_from + 1}~{len(rows)}）")
    for c in col_indices:
        if 0 <= c < len(rows[row_from]):
            source = rows[row_from][c]
            for r in range(row_from + 1, row_to + 1):
                if c < len(rows[r]):
                    rows[r][c] = source
    return rows
