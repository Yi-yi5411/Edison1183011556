# -*- coding: utf-8 -*-
"""报告预检/兜底结论/锚固表合并回归。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from docx import Document  # noqa: E402

from core.app_controller import AppController  # noqa: E402
from utils.report_docx import _fill_result_table  # noqa: E402
from utils.report_preflight import run_preflight  # noqa: E402
from utils.report_template_map import (  # noqa: E402
    _ANCHOR_ALIASES, build_conclusion,
)
from utils.report_templates import ReportTemplateSet  # noqa: E402

results = []


def check(desc, ok, got=None):
    results.append((desc, ok))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def complete_info():
    return {
        "report_no": "JC-2026-001",
        "project_name": "测试工程",
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
        "report_date": "2099-12-31",
        "tester": "张三",
        "writer": "李四",
        "checker": "王五",
        "reviewer": "赵六",
        "approver": "钱七",
        "project_overview": "本工程为测试工程，位于武汉市。",
    }


def preflight_case():
    key = "钻芯法检测（梁）"
    rows = [["1#", "1", "K-1", "一层", "1", "30", "30", "C30"]]
    result = run_preflight(
        complete_info(), [key], {key: rows}, ReportTemplateSet.builtin(),
        {key: {"ok": True, "warnings": []}})
    check("完整数据可通过预检", not result["errors"], result["errors"])
    check("完整数据无多余警告", not result["warnings"], result["warnings"])

    empty = run_preflight(
        complete_info(), [key], {key: []}, ReportTemplateSet.builtin(),
        {key: {"ok": True}})
    check("空数据被预检拦截", any("没有有效数据" in e for e in empty["errors"]),
          empty["errors"])

    unassessed = run_preflight(
        complete_info(), [key], {key: rows}, ReportTemplateSet.builtin(), {})
    check("未评定被预检拦截", any("尚未评定" in e for e in unassessed["errors"]),
          unassessed["errors"])

    no_template = run_preflight(
        complete_info(), ["砖强度检测"], {"砖强度检测": [["1", "2"]]},
        ReportTemplateSet.builtin(), {"砖强度检测": {"ok": True}})
    check("缺模板被预检拦截",
          any("缺少对应的报告结果表模板" in e for e in no_template["errors"]),
          no_template["errors"])


def conclusion_case():
    ac = AppController()
    core_cols = ac.get_columns("钻芯法检测（板）")
    core_rows = [["1#", "1", "1", "", "", "1", "75", "4418", "", "", "/", "", "C40"]]
    text = build_conclusion("钻芯法检测", "板", core_rows, core_cols)
    check("空强度数据不得判满足", "满足" not in text and "无法判定" in text, text)

    anchor_cols = ac.get_columns("化学植筋锚固承载力检测")
    anchor_rows = [["1#", 1, "11FQ", "3-J", "HRB400", 6, "7.3 kN", 0.03,
                    "基材无裂缝、钢筋无滑移；", "符合规范要求", ""]]
    text2 = build_conclusion("化学植筋锚固承载力检测", None, anchor_rows, anchor_cols)
    check("逐行合格结论可判满足", "满足" in text2, text2)

    pass_cols = ["构件名称", "推定值(MPa)", "设计强度等级"]
    pass_rows = [["K-1", "29.8", "C30"]]
    text3 = build_conclusion("钻芯法检测", "梁", pass_rows, pass_cols)
    check("低于设计等级判不满足", "不满足" in text3, text3)


def anchor_merge_case():
    path = os.path.join(
        ROOT, "report_template", "五、实际检测内容模板",
        "五、检测结果-表5.7 填充墙化学植筋锚固承载力试验结果一览表.docx")
    doc = Document(path)
    table = doc.tables[0]
    gui = AppController().get_columns("化学植筋锚固承载力检测")
    rows = [
        ["1#", 1, "11FQ", "3-J", "HRB400", 6, "7.3 kN", 0.03,
         "基材无裂缝、钢筋无滑移；", "符合规范要求", ""],
        ["1#", 2, "11FQ", "3-H", "HRB400", 6, "7.0 kN", 0.02,
         "基材无裂缝、钢筋无滑移；", "符合规范要求", ""],
    ]
    _fill_result_table(table, rows, gui, 1, _ANCHOR_ALIASES, [], "化学植筋锚固承载力检测")
    check("锚固表构件名称不被自动合并清空",
          table.rows[1].cells[1].text.strip() == "11FQ",
          table.rows[1].cells[1].text)


preflight_case()
conclusion_case()
anchor_merge_case()

failed = [desc for desc, ok in results if not ok]
print("=" * 50)
print("%d/%d PASS" % (len(results) - len(failed), len(results)))
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
