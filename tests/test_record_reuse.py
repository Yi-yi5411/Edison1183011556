# -*- coding: utf-8 -*-
"""记录库检索与历史快照复用冒烟（P4-4）。

覆盖：
1. 关键词打分与排序（纯函数）
2. 快照解析/列比对/行重排（纯函数）
3. 数据往返：行 → 评定 → 快照 → 还原 → 再评定，结论类型一致
4. 真实记录库：有快照的记录能列出表、复用进当前工程（用后还原工程状态）
5. 三个端点与 MCP 工具

运行：python test_record_reuse.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

from framework.models import ITEM_COLUMNS  # noqa: E402
from utils.assessment_engine import assess  # noqa: E402
from utils.record_search import (align_rows, compare_columns,  # noqa: E402
                                 extract_sheet, rank_records,
                                 sheet_summary, snapshot_sheets, tokenize)

from _harness import Results

_R = Results()
check = _R.check


skip = _R.skip


# ── 1. 打分与排序 ─────────────────────────────────────────
def test_scoring():
    records = [
        {"id": "a", "project_name": "武汉市轨道交通11号线", "sheet_key": "钻芯法检测（梁）",
         "template_name": "标准模板", "generated_at": "2026-11-01 10:00:00"},
        {"id": "b", "project_name": "新建租赁住房项目", "sheet_key": "回弹法检测（梁）",
         "template_name": "标准模板", "generated_at": "2026-11-05 10:00:00"},
        {"id": "c", "project_name": "武汉市轨道交通11号线", "sheet_key": "回弹法检测（梁）",
         "template_name": "标准模板", "generated_at": "2026-11-09 10:00:00"},
    ]
    ranked = rank_records(records, "回弹法 武汉")
    check("相关度排序把双命中放第一", [r["id"] for r in ranked][:1] == ["c"],
          [(r["id"], r["score"]) for r in ranked])
    check("命中字段可解释", "project_name" in ranked[0]["matched_fields"]
          and "sheet_key" in ranked[0]["matched_fields"],
          ranked[0]["matched_fields"])
    no_hit = rank_records(records, "完全不相干的词")
    check("无命中返回空", no_hit == [], no_hit)
    by_time = rank_records(records, "")
    check("无查询按时间倒序", [r["id"] for r in by_time] == ["c", "b", "a"],
          [r["id"] for r in by_time])
    check("分词包含整句与短片段", "回弹法" in tokenize("回弹法检测"))
    check("空查询分词为空", tokenize("") == [], tokenize(""))


# ── 2. 快照解析与列对齐 ───────────────────────────────────
def test_snapshot_helpers():
    single = {
        "sheet_key": "钻芯法检测（梁）",
        "columns": ["楼栋", "批次", "构件编号", "测试强度(MPa)"],
        "rows": [["1#", "1", "KL-1", "29.8"], ["1#", "1", "KL-2", "30.1"]],
        "params": {"building": "1#"},
        "assessment_result": {"conclusion_type": "类型一",
                              "conclusion": "均满足设计要求"},
    }
    sheets = snapshot_sheets(single)
    check("单表快照解析", len(sheets) == 1
          and sheets[0]["rows_filled"] == 2
          and sheets[0]["params"] == {"building": "1#"}, sheets[0]["sheet_key"])
    summary = sheet_summary(single)
    check("摘要带当时结论", summary[0]["conclusion_type"] == "类型一",
          summary[0]["conclusion_type"])

    multi = {"sheets": {"A": {"columns": ["x"], "rows": [["1"]]},
                        "B": {"columns": ["y"], "rows": []}}}
    multi_sheets = snapshot_sheets(multi)
    check("工程级快照解析", {s["sheet_key"] for s in multi_sheets} == {"A", "B"},
          [s["sheet_key"] for s in multi_sheets])
    check("取指定表", extract_sheet(multi)["sheet_key"] == "A")
    try:
        extract_sheet(multi, "C")
        check("取不存在的表报错", False, "未抛错")
    except ValueError as e:
        check("取不存在的表报错", "没有工作表" in str(e), str(e)[:60])

    current = ["楼栋", "构件编号", "批次", "测试强度(MPa)", "楼层"]
    comparison = compare_columns(single["columns"], current)
    check("列比对：兼容但需重排",
          comparison["compatible"] and comparison["needs_reorder"]
          and comparison["extra_columns"] == ["楼层"],
          comparison)
    rows = align_rows(single["rows"], single["columns"], current)
    check("行按当前列重排并补空",
          rows == [["1#", "KL-1", "1", "29.8", ""],
                   ["1#", "KL-2", "1", "30.1", ""]], rows)

    incompatible = compare_columns(["已经不存在的列", "楼栋"], ["楼栋"])
    check("缺列判定不兼容",
          not incompatible["compatible"]
          and incompatible["missing_columns"] == ["已经不存在的列"],
          incompatible["missing_columns"])


# ── 3. 数据往返：行 → 评定 → 快照 → 还原 → 再评定 ─────────
def test_roundtrip_fixture():
    key = "剪力墙厚度检测"
    columns = list(ITEM_COLUMNS[key])
    rows = [["1#", "2层墙Q1", "1/A", 200, 201, 202, 199,
             "", "", "", "", "", "", "", "1F"]]
    first = assess(key, key, None, columns, rows)
    check("首次评定成功", first.get("ok") and first.get("conclusion_type"),
          first.get("conclusion_type"))

    snapshot = {
        "sheet_key": key,
        "columns": columns,
        "rows": rows,
        "params": {},
        "assessment_result": first,
    }
    sheet = extract_sheet(snapshot)
    restored_columns = list(ITEM_COLUMNS[key])
    comparison = compare_columns(sheet["columns"], restored_columns)
    check("同版本列定义兼容", comparison["compatible"]
          and comparison["same_order"], comparison["missing_columns"])
    restored_rows = align_rows(sheet["rows"], sheet["columns"],
                               restored_columns) \
        if comparison["needs_reorder"] else sheet["rows"]
    second = assess(key, key, None, restored_columns, restored_rows)
    check("还原后再评定结论一致",
          second.get("conclusion_type") == first.get("conclusion_type"),
          [first.get("conclusion_type"), second.get("conclusion_type")])
    check("还原后结论表述一致",
          second.get("conclusion") == first.get("conclusion"),
          second.get("conclusion"))


# ── 4. 真实记录库 ─────────────────────────────────────────
def _with_snapshots():
    from deps import get_record_store
    rows, _total = get_record_store().list_original_records(limit=100)
    return get_record_store(), [r for r in rows if r.get("has_snapshot")]


def test_real_records():
    store, snaps = _with_snapshots()
    check("记录库存在带快照的原始记录", bool(snaps), len(snaps))
    if not snaps:
        return
    record = snaps[0]
    sheets = sheet_summary(store.get_original_record(record["id"],
                                                     with_snapshot=True)["snapshot"])
    check("快照里有表与行", sheets and sheets[0]["rows"] > 0
          and len(sheets[0]["columns"]) > 0,
          [(s["sheet_key"], s["rows"]) for s in sheets])

    from deps import get_state
    from record_reuse import list_record_sheets, reuse_record

    listed = list_record_sheets(record["id"])
    check("接口列出快照表", listed["sheet_count"] >= 1,
          listed["sheet_count"])
    compatibility = listed["sheets"][0]["compatibility"]
    check("列出兼容性与当前列", isinstance(compatibility, dict)
          and "compatible" in compatibility, compatibility)

    key = listed["sheets"][0]["sheet_key"]
    state = get_state()
    saved = {
        "rows": state.sheet_data.get(key),
        "params": state.cd_params.get(key),
        "input": state.assessment_inputs.get(key),
        "merges": state.merges.get(key),
        "merge_formats": state.merge_formats.get(key),
        "cell_formats": state.cell_formats.get(key),
        "checked": list(state.checked_items or []),
    }
    try:
        result = reuse_record(record["id"], append=False)
        check("复用写回当前工程", result["rows"] > 0
              and result["sheet_key"] == key, result["rows"])
        check("复用结果带告警与参数标记",
              isinstance(result["warnings"], list)
              and isinstance(result["params_restored"], bool),
              [len(result["warnings"]), result["params_restored"]])
        check("工程状态里确实有数据",
              any(str(v).strip() for row in state.sheet_data.get(key) or []
                  for v in row), key)
        again = reuse_record(record["id"], append=True)
        check("追加复用行数翻倍",
              again["rows"] == result["rows"] * 2, again["rows"])
    finally:
        if saved["rows"] is None:
            state.sheet_data.pop(key, None)
        else:
            state.sheet_data[key] = saved["rows"]
        if saved["params"] is None:
            state.cd_params.pop(key, None)
        else:
            state.cd_params[key] = saved["params"]
        if saved["input"] is None:
            state.assessment_inputs.pop(key, None)
        else:
            state.assessment_inputs[key] = saved["input"]
        for field in ("merges", "merge_formats", "cell_formats"):
            bucket = getattr(state, field)
            if saved[field] is None:
                bucket.pop(key, None)
            else:
                bucket[key] = saved[field]
        state.checked_items = saved["checked"]

    legacy = next((r for r in store.list_original_records(limit=100)[0]
                   if not r.get("has_snapshot")), None)
    if legacy:
        try:
            list_record_sheets(legacy["id"])
            check("无快照记录报错", False, "未抛错")
        except Exception as e:  # noqa: BLE001
            check("无快照记录报错", "快照" in str(e), str(e)[:60])


# ── 5. 端点与工具 ─────────────────────────────────────────
def test_endpoints():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("记录库端点", "当前解释器没有 fastapi")
        return
    from routers.records import (ReuseBody, original_record_sheets,
                                 reuse_original_record, similar_records)

    data = similar_records(q="回弹法", kind="original", limit=5)
    body = data.get("data") or {}
    check("相似检索返回结果", data.get("ok") is True
          and isinstance(body.get("items"), list), len(body.get("items") or []))
    if body.get("items"):
        item = body["items"][0]
        check("检索结果带相关度与命中字段",
              "score" in item and "matched_fields" in item,
              [item.get("score"), item.get("matched_fields")])

    data = similar_records(q="", kind="both", limit=3)
    items = (data.get("data") or {}).get("items") or []
    check("不限类型时混合返回", len(items) <= 3, len(items))

    _store, snaps = _with_snapshots()
    if not snaps:
        skip("快照端点", "没有带快照的记录")
        return
    record_id = snaps[0]["id"]
    data = original_record_sheets(record_id)
    check("列出快照表端点", data.get("ok") is True
          and (data.get("data") or {}).get("sheet_count") >= 1,
          (data.get("data") or {}).get("sheet_count"))

    from deps import get_state
    listed = original_record_sheets(record_id)["data"]
    key = listed["sheets"][0]["sheet_key"]
    state = get_state()
    saved = {
        "rows": state.sheet_data.get(key),
        "merges": state.merges.get(key),
        "merge_formats": state.merge_formats.get(key),
        "cell_formats": state.cell_formats.get(key),
        "params": state.cd_params.get(key),
        "input": state.assessment_inputs.get(key),
        "checked": list(state.checked_items or []),
    }
    try:
        data = reuse_original_record(record_id, ReuseBody(sheet_key=key))
        check("复用端点返回成功", data.get("ok") is True
              and (data.get("data") or {}).get("rows", 0) > 0,
              (data.get("data") or {}).get("rows"))
    finally:
        for field, bucket_name in (("rows", "sheet_data"),
                                   ("merges", "merges"),
                                   ("merge_formats", "merge_formats"),
                                   ("cell_formats", "cell_formats"),
                                   ("params", "cd_params"),
                                   ("input", "assessment_inputs")):
            bucket = getattr(state, bucket_name)
            if saved[field] is None:
                bucket.pop(key, None)
            else:
                bucket[key] = saved[field]
        state.checked_items = saved["checked"]


def test_tool_schema():
    sys.path.insert(0, os.path.join(ROOT, "webapp"))
    import mcp_server  # noqa: E402
    for name, is_write in (("find_similar_records", False),
                           ("list_record_sheets", False),
                           ("reuse_original_record", True)):
        tool = mcp_server._TOOL_MAP.get(name)
        check("工具存在且写标记正确：%s" % name,
              tool is not None and bool(tool.get("write")) == is_write,
              tool and tool.get("write"))



def main():
    test_scoring()
    test_snapshot_helpers()
    test_roundtrip_fixture()
    test_real_records()
    test_endpoints()
    test_tool_schema()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
