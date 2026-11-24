# -*- coding: utf-8 -*-
"""评定引擎冒烟测试：首批 A（回弹/保护层/截面尺寸/厚度/钢筋间距）+ 根数。"""
import os
import shutil
import sys
import tempfile
try:  # 控制台/重定向可能是 cp936，统一按 UTF-8 输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from docx import Document  # noqa: E402
from framework.models import ITEM_COLUMNS  # noqa: E402
from utils.assessment_engine import assess, format_conclusion  # noqa: E402
from utils.assessment_specs import list_specs  # noqa: E402
from utils.word_report import generate_report  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


def run(base_item, columns, rows, component="", options=None, raw=None):
    return assess(base_item + "（%s）" % component if component else base_item,
                  base_item, component, columns, rows, options=options,
                  raw_input=raw)


def main():
    check("规则数量 29", len(list_specs()) == 29, len(list_specs()))

    # ── 回弹法：n<10 单构件 ──
    raw_single = {"components": [
        {"floor": "1F", "component_type": "墙", "component_code": "Q1",
         "axis": "1/A", "grade": "C30",
         "zones": [35.2, 34.8, 36.1, 35.5, 34.9]},
    ]}
    r1 = run("回弹法检测", [], [], "墙",
             options={"table_no": "5.1"}, raw=raw_single)
    check("回弹单构件评定成功", r1["ok"], r1.get("errors"))
    check("回弹单构件类型一", r1["conclusion_type"] == "类型一",
          r1.get("conclusion"))
    check("回弹单构件结论含推定值范围",
          "混凝土剪力墙构件混凝土抗压强度推定值范围为" in r1["conclusion"],
          r1.get("conclusion"))

    # ── 回弹法：n>=10 且同组有效批 → 批评定 ──
    raw_batch = {"components": [
        {"floor": "1F", "component_type": "墙", "component_code": "Q1",
         "grade": "C30",
         "zones": [35.2, 34.8, 36.1, 35.5, 34.9, 35.8, 36.2, 35.0, 34.7, 35.9]},
        {"floor": "1F", "component_type": "墙", "component_code": "Q2",
         "grade": "C30",
         "zones": [36.2, 35.8, 36.4, 35.9, 36.1, 35.7, 36.0, 35.6, 36.3, 35.9]},
    ]}
    r2 = run("回弹法检测", [], [], "墙",
             options={"table_no": "5.1"}, raw=raw_batch)
    check("回弹批评定成功", r2["ok"], r2.get("errors"))
    check("回弹批评定模板B", "构件批混凝土抗压强度推定值" in r2["conclusion"],
          r2.get("conclusion"))
    check("回弹批评定有效批组数", len(r2.get("batch_groups") or []) == 1,
          r2.get("batch_groups"))

    # ── 回弹法：无图纸 ──
    raw_no = {"components": [
        {"component_type": "墙", "component_code": "Q1", "grade": "/",
         "zones": [35.2, 34.8, 36.1]},
    ]}
    r3 = run("回弹法检测", [], [], "墙", raw=raw_no)
    check("回弹无图纸类型三", r3["conclusion_type"] == "类型三",
          r3.get("conclusion"))
    check("回弹无图纸结论表号", "表1" in r3["conclusion"], r3.get("conclusion"))

    # ── 化学植筋锚固承载力：合格/不合格 ──
    anchor_cols = ITEM_COLUMNS["化学植筋锚固承载力检测"]
    anchor_ok = [["1#", 1, "1FL-3J", "3-J", "HRB400", 6, "7.3 kN", 0.03,
                  "基材无裂缝、钢筋无滑移；", "符合规范要求", ""]]
    r_anchor = run("化学植筋锚固承载力检测", anchor_cols, anchor_ok,
                   options={"table_no": "5.4"})
    check("锚固评定成功", r_anchor["ok"], r_anchor.get("errors"))
    check("锚固合格类型一", r_anchor["conclusion_type"] == "类型一",
          r_anchor.get("conclusion"))
    check("锚固结论含标准项目名",
          "填充砌体墙化学植筋锚固承载力满足设计要求" in r_anchor["conclusion"],
          r_anchor.get("conclusion"))

    anchor_fail = [["1#", 1, "1FL-3J", "3-J", "HRB400", 6, "5.5 kN", 0.03,
                    "基材无裂缝、钢筋无滑移；", "符合规范要求", ""]]
    r_anchor_fail = run("化学植筋锚固承载力检测", anchor_cols, anchor_fail)
    check("锚固不合格类型二", r_anchor_fail["conclusion_type"] == "类型二",
          r_anchor_fail.get("conclusion"))
    check("锚固不合格结论含根数",
          "1根不满足设计要求" in r_anchor_fail["conclusion"],
          r_anchor_fail.get("conclusion"))

    # ── 保护层：合格 ──
    cover_cols = ITEM_COLUMNS["混凝土梁保护层厚度检测"]
    cover_rows = [["1#", "2层梁", "1/A", 15.0, 2] + [15.5] * 10 + [""] * 10 + [""]]
    r4 = run("混凝土梁保护层厚度检测", cover_cols, cover_rows)
    check("保护层评定成功", r4["ok"], r4.get("errors"))
    check("保护层合格类型一", r4["conclusion_type"] == "类型一", r4.get("conclusion"))
    check("保护层合格点率 100", "100.00%" in r4["conclusion"],
          r4.get("conclusion"))

    # ── 保护层：1.5 倍一票否决 ──
    cover_rows_veto = [["1#", "2层梁", "1/A", 15.0, 2]
                       + [15.5] * 9 + [31.0] + [""] * 10 + [""]]
    r5 = run("混凝土梁保护层厚度检测", cover_cols, cover_rows_veto)
    check("保护层一票否决类型二", r5["conclusion_type"] == "类型二"
          and "1.5倍" in r5["conclusion"], r5.get("conclusion"))

    # ── 截面尺寸：合格 ──
    sec_cols = ITEM_COLUMNS["混凝土梁结构尺寸检测"]
    sec_rows = [["1#", "2层梁KL1", "1/A", 300, 500,
                 301, 302, 300, 501, 502, 500, "", "", "", ""]]
    r6 = run("混凝土梁结构尺寸检测", sec_cols, sec_rows)
    check("截面尺寸合格类型一", r6["ok"] and r6["conclusion_type"] == "类型一",
          r6.get("conclusion") or r6.get("errors"))
    check("截面尺寸测点合格率", r6.get("point_stats", {}).get("pass_rate") == 100.0,
          r6.get("point_stats"))

    # ── 截面尺寸：正偏差占优 → 模板3 ──
    sec_rows_high = []
    for i in range(4):
        # 宽度正偏差 +15（符合要求），高度偏差 +5（符合规范）
        sec_rows_high.append(["1#", "梁%d" % i, "轴%d" % i, 300, 500,
                              314, 315, 316, 504, 505, 506,
                              "", "", "", ""])
    r7 = run("混凝土梁结构尺寸检测", sec_cols, sec_rows_high)
    check("截面尺寸模板3（正偏差占优）",
          r7["conclusion_type"] == "类型二"
          and "主要表现为实测正偏差" in r7["conclusion"], r7.get("conclusion"))
    check("截面尺寸三类统计", r7.get("point_stats", {}).get("meets_points", 0) > 0,
          r7.get("point_stats"))
    r7b = run("混凝土梁结构尺寸检测", sec_cols, sec_rows_high,
              options={"include_component_stats": True})
    check("截面尺寸模板2（构件统计）",
          "全楼共抽取了" in r7b["conclusion"], r7b.get("conclusion"))

    # ── 厚度：合格 ──
    th_cols = ITEM_COLUMNS["剪力墙厚度检测"]
    th_rows = [["1#", "2层墙Q1", "1/A", 200, 201, 202, 199, "", "", "", "", "", "", ""]]
    r8 = run("剪力墙厚度检测", th_cols, th_rows)
    check("厚度合格类型一", r8["ok"] and r8["conclusion_type"] == "类型一",
          r8.get("conclusion") or r8.get("errors"))

    # ── 钢筋间距：合格 + 模板3 ──
    sp_cols = ITEM_COLUMNS["现浇板钢筋间距检测"]
    sp_rows = [["1#", "2层板", "1/A", "竖向", 200, 201, 202, 199, 200, 201, 200,
                "", "", "", "", "", "", "", "", ""]]
    r9 = run("现浇板钢筋间距检测", sp_cols, sp_rows)
    check("间距合格类型一", r9["ok"] and r9["conclusion_type"] == "类型一",
          r9.get("conclusion") or r9.get("errors"))
    sp_rows_low = [["1#", "板%d" % i, "轴%d" % i, "竖向", 200,
                    188, 189, 190, 189, 188, 190,
                    "", "", "", "", "", "", "", "", ""] for i in range(4)]
    r10 = run("现浇板钢筋间距检测", sp_cols, sp_rows_low)
    check("间距模板3（负偏差占优）",
          r10["conclusion_type"] == "类型二"
          and "主要表现为实测负偏差" in r10["conclusion"],
          r10.get("conclusion"))

    # ── 根数：合格/不合格/无图纸 ──
    c_cols = ITEM_COLUMNS["梁构件底排受力钢筋根数检测"]
    c_rows = [["1#", "2层梁L1", "1/A", 4, 4, "合格"],
              ["1#", "2层梁L2", "2/A", 4, 3, "不合格"]]
    r11 = run("梁构件底排受力钢筋根数检测", c_cols, c_rows)
    check("根数类型二", r11["ok"] and r11["conclusion_type"] == "类型二",
          r11.get("conclusion") or r11.get("errors"))
    check("根数结论数字", "符合设计要求的有1个，不符合设计要求的有1个" in r11["conclusion"],
          r11.get("conclusion"))
    c_rows_no = [["1#", "2层梁L1", "1/A", "/", 4, ""]]
    r12 = run("梁构件底排受力钢筋根数检测", c_cols, c_rows_no)
    check("根数无图纸类型三", r12["conclusion_type"] == "类型三",
          r12.get("conclusion"))

    # ── 钻芯法：单构件合格/不合格/批评定 ──
    core_cols = ITEM_COLUMNS["钻芯法检测"]
    core_rows = [
        ["1#", "1", "KL1", "1层梁", "1/A", "1", "100", "7854", "275", "35.0", "", "", "C30"],
        ["1#", "1", "KL1", "1层梁", "1/A", "2", "100", "7854", "283", "36.0", "", "", "C30"],
        ["1#", "1", "KL1", "1层梁", "1/A", "3", "100", "7854", "267", "34.0", "", "", "C30"],
    ]
    r13 = run("钻芯法检测", core_cols, core_rows, "梁")
    check("钻芯法单构件类型一", r13["ok"] and r13["conclusion_type"] == "类型一",
          r13.get("conclusion") or r13.get("errors"))
    core_rows_fail = [row[:9] + [str(float(row[9]) - 6)] + row[10:] for row in core_rows]
    r14 = run("钻芯法检测", core_cols, core_rows_fail, "梁")
    check("钻芯法单构件类型二", r14["ok"] and r14["conclusion_type"] == "类型二",
          r14.get("conclusion"))
    core_rows_batch = []
    for i in range(15):
        core_rows_batch.append(["1#", "1", "KL1", "1层梁", "1/A", str(i + 1),
                                "100", "7854", "280", str(35.0 + (i % 3) * 0.5),
                                "", "", "C30"])
    r15 = run("钻芯法检测", core_cols, core_rows_batch, "梁")
    check("钻芯法批评定模板B",
          r15["ok"] and "构件批混凝土抗压强度推定值" in r15["conclusion"],
          r15.get("conclusion") or r15.get("errors"))
    # 两个批次各 15 个芯样：批次列必须参与分组，不能被合并成一个批
    core_rows_two_batch = []
    for batch, base in (("1", 45.0), ("2", 30.0)):
        for i in range(15):
            core_rows_two_batch.append(["1#", batch, "K%s" % batch, "", "1/A",
                                        str(i + 1), "100", "7854", "280",
                                        "%.1f" % (base + (i % 3) * 0.5),
                                        "", "", "C40"])
    r15b = run("钻芯法检测", core_cols, core_rows_two_batch, "梁")
    check("钻芯法两批次分别评定",
          r15b["ok"] and len(r15b.get("batch_groups") or []) == 2,
          [(g.get("batch"), g.get("value"))
           for g in r15b.get("batch_groups") or []])

    # ── 回弹钻芯修正法 ──
    r16 = run("回弹钻芯修正法检测", [], [], "墙", raw={
        "components": [{
            "component_type": "墙", "component_code": "Q1", "axis": "1/A",
            "grade": "C30", "diameter": 100,
            "zones": [35.2, 34.8, 36.1, 35.5, 34.9],
            "cores": [{"actual": 36.0 + i * 0.2, "zone": 35.0 + i * 0.1}
                      for i in range(6)],
        }],
    })
    check("回弹钻芯修正法评定成功", r16["ok"], r16.get("errors"))
    check("回弹钻芯修正法结论前缀",
          "回弹-钻芯修正法" in r16["conclusion"], r16.get("conclusion"))
    check("回弹钻芯修正法形成修正批",
          len(r16.get("corrections") or []) == 1, r16.get("corrections"))

    # ── 结论重格式化（报告表号） ──
    formatted = format_conclusion(r3, "5.3")
    check("结论按报告表号格式化", "表5.3" in formatted, formatted)

    # ── 报告生成使用评定结论 ──
    tmp = tempfile.mkdtemp(prefix="assessment_report_")
    out_path = os.path.join(tmp, "评定结论报告.docx")
    rebound_cols = ITEM_COLUMNS["回弹法检测"]
    rebound_rows = [["Q1", "1/A", "C30", "35.4", "0.5", "34.8", "34.8", "28"]]
    report = generate_report(
        "评定冒烟工程", {"project_name": "评定冒烟工程"},
        {"回弹法检测（墙）": rebound_rows},
        {"回弹法检测（墙）": rebound_cols},
        checked_order=["回弹法检测（墙）"], output_path=out_path,
        assessment_results={"回弹法检测（墙）": r1})
    text = "\n".join(p.text for p in Document(out_path).paragraphs)
    check("报告生成写入评定结论",
          "回弹法所检混凝土剪力墙构件混凝土抗压强度推定值范围为" in text,
          [p for p in text.split("\n") if "回弹法" in p][:2])
    check("报告生成成功", report.get("tables") == 1, report)
    shutil.rmtree(tmp, ignore_errors=True)

    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
