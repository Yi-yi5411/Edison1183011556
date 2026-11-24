# -*- coding: utf-8 -*-
"""报告事实包（report.facts/1）：把"事实"与"措辞"分开。

- 事实：项目抬头、检测项目/列/行、评定结论与统计、规范清单、设备、模板；
  全部来自入参，不含任何模型生成内容，可重复、可核对。
- 措辞底稿：overview（工程概况）、basis（检测依据）、conclusions（结论句）
  由 report_narrative / assessment_engine 确定性生成；上层可只替换这几段文字，
  由 report_render.render_from_facts(..., narrative=...) 写回。

任何需要写进报告的数值都必须先出现在事实包里；措辞层只允许改写句子，
不允许新增数值——这是报告可追溯性的底线。
"""
import datetime

try:
    from report_generator.utils.assessment_engine import format_conclusion
    from report_generator.utils.report_narrative import (
        equipment_for, item_narrative, overview_text, standards_for)
    from report_generator.utils.report_chapters import next_conclusion_no
    from report_generator.utils.report_items import (
        category_key, category_number_map)
    from report_generator.utils.report_template_map import (
        build_conclusion as build_conclusion_sentence, resolve_sheet_key)
    from report_generator.utils.report_templates import ReportTemplateSet
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.assessment_engine import format_conclusion
    from utils.report_narrative import (
        equipment_for, item_narrative, overview_text, standards_for)
    from utils.report_chapters import next_conclusion_no
    from utils.report_items import category_key, category_number_map
    from utils.report_template_map import (
        build_conclusion as build_conclusion_sentence, resolve_sheet_key)
    from utils.report_templates import ReportTemplateSet

SCHEMA = "report.facts/1"

# 评定结果里进入事实包的字段（points/details 体积大且可重算，不复制；
# template/data 保留：结论句需要按实际表号重新格式化）
ASSESSMENT_KEYS = ("ok", "sheet_key", "base_item", "family", "spec_id",
                   "source", "template_key", "template", "data",
                   "conclusion_type", "conclusion", "summary",
                   "point_stats", "component_stats", "warnings", "errors")


def _s(value):
    return str(value or "")


def rows_filled(rows):
    """非空行数（任一单元格有内容即算）。"""
    return sum(1 for row in (rows or [])
               if any(_s(cell).strip() for cell in row))


def _compact_assessment(result):
    if not isinstance(result, dict):
        return None
    compact = {key: result.get(key) for key in ASSESSMENT_KEYS if key in result}
    return compact or None


def build_facts(project_name, report_info, checked_order, sheet_data,
                columns_map, assessment_results=None, equipment=None,
                template_set=None, params_map=None, generated_at=None):
    """构建事实包。

    :param checked_order: 参与报告的 sheet_key 顺序
    :param sheet_data: {sheet_key: [[...]]}
    :param columns_map: {sheet_key: [列头]}
    :param assessment_results: {sheet_key: 评定结果}
    :param equipment: 报告设备行（缺省按检测项目从设备库兜底）
    :param params_map: {sheet_key: 钻芯参数}，仅作事实留档
    :return: dict（schema=report.facts/1）
    """
    ts = template_set or ReportTemplateSet.builtin()
    try:
        from report_generator.utils.report_items import report_order
    except ImportError:  # 以 report_generator/ 为工作目录导入时
        from utils.report_items import report_order
    checked_order = report_order(checked_order)
    info = dict(report_info or {})
    if not _s(info.get("project_name")).strip():
        info["project_name"] = _s(project_name)

    items = []
    warnings = []
    conclusions = []
    table_no = 0
    assessed = 0
    conclusion_counters = {}
    category_numbers = category_number_map(checked_order)
    checked_order = list(checked_order or [])

    for key in checked_order:
        rows = list((sheet_data or {}).get(key) or [])
        cols = list((columns_map or {}).get(key) or [])
        base, comp = resolve_sheet_key(key)
        entry = ts.result_entry(base, comp)
        filled = rows_filled(rows)
        assessment = _compact_assessment(
            (assessment_results or {}).get(key))
        if assessment and assessment.get("ok"):
            assessed += 1

        has_data = filled > 0
        has_template = entry is not None
        rendered = has_data and has_template
        if rendered:
            table_no += 1
            number = "5.%d" % table_no
        else:
            number = ""

        if has_data and assessment and assessment.get("ok") \
                and assessment.get("conclusion"):
            conclusion_text = format_conclusion(assessment, number or None)
        elif has_data:
            conclusion_text = build_conclusion_sentence(base, comp, rows, cols)
        else:
            conclusion_text = ""

        if not has_data:
            warnings.append("%s 没有数据，未进入报告" % key)
        elif not has_template:
            warnings.append("%s 没有对应的报告结果模板，未生成一览表" % key)
        elif not (assessment and assessment.get("ok")):
            warnings.append("%s 尚未评定，结论句按原始数据生成" % key)

        notes = []
        if rendered:
            notes = item_narrative(base, comp, rows, conclusion_text,
                                   number, table_no, checked_order)
        sentence = ""
        if rendered and conclusion_text:
            # 与报告正文同源的编号（1.1、2.1、…），措辞层改写时保留前缀
            sentence = next_conclusion_no(
                base, conclusion_counters,
                category_numbers.get(category_key(key))) + conclusion_text
        if conclusion_text:
            conclusions.append({
                "sheet_key": key,
                "table_no": number,
                "text": conclusion_text,
                "sentence": sentence,
            })

        items.append({
            "sheet_key": key,
            "base_item": base,
            "component": comp,
            "columns": cols,
            "rows": rows,
            "rows_filled": filled,
            "params": dict((params_map or {}).get(key) or {}),
            "has_template": has_template,
            "table_no": number,
            "assessment": assessment,
            "conclusion_text": conclusion_text,
            "narrative": notes,
        })

    equipment_rows = list(equipment) if equipment else equipment_for(
        checked_order)
    facts = {
        "schema": SCHEMA,
        "generated_at": generated_at or datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"),
        "project": {
            "project_name": _s(project_name),
            "report_info": info,
        },
        "items": items,
        "equipment": equipment_rows,
        "standards": standards_for(checked_order),
        "template": {
            "id": getattr(ts, "template_id", ""),
            "name": getattr(ts, "name", ""),
        },
        "stats": {
            "items": len(items),
            "rendered_tables": table_no,
            "assessed": assessed,
            "conclusions": len(conclusions),
            "rows": sum(item["rows_filled"] for item in items),
        },
        # 措辞底稿：渲染时可用 narrative 覆盖这三段
        "narrative": {
            "overview": overview_text(info),
            "basis": standards_for(checked_order),
            # 带编号的结论句：可直接原样回填为 narrative.conclusions
            "conclusions": [c["sentence"] for c in conclusions if c["sentence"]],
        },
        "conclusions": conclusions,
        "warnings": warnings,
    }
    return facts
