# -*- coding: utf-8 -*-
"""P5 报告事实/措辞分离冒烟。

覆盖：
1. 事实包：结构、确定性、数值与评定结论同源、缺少数据/评定的告警
2. 渲染：措辞覆盖（概况/依据/结论句）写进 docx，且无残留占位符
3. 原有确定性生成路径仍然可用（无措辞覆盖时与底稿一致）
4. report_agent 已删除（模块不可导入）
5. 端点 /report/facts、/report/render 与 MCP 工具面

运行：python test_report_facts.py
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

from docx import Document  # noqa: E402
from framework.models import ITEM_COLUMNS  # noqa: E402
from utils.assessment_engine import assess  # noqa: E402
from utils.report_facts import SCHEMA, build_facts, rows_filled  # noqa: E402
from utils.report_render import clean_narrative, render_from_facts  # noqa: E402

RESULTS = []
KEY = "剪力墙厚度检测"


def check(desc, ok, got=None):
    RESULTS.append((desc, bool(ok)))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def skip(desc, why=""):
    print("SKIP", desc, "->", why)


def sample():
    cols = list(ITEM_COLUMNS[KEY])
    rows = [
        ["1#", "2层墙Q1", "1/A", 200, 201, 202, 199, "", "", "", "", "", "", "", "1F"],
        ["1#", "2层墙Q2", "1/B", 200, 205, 206, 204, "", "", "", "", "", "", "", "1F"],
    ]
    result = assess(KEY, KEY, None, cols, rows)
    return cols, rows, result


def doc_text(path):
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


# ── 1. 事实包 ────────────────────────────────────────────
def test_facts():
    cols, rows, result = sample()
    facts = build_facts("事实测试工程", {"project_name": "事实测试工程"},
                        [KEY], {KEY: rows}, {KEY: cols},
                        assessment_results={KEY: result}, equipment=[])
    check("schema 正确", facts.get("schema") == SCHEMA, facts.get("schema"))
    check("项目抬头保留", facts["project"]["project_name"] == "事实测试工程")
    check("行数与非空行数", facts["items"][0]["rows_filled"] == 2
          and rows_filled(rows) == 2, facts["items"][0]["rows_filled"])
    check("列头与录入一致", facts["items"][0]["columns"] == cols)
    check("评定结论同源",
          facts["items"][0]["conclusion_text"] == result["conclusion"],
          facts["items"][0]["conclusion_text"][:40])
    check("表号按渲染顺序分配", facts["items"][0]["table_no"] == "5.1",
          facts["items"][0]["table_no"])
    check("结论句带编号",
          facts["narrative"]["conclusions"][0].startswith("1.1、"),
          facts["narrative"]["conclusions"][0][:10])
    check("统计字段", facts["stats"]["items"] == 1
          and facts["stats"]["rendered_tables"] == 1
          and facts["stats"]["assessed"] == 1, facts["stats"])
    check("规范清单非空", bool(facts["narrative"]["basis"]),
          len(facts["narrative"]["basis"]))

    again = build_facts("事实测试工程", {"project_name": "事实测试工程"},
                        [KEY], {KEY: rows}, {KEY: cols},
                        assessment_results={KEY: result}, equipment=[])
    again["generated_at"] = facts["generated_at"]
    check("同一输入事实可复现",
          json.dumps(again, sort_keys=True, ensure_ascii=False)
          == json.dumps(facts, sort_keys=True, ensure_ascii=False))

    empty = build_facts("空工程", {}, [KEY], {KEY: []}, {KEY: cols}, equipment=[])
    check("无数据告警", any("没有数据" in w for w in empty["warnings"]),
          empty["warnings"])
    check("无数据不产结论", empty["items"][0]["conclusion_text"] == ""
          and empty["conclusions"] == [], empty["conclusions"])


# ── 2. 渲染 + 措辞覆盖 ───────────────────────────────────
def test_render():
    cols, rows, result = sample()
    facts = build_facts("渲染测试工程", {"project_name": "渲染测试工程"},
                        [KEY], {KEY: rows}, {KEY: cols},
                        assessment_results={KEY: result}, equipment=[])
    tmp = tempfile.mkdtemp(prefix="report_facts_")
    try:
        out = os.path.join(tmp, "report.docx")
        narrative = {
            "overview": "本工程为渲染测试工程，位于测试路 9 号，本次检测对象为剪力墙。",
            "basis": ["《测试规范》GB/T 00000-2026"],
            "conclusions": ["3.1、经检测，所检剪力墙厚度全部合格。"],
        }
        res = render_from_facts(facts, narrative, output_path=out)
        check("渲染产出文件", os.path.isfile(out) and os.path.getsize(out) > 1000,
              os.path.getsize(out) if os.path.isfile(out) else None)
        check("覆盖字段被记录", res.get("applied_narrative")
              == ["basis", "conclusions", "overview"], res.get("applied_narrative"))
        text = doc_text(out)
        check("概况覆盖生效", "渲染测试工程，位于测试路 9 号" in text)
        check("依据覆盖生效", "《测试规范》GB/T 00000-2026" in text)
        check("结论覆盖生效", "3.1、经检测，所检剪力墙厚度全部合格。" in text)
        check("无残留占位符", "{{" not in text, text.count("{{"))
        check("一览表已生成", res.get("tables") == 1, res.get("tables"))

        out2 = os.path.join(tmp, "report_default.docx")
        res2 = render_from_facts(facts, None, output_path=out2)
        text2 = doc_text(out2)
        check("无覆盖时用确定性底稿",
              facts["narrative"]["conclusions"][0] in text2,
              facts["narrative"]["conclusions"][0][:24])
        check("无覆盖时 applied 为空", res2.get("applied_narrative") == [],
              res2.get("applied_narrative"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_narrative_guard():
    cleaned = clean_narrative({
        "overview": "  ", "basis": [], "conclusions": [" ", "1.1、x"],
        "injected": "不应进入报告", "table_no": "9.9",
    })
    check("只保留白名单字段",
          set(cleaned) == {"conclusions"}, sorted(cleaned))
    check("空措辞被过滤", cleaned["conclusions"] == ["1.1、x"],
          cleaned["conclusions"])


def test_agent_removed():
    spec = importlib.util.find_spec("utils.report_agent")
    check("report_agent 模块已删除", spec is None, spec)
    from pathlib import Path
    check("report_agent.py 不存在",
          not Path(ROOT, "report_generator", "utils", "report_agent.py").exists())


# ── 3. 端点 ──────────────────────────────────────────────
def test_endpoints():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("报告端点", "当前解释器没有 fastapi")
        return
    from deps import get_state
    from routers.report import RenderBody, report_facts_endpoint, render_report_endpoint

    cols, rows, result = sample()
    state = get_state()
    saved = {
        "checked": list(state.checked_items or []),
        "sheets": state.sheet_data,
        "assessments": state.assessment_results,
        "info": state.report_info,
        "params": state.cd_params,
    }
    state.checked_items = [KEY]
    state.sheet_data = {KEY: rows}
    state.assessment_results = {KEY: result}
    state.report_info = {
        "report_no": "JC-2026-001",
        "project_name": "端点测试工程",
        "project_location": "武汉市",
        "client": "委托单位",
        "witness": "见证单位",
        "construction_unit": "建设单位",
        "contractor": "施工单位",
        "design_unit": "设计单位",
        "supervision_unit": "监理单位",
        "survey_unit": "勘察单位",
        "structure_type": "框架",
        "building_area": "1000",
        "floor_count": "3",
        "building_height": "12",
        "start_date": "2026-01-01",
        "completion_date": "2026-06-01",
        "inspection_purpose": "检测",
        "test_date": "2026-11-01",
        "report_date": "2026-11-12",
        "tester": "张三",
        "writer": "李四",
        "checker": "王五",
        "reviewer": "赵六",
        "approver": "钱七",
        "project_overview": "端点测试工程，位于武汉市。",
    }
    state.cd_params = {}
    tmp = tempfile.mkdtemp(prefix="report_endpoint_")
    try:
        data = report_facts_endpoint()
        body = data.get("data") or {}
        check("事实端点返回事实包", data.get("ok") is True
              and body.get("schema") == SCHEMA, body.get("schema"))
        check("事实端点带模板信息", bool((body.get("template") or {}).get("name")),
              (body.get("template") or {}).get("name"))

        out = os.path.join(tmp, "endpoint.docx")
        res = render_report_endpoint(RenderBody(
            narrative={"overview": "端点渲染的工程概况。"},
            output_path=out))
        payload = res.get("data") or {}
        check("渲染端点成功", res.get("ok") is True
              and os.path.isfile(out), payload.get("filepath"))
        check("渲染端点应用措辞", payload.get("applied_narrative") == ["overview"],
              payload.get("applied_narrative"))
        check("渲染端点写记录", bool(payload.get("record_id")), payload.get("record_id"))
        # 测试记录不留在用户的记录库里
        try:
            from deps import get_record_store
            if payload.get("record_id"):
                get_record_store().delete_report_record(payload["record_id"])
        except Exception:
            pass
    finally:
        state.checked_items = saved["checked"]
        state.sheet_data = saved["sheets"]
        state.assessment_results = saved["assessments"]
        state.report_info = saved["info"]
        state.cd_params = saved["params"]
        shutil.rmtree(tmp, ignore_errors=True)


def test_tool_schema():
    sys.path.insert(0, os.path.join(ROOT, "webapp"))
    import mcp_server  # noqa: E402
    for name, is_write in (("report_facts", False), ("render_report", True),
                           ("generate_report", True)):
        tool = mcp_server._TOOL_MAP.get(name)
        check("工具存在且写标记正确：%s" % name,
              tool is not None and bool(tool.get("write")) == is_write,
              tool and tool.get("write"))
    generate = mcp_server._TOOL_MAP.get("generate_report") or {}
    props = (generate.get("inputSchema") or {}).get("properties") or {}
    check("generate_report 已去掉 use_agent", "use_agent" not in props, list(props))



def main():
    test_facts()
    test_render()
    test_narrative_guard()
    test_agent_removed()
    test_endpoints()
    test_tool_schema()
    fails = [d for d, ok in RESULTS if not ok]
    print("=" * 50)
    print("%d/%d PASS" % (len(RESULTS) - len(fails), len(RESULTS)))
    if fails:
        print("FAILED:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
