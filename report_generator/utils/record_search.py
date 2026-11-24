# -*- coding: utf-8 -*-
"""记录库检索与历史快照复用（纯数据，不依赖 FastAPI）。

查询口径：
- 多字段加权命中（项目名 > 检测项/工作表键 > 模板/报告编号 > 文件路径/结论）；
- 中文不分词：整句 + 2~4 字片段；短词（2 字）权重降一档，避免误命中。

快照口径（utils/record_store 的 snapshot_json）：
- 单表快照：{sheet_key, columns, rows, params, assessment_input,
  assessment_result, report_info, base_item, project_name}
- 工程快照：{sheets: {...}}（历史遗留形态，做兼容）
"""
import re

FIELD_WEIGHTS = {
    "project_name": 5,
    "report_no": 4,
    "sheet_key": 4,
    "base_item": 4,
    "template_name": 2,
    "filepath": 1,
    "conclusion": 3,
}

MAX_TOKENS = 24


def _clean(text):
    return "".join(ch for ch in str(text or "")
                   if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def tokenize(query):
    """查询分词：整句 + 去噪片段 + 2~4 字滑窗，去重保序。"""
    text = _clean(query)
    if not text:
        return []
    tokens = [text[:24]] if len(text) >= 2 else []
    for size in (4, 3, 2):
        if len(tokens) >= MAX_TOKENS:
            break
        for start in range(0, len(text) - size + 1):
            gram = text[start:start + size]
            if gram not in tokens:
                tokens.append(gram)
            if len(tokens) >= MAX_TOKENS:
                break
    return tokens


def _weight(token):
    """2 字片段降权，避免「检测」「混凝土」这类通用词拉高噪声。"""
    return 0.5 if len(token) <= 2 else 1.0


def score_record(record, query, tokens=None):
    """给一条记录打分，返回 {score, matched_fields}。"""
    tokens = tokens if tokens is not None else tokenize(query)
    if not tokens:
        return {"score": 0.0, "matched_fields": []}
    total = 0.0
    matched = []
    for field, weight in FIELD_WEIGHTS.items():
        value = _clean(record.get(field) or "")
        if not value:
            continue
        hits = 0.0
        for token in tokens:
            if not token:
                continue
            # 字段值短（如项目名「工程A」）时允许反向包含，但太短的不算
            if token in value or (len(value) >= 3 and value in token):
                hits += _weight(token)
        if hits > 0:
            total += weight * min(hits, 3.0)
            matched.append(field)
    return {"score": round(total, 2), "matched_fields": matched}


def rank_records(records, query, limit=10):
    """按相关度排序；无查询时按生成时间倒序。"""
    tokens = tokenize(query)
    scored = []
    for record in records or []:
        row = dict(record)
        result = score_record(row, query, tokens)
        row["score"] = result["score"]
        row["matched_fields"] = result["matched_fields"]
        scored.append(row)
    if tokens:
        scored = [row for row in scored if row["score"] > 0]
        # 稳定排序两遍：先时间倒序，再相关度降序 → 同分时新的在前
        scored.sort(key=lambda r: str(r.get("generated_at") or ""), reverse=True)
        scored.sort(key=lambda r: -r["score"])
    else:
        scored.sort(key=lambda r: str(r.get("generated_at") or ""), reverse=True)
    try:
        limit = max(1, min(int(limit or 10), 100))
    except (TypeError, ValueError):
        limit = 10
    return scored[:limit]


def snapshot_sheets(snapshot):
    """把快照摊平成 [{sheet_key, columns, rows, rows_filled, ...}]。"""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    sheets = snapshot.get("sheets")
    if isinstance(sheets, dict) and sheets:
        out = []
        for key, value in sheets.items():
            value = value if isinstance(value, dict) else {}
            rows = value.get("rows") or []
            out.append({
                "sheet_key": str(key),
                "columns": list(value.get("columns") or []),
                "rows": rows,
                "rows_filled": sum(1 for row in rows
                                   if any(str(v).strip() for v in row)),
                "params": value.get("params") or {},
                "assessment_result": value.get("assessment_result"),
            })
        return out
    key = str(snapshot.get("sheet_key") or "")
    rows = snapshot.get("rows") or []
    if not key and not rows:
        return []
    return [{
        "sheet_key": key,
        "columns": list(snapshot.get("columns") or []),
        "rows": rows,
        "rows_filled": sum(1 for row in rows
                           if any(str(v).strip() for v in row)),
        "params": snapshot.get("params") or {},
        "assessment_input": snapshot.get("assessment_input"),
        "assessment_result": snapshot.get("assessment_result"),
        "base_item": snapshot.get("base_item") or "",
        "report_info": snapshot.get("report_info") or {},
    }]


def extract_sheet(snapshot, sheet_key=None):
    """取快照里的某张表；sheet_key 为空时取第一张。"""
    sheets = snapshot_sheets(snapshot)
    if not sheets:
        raise ValueError("快照里没有可复用的数据表")
    wanted = str(sheet_key or "").strip()
    if wanted:
        for sheet in sheets:
            if sheet["sheet_key"] == wanted:
                return sheet
        # 允许传基础检测项名（历史快照的 sheet_key 可能带构件后缀）
        for sheet in sheets:
            if sheet["sheet_key"].startswith(wanted) or wanted.startswith(
                    sheet["sheet_key"]):
                return sheet
        raise ValueError("快照里没有工作表：%s" % wanted)
    return sheets[0]


def _norm_columns(columns):
    return [str(c).strip() for c in (columns or [])]


def compare_columns(snapshot_columns, current_columns):
    """历史列 vs 当前列：能否直接复用、缺哪些列、行要不要重排。"""
    old = _norm_columns(snapshot_columns)
    new = _norm_columns(current_columns)
    missing = [c for c in old if c and c not in new]
    extra = [c for c in new if c and c not in old]
    same_order = old == new
    return {
        "old_columns": old,
        "current_columns": new,
        "missing_columns": missing,
        "extra_columns": extra,
        "same_order": same_order,
        "compatible": not missing,
        "needs_reorder": bool(old) and bool(new) and not same_order
                          and not missing,
    }


def align_rows(rows, snapshot_columns, current_columns):
    """缺失列补空；同名列按当前列顺序重排。"""
    old = _norm_columns(snapshot_columns)
    new = _norm_columns(current_columns)
    index = {name: idx for idx, name in enumerate(old) if name}
    aligned = []
    for row in rows or []:
        row = list(row)
        aligned.append([
            row[index[name]] if name in index and index[name] < len(row) else ""
            for name in new
        ])
    return aligned


def sheet_summary(snapshot):
    """给「列快照里有哪些表」接口用的摘要。"""
    out = []
    for sheet in snapshot_sheets(snapshot):
        result = sheet.get("assessment_result") or {}
        out.append({
            "sheet_key": sheet["sheet_key"],
            "columns": sheet["columns"],
            "rows": sheet["rows_filled"],
            "params": sheet.get("params") or {},
            "conclusion_type": result.get("conclusion_type") or "",
            "conclusion": result.get("conclusion") or "",
        })
    return out
