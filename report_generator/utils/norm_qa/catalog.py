# -*- coding: utf-8 -*-
"""规范库的「检测项目 → 规范」映射、查询词扩展与覆盖度统计。

设计要点：
- 映射不另写一份：直接解析 report_narrative.standards_for（报告第二章依据），
  保证「报告里引用的规范」与「检索时优先的规范」永远是同一套；
- 词扩展只做同义收敛（口语 → 规范用词），不做联想，避免检索漂移；
- 覆盖度按 manifest 的检测项目清单算，能直接看出哪些项目还没有规范可依。
"""
import re
import sqlite3
from pathlib import Path

from .parser import normalize_code
from .store import get_db_path

try:  # utils 包内与扁平导入两种环境
    from ..report_narrative import standards_for
except ImportError:  # pragma: no cover
    from utils.report_narrative import standards_for

RE_CODE_TOKEN = re.compile(
    r"([A-Z]{1,4}(?:\s*/\s*[A-Z]{1,2})?\s*\d{2,5}(?:-\d{4})?)")

# 口语词 → 规范用词（只收本领域同义词，宁缺毋滥）
TERM_EXPANSIONS = {
    "回弹": ["回弹法", "测区", "碳化深度"],
    "钻芯": ["钻芯法", "芯样", "高径比"],
    "芯样": ["钻芯法", "高径比"],
    "保护层": ["保护层厚度", "受力钢筋"],
    "钢筋": ["受力钢筋", "钢筋间距", "保护层厚度"],
    "间距": ["钢筋间距"],
    "根数": ["受力钢筋根数"],
    "厚度": ["结构厚度", "截面尺寸"],
    "尺寸": ["截面尺寸", "允许偏差"],
    "偏差": ["允许偏差", "实测偏差"],
    "砖": ["砖强度", "回弹法"],
    "砂浆": ["砂浆强度", "贯入法"],
    "砌体": ["尺寸偏差"],
    "锚固": ["锚固承载力", "植筋"],
    "植筋": ["锚固承载力"],
    "螺栓": ["扭矩系数", "高强度螺栓"],
    "焊缝": ["超声波探伤"],
    "钢材": ["硬度法"],
    "木材": ["含水率", "挠度", "缺陷"],
    "含水率": ["木材含水率"],
    "碳化": ["碳化深度"],
    "推定值": ["强度推定值"],
    "换算": ["强度换算"],
    "批量": ["批评定", "批检验"],
}

MAX_EXPANDED = 16


def _code_key(code):
    """规范化后的比较键：去空格、大写。"""
    return re.sub(r"\s+", "", normalize_code(code).upper())


def _same_code(left, right):
    """两个代号是否指同一本规范（容忍有无年份、有无空格）。"""
    a, b = _code_key(left), _code_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.split("-")[0] == b.split("-")[0]


def standards_for_items(items):
    """检测项目名（可带构件后缀）→ 报告依据里的规范名列表。"""
    items = [str(i) for i in (items or []) if str(i).strip()]
    if not items:
        return []
    try:
        return list(standards_for(items))
    except Exception:  # noqa: BLE001
        return []


def codes_for_items(items):
    """检测项目 → 规范代号列表（去重、保序）。"""
    codes = []
    for text in standards_for_items(items):
        for token in RE_CODE_TOKEN.findall(str(text)):
            code = normalize_code(token)
            if code and code not in codes:
                codes.append(code)
    return codes


def expand_keywords(keywords):
    """在原始关键词上补同义规范词，返回去重后的扩展列表。"""
    expanded = list(keywords or [])
    for keyword in keywords or []:
        key = str(keyword or "")
        if not key:
            continue
        for trigger, synonyms in TERM_EXPANSIONS.items():
            if trigger in key or key in trigger:
                for synonym in synonyms:
                    if synonym not in expanded:
                        expanded.append(synonym)
            if len(expanded) >= MAX_EXPANDED:
                return expanded[:MAX_EXPANDED]
    return expanded[:MAX_EXPANDED]


def _db_codes(db_path):
    path = Path(db_path) if db_path else get_db_path()
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT code, code_name, COUNT(*) FROM clauses"
                    " GROUP BY code, code_name ORDER BY code")
        return [{"code": row[0], "code_name": row[1], "clauses": row[2]}
                for row in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def match_db_codes(wanted, db_path=None):
    """把目标代号映射到库里真实存在的代号（用于检索过滤）。"""
    present = [row["code"] for row in _db_codes(db_path)]
    matched = []
    for code in present:
        if any(_same_code(code, target) for target in wanted or []):
            matched.append(code)
    return matched


def _all_items():
    try:
        from structural_items import iter_items
        return [item.get("key") for _, item in iter_items() if item.get("key")]
    except Exception:  # noqa: BLE001
        return []


def coverage(db_path=None, items=None):
    """规范库覆盖度：每本规范多少条、每个检测项目有几条可依。"""
    db_codes = _db_codes(db_path)
    item_names = list(items) if items else _all_items()
    total = sum(row["clauses"] for row in db_codes)
    per_item = []
    for item in item_names:
        wanted = codes_for_items([item])
        covered = []
        clause_count = 0
        for row in db_codes:
            if any(_same_code(row["code"], code) for code in wanted):
                covered.append(row["code"])
                clause_count += row["clauses"]
        per_item.append({
            "item": item,
            "codes": wanted,
            "covered_codes": covered,
            "clause_count": clause_count,
            "covered": bool(covered),
        })
    return {
        "db_path": str(Path(db_path) if db_path else get_db_path()),
        "total_clauses": total,
        "codes": db_codes,
        "code_count": len(db_codes),
        "items": per_item,
        "covered_items": sum(1 for row in per_item if row["covered"]),
        "uncovered_items": [row["item"] for row in per_item if not row["covered"]],
    }
