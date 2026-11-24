# -*- coding: utf-8 -*-
"""逐行结论汇总型评定规则回归（砂浆/螺栓/涂层/钢材/焊缝/木结构）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from framework.models import ITEM_COLUMNS  # noqa: E402
from utils.assessment_engine import assess  # noqa: E402
from utils.assessment_specs import list_specs  # noqa: E402

results = []


def check(desc, ok, got=None):
    results.append((desc, ok))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def row_for(base, conclusion):
    cols = ITEM_COLUMNS[base]
    row = [""] * len(cols)
    # 位置/名称列尽量填第一列，其余关键结论列放到“结论”列
    if "构件位置及名称" in cols:
        row[cols.index("构件位置及名称")] = "测试构件"
    if "焊缝位置及名称" in cols:
        row[cols.index("焊缝位置及名称")] = "测试焊缝"
    if "结论" in cols:
        row[cols.index("结论")] = conclusion
    return cols, [row]


def run(base, conclusion):
    cols, rows = row_for(base, conclusion)
    return assess(base, base, None, cols, rows, options={"table_no": "5.1"})


record_items = [
    "砌筑砂浆强度检测",
    "高强度螺栓扭矩系数检测",
    "防腐涂层厚度检测",
    "防火涂层厚度检测",
    "钢材强度检测",
    "焊缝超声波探伤检测",
    "木构件挠度检测",
    "木材含水率检测",
]
for base in record_items:
    r = run(base, "符合要求")
    check("%s 逐行合格 -> 类型一" % base,
          r.get("ok") and r.get("conclusion_type") == "类型一",
          r.get("conclusion") or r.get("errors"))
    rf = run(base, "不符合要求")
    check("%s 逐行不合格 -> 类型二" % base,
          rf.get("ok") and rf.get("conclusion_type") == "类型二",
          rf.get("conclusion") or rf.get("errors"))

for base in ("砌体构件尺寸偏差检测", "木构件缺陷检测", "木构件尺寸偏差检测"):
    r = run(base, "")
    check("%s 无判定列 -> 仅记录" % base,
          r.get("ok") and r.get("conclusion_type") == "类型三"
          and "仅提供检测结果" in r.get("conclusion", ""),
          r.get("conclusion") or r.get("errors"))

check("评定规则总数 29", len(list_specs()) == 29, len(list_specs()))

failed = [desc for desc, ok in results if not ok]
print("=" * 50)
print("%d/%d PASS" % (len(results) - len(failed), len(results)))
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
