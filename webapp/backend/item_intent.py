# -*- coding: utf-8 -*-
"""检测意图识别（规则版）。

LLM 可通过内部工具 set_intent 覆盖本结果；离线/模型不可用时依赖本模块。
"""

import re

COMPONENTS = ["剪力墙", "梁", "柱", "板", "基础", "墙"]

PAGE_BY_CATEGORY = {
    "data_collection": "/project",
    "assessment": "/project",
    "report": "/report",
    "original": "/report",
    "equipment": "/equipment",
    "template": "/templates",
    "knowledge_wiki": "/wiki",
    "knowledge_norm": "/normqa",
    "records": "/records",
    "other": "",
}

ALIASES = [
    ("回弹法检测", ["回弹法", "回弹"]),
    ("钻芯法检测", ["钻芯法", "钻芯", "芯样"]),
    ("回弹钻芯修正法检测", ["回弹钻芯修正", "修正法"]),
    ("剪力墙构件钢筋间距检测", ["剪力墙钢筋间距", "剪力墙间距"]),
    ("现浇板钢筋间距检测", ["板钢筋间距", "现浇板钢筋间距"]),
    ("梁构件底排受力钢筋根数检测", ["梁钢筋根数", "梁底排", "梁根数"]),
    ("柱构件主要受力钢筋根数检测", ["柱钢筋根数", "柱根数"]),
    ("剪力墙钢筋根数检测", ["墙钢筋根数", "剪力墙根数"]),
    ("楼板构件厚度检测", ["楼板厚度", "板厚"]),
    ("剪力墙厚度检测", ["剪力墙厚度", "墙厚"]),
    ("混凝土梁结构尺寸检测", ["梁截面尺寸", "梁尺寸"]),
    ("混凝土柱结构尺寸检测", ["柱截面尺寸", "柱尺寸"]),
    ("混凝土梁保护层厚度检测", ["梁保护层"]),
    ("混凝土柱保护层厚度检测", ["柱保护层"]),
    ("剪力墙保护层厚度检测", ["墙保护层", "剪力墙保护层"]),
    ("混凝土板保护层厚度检测", ["板保护层"]),
    ("化学植筋锚固承载力检测", ["植筋", "锚固承载力", "拉拔"]),
    ("碳化深度", ["碳化深度", "碳化"]),
    ("砖强度检测", ["砖强度"]),
    ("砌筑砂浆强度检测", ["砂浆强度", "砂浆"]),
    ("砌体构件尺寸偏差检测", ["砌体尺寸", "砌体偏差"]),
    ("高强度螺栓扭矩系数检测", ["螺栓扭矩", "高强螺栓"]),
    ("防腐涂层厚度检测", ["防腐涂层"]),
    ("防火涂层厚度检测", ["防火涂层"]),
    ("焊缝超声波探伤检测", ["焊缝", "探伤"]),
    ("钢材强度检测", ["钢材强度"]),
    ("木构件缺陷检测", ["木构件缺陷"]),
    ("木构件挠度检测", ["木构件挠度", "挠度"]),
    ("木构件尺寸偏差检测", ["木构件尺寸"]),
    ("木材含水率检测", ["含水率"]),
]

COLLECT_WORDS = ["录入", "采集", "建表", "勾选", "开始检测", "新增", "填写",
                 "导入", "做一下", "做", "检测"]
REPORT_WORDS = ["生成报告", "出报告", "检测报告", "报告生成", "报告"]
ORIGINAL_WORDS = ["原始记录"]
ASSESS_WORDS = ["评定", "结论", "判定", "合格率", "批推定"]
EQUIPMENT_WORDS = ["设备", "仪器"]
TEMPLATE_WORDS = ["模板"]
NORM_WORDS = ["规范", "条文", "标准", "依据", "图集", "验收规范", "规程"]
WIKI_WORDS = ["知识库", "wiki", "操作步骤", "怎么检测", "如何检测", "检测方法"]
RECORD_WORDS = ["记录库", "历史记录", "归档", "记录管理"]


def _norm(text):
    return re.sub(r"\s+", "", str(text or ""))


def _match_items(text, items=None):
    hits = []
    text_n = _norm(text)
    if items:
        for entry in items:
            name = str((entry or {}).get("item") or "")
            if not name:
                continue
            name_n = _norm(name)
            if name in text or name_n in text_n:
                hits.append(entry)
                continue
            for base, aliases in ALIASES:
                if not (base in name or name in base):
                    continue
                if base in text or any(a in text for a in aliases):
                    hits.append(entry)
                    break
        if hits:
            return hits
    for base, aliases in ALIASES:
        if base in text or any(a in text for a in aliases):
            hits.append({"item": base, "components": [], "sheet_keys": [base]})
    # 去重
    seen, out = set(), []
    for entry in hits:
        name = entry.get("item")
        if name and name not in seen:
            seen.add(name)
            out.append(entry)
    return out


def _match_components(text, item_entries):
    found = []
    for comp in COMPONENTS:
        if comp == "墙" and "剪力墙" in text:
            continue
        if comp in text:
            found.append(comp)
    allowed = []
    for entry in item_entries:
        comps = (entry or {}).get("components") or []
        if comps:
            allowed.extend(comps)
    if allowed:
        if "剪力墙" in allowed and "墙" in found:
            found = ["剪力墙" if c == "墙" else c for c in found]
        found = [c for c in found if c in allowed]
    return list(dict.fromkeys(found))


def _sheet_keys(item_entries, components):
    keys = []
    for entry in item_entries:
        name = entry.get("item") or ""
        comps = entry.get("components") or []
        if not comps:
            keys.append(name)
            continue
        chosen = [c for c in components if c in comps] if components else []
        for comp in chosen:
            keys.append("%s（%s）" % (name, comp))
    return list(dict.fromkeys(keys))


def detect(text, items=None):
    """返回意图字典；items 可传 list_detection_items 的 items。"""
    raw = str(text or "").strip()
    text_n = _norm(raw)
    item_entries = _match_items(raw, items=items)
    components = _match_components(raw, item_entries)
    base_items = [e.get("item") for e in item_entries if e.get("item")]

    category = "other"
    reason = ""
    if any(w in raw for w in RECORD_WORDS):
        category, reason = "records", "记录库/历史"
    elif any(w in raw for w in ORIGINAL_WORDS):
        category, reason = "original", "原始记录"
    elif any(w in raw for w in REPORT_WORDS):
        category, reason = "report", "报告生成"
    elif any(w in raw for w in ASSESS_WORDS):
        category, reason = "assessment", "检测评定"
    elif any(w in raw for w in EQUIPMENT_WORDS):
        category, reason = "equipment", "设备库"
    elif any(w in raw for w in TEMPLATE_WORDS):
        category, reason = "template", "模板库"
    elif any(w in raw for w in NORM_WORDS):
        category, reason = "knowledge_norm", "规范条文"
    elif any(w in raw for w in WIKI_WORDS):
        category, reason = "knowledge_wiki", "知识库/检测方法"
    elif base_items or any(w in raw for w in COLLECT_WORDS):
        category, reason = "data_collection", "检测/数据采集"

    if category == "other" and base_items:
        category, reason = "data_collection", "提到检测项目"

    confidence = 0.2
    if base_items and category in ("data_collection", "assessment",
                                   "report", "original"):
        confidence = 0.9
    elif base_items:
        confidence = 0.8
    elif category != "other":
        confidence = 0.55

    summary = ""
    if base_items:
        summary = "检测项目：%s" % "、".join(base_items)
        if components:
            summary += "；构件：%s" % "、".join(components)
    elif category != "other":
        summary = reason

    next_page = PAGE_BY_CATEGORY.get(category, "")
    sheet_keys = _sheet_keys(item_entries, components)
    return {
        "category": category,
        "items": base_items,
        "components": components,
        "sheet_keys": sheet_keys,
        "next_page": next_page,
        "confidence": confidence,
        "reason": reason,
        "summary": summary or raw[:80],
        "source": "rules",
    }
