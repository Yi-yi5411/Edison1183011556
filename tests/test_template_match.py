# -*- coding: utf-8 -*-
"""报告模板匹配冒烟（P4-2）：打分、排序、切换建议、真实端点。

分三部分：纯函数打分（假模板集合）→ 真实端点无数据 → 真实端点带两个检测项。
后两部分在缺少 fastapi 的解释器上自动 SKIP。

运行：python test_template_match.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

from utils.report_templates import REQUIRED_CHAPTERS  # noqa: E402
from utils.template_match import (explain_switch, rank_templates,  # noqa: E402
                                  score_template)

from _harness import Results

_R = Results()
check = _R.check


skip = _R.skip


class FakeSet(object):
    """只实现打分用到的两个方法，避免依赖真实 docx。"""

    def __init__(self, present_chapters, results, name="", template_id=""):
        self.present = max(0, min(present_chapters, len(REQUIRED_CHAPTERS)))
        self.results = set(results)
        self.name = name or "假模板"
        self.template_id = template_id or "fake"

    def missing_chapters(self):
        return ["缺少章节：x"] * (len(REQUIRED_CHAPTERS) - self.present)

    def result_entry(self, base, component=None):
        if (base, component) in self.results:
            return {"base": base, "component": component}
        if (base, None) in self.results:
            return {"base": base, "component": None}
        return None


ENTRIES = [
    {"base": "回弹法检测", "component": "墙", "key": "回弹法检测（墙）"},
    {"base": "钻芯法检测", "component": "梁", "key": "钻芯法检测（梁）"},
]


def test_score():
    full = FakeSet(len(REQUIRED_CHAPTERS),
                   {("回弹法检测", "墙"), ("钻芯法检测", "梁")}, name="全量")
    row = score_template(full, ENTRIES, template_id="t-full")
    check("全覆盖模板得 1.0", row["score"] == 1.0, row["score"])
    check("依据说明覆盖检测项",
          any("结果表覆盖 2/2" in r for r in row["reasons"]), row["reasons"])
    check("章节齐全写进依据",
          any("章节齐全" in r for r in row["reasons"]), row["reasons"])

    partial = FakeSet(5, {("回弹法检测", "墙")}, name="部分")
    row = score_template(partial, ENTRIES, template_id="t-part")
    expect = round(0.6 * 0.5 + 0.4 * (5.0 / len(REQUIRED_CHAPTERS)), 4)
    check("部分覆盖按权重打分", row["score"] == expect,
          [row["score"], expect])
    check("缺结果表被标出",
          row["missing_items"] == ["钻芯法检测（梁）"], row["missing_items"])
    check("缺章节被标出", len(row["missing_chapters"]) == 3,
          len(row["missing_chapters"]))

    empty = score_template(full, [], template_id="t-empty")
    check("无检测项时按章节打分",
          empty["result_coverage"] == 1.0 and empty["score"] == 1.0,
          [empty["result_coverage"], empty["score"]])
    check("无检测项时给出解释",
          any("还没有已录入" in r for r in empty["reasons"]), empty["reasons"])


def test_rank_and_switch():
    full = FakeSet(len(REQUIRED_CHAPTERS),
                   {("回弹法检测", "墙"), ("钻芯法检测", "梁")},
                   name="全量", template_id="full")
    partial = FakeSet(5, {("回弹法检测", "墙")}, name="部分",
                      template_id="partial")
    candidates = [
        {"id": "full", "name": "全量", "template_set": full, "builtin": False},
        {"id": "partial", "name": "部分", "template_set": partial,
         "builtin": True},
    ]
    scored = rank_templates(candidates, ENTRIES, selected_id="partial",
                            default_id="full")
    check("排序把高分的放前面", [r["id"] for r in scored] == ["full", "partial"],
          [r["id"] for r in scored])
    check("标记当前选择与默认",
          scored[0]["is_default"] and scored[1]["is_selected"],
          [(r["id"], r["is_selected"], r["is_default"]) for r in scored])

    switch, reason = explain_switch(scored, "partial")
    check("选中低分模板时建议切换", switch is True, reason)
    check("切换理由含目标模板名", "全量" in reason, reason)
    check("理由指出当前模板缺结果表", "钻芯法检测（梁）" in reason, reason)

    switch, reason = explain_switch(scored, "full")
    check("选中最佳模板时不建议切换", switch is False, reason)

    tie = [dict(scored[0]), dict(scored[1])]
    tie[0]["score"] = 0.9
    tie[1]["score"] = 0.88
    switch, reason = explain_switch(tie, "partial")
    check("差距很小时不建议切换", switch is False and "差距很小" in reason, reason)

    switch, reason = explain_switch(scored, "not-in-library")
    check("生效模板不在库时不做建议", switch is False, reason)
    check("空列表不报错", explain_switch([], "x")[0] is False, None)


def test_endpoint():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("模板匹配端点", "当前解释器没有 fastapi")
        return
    from routers.report import match_report_template

    data = match_report_template()
    body = data.get("data") or {}
    check("端点返回成功", data.get("ok") is True, list(body)[:6])
    check("返回生效模板与来源",
          isinstance(body.get("effective"), dict)
          and body["effective"].get("source") in ("project", "default",
                                                  "builtin"),
          body.get("effective"))
    check("返回打分后的模板列表",
          isinstance(body.get("templates"), list) and bool(body["templates"])
          and all("score" in row and "reasons" in row
                  for row in body["templates"]),
          len(body.get("templates") or []))
    check("兼容旧字段 recommended",
          body.get("recommended") == (body.get("effective") or {}).get("id"),
          body.get("recommended"))
    check("返回切换建议字段",
          isinstance(body.get("recommend_switch"), bool)
          and bool(body.get("switch_reason")), body.get("switch_reason"))

    from deps import get_state
    state = get_state()
    keys = ["回弹法检测(主要来源为仪器数据，可选用)（墙）", "钻芯法检测（梁）"]
    saved = {key: state.sheet_data.get(key) for key in keys}
    saved_checked = list(state.checked_items or [])
    try:
        for key in keys:
            state.sheet_data[key] = [["测试"]]
            if key not in state.checked_items:
                state.checked_items.append(key)
        data = match_report_template()
        body = data.get("data") or {}
        checked = body.get("checked_items") or []
        check("按已录入检测项计算覆盖",
              set(keys) <= set(checked)
              and body.get("result_entries") == len(checked),
              [body.get("result_entries"), checked])
        builtin = next((row for row in body["templates"]
                        if row["id"] == "builtin_standard"), None)
        check("内置模板覆盖这两个检测项",
              builtin is not None
              and set(keys) <= set(builtin["covered_items"]),
              builtin and builtin["covered_items"])
        check("最佳匹配给出依据",
              bool((body.get("best_fit") or {}).get("reasons")),
              body.get("best_fit"))
    finally:
        for key in keys:
            if saved.get(key) is None:
                state.sheet_data.pop(key, None)
            else:
                state.sheet_data[key] = saved[key]
        state.checked_items = saved_checked


def test_tool_schema():
    sys.path.insert(0, os.path.join(ROOT, "webapp"))
    import mcp_server  # noqa: E402
    tool = mcp_server._TOOL_MAP.get("match_report_template")
    check("match_template 工具存在且只读",
          tool is not None and not tool.get("write"),
          tool and tool.get("write"))
    check("工具描述含切换建议",
          "recommend_switch" in (tool or {}).get("description", ""),
          (tool or {}).get("description", "")[:40])


def main():
    test_score()
    test_rank_and_switch()
    test_endpoint()
    test_tool_schema()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
