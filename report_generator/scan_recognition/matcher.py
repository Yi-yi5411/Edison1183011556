# -*- coding: utf-8 -*-
"""第6步：将结构化数据匹配到 report_generator 的对应检测项目列。

采用数据驱动：从插件系统的 ``COLUMNS`` / ``COLUMN_TYPES`` 读取每个
子检测项的列头，把识别记录({字段名:值})按“归一化表头模糊匹配”映射到
目标列的索引，输出可直接回填表格的“对齐行”。不写死任何具体检测项，
从而天然覆盖全部已注册模块。
"""
import re
from pathlib import Path

from report_generator.scan_recognition.config import Config


def _norm(text):
    text = str(text or "")
    text = re.sub(r"[（(].*?[)）]", "", text)   # 去括号内容(通常是单位)
    return re.sub(r"\s+", "", text).lower()


def build_schema_index(columns):
    """返回 {归一化列名: 列索引}，同时把"列名/简称/去掉单位"归一化。"""
    idx = {}
    for i, col in enumerate(columns):
        key = _norm(col)
        idx[key] = i
        idx.setdefault(key.replace("mm", "").replace("mpa", "").replace("kn", ""), i)
    return idx


def map_record_to_row(record, columns, computed_columns, fuzzy=True):
    """把识别记录映射为对齐行(list)。返回 (row_list, matched_fields)。

    计算列(computed_columns)即使被识别到也置空，交由检测模块自动计算。
    """
    idx = build_schema_index(columns)
    row = ["" for _ in columns]
    matched = {}
    comp_norm = set(_norm(c) for c in (computed_columns or []))

    for field, value in (record or {}).items():
        fkey = _norm(field)
        col = idx.get(fkey)
        if col is None and fuzzy:
            # 尝试子串匹配（如 识别"芯样直径" -> 表头"芯样直径(mm)"）
            for k, i in idx.items():
                if fkey and (fkey in k or k in fkey) and len(fkey) >= 2:
                    col = i
                    break
        if col is None:
            continue
        if _norm(columns[col]) in comp_norm:
            row[col] = ""          # 计算列不直接回填
            continue
        clean = NormalizerLike(value)
        row[col] = clean
        matched[col] = field

    return row, matched


def NormalizerLike(value):
    """轻量清洗：直接返回去空白字符串（保留数值原貌）。"""
    value = str(value if value is not None else "").strip()
    return value


def available_sub_items():
    """返回框架中所有已注册检测子项与其列头。失败时返回空。"""
    try:
        import os
        import sys
        _report_gen = Path(__file__).resolve().parent.parent
        if str(_report_gen) not in sys.path:
            sys.path.insert(0, str(_report_gen))
        from framework.models import ITEM_COLUMNS
        return dict(ITEM_COLUMNS)
    except Exception:
        return {}


def match_rows(records, columns, cfg: Config = None):
    """把多条识别记录转换为对齐行列表。返回 (rows, per_row_matched)."""
    cfg = cfg or Config.load()
    computed = cfg.matcher.get("computed_columns", []) or []
    fuzzy = cfg.matcher.get("fuzzy_match", True)
    rows, matched_rows = [], []
    for rec in records:
        row, matched = map_record_to_row(rec, columns, computed, fuzzy)
        rows.append(row)
        matched_rows.append(matched)
    return rows, matched_rows