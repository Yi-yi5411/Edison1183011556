# -*- coding: utf-8 -*-
"""按事实包渲染《检测报告》.docx（不调用任何模型）。

用法（典型 DSH 流程）：
    facts = build_facts(...)                       # 只读事实
    narrative = {"overview": "...", "conclusions": ["1.1、..."]}
    result = render_from_facts(facts, narrative, output_path="...")

只允许覆盖三段措辞：overview（工程概况）、basis（检测依据清单）、
conclusions（结论句，需保留编号前缀）。其余内容（表格、设备、目录、
封面、首页）一律由事实包确定性渲染。
"""
try:
    from report_generator.utils.report_facts import build_facts
    from report_generator.utils.word_report import generate_report
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_facts import build_facts
    from utils.word_report import generate_report

NARRATIVE_KEYS = ("overview", "basis", "conclusions")


def clean_narrative(narrative):
    """只保留允许覆盖的字段，并做类型归一。"""
    if not isinstance(narrative, dict):
        return {}
    cleaned = {}
    overview = str(narrative.get("overview") or "").strip()
    if overview:
        cleaned["overview"] = overview
    basis = narrative.get("basis")
    if isinstance(basis, list) and basis:
        cleaned["basis"] = [str(item) for item in basis if str(item).strip()]
    conclusions = narrative.get("conclusions")
    if isinstance(conclusions, list) and conclusions:
        cleaned["conclusions"] = [str(item) for item in conclusions
                                  if str(item).strip()]
    return cleaned


def _rehydrate(facts):
    """事实包 → generate_report 的入参。"""
    facts = facts if isinstance(facts, dict) else {}
    items = facts.get("items") or []
    project = facts.get("project") or {}
    info = dict(project.get("report_info") or {})
    project_name = str(project.get("project_name") or info.get("project_name")
                       or "")
    checked_order = [item.get("sheet_key") for item in items
                     if item.get("sheet_key")]
    sheet_data = {item["sheet_key"]: list(item.get("rows") or [])
                  for item in items if item.get("sheet_key")}
    columns_map = {item["sheet_key"]: list(item.get("columns") or [])
                   for item in items if item.get("sheet_key")}
    assessment_results = {}
    for item in items:
        key = item.get("sheet_key")
        if key and item.get("assessment"):
            assessment_results[key] = item["assessment"]
    return (project_name, info, sheet_data, columns_map, checked_order,
            assessment_results)


def render_from_facts(facts, narrative=None, output_path=None,
                      template_set=None, format_options=None, on_log=None):
    """渲染报告，返回 generate_report 的结果（含 filepath 之外的统计）。"""
    (project_name, info, sheet_data, columns_map, checked_order,
     assessment_results) = _rehydrate(facts)
    if not checked_order:
        raise ValueError("事实包里没有检测项目，无法生成报告")
    cleaned = clean_narrative(narrative)
    if cleaned.get("overview"):
        info["project_overview"] = cleaned["overview"]
    result = generate_report(
        project_name, info, sheet_data, columns_map,
        checked_order=checked_order, output_path=output_path,
        on_log=on_log, format_options=format_options,
        template_set=template_set, assessment_results=assessment_results,
        equipment=(facts.get("equipment") or None),
        narrative=cleaned or None)
    result["applied_narrative"] = sorted(cleaned.keys())
    return result
