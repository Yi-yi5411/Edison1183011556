# -*- coding: utf-8 -*-
"""检测数据评定引擎（纯函数，无 Qt 依赖）。

输入：检测项目基础名、工作表列头、二维行数据、可选的原始数据（回弹测区等）、
选项（无图纸/表号/是否输出构件统计）。
输出：结构化评定结果 + 结论类型 + 结论表述（模板 + 填充数据）。

规则定义见 utils/assessment_specs.py（来自 prompt/01~13）。
LLM/Agent 不应自行计算，只能调用本引擎。
"""
import math
import re

try:
    from report_generator.utils.assessment_specs import get_spec
    from report_generator.framework.engine.core_drilling import (
        batch_assess, parse_design_value,
    )
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.assessment_specs import get_spec
    from framework.engine.core_drilling import batch_assess, parse_design_value

_COMPONENT_MAP = {
    "梁": "混凝土梁",
    "板": "混凝土板",
    "柱": "混凝土柱",
    "剪力墙": "混凝土剪力墙",
    "墙": "混凝土剪力墙",
    "基础": "混凝土基础",
}
_CLASS_QUALIFIED = "符合规范"
_CLASS_MEETS = "符合要求"
_CLASS_UNQUALIFIED = "不符合规范"
_BLANK_DESIGN = ("", "/", "—", "-", "无", "无图纸")


# ── 基础工具 ──────────────────────────────────────────────
def _norm(text):
    s = str(text or "").replace("（", "(").replace("）", ")")
    s = re.sub(r"\([^()]*\)", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def _find_col(columns, names):
    normalized = [_norm(c) for c in (columns or [])]
    for name in names:
        target = _norm(name)
        for i, label in enumerate(normalized):
            if label and label == target:
                return i
    return None


def _cell(row, index):
    if index is None or index < 0 or index >= len(row or []):
        return ""
    return row[index]


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace("，", ",").replace(" ", "")
    if text in _BLANK_DESIGN:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _is_blank(value):
    return str(value or "").strip() in _BLANK_DESIGN


def _split_values(value):
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            n = _num(v)
            if n is not None:
                out.append(n)
        return out
    text = str(value or "").replace("，", ",")
    parts = re.split(r"[,、;；\s]+", text)
    out = []
    for part in parts:
        n = _num(part)
        if n is not None:
            out.append(n)
    return out


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _stdev(values):
    values = [v for v in values if v is not None]
    n = len(values)
    if n <= 1:
        return 0.0
    m = sum(values) / n
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def _fmt(value, decimals=1):
    if value is None:
        return ""
    try:
        return ("%%.%df" % decimals) % float(value)
    except (TypeError, ValueError):
        return str(value)


def _fmt_signed(value, decimals=1):
    if value is None:
        return ""
    f = float(value)
    if f > 1e-9:
        return "+" + _fmt(f, decimals)
    return _fmt(f, decimals)


def _value_range(values, decimals=1, unit=""):
    values = [float(v) for v in values if v is not None]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    suffix = unit or ""
    if abs(hi - lo) < 1e-9:
        return "%s%s" % (_fmt(lo, decimals), suffix)
    return "%s%s~%s%s" % (_fmt(lo, decimals), suffix,
                          _fmt(hi, decimals), suffix)


def _rate_text(value, decimals=1):
    return "" if value is None else ("%%.%df" % decimals) % float(value)


def _component_name(component=None, types=None):
    types = [str(t).strip() for t in (types or []) if str(t or "").strip()]
    distinct = []
    for t in types:
        if t not in distinct:
            distinct.append(t)
    if len(distinct) > 1:
        return "混凝土构件"
    raw = distinct[0] if distinct else str(component or "").strip()
    if not raw:
        return "混凝土构件"
    if raw.startswith("混凝土"):
        return raw
    return _COMPONENT_MAP.get(raw, "混凝土" + raw)


def _data_rows(rows):
    return [list(r) for r in (rows or []) if any(str(v).strip() for v in r)]


def _default_data():
    return {
        "component": "", "count": 0, "failed_count": 0,
        "value_range": "", "rate": "", "failed_details": "",
        "table_no": "1", "component_count": 0, "qualified": 0,
        "meets": 0, "unqualified": 0, "qualified_rate": "",
        "meets_rate": "", "unqualified_rate": "", "location": "",
    }


def format_conclusion(result, table_no=None):
    """按结果中的模板/数据重新生成结论（报告生成时传实际表号）。"""
    if not result:
        return ""
    template = result.get("template") or ""
    data = dict(result.get("data") or {})
    if table_no not in (None, ""):
        data["table_no"] = str(table_no)
    merged = _default_data()
    merged.update(data)
    try:
        return template.format(**merged)
    except Exception:
        return template


def _finish(spec, sheet_key, base_item, options, template_key,
            data, summary, details, warnings, conclusion_type,
            source="sheet_rows", point_stats=None, component_stats=None):
    template = (spec.get("templates") or {}).get(template_key, "")
    data = dict(data or {})
    data.setdefault("table_no", str((options or {}).get("table_no") or "1"))
    merged = _default_data()
    merged.update(data)
    result = {
        "ok": True,
        "sheet_key": sheet_key,
        "base_item": base_item,
        "spec_id": spec.get("id"),
        "family": spec.get("family"),
        "source": source,
        "conclusion_type": conclusion_type,
        "template_key": template_key,
        "template": template,
        "data": merged,
        "conclusion": format_conclusion({"template": template, "data": merged}),
        "summary": summary or {},
        "details": details or [],
        "warnings": warnings or [],
        "errors": [],
    }
    if point_stats is not None:
        result["point_stats"] = point_stats
    if component_stats is not None:
        result["component_stats"] = component_stats
    return result


def _error(spec, sheet_key, base_item, message, warnings=None):
    return {
        "ok": False,
        "sheet_key": sheet_key,
        "base_item": base_item,
        "spec_id": (spec or {}).get("id"),
        "family": (spec or {}).get("family"),
        "conclusion_type": "",
        "template_key": "",
        "template": "",
        "data": _default_data(),
        "conclusion": "",
        "summary": {},
        "details": [],
        "warnings": list(warnings or []),
        "errors": [message],
    }


def _classify(deviation, lower, upper, positive_is_meet=True):
    if deviation is None:
        return None
    if lower <= deviation <= upper:
        return _CLASS_QUALIFIED
    if positive_is_meet:
        return _CLASS_MEETS if deviation > upper else _CLASS_UNQUALIFIED
    # 钢筋间距：负偏差偏密=符合要求，正偏差偏疏=不符合规范
    return _CLASS_MEETS if deviation < lower else _CLASS_UNQUALIFIED


def _component_stats(points):
    """按构件汇总三类测点（仅模板2/明细使用）。"""
    groups = {}
    for p in points:
        groups.setdefault(p.get("component") or "构件", []).append(p)
    total = len(groups)
    qualified = 0
    meets = 0
    unqualified = 0
    for _name, items in groups.items():
        classes = [p.get("class") for p in items if p.get("class")]
        if classes and all(c == _CLASS_QUALIFIED for c in classes):
            qualified += 1
        elif any(c == _CLASS_UNQUALIFIED for c in classes):
            unqualified += 1
        else:
            meets += 1
    return {
        "component_count": total,
        "qualified": qualified,
        "meets": meets,
        "unqualified": unqualified,
    }


def _row_position(row, idx):
    for key in ("position", "component_code", "component_name"):
        value = str(_cell(row, idx.get(key)) or "").strip()
        if value:
            return value
    return ""


def _row_floor(row, idx):
    return str(_cell(row, idx.get("floor")) or "").strip()


def _append_detail(details, point):
    details.append({
        "floor": point.get("floor") or "全楼",
        "component": point.get("component") or "",
        "point": point.get("point") or "",
        "class": point.get("class") or "",
        "deviation": point.get("deviation"),
    })


# ── 强度类：回弹法 ─────────────────────────────────────────
def _normalize_rebound_records(raw_input, component):
    comps = raw_input
    if isinstance(raw_input, dict):
        comps = (raw_input.get("components")
                 or raw_input.get("rows")
                 or raw_input.get("data")
                 or [])
    if not isinstance(comps, list):
        return [], ["原始数据格式不正确：components 必须是数组"]
    records = []
    warnings = []
    for i, item in enumerate(comps):
        if not isinstance(item, dict):
            warnings.append("第 %d 条原始数据不是对象，已跳过" % (i + 1))
            continue
        zones = _split_values(item.get("zones") or item.get("zone_values")
                              or item.get("values") or [])
        if not zones:
            warnings.append("第 %d 条原始数据没有测区换算值，已跳过" % (i + 1))
            continue
        raw_type = (item.get("component_type") or item.get("component")
                    or component or "")
        records.append({
            "component_type": str(raw_type).strip(),
            "component_code": str(item.get("component_code")
                                  or item.get("component")
                                  or item.get("code") or ("构件%d" % (i + 1))).strip(),
            "axis": str(item.get("axis") or "").strip(),
            "floor": str(item.get("floor") or "").strip(),
            "grade": str(item.get("grade")
                         or item.get("design_grade") or "").strip(),
            "values": zones,
        })
    return records, warnings


def _strength_single_value(values, min_value=10.0):
    """返回 (推定值或 None, 是否低于最小值, 是否合格, 说明)。"""
    if not values:
        return None, False, False, "无有效测区值"
    if any(v < min_value for v in values):
        return None, True, False, "存在测区强度＜%.1f MPa" % min_value
    n = len(values)
    if n < 10:
        return min(values), False, None, "测区数＜10，取最小值"
    value = _mean(values) - 1.645 * _stdev(values)
    return round(value, 1), False, None, "测区数≥10，取 m-1.645s"


def _assess_rebound(spec, sheet_key, base_item, component, columns, rows,
                    options, raw_input):
    records, warnings = _normalize_rebound_records(raw_input, component)
    if not records:
        return _error(spec, sheet_key, base_item,
                      "回弹法评定需要原始测区数据：请填写楼层/构件编号/设计强度等级/测区换算值",
                      warnings)
    options = dict(options or {})
    no_drawing = bool(options.get("no_drawing")) or all(
        not r.get("grade") or _is_blank(r.get("grade")) for r in records)

    thresholds = spec.get("thresholds") or {}
    min_value = float(thresholds.get("min_zone_value", 10.0))
    components = []
    for rec in records:
        value, below, _meet, note = _strength_single_value(rec["values"], min_value)
        design = parse_design_value(rec.get("grade"))
        if design is None:
            meet = None
        elif below or value is None:
            meet = False
        else:
            meet = value >= design - 1e-9
        if note and note != "测区数≥10，取 m-1.645s":
            warnings.append("%s：%s" % (rec["component_code"], note))
        components.append({
            "component": rec["component_code"],
            "component_type": rec.get("component_type") or "",
            "axis": rec.get("axis") or "",
            "floor": rec.get("floor") or "",
            "grade": rec.get("grade") or "",
            "design": design,
            "n": len(rec["values"]),
            "values": rec["values"],
            "value": value,
            "below": below,
            "meet": meet,
        })

    # 批分组（构件类型 + 设计等级）
    groups = {}
    for comp in components:
        if comp["design"] is None:
            continue
        key = (comp["component_type"], comp["grade"])
        groups.setdefault(key, []).extend(comp["values"])
    batch_groups = []
    for (ctype, grade), values in groups.items():
        n = len(values)
        if n < int(thresholds.get("batch_min_n", 10)):
            continue
        m = _mean(values)
        s = _stdev(values)
        low_mean = float(thresholds.get("std_low_mean", 25.0))
        std_low = float(thresholds.get("std_low", 4.5))
        std_normal = float(thresholds.get("std_normal", 5.5))
        if (m < low_mean and s > std_low) or (low_mean <= m <= 60.0 and s > std_normal):
            warnings.append("%s-%s：标准差超限，不能作为有效批量批" % (ctype, grade))
            continue
        value = round(m - 1.645 * s, 1)
        design = parse_design_value(grade)
        batch_groups.append({
            "component_type": ctype, "grade": grade, "n": n,
            "value": value, "design": design,
            "meet": (design is not None and value >= design - 1e-9),
        })

    component_name = _component_name(component, [c["component_type"] for c in components])
    valid = [c for c in components if c["meet"] is not None]
    qualified = [c for c in valid if c["meet"]]
    failed = [c for c in valid if not c["meet"]]
    single_rate = (100.0 * len(qualified) / len(valid)) if valid else None

    if no_drawing:
        value_range = _value_range(
            [c["value"] for c in components if c["value"] is not None],
            1, "MPa")
        result = _finish(
            spec, sheet_key, base_item, options, "no_drawing",
            {"component": component_name, "value_range": value_range,
             "table_no": options.get("table_no") or "1"},
            {"total_components": len(components),
             "valid_batch_groups": len(batch_groups)},
            [], warnings, "类型三")
        result["components"] = components
        result["batch_groups"] = batch_groups
        return result

    if batch_groups:
        values = [g["value"] for g in batch_groups]
        failed_groups = [g for g in batch_groups if not g["meet"]]
        pass_groups = [g for g in batch_groups if g["meet"]]
        value_range = _value_range(values, 1, "MPa")
        failed_details = "、".join(
            "%s-%s批评定值为%.1fMPa" % (g["component_type"], g["grade"], g["value"])
            for g in failed_groups)
        if not failed_groups:
            key, ctype = "batch_pass", "类型一"
        elif not pass_groups:
            key, ctype = "batch_all_fail", "类型二"
        else:
            key, ctype = "batch_partial", "类型二"
        result = _finish(
            spec, sheet_key, base_item, options, key,
            {"component": component_name, "value_range": value_range,
             "failed_details": failed_details,
             "table_no": options.get("table_no") or "1"},
            {"total_components": len(components),
             "qualified_components": len(qualified),
             "unqualified_components": len(failed),
             "single_pass_rate": _rate_text(single_rate, 1),
             "valid_batch_groups": len(batch_groups),
             "batch_values": [g["value"] for g in batch_groups]},
            failed_groups, warnings, ctype)
        result["components"] = components
        result["batch_groups"] = batch_groups
        return result

    # 单构件评定
    values = [c["value"] for c in components if c["value"] is not None]
    value_range = _value_range(values, 1, "MPa")
    if not failed:
        key, ctype = "single_pass", "类型一"
    elif not qualified:
        key, ctype = "single_all_fail", "类型二"
    else:
        key, ctype = "single_partial", "类型二"
    details = [c for c in failed]
    result = _finish(
        spec, sheet_key, base_item, options, key,
        {"component": component_name, "count": len(valid),
         "failed_count": len(failed), "value_range": value_range,
         "table_no": options.get("table_no") or "1"},
        {"total_components": len(components),
         "qualified_components": len(qualified),
         "unqualified_components": len(failed),
         "single_pass_rate": _rate_text(single_rate, 1),
         "valid_batch_groups": 0},
        details, warnings, ctype)
    result["components"] = components
    result["batch_groups"] = []
    return result


# ── 尺寸/厚度/间距类通用 ──────────────────────────────────
def _assess_point_family(spec, sheet_key, base_item, component, columns, rows,
                         options, kind):
    spec = dict(spec or {})
    options = dict(options or {})
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "当前工作表没有数据行")
    if kind == "section":
        idx = {
            "floor": _find_col(columns, ["楼层"]),
            "position": _find_col(columns, ["构件位置及名称", "构件名称"]),
            "axis": _find_col(columns, ["轴线编号", "构件轴线编号", "构件轴号"]),
            "design_b": _find_col(columns, ["设计宽度B(mm)", "设计宽度B"]),
            "design_h": _find_col(columns, ["设计高度H(mm)", "设计高度H"]),
            "b1": _find_col(columns, ["实测宽度B1"]),
            "b2": _find_col(columns, ["实测宽度B2"]),
            "b3": _find_col(columns, ["实测宽度B3"]),
            "h1": _find_col(columns, ["实测高度H1"]),
            "h2": _find_col(columns, ["实测高度H2"]),
            "h3": _find_col(columns, ["实测高度H3"]),
        }
        required = ["design_b", "design_h", "b1", "h1"]
    elif kind == "thickness":
        idx = {
            "floor": _find_col(columns, ["楼层"]),
            "position": _find_col(columns, ["构件位置及名称", "构件名称"]),
            "axis": _find_col(columns, ["轴线编号", "构件轴线编号"]),
            "design": _find_col(columns, ["设计值(mm)", "设计值"]),
            "m1": _find_col(columns, ["实测值1(mm)", "实测值1"]),
            "m2": _find_col(columns, ["实测值2(mm)", "实测值2"]),
            "m3": _find_col(columns, ["实测值3(mm)", "实测值3"]),
            "judge": _find_col(columns, ["合格判断结果"]),
            "dev_avg": _find_col(columns, ["实测偏差平均值"]),
        }
        required = ["design", "m1"]
    else:  # spacing
        idx = {
            "floor": _find_col(columns, ["楼层"]),
            "position": _find_col(columns, ["构件位置及名称", "构件名称"]),
            "axis": _find_col(columns, ["轴线编号", "构件轴线编号"]),
            "direction": _find_col(columns, ["方向"]),
            "design": _find_col(columns, ["设计值"]),
            "m1": _find_col(columns, ["实测值1"]),
            "m2": _find_col(columns, ["实测值2"]),
            "m3": _find_col(columns, ["实测值3"]),
            "m4": _find_col(columns, ["实测值4"]),
            "m5": _find_col(columns, ["实测值5"]),
            "m6": _find_col(columns, ["实测值6"]),
            "dev_avg": _find_col(columns, ["偏差值平均值"]),
        }
        required = ["design", "m1"]
    if any(idx.get(k) is None for k in required):
        labels = {"design_b": "设计宽度B", "design_h": "设计高度H",
                  "b1": "实测宽度B1", "h1": "实测高度H1",
                  "design": "设计值", "m1": "实测值1"}
        missing = [labels.get(k, k) for k in required if idx.get(k) is None]
        return _error(spec, sheet_key, base_item,
                      "当前工作表缺少评定所需列：%s" % "、".join(missing))

    thresholds = spec.get("thresholds") or {}
    lower = float(thresholds.get("lower", -5.0))
    upper = float(thresholds.get("upper", 10.0))
    pass_rate = float(thresholds.get("pass_rate", 80.0))
    points = []
    warnings = []
    no_drawing = bool(options.get("no_drawing"))

    for row_no, row in enumerate(data_rows):
        position = _row_position(row, idx)
        if not position:
            position = "构件%d" % (row_no + 1)
        floor = _row_floor(row, idx)
        axis = str(_cell(row, idx.get("axis")) or "").strip()
        component_label = (position + ("-" + axis if axis else ""))
        if kind == "section":
            design_b = _num(_cell(row, idx.get("design_b")))
            design_h = _num(_cell(row, idx.get("design_h")))
            measured_b = [_num(_cell(row, idx.get(k))) for k in ("b1", "b2", "b3")]
            measured_h = [_num(_cell(row, idx.get(k))) for k in ("h1", "h2", "h3")]
            measured_b = [v for v in measured_b if v is not None]
            measured_h = [v for v in measured_h if v is not None]
            if not measured_b and not measured_h:
                continue
            for dim, design, measured in (("宽度", design_b, measured_b),
                                          ("高度", design_h, measured_h)):
                if not measured:
                    continue
                avg = _mean(measured)
                if design is None:
                    no_drawing = True
                    points.append({"floor": floor, "component": component_label,
                                   "point": "%s.%s" % (position, dim),
                                   "deviation": None, "class": None,
                                   "measured": avg})
                    continue
                deviation = avg - design
                cls = _classify(deviation, lower, upper, positive_is_meet=True)
                points.append({"floor": floor, "component": component_label,
                               "point": "%s.%s" % (position, dim),
                               "deviation": deviation, "class": cls,
                               "design": design, "measured": avg})
        elif kind == "thickness":
            design = _num(_cell(row, idx.get("design")))
            measured = [_num(_cell(row, idx.get(k))) for k in ("m1", "m2", "m3")]
            measured = [v for v in measured if v is not None]
            if not measured:
                continue
            avg = _mean(measured)
            pre_dev = _num(_cell(row, idx.get("dev_avg")))
            deviation = pre_dev if pre_dev is not None else (
                avg - design if design is not None else None)
            judge_col = idx.get("judge")
            judge_text = str(_cell(row, judge_col) or "").strip() if judge_col is not None else ""
            if judge_text in (_CLASS_QUALIFIED, _CLASS_MEETS, _CLASS_UNQUALIFIED):
                cls = judge_text
            else:
                cls = _classify(deviation, lower, upper, positive_is_meet=True) if deviation is not None else None
            if design is None:
                no_drawing = True
            points.append({"floor": floor, "component": component_label,
                           "point": position, "deviation": deviation,
                           "class": cls, "design": design, "measured": avg})
        else:
            design = _num(_cell(row, idx.get("design")))
            measured = [_num(_cell(row, idx.get(k)))
                        for k in ("m1", "m2", "m3", "m4", "m5", "m6")]
            measured = [v for v in measured if v is not None]
            if not measured:
                continue
            avg = _mean(measured)
            pre_dev = _num(_cell(row, idx.get("dev_avg")))
            deviation = pre_dev if pre_dev is not None else (
                avg - design if design is not None else None)
            direction = str(_cell(row, idx.get("direction")) or "").strip()
            if design is None:
                no_drawing = True
            cls = _classify(deviation, lower, upper, positive_is_meet=False) if deviation is not None else None
            points.append({"floor": floor, "component": component_label,
                           "point": "%s%s" % (position, ("-" + direction) if direction else ""),
                           "deviation": deviation, "class": cls,
                           "design": design, "measured": avg})

    if not points:
        return _error(spec, sheet_key, base_item, "没有可用于评定的测点数据")
    if not any(p.get("class") for p in points) and no_drawing:
        # 无图纸：只输出实测值范围
        measured_values = [p.get("measured") for p in points if p.get("measured") is not None]
        value_range = _value_range(measured_values, 2, "mm")
        result = _finish(
            spec, sheet_key, base_item, options, "no_drawing",
            {"component": spec.get("component_label") or _component_name(component),
             "value_range": value_range, "table_no": options.get("table_no") or "1"},
            {"total_points": len(points), "no_drawing": True},
            [], warnings, "类型三")
        result["points"] = points
        return result
    if no_drawing:
        warnings.append("存在设计值缺失，按无图纸处理")

    classified = [p for p in points if p.get("class")]
    total = len(classified)
    qualified_points = [p for p in classified if p["class"] == _CLASS_QUALIFIED]
    meets_points = [p for p in classified if p["class"] == _CLASS_MEETS]
    unqualified_points = [p for p in classified if p["class"] == _CLASS_UNQUALIFIED]
    rate = 100.0 * len(qualified_points) / total if total else 0.0
    deviations = [p["deviation"] for p in points if p.get("deviation") is not None]
    if no_drawing:
        measured_values = [p.get("measured") for p in points
                           if p.get("measured") is not None]
        value_range = _value_range(measured_values, 2, "mm")
    else:
        value_range = _value_range(deviations, 2, "mm")
    component_stats = _component_stats(classified)
    point_stats = {
        "total_points": total,
        "qualified_points": len(qualified_points),
        "meets_points": len(meets_points),
        "unqualified_points": len(unqualified_points),
        "pass_rate": round(rate, 1),
    }
    details = []
    for p in classified:
        if p["class"] != _CLASS_QUALIFIED:
            _append_detail(details, p)
    component_label = spec.get("component_label") or _component_name(component)
    if spec.get("family") == "thickness":
        component_label = "混凝土结构构件结构厚度"

    data = {
        "component": component_label,
        "rate": _rate_text(rate, 1),
        "value_range": value_range,
        "table_no": options.get("table_no") or "1",
        "component_count": component_stats["component_count"],
        "qualified": component_stats["qualified"],
        "meets": component_stats["meets"],
        "unqualified": component_stats["unqualified"],
        "qualified_rate": _rate_text(
            100.0 * component_stats["qualified"] / component_stats["component_count"], 1)
        if component_stats["component_count"] else "",
        "meets_rate": _rate_text(
            100.0 * component_stats["meets"] / component_stats["component_count"], 1)
        if component_stats["component_count"] else "",
        "unqualified_rate": _rate_text(
            100.0 * component_stats["unqualified"] / component_stats["component_count"], 1)
        if component_stats["component_count"] else "",
    }
    summary = {
        "total_points": total,
        "qualified_points": len(qualified_points),
        "meets_points": len(meets_points),
        "unqualified_points": len(unqualified_points),
        "pass_rate": round(rate, 1),
        "avg_deviation": round(_mean(deviations), 2) if deviations else None,
        "component_stats": component_stats,
        "no_drawing": no_drawing,
    }
    if no_drawing:
        key, conclusion_type = "no_drawing", "类型三"
    elif rate >= pass_rate:
        key, conclusion_type = "pass", "类型一"
    else:
        non_qualified = len(meets_points) + len(unqualified_points)
        if spec.get("family") == "spacing":
            ratio = (len(meets_points) / non_qualified) if non_qualified else 0.0
        else:
            ratio = (len(meets_points) / non_qualified) if non_qualified else 0.0
        if options.get("include_component_stats"):
            key, conclusion_type = "component_stats", "类型二"
        elif ratio >= 0.6:
            key, conclusion_type = "fail_high", "类型二"
        else:
            key, conclusion_type = "fail_rate", "类型二"
    result = _finish(
        spec, sheet_key, base_item, options, key, data, summary, details,
        warnings, conclusion_type, point_stats=point_stats,
        component_stats=component_stats)
    result["points"] = points
    return result


# ── 钢筋数量 ──────────────────────────────────────────────
def _assess_count(spec, sheet_key, base_item, component, columns, rows,
                  options, raw_input):
    spec = dict(spec or {})
    options = dict(options or {})
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "当前工作表没有数据行")
    idx = {
        "floor": _find_col(columns, ["楼层"]),
        "position": _find_col(columns, ["构件位置及名称", "构件名称"]),
        "axis": _find_col(columns, ["轴线编号", "构件轴线编号"]),
        "design": _find_col(columns, ["设计根数(梁底跨中底排)", "设计根数"]),
        "measured": _find_col(columns, ["实测根数(梁底跨中底排)", "实测根数"]),
        "design_b": _find_col(columns, ["设计根数-b", "设计根数b"]),
        "design_h": _find_col(columns, ["设计根数-h", "设计根数h"]),
        "measured_b": _find_col(columns, ["实测根数-b", "实测根数b"]),
        "measured_h": _find_col(columns, ["实测根数-h", "实测根数h"]),
    }
    two_axis = idx["design_b"] is not None and idx["design_h"] is not None
    if not two_axis and (idx["design"] is None or idx["measured"] is None):
        return _error(spec, sheet_key, base_item,
                      "当前工作表缺少设计根数/实测根数列")
    no_drawing = bool(options.get("no_drawing"))
    components = []
    warnings = []
    for row_no, row in enumerate(data_rows):
        position = _row_position(row, idx) or ("构件%d" % (row_no + 1))
        floor = _row_floor(row, idx)
        axis = str(_cell(row, idx.get("axis")) or "").strip()
        if two_axis:
            db = _num(_cell(row, idx["design_b"]))
            dh = _num(_cell(row, idx["design_h"]))
            mb = _num(_cell(row, idx["measured_b"]))
            mh = _num(_cell(row, idx["measured_h"]))
            if db is None or dh is None:
                no_drawing = True
            if mb is None or mh is None:
                warnings.append("%s：实测根数缺失，已跳过" % position)
                continue
            qualified = (db is not None and dh is not None
                         and abs(mb - db) < 1e-9 and abs(mh - dh) < 1e-9)
            components.append({
                "component": position + (("-" + axis) if axis else ""),
                "floor": floor, "design_b": db, "design_h": dh,
                "measured_b": mb, "measured_h": mh,
                "qualified": qualified,
            })
        else:
            design = _num(_cell(row, idx["design"]))
            measured = _num(_cell(row, idx["measured"]))
            if design is None:
                no_drawing = True
            if measured is None:
                warnings.append("%s：实测根数缺失，已跳过" % position)
                continue
            qualified = design is not None and abs(measured - design) < 1e-9
            components.append({
                "component": position + (("-" + axis) if axis else ""),
                "floor": floor, "design": design, "measured": measured,
                "qualified": qualified,
            })
    if not components:
        return _error(spec, sheet_key, base_item, "没有可用于评定的构件数据", warnings)
    qualified = [c for c in components if c.get("qualified")]
    unqualified = [c for c in components if not c.get("qualified")]
    component_name = spec.get("component_label") or _component_name(component)
    data = {
        "component": component_name,
        "qualified": len(qualified),
        "unqualified": len(unqualified),
        "table_no": options.get("table_no") or "1",
    }
    summary = {
        "total_components": len(components),
        "qualified_components": len(qualified),
        "unqualified_components": len(unqualified),
    }
    if no_drawing:
        key, conclusion_type = "no_drawing", "类型三"
    elif not unqualified:
        key, conclusion_type = "pass", "类型一"
    else:
        key, conclusion_type = "fail", "类型二"
    details = [c for c in unqualified]
    result = _finish(spec, sheet_key, base_item, options, key, data, summary,
                     details, warnings, conclusion_type)
    result["components"] = components
    return result


# ── 保护层 ────────────────────────────────────────────────
def _assess_cover(spec, sheet_key, base_item, component, columns, rows,
                  options, raw_input):
    spec = dict(spec or {})
    options = dict(options or {})
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "当前工作表没有数据行")
    idx = {
        "floor": _find_col(columns, ["楼层"]),
        "position": _find_col(columns, ["构件位置及名称", "构件名称"]),
        "axis": _find_col(columns, ["构件轴线编号", "轴线编号", "构件轴号"]),
        "design": _find_col(columns, ["设计值(mm)", "设计值"]),
        "m": [_find_col(columns, ["实测值%d" % i]) for i in range(1, 11)],
    }
    if idx["design"] is None or all(i is None for i in idx["m"]):
        return _error(spec, sheet_key, base_item,
                      "保护层评定需要设计值(mm)与实测值1~10列")
    thresholds = spec.get("thresholds") or {}
    lower = float(thresholds.get("lower", -7.0))
    upper = float(thresholds.get("upper", 10.0))
    veto_lower = float(thresholds.get("veto_lower", -10.5))
    veto_upper = float(thresholds.get("veto_upper", 15.0))
    pass_rate = float(thresholds.get("pass_rate", 90.0))
    no_drawing = bool(options.get("no_drawing"))
    points = []
    warnings = []
    for row_no, row in enumerate(data_rows):
        position = _row_position(row, idx) or ("构件%d" % (row_no + 1))
        floor = _row_floor(row, idx)
        axis = str(_cell(row, idx.get("axis")) or "").strip()
        design = _num(_cell(row, idx["design"]))
        measured = []
        for col in idx["m"]:
            if col is not None:
                value = _num(_cell(row, col))
                if value is not None:
                    measured.append(value)
        if not measured:
            continue
        if design is None:
            no_drawing = True
            points.append({"floor": floor, "component": position + (("-" + axis) if axis else ""),
                           "point": position, "deviation": None, "class": None,
                           "measured": measured})
            continue
        deviations = [v - design for v in measured]
        qualified = [d for d in deviations if lower <= d <= upper]
        veto = [d for d in deviations if d > veto_upper or d < veto_lower]
        points.append({
            "floor": floor,
            "component": position + (("-" + axis) if axis else ""),
            "point": position,
            "design": design,
            "measured": measured,
            "deviations": deviations,
            "qualified": len(qualified),
            "total": len(deviations),
            "veto": bool(veto),
            "max_abs": max(abs(d) for d in deviations),
            "veto_value": veto[0] if veto else None,
        })
    if not points:
        return _error(spec, sheet_key, base_item, "没有可用于评定的保护层测点", warnings)
    if no_drawing:
        measured_values = [v for p in points for v in p.get("measured") or []]
        value_range = _value_range(measured_values, 2, "mm")
        result = _finish(
            spec, sheet_key, base_item, options, "no_drawing",
            {"component": spec.get("component_label") or _component_name(component),
             "table_no": options.get("table_no") or "1"},
            {"total_points": sum(p.get("total", 0) for p in points),
             "no_drawing": True}, [], warnings, "类型三")
        result["points"] = points
        return result
    if any(p.get("veto") for p in points):
        warnings.append("存在偏差超过允许偏差 1.5 倍的测点，按一票否决处理")
    total = sum(p.get("total", 0) for p in points)
    qualified = sum(p.get("qualified", 0) for p in points)
    rate = 100.0 * qualified / total if total else 0.0
    veto_point = next((p for p in points if p.get("veto")), None)
    data = {
        "component": spec.get("component_label") or _component_name(component),
        "rate": _rate_text(rate, 2),
        "location": (veto_point or {}).get("component") or "",
        "table_no": options.get("table_no") or "1",
    }
    summary = {
        "total_points": total,
        "qualified_points": qualified,
        "pass_rate": round(rate, 2),
        "veto": bool(veto_point),
        "max_abs_deviation": max((p.get("max_abs", 0) for p in points), default=0),
    }
    if total and rate >= pass_rate and not veto_point:
        key, conclusion_type = "pass", "类型一"
    elif rate < pass_rate and not veto_point:
        key, conclusion_type = "fail_rate", "类型二"
    else:
        key, conclusion_type = "veto", "类型二"
    details = []
    for p in points:
        if p.get("veto") or p.get("qualified", 0) < p.get("total", 0):
            details.append({
                "floor": p.get("floor") or "全楼",
                "component": p.get("component"),
                "point": p.get("point"),
                "class": "超过1.5倍" if p.get("veto") else "存在不合格测点",
                "deviation": p.get("veto_value"),
            })
    result = _finish(spec, sheet_key, base_item, options, key, data, summary,
                     details, warnings, conclusion_type)
    result["points"] = points
    return result


# ── 强度类：钻芯法 ─────────────────────────────────────────
def _assess_core(spec, sheet_key, base_item, component, columns, rows,
                 options, raw_input):
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "当前工作表没有数据行")
    idx = {
        "floor": _find_col(columns, ["楼层"]),
        "batch": _find_col(columns, ["批次"]),
        "position": _find_col(columns, ["构件位置及名称", "构件名称"]),
        "code": _find_col(columns, ["构件编号"]),
        "axis": _find_col(columns, ["轴线编号", "构件轴线编号"]),
        "diameter": _find_col(columns, ["芯样直径(mm)", "芯样直径"]),
        "test": _find_col(columns, ["测试强度(MPa)", "测试强度"]),
        "load": _find_col(columns, ["测试荷载(kN)", "测试荷载"]),
        "area": _find_col(columns, ["截面积(mm²)", "截面积"]),
        "grade": _find_col(columns, ["设计等级", "设计强度等级"]),
    }
    if idx["test"] is None and (idx["load"] is None or idx["area"] is None):
        return _error(spec, sheet_key, base_item,
                      "钻芯法评定需要“测试强度(MPa)”列，或“测试荷载+截面积”列")
    options = dict(options or {})
    groups = {}
    last_code = last_position = last_axis = last_batch = ""
    last_grade = last_floor = ""
    last_diameter = None
    for row_no, row in enumerate(data_rows):
        raw_code = str(_cell(row, idx.get("code")) or "").strip()
        code_changed = bool(raw_code and last_code and raw_code != last_code)
        if raw_code:
            last_code = raw_code
        code = last_code

        raw_position = str(_cell(row, idx.get("position")) or "").strip()
        if raw_position:
            last_position = raw_position
        position = last_position

        raw_axis = str(_cell(row, idx.get("axis")) or "").strip()
        if raw_axis:
            last_axis = raw_axis
        elif code_changed:
            # 新构件首行轴线为空时，不沿用上一个构件的轴线
            last_axis = ""
        axis = last_axis

        raw_batch = str(_cell(row, idx.get("batch")) or "").strip()
        if raw_batch:
            last_batch = raw_batch
        grade = str(_cell(row, idx.get("grade")) or "").strip() or last_grade
        if grade:
            last_grade = grade
        floor = str(_cell(row, idx.get("floor")) or "").strip() or last_floor
        if floor:
            last_floor = floor
        diameter = _num(_cell(row, idx.get("diameter")))
        if diameter is not None:
            last_diameter = diameter
        else:
            diameter = last_diameter

        name = position or code or ("构件%d" % (row_no + 1))
        if axis and axis not in name:
            name = name + "-" + axis
        strength = _num(_cell(row, idx.get("test")))
        if strength is None:
            load = _num(_cell(row, idx.get("load")))
            area = _num(_cell(row, idx.get("area")))
            if load is not None and area and area > 0:
                strength = load * 1000.0 / area
        if strength is None:
            continue
        groups.setdefault(name, []).append({
            "strength": strength,
            "diameter": diameter,
            "grade": grade,
            "batch": last_batch,
            "floor": floor,
        })

    if not groups:
        return _error(spec, sheet_key, base_item, "没有有效的芯样测试强度数据")
    warnings = []
    components = []
    for name, items in groups.items():
        strengths = [it["strength"] for it in items if it["strength"] is not None]
        if not strengths:
            continue
        grade = next((it["grade"] for it in items if it["grade"]), "")
        design = parse_design_value(grade)
        diameters = [it["diameter"] for it in items if it["diameter"] is not None]
        diameter = diameters[0] if diameters else None
        if len(set(round(d, 3) for d in diameters)) > 1:
            warnings.append("%s：芯样直径不一致（%s）" % (
                name, "、".join(str(d) for d in sorted(set(diameters)))))
        if len(strengths) == 1:
            warnings.append("%s：只有1个芯样，按规程应补钻至不少于3个" % name)
        elif len(strengths) == 2:
            warnings.append("%s：只有2个芯样，数据离散性大，仅作参考" % name)
        value = min(strengths)
        components.append({
            "component": name,
            "floor": next((it["floor"] for it in items if it["floor"]), ""),
            "batch": next((it["batch"] for it in items if it["batch"]), ""),
            "grade": grade,
            "design": design,
            "diameter": diameter,
            "n": len(strengths),
            "values": strengths,
            "value": value,
            "meet": (design is not None and value >= design - 1e-9),
        })

    no_drawing = bool(options.get("no_drawing")) or all(
        c["design"] is None for c in components)
    if not no_drawing:
        for c in components:
            if c["design"] is None:
                warnings.append("%s：设计等级缺失，按无图纸处理" % c["component"])
                no_drawing = True
                break

    batch_groups = []
    group_values = {}
    for c in components:
        if c["design"] is None or c["diameter"] is None:
            continue
        key = (c.get("batch") or "", component, c["grade"],
               round(c["diameter"], 3))
        group_values.setdefault(key, []).extend(c["values"])
    for (batch, ctype, grade, diameter), values in group_values.items():
        n = len(values)
        required = 15 if abs(diameter - 100.0) < 1e-6 else 20
        label = ("%s批%s" % (ctype, batch)) if batch else ctype
        if n < required:
            warnings.append("%s-%s-D%s：芯样数 %d 少于规范最小样本量 %d，不形成有效批量批"
                            % (label, grade, diameter, n, required))
            continue
        design = parse_design_value(grade)
        result = batch_assess(diameter, values, design, mode="batch")
        if result.get("error") or result.get("valid") is False:
            warnings.append("%s-%s-D%s：批量评定无法形成有效推定（%s）"
                            % (label, grade, diameter,
                               result.get("error") or result.get("warning") or ""))
            continue
        value = result.get("f_cu_e")
        if value is None:
            continue
        batch_groups.append({
            "batch": batch, "component_type": ctype, "grade": grade,
            "diameter": diameter, "n": n, "value": value, "design": design,
            "meet": (design is not None and value >= design - 1e-9),
        })

    component_name = _component_name(component, [component])
    qualified = [c for c in components if c["meet"]]
    failed = [c for c in components if not c["meet"]]
    single_rate = (100.0 * len(qualified) / len(components)) if components else None
    if no_drawing:
        values = [c["value"] for c in components if c["value"] is not None]
        result = _finish(
            spec, sheet_key, base_item, options, "no_drawing",
            {"component": component_name,
             "value_range": _value_range(values, 1, "MPa"),
             "table_no": options.get("table_no") or "1"},
            {"total_components": len(components),
             "valid_batch_groups": len(batch_groups)},
            [], warnings, "类型三")
        result["components"] = components
        result["batch_groups"] = batch_groups
        return result

    if batch_groups:
        values = [g["value"] for g in batch_groups]
        failed_groups = [g for g in batch_groups if not g["meet"]]
        pass_groups = [g for g in batch_groups if g["meet"]]
        failed_details = "、".join(
            "%s-%s批评定值为%.1fMPa" % (g["component_type"], g["grade"], g["value"])
            for g in failed_groups)
        if not failed_groups:
            key, ctype = "batch_pass", "类型一"
        elif not pass_groups:
            key, ctype = "batch_all_fail", "类型二"
        else:
            key, ctype = "batch_partial", "类型二"
        result = _finish(
            spec, sheet_key, base_item, options, key,
            {"component": component_name,
             "value_range": _value_range(values, 1, "MPa"),
             "failed_details": failed_details,
             "table_no": options.get("table_no") or "1"},
            {"total_components": len(components),
             "qualified_components": len(qualified),
             "unqualified_components": len(failed),
             "single_pass_rate": _rate_text(single_rate, 1),
             "valid_batch_groups": len(batch_groups),
             "batch_values": [g["value"] for g in batch_groups]},
            failed_groups, warnings, ctype)
        result["components"] = components
        result["batch_groups"] = batch_groups
        return result

    values = [c["value"] for c in components if c["value"] is not None]
    if not failed:
        key, ctype = "single_pass", "类型一"
    elif not qualified:
        key, ctype = "single_all_fail", "类型二"
    else:
        key, ctype = "single_partial", "类型二"
    result = _finish(
        spec, sheet_key, base_item, options, key,
        {"component": component_name, "count": len(components),
         "failed_count": len(failed),
         "value_range": _value_range(values, 1, "MPa"),
         "table_no": options.get("table_no") or "1"},
        {"total_components": len(components),
         "qualified_components": len(qualified),
         "unqualified_components": len(failed),
         "single_pass_rate": _rate_text(single_rate, 1),
         "valid_batch_groups": 0},
        failed, warnings, ctype)
    result["components"] = components
    result["batch_groups"] = []
    return result


# ── 强度类：回弹钻芯修正法 ────────────────────────────────
def _normalize_rebound_core_records(raw_input, component):
    comps = raw_input
    if isinstance(raw_input, dict):
        comps = (raw_input.get("components")
                 or raw_input.get("rows")
                 or raw_input.get("data") or [])
    if not isinstance(comps, list):
        return [], ["原始数据格式不正确：components 必须是数组"]
    records = []
    warnings = []
    for i, item in enumerate(comps):
        if not isinstance(item, dict):
            warnings.append("第 %d 条原始数据不是对象，已跳过" % (i + 1))
            continue
        zones = _split_values(item.get("zones") or item.get("zone_values") or [])
        if not zones:
            warnings.append("第 %d 条原始数据没有测区换算值，已跳过" % (i + 1))
            continue
        cores = []
        for core in (item.get("cores") or item.get("corrections") or []):
            if isinstance(core, dict):
                actual = _num(core.get("actual") or core.get("f_cor")
                              or core.get("core") or core.get("strength"))
                zone = _num(core.get("zone") or core.get("f_cu")
                            or core.get("rebound"))
            elif isinstance(core, (list, tuple)) and len(core) >= 2:
                actual, zone = _num(core[0]), _num(core[1])
            else:
                actual = zone = None
            if actual is not None and zone is not None and abs(zone) > 1e-9:
                cores.append({"actual": actual, "zone": zone})
        raw_type = (item.get("component_type") or item.get("component")
                    or component or "")
        records.append({
            "component_type": str(raw_type).strip(),
            "component_code": str(item.get("component_code")
                                  or item.get("component")
                                  or item.get("code") or ("构件%d" % (i + 1))).strip(),
            "axis": str(item.get("axis") or "").strip(),
            "floor": str(item.get("floor") or "").strip(),
            "grade": str(item.get("grade")
                         or item.get("design_grade") or "").strip(),
            "zones": zones,
            "cores": cores,
            "diameter": _num(item.get("diameter")),
            "method": str(item.get("method") or "修正系数法").strip(),
        })
    return records, warnings


def _assess_rebound_core(spec, sheet_key, base_item, component, columns, rows,
                         options, raw_input):
    records, warnings = _normalize_rebound_core_records(raw_input, component)
    if not records:
        return _error(spec, sheet_key, base_item,
                      "回弹钻芯修正法评定需要原始数据：测区换算值 + 成对芯样数据",
                      warnings)
    options = dict(options or {})
    thresholds = spec.get("thresholds") or {}
    no_drawing = bool(options.get("no_drawing")) or all(
        not r.get("grade") or _is_blank(r.get("grade")) for r in records)

    # 修正批：构件类型 + 设计等级 + 芯样直径；芯样数 n>=6 且直径一致
    correction_groups = {}
    for rec in records:
        if not rec["cores"] or rec["diameter"] is None:
            continue
        key = (rec["component_type"], rec["grade"], round(rec["diameter"], 3))
        correction_groups.setdefault(key, []).extend(rec["cores"])

    corrections = {}
    batch_corrections = []
    for key, pairs in correction_groups.items():
        ctype, grade, diameter = key
        n = len(pairs)
        if n < int(thresholds.get("correction_min_n", 6)):
            warnings.append("%s-%s-D%s：修正芯样数 %d < 6，不能形成有效修正批"
                            % (ctype, grade, diameter, n))
            continue
        ratios = [p["actual"] / p["zone"] for p in pairs if abs(p["zone"]) > 1e-9]
        deltas = [p["actual"] - p["zone"] for p in pairs]
        eta = _mean(ratios)
        delta = _mean(deltas)
        if eta is None or delta is None:
            warnings.append("%s-%s-D%s：修正数据无效" % (ctype, grade, diameter))
            continue
        method = ""
        if isinstance(raw_input, dict):
            method = str(raw_input.get("method") or "").strip()
        if not method:
            method = next((r.get("method") for r in records
                           if r.get("method")), "修正系数法")
        corrections[key] = {
            "method": method, "eta": eta, "delta": delta,
            "n": n, "diameter": diameter,
        }
        batch_corrections.append({
            "key": key, "component_type": ctype, "grade": grade,
            "diameter": diameter, "n": n, "eta": eta, "delta": delta,
            "method": method,
        })

    components = []
    for rec in records:
        design = parse_design_value(rec.get("grade"))
        key = None
        if rec["diameter"] is not None:
            key = (rec["component_type"], rec["grade"], round(rec["diameter"], 3))
        correction = corrections.get(key)
        if correction:
            if correction["method"] == "修正量法":
                values = [v + correction["delta"] for v in rec["zones"]]
            else:
                values = [round(v * correction["eta"], 1) for v in rec["zones"]]
        else:
            values = list(rec["zones"])
            warnings.append("%s：无有效修正批，按原回弹换算值评定"
                            % rec["component_code"])
        values = [round(v, 1) for v in values]
        min_value = float(thresholds.get("min_zone_value", 10.0))
        value, below, _meet, note = _strength_single_value(values, min_value)
        if below:
            meet = False
        elif value is None:
            meet = False
        elif design is None:
            meet = None
        else:
            meet = value >= design - 1e-9
        components.append({
            "component": rec["component_code"],
            "component_type": rec["component_type"],
            "axis": rec["axis"],
            "floor": rec["floor"],
            "grade": rec["grade"],
            "design": design,
            "diameter": rec.get("diameter"),
            "n": len(values),
            "values": values,
            "value": value,
            "below": below,
            "meet": meet,
            "corrected": bool(correction),
        })

    # 批：修正批必须有效，再按修正后测区值统计
    batch_values = {}
    for comp in components:
        key = None
        if comp["design"] is not None and comp.get("diameter") is not None:
            key = (comp["component_type"], comp["grade"],
                   round(comp["diameter"], 3))
        if key is None or key not in corrections:
            continue
        batch_values.setdefault(key, []).extend(comp["values"])
    batch_groups = []
    for (ctype, grade, diameter), values in batch_values.items():
        n = len(values)
        if n < int(thresholds.get("batch_min_n", 10)):
            continue
        m = _mean(values)
        s = _stdev(values)
        low_mean = float(thresholds.get("std_low_mean", 25.0))
        std_low = float(thresholds.get("std_low", 4.5))
        std_normal = float(thresholds.get("std_normal", 5.5))
        if (m < low_mean and s > std_low) or (low_mean <= m <= 60.0 and s > std_normal):
            warnings.append("%s-%s：修正后标准差超限，不能作为有效批量批"
                            % (ctype, grade))
            continue
        value = round(m - 1.645 * s, 1)
        design = parse_design_value(grade)
        batch_groups.append({
            "component_type": ctype, "grade": grade, "diameter": diameter,
            "n": n, "value": value, "design": design,
            "meet": (design is not None and value >= design - 1e-9),
        })

    component_name = _component_name(component, [c["component_type"] for c in components])
    qualified = [c for c in components if c["meet"]]
    failed = [c for c in components if not c["meet"]]
    single_rate = (100.0 * len(qualified) / len(components)) if components else None
    if no_drawing:
        values = [c["value"] for c in components if c["value"] is not None]
        result = _finish(
            spec, sheet_key, base_item, options, "no_drawing",
            {"component": component_name,
             "value_range": _value_range(values, 1, "MPa"),
             "table_no": options.get("table_no") or "1"},
            {"total_components": len(components),
             "correction_groups": len(batch_corrections)},
            [], warnings, "类型三")
        result["components"] = components
        result["corrections"] = batch_corrections
        return result

    if batch_groups:
        values = [g["value"] for g in batch_groups]
        failed_groups = [g for g in batch_groups if not g["meet"]]
        pass_groups = [g for g in batch_groups if g["meet"]]
        failed_details = "、".join(
            "%s-%s批评定值为%.1fMPa" % (g["component_type"], g["grade"], g["value"])
            for g in failed_groups)
        if not failed_groups:
            key, ctype = "batch_pass", "类型一"
        elif not pass_groups:
            key, ctype = "batch_all_fail", "类型二"
        else:
            key, ctype = "batch_partial", "类型二"
        result = _finish(
            spec, sheet_key, base_item, options, key,
            {"component": component_name,
             "value_range": _value_range(values, 1, "MPa"),
             "failed_details": failed_details,
             "table_no": options.get("table_no") or "1"},
            {"total_components": len(components),
             "qualified_components": len(qualified),
             "unqualified_components": len(failed),
             "single_pass_rate": _rate_text(single_rate, 1),
             "valid_batch_groups": len(batch_groups),
             "batch_values": [g["value"] for g in batch_groups],
             "correction_groups": len(batch_corrections)},
            failed_groups, warnings, ctype)
        result["components"] = components
        result["batch_groups"] = batch_groups
        result["corrections"] = batch_corrections
        return result

    values = [c["value"] for c in components if c["value"] is not None]
    if not failed:
        key, ctype = "single_pass", "类型一"
    elif not qualified:
        key, ctype = "single_all_fail", "类型二"
    else:
        key, ctype = "single_partial", "类型二"
    result = _finish(
        spec, sheet_key, base_item, options, key,
        {"component": component_name, "count": len(components),
         "failed_count": len(failed),
         "value_range": _value_range(values, 1, "MPa"),
         "table_no": options.get("table_no") or "1"},
        {"total_components": len(components),
         "qualified_components": len(qualified),
         "unqualified_components": len(failed),
         "single_pass_rate": _rate_text(single_rate, 1),
         "valid_batch_groups": 0,
         "correction_groups": len(batch_corrections)},
        failed, warnings, ctype)
    result["components"] = components
    result["batch_groups"] = []
    result["corrections"] = batch_corrections
    return result


def _assess_anchor(spec, sheet_key, base_item, component, columns, rows,
                   options, raw_input):
    """填充砌体墙化学植筋锚固承载力：逐根判定，全部满足才合格。"""
    spec = dict(spec or {})
    options = dict(options or {})
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "当前工作表没有数据行")

    idx = {
        "position": _find_col(columns, ["构件名称", "构件位置及名称"]),
        "axis": _find_col(columns, ["构件轴线编号", "轴线编号", "构件轴号"]),
        "grade": _find_col(columns, ["钢筋牌号/植筋规格", "钢筋牌号"]),
        "diameter": _find_col(columns, ["公称直径(mm)", "公称直径"]),
        "load": _find_col(columns, ["检测荷载（kN）", "检测荷载", "检验荷载（kN）", "检验荷载"]),
        "drop": _find_col(columns, ["持荷2min内荷载值降低率",
                                     "持续2min内荷载降低率",
                                     "持荷2min内荷载降低率"]),
        "phenomenon": _find_col(columns, ["实测现象", "试验现象"]),
        "conclusion": _find_col(columns, ["结论", "试验结果"]),
    }
    if idx["load"] is None or idx["drop"] is None:
        return _error(spec, sheet_key, base_item,
                      "锚固承载力评定需要检测荷载、持荷2min荷载降低率列")

    thresholds = spec.get("thresholds") or {}
    min_load = float(thresholds.get("min_load", 6.0))
    max_drop = float(thresholds.get("max_drop", 0.05))
    warnings = []
    points = []
    failed = []

    def _unit_num(value):
        text = str(value or "").strip().replace("kN", "").replace("KN", "")
        return _num(text)

    def _drop_ratio(value):
        text = str(value or "").strip()
        if not text:
            return None
        percent = "%" in text
        num = _num(text.replace("%", ""))
        if num is None:
            return None
        if percent:
            return num / 100.0
        return num / 100.0 if abs(num) > 1 else num

    for row_no, row in enumerate(data_rows):
        position = _row_position(row, idx) or ("构件%d" % (row_no + 1))
        axis = str(_cell(row, idx.get("axis")) or "").strip()
        grade = str(_cell(row, idx.get("grade")) or "").strip()
        diameter = _num(_cell(row, idx.get("diameter")))
        load = _unit_num(_cell(row, idx.get("load")))
        drop = _drop_ratio(_cell(row, idx.get("drop")))
        phenomenon = str(_cell(row, idx.get("phenomenon")) or "").strip()
        conclusion = str(_cell(row, idx.get("conclusion")) or "").strip()

        reason = ""
        if "不合格" in conclusion or "不符合" in conclusion:
            reason = "逐行结论为不合格"
        elif load is not None and load < min_load:
            reason = "检测荷载 %.1fkN 低于 %.1fkN" % (load, min_load)
        elif drop is not None and drop > max_drop:
            reason = "荷载降低率 %.2f%% 超过 %.1f%%" % (
                drop * 100, max_drop * 100)
        elif phenomenon and (
                ("裂缝" in phenomenon and "无裂缝" not in phenomenon)
                or ("滑移" in phenomenon and "无滑移" not in phenomenon)):
            reason = "试验现象存在裂缝/滑移"
        elif conclusion and ("符合" in conclusion or "合格" in conclusion):
            reason = ""
        elif load is None or drop is None:
            reason = "缺少检测荷载/荷载降低率，无法判定"

        item = {
            "floor": "",
            "component": position + (("-" + axis) if axis else ""),
            "axis": axis,
            "grade": grade,
            "diameter": diameter,
            "load": load,
            "drop": drop,
            "phenomenon": phenomenon,
            "conclusion": conclusion,
            "pass": not reason,
            "reason": reason,
        }
        points.append(item)
        if reason:
            failed.append(item)

    total = len(points)
    failed_count = len(failed)
    failed_text = "、".join(p["component"] for p in failed[:8])
    if failed_count > 8:
        failed_text += " 等 %d 根" % failed_count
    detail_text = ("（不合格位置：%s）" % failed_text) if failed_text else ""
    data = {
        "component": spec.get("component_label") or _component_name(component),
        "count": total,
        "failed_count": failed_count,
        "failed_details": detail_text,
        "table_no": options.get("table_no") or "1",
    }
    summary = {
        "total": total,
        "passed": total - failed_count,
        "failed": failed_count,
        "pass_rate": round(100.0 * (total - failed_count) / total, 2) if total else 0.0,
    }
    if failed_count:
        key, conclusion_type = "fail", "类型二"
        warnings.append("存在 %d 根锚固试件不满足要求" % failed_count)
    else:
        key, conclusion_type = "pass", "类型一"
    result = _finish(spec, sheet_key, base_item, options, key, data, summary,
                     failed, warnings, conclusion_type)
    result["points"] = points
    return result


def _assess_record_check(spec, sheet_key, base_item, component, columns,
                          rows, options, raw_input):
    """逐行结论汇总型：只按采集表已有结论/等级评定汇总，不另造阈值。"""
    spec = dict(spec or {})
    options = dict(options or {})
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "当前工作表没有数据行")

    idx = {
        "position": _find_col(columns, ["构件位置及名称", "构件名称", "焊缝位置及名称"]),
        "axis": _find_col(columns, ["轴线编号", "构件轴线编号", "构件轴号"]),
        "conclusion": _find_col(columns, ["结论", "试验结果", "等级评定"]),
    }
    warnings = []
    points = []
    failed = []
    passed = 0
    undetermined = 0

    for row_no, row in enumerate(data_rows):
        position = _row_position(row, idx) or ("构件%d" % (row_no + 1))
        axis = str(_cell(row, idx.get("axis")) or "").strip()
        text = str(_cell(row, idx.get("conclusion")) or "").strip()
        if "不合格" in text or "不符合" in text or "未通过" in text:
            state = "fail"
            failed.append({"component": position, "axis": axis, "conclusion": text})
        elif "合格" in text or "符合" in text or "通过" in text:
            state = "pass"
            passed += 1
        else:
            state = "undetermined"
            undetermined += 1
        points.append({
            "floor": "",
            "component": position + (("-" + axis) if axis else ""),
            "axis": axis,
            "conclusion": text,
            "state": state,
        })

    total = len(points)
    failed_count = len(failed)
    if failed_count:
        key, conclusion_type = "fail", "类型二"
        warnings.append("存在 %d 处逐行结论不合格" % failed_count)
    elif passed == total:
        key, conclusion_type = "pass", "类型一"
    elif passed == 0:
        key, conclusion_type = "no_judgement", "类型三"
        warnings.append("全部 %d 处缺少明确判定结论，仅记录" % undetermined)
    else:
        key, conclusion_type = "partial", "类型三"
        warnings.append("有 %d 处缺少明确判定结论，仅记录" % undetermined)

    failed_text = "、".join(p["component"] for p in failed[:8])
    if failed_count > 8:
        failed_text += " 等 %d 处" % failed_count
    detail_text = ("（不合格位置：%s）" % failed_text) if failed_text else ""
    data = {
        "component": spec.get("component_label") or _component_name(component),
        "count": total,
        "failed_count": failed_count,
        "failed_details": detail_text,
        "table_no": options.get("table_no") or "1",
    }
    summary = {
        "total": total,
        "passed": passed,
        "failed": failed_count,
        "undetermined": undetermined,
        "pass_rate": round(100.0 * passed / total, 2) if total else 0.0,
    }
    result = _finish(spec, sheet_key, base_item, options, key, data, summary,
                     failed, warnings, conclusion_type)
    result["points"] = points
    return result


def _assess_brick(spec, sheet_key, base_item, component, columns, rows,
                  options, raw_input):
    """砖回弹法评定：按构件平均强度统计批次并比较设计等级。"""
    data_rows = _data_rows(rows)
    if not data_rows:
        return _error(spec, sheet_key, base_item, "工作表没有可评定的砖回弹数据")
    idx = {
        "batch": _find_col(columns, ["批次"]),
        "component": _find_col(columns, ["构件编号"]),
        "location": _find_col(columns, ["构件位置及类型", "构件位置及名称"]),
        "axis": _find_col(columns, ["轴号编号", "轴线编号"]),
        "component_mean": _find_col(columns, ["构件平均强度"]),
        "grade": _find_col(columns, ["评定等级"]),
        "avg": _find_col(columns, ["批次平均值"]),
        "std": _find_col(columns, ["标准差"]),
        "cv": _find_col(columns, ["变异系数"]),
        "std_value": _find_col(columns, ["强度标准值"]),
    }
    if idx["batch"] is None or idx["grade"] is None:
        return _error(spec, sheet_key, base_item,
                      "砖回弹表缺少“批次”或“评定等级”列，请重新生成表格")
    if idx["component_mean"] is None:
        return _error(spec, sheet_key, base_item,
                      "砖回弹表缺少“构件平均强度”列，请重新生成表格")

    def cell(row, key):
        return str(_cell(row, idx[key]) or "").strip()

    def component_key(row):
        return (cell(row, "batch"), cell(row, "component"),
                cell(row, "location"), cell(row, "axis"))

    batches = {}
    for row in data_rows:
        batch = cell(row, "batch")
        if not batch:
            continue
        key = component_key(row)
        item = batches.setdefault(batch, {"components": {}, "grades": set()})
        mean = _num(_cell(row, idx["component_mean"]))
        if mean is not None:
            item["components"][key] = mean
        grade = cell(row, "grade")
        if grade:
            item["grades"].add(grade)

    if not batches:
        return _error(spec, sheet_key, base_item,
                      "没有找到有效批次数据，请先填写批次和构件数据并计算")

    thresholds = spec.get("thresholds") or {}
    grade_table = thresholds.get("grades") or {}
    rank = {name: i for i, name in enumerate(
        ["MU10", "MU15", "MU20", "MU25", "MU30"])}

    design_grade = ""
    if isinstance(raw_input, dict):
        design_grade = str(raw_input.get("design_grade") or "").strip().upper()
    design_valid = design_grade in rank if design_grade else False

    details = []
    grades = []
    all_pass = True
    warnings = []
    total_components = 0
    for batch_name in sorted(batches.keys()):
        item = batches[batch_name]
        comp_values = list(item["components"].values())
        total_components += len(comp_values)
        batch_grades = sorted(item["grades"])
        if not batch_grades:
            return _error(spec, sheet_key, base_item,
                          "批次“%s”尚未计算评定等级，请先点击“计算”" % batch_name)
        if len(batch_grades) > 1:
            warnings.append("批次“%s”存在多个评定等级：%s，取最低等级参与比较"
                            % (batch_name, "、".join(batch_grades)))
        grade = min(batch_grades, key=lambda g: rank.get(g, -1))
        grades.append(grade)
        avg = _mean(comp_values)
        std = _stdev(comp_values) if len(comp_values) > 1 else None
        cv = (std / avg) if (std is not None and avg) else None
        std_value = (avg - 1.8 * std) if (std is not None and avg is not None) else None
        display_avg = _num(_cell(next((r for r in data_rows
                                       if cell(r, "batch") == batch_name), []), idx["avg"]))
        display_std = _num(_cell(next((r for r in data_rows
                                       if cell(r, "batch") == batch_name), []), idx["std"]))
        display_std_value = _num(_cell(next((r for r in data_rows
                                             if cell(r, "batch") == batch_name), []), idx["std_value"]))
        if display_avg is not None:
            avg = display_avg
        if display_std is not None:
            std = display_std
        if display_std_value is not None:
            std_value = display_std_value
        if len(comp_values) < 10:
            warnings.append("批次“%s”参与评定的构件数为 %d 个，少于 10 个，"
                            "批评定代表性有限" % (batch_name, len(comp_values)))
        if design_valid and rank.get(grade, -1) < rank[design_grade]:
            all_pass = False
        details.append({
            "批次": batch_name,
            "构件数": len(comp_values),
            "构件平均强度范围": _value_range(comp_values, 2, "MPa"),
            "批次平均值": "" if avg is None else _fmt(avg, 2) + " MPa",
            "标准差": "" if std is None else _fmt(std, 2) + " MPa",
            "变异系数": "" if cv is None else _fmt(cv * 100, 2) + "%",
            "强度标准值": "" if std_value is None else _fmt(std_value, 2) + " MPa",
            "评定等级": grade,
        })

    unique_grades = []
    for grade in grades:
        if grade not in unique_grades:
            unique_grades.append(grade)
    grade_text = "、".join(unique_grades) if unique_grades else "—"
    if not design_grade:
        template_key = "no_design"
        conclusion_type = "类型三"
        message = "所检砖砌体砖强度评定为%s，本次仅提供检测结果。" % grade_text
    elif not design_valid:
        template_key = "no_design"
        conclusion_type = "类型三"
        warnings.append("设计等级“%s”无法识别，按无设计等级处理" % design_grade)
        message = "所检砖砌体砖强度评定为%s，本次仅提供检测结果。" % grade_text
    elif all_pass:
        template_key = "pass"
        conclusion_type = "类型一"
        message = "所检砖砌体砖强度评定为%s，满足设计强度等级%s要求。" % (
            grade_text, design_grade)
    else:
        template_key = "fail"
        conclusion_type = "类型二"
        message = "所检砖砌体砖强度评定为%s，不满足设计强度等级%s要求。" % (
            grade_text, design_grade)

    return _finish(
        spec, sheet_key, base_item, options, template_key,
        {
            "grade": grade_text,
            "design_grade": design_grade if design_valid else "—",
        },
        {
            "批次数": len(batches),
            "构件数": total_components,
            "评定等级": grade_text,
            "设计等级": design_grade if design_valid else "未填写",
        },
        details,
        warnings,
        conclusion_type,
        source="sheet_rows",
    )


# ── 对外入口 ──────────────────────────────────────────────
def assess(sheet_key, base_item, component, columns, rows,
           options=None, raw_input=None):
    """执行单个检测项目的评定。

    :param sheet_key: 工作表键（如“回弹法检测(...)（墙）”）
    :param base_item: 规范化后的检测项目基础名
    :param component: 构件名（墙/梁/柱/板/剪力墙/基础，可为空）
    :param columns: 列头列表
    :param rows: 二维行数据
    :param options: {no_drawing, table_no, include_component_stats}
    :param raw_input: 回弹法等需要的原始数据
    """
    spec = get_spec(base_item)
    if spec is None:
        return _error(None, sheet_key, base_item,
                      "未找到检测项目评定规则：%s" % base_item)
    if not spec.get("implemented"):
        return _error(spec, sheet_key, base_item,
                      "“%s”的评定规则尚未接入，请先使用现有汇总逻辑" % spec.get("name"))
    family = spec.get("family")
    if family == "rebound":
        result = _assess_rebound(spec, sheet_key, base_item, component,
                                 columns, rows, options, raw_input)
        if result.get("ok"):
            result["source"] = "raw_input"
        return result
    if family == "rebound_core":
        result = _assess_rebound_core(spec, sheet_key, base_item, component,
                                      columns, rows, options, raw_input)
        if result.get("ok"):
            result["source"] = "raw_input"
        return result
    if family == "core":
        return _assess_core(spec, sheet_key, base_item, component,
                            columns, rows, options, raw_input)
    if family in ("section", "thickness", "spacing"):
        return _assess_point_family(spec, sheet_key, base_item, component,
                                    columns, rows, options, family)
    if family == "count":
        return _assess_count(spec, sheet_key, base_item, component,
                             columns, rows, options, raw_input)
    if family == "cover":
        return _assess_cover(spec, sheet_key, base_item, component,
                             columns, rows, options, raw_input)
    if family == "anchor":
        return _assess_anchor(spec, sheet_key, base_item, component,
                              columns, rows, options, raw_input)
    if family == "record_check":
        return _assess_record_check(spec, sheet_key, base_item, component,
                                    columns, rows, options, raw_input)
    if family == "brick":
        return _assess_brick(spec, sheet_key, base_item, component,
                             columns, rows, options, raw_input)
    return _error(spec, sheet_key, base_item,
                  "暂不支持该检测项目评定族：%s" % family)
