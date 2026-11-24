# -*- coding: utf-8 -*-
"""报告生成前置检查：结构性问题阻断，抬头/概况缺失仅提示。

只做只读判断，不修改状态、不占用设备。返回 errors（阻断）与
warnings（提示）。报告抬头、人员、工程概况的空缺或占位只进 warnings，
允许先出报告后补；空数据、缺模板、未评定等仍进 errors。
"""
import datetime
import re

try:
    from report_generator.utils.report_template_map import resolve_sheet_key
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_template_map import resolve_sheet_key


PLACEHOLDER_MARKERS = ("【请填写】", "{{", "}}", "待定", "TODO", "XXX")
GENERIC_PERSONNEL = {
    "检测人", "报告编写人", "编写人", "复核人", "审核人", "批准人",
    "检测人员", "编写人员", "复核人员", "审核人员", "批准人员",
}

# (key, label, level, hint)
# 说明：报告抬头/人员/概况属于“可以后补”的信息，缺失或占位只提示，
# 不阻断生成；空数据、缺模板、未评定等结构性问题仍然阻断。
REQUIRED_FIELDS = [
    ("report_no", "报告编号", "warning"),
    ("project_name", "工程名称", "warning"),
    ("project_location", "工程地点", "warning"),
    ("client", "委托单位", "warning"),
    ("witness", "见证单位", "warning"),
    ("construction_unit", "建设单位", "warning"),
    ("contractor", "施工单位", "warning"),
    ("test_date", "检测日期", "warning"),
    ("report_date", "报告日期", "warning"),
    ("tester", "检测人", "warning"),
    ("writer", "报告编写人", "warning"),
    ("checker", "复核人", "warning"),
    ("reviewer", "审核人", "warning"),
    ("approver", "批准人", "warning"),
    ("design_unit", "设计单位", "warning"),
    ("supervision_unit", "监理单位", "warning"),
    ("survey_unit", "勘察单位", "warning"),
    ("structure_type", "结构类型", "warning"),
    ("building_area", "建筑面积", "warning"),
    ("floor_count", "层数", "warning"),
    ("building_height", "建筑高度", "warning"),
    ("start_date", "开工日期", "warning"),
    ("completion_date", "竣工日期", "warning"),
    ("inspection_purpose", "检测目的", "warning"),
]


def _text(value):
    return str(value or "").strip()


def _has_placeholder(value):
    text = _text(value)
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def _valid_rows(rows):
    return [row for row in (rows or [])
            if any(_text(cell) for cell in (row or []))]


def _parse_date(value):
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt)
        except ValueError:
            continue
    return None


def run_preflight(report_info, checked_order, sheet_data, template_set,
                  assessment_results=None):
    """返回 {"errors": [...], "warnings": [...]}。"""
    info = dict(report_info or {})
    checked_order = list(checked_order or [])
    sheet_data = dict(sheet_data or {})
    assessments = dict(assessment_results or {})
    errors, warnings = [], []

    if not checked_order:
        errors.append("没有已勾选且有数据的检测项目")
        return {"errors": errors, "warnings": warnings}

    # 1) 抬头字段与占位值
    for key, label, level in REQUIRED_FIELDS:
        value = _text(info.get(key))
        if not value:
            target = errors if level == "error" else warnings
            target.append("%s未填写" % label)
            continue
        if _has_placeholder(value):
            target = errors if level == "error" else warnings
            target.append("%s仍含占位符：%s" % (label, value[:40]))
        if key in ("tester", "writer", "checker", "reviewer", "approver") and value in GENERIC_PERSONNEL:
            target = errors if level == "error" else warnings
            target.append("%s仍为占位值“%s”" % (label, value))

    overview = _text(info.get("project_overview"))
    if _has_placeholder(overview):
        warnings.append("工程概况仍含占位符（【请填写】/{{}} 等），可先出报告后再补")

    # 2) 每个勾选项：有数据、有模板、已评定
    for key in checked_order:
        rows = _valid_rows(sheet_data.get(key))
        if not rows:
            errors.append("%s：没有有效数据，不能进入报告" % key)
            continue
        base, comp = resolve_sheet_key(key)
        if template_set is None or template_set.result_entry(base, comp) is None:
            errors.append("%s：缺少对应的报告结果表模板" % key)
        assessment = assessments.get(key) or {}
        if not assessment.get("ok"):
            errors.append("%s：尚未评定，不能生成正式结论" % key)
        else:
            for warning in (assessment.get("warnings") or []):
                if warning and warning not in warnings:
                    warnings.append("%s：%s" % (key, warning))

    # 3) 日期与编号（提示级，不阻断）
    report_no = _text(info.get("report_no"))
    if report_no and not re.match(
            "^[A-Za-z0-9\u4e00-\u9fa5]+[-_][0-9]{4}[-_][0-9]+$", report_no):
        warnings.append("报告编号“%s”不符合“前缀-年份-序号”规则，自动续号可能失效" % report_no)

    test_date = _parse_date(info.get("test_date"))
    report_date = _parse_date(info.get("report_date"))
    if test_date and report_date and report_date < test_date:
        errors.append("报告日期早于检测日期")
    if report_date and report_date.date() < datetime.date.today():
        warnings.append("报告日期早于今天，请确认是否为补发/历史报告")

    # 4) 设备表（设备占用在生成时另行校验）
    return {"errors": errors, "warnings": warnings}


def format_errors(result):
    """把预检结果转成可直接展示的多行文本。"""
    errors = list((result or {}).get("errors") or [])
    return "\n".join("· " + item for item in errors)
