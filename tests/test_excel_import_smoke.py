# -*- coding: utf-8 -*-
"""Excel 导入冒烟测试：工作表行 / 回弹原始数据 / 回弹钻芯成对数据。"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from openpyxl import Workbook  # noqa: E402
from framework.models import ITEM_COLUMNS  # noqa: E402
from utils.excel_import import (  # noqa: E402
    import_assessment_input,
    import_rebound_core_input,
    import_rebound_input,
    import_sheet_rows,
)

from _harness import Results

_R = Results()
check = _R.check


def write_xlsx(path, rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


def main():
    import shutil
    tmp = tempfile.mkdtemp(prefix="excel_import_smoke_")
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp):
    thickness = os.path.join(tmp, "thickness.xlsx")
    cols = ITEM_COLUMNS["剪力墙厚度检测"]
    write_xlsx(thickness, [cols, ["1#", "2层墙Q1", "1/A", 200, 201, 202, 199,
                                  "", "", "", "", "", "", "", "1F"]])
    data = import_sheet_rows(thickness, cols)
    check("工作表导入匹配列", data["matched"] == len(cols), data["matched"])
    check("工作表导入行数/楼层",
          len(data["rows"]) == 1 and data["rows"][0][-1] == "1F", data["rows"])

    rebound = os.path.join(tmp, "rebound.xlsx")
    write_xlsx(rebound, [
        ["楼层", "构件类型", "构件编号", "轴线", "设计强度等级", "测区1", "测区2", "测区3"],
        ["1F", "墙", "Q1", "1/A", "C30", 35.2, 34.8, 36.1],
        ["2F", "墙", "Q2", "2/A", "C30", 36.0, 35.6, 35.9],
    ])
    r = import_rebound_input(rebound)
    check("回弹原始数据导入", r["components"] == 2
          and r["input"]["components"][0]["zones"] == [35.2, 34.8, 36.1], r)
    check("回弹原始数据楼层", r["input"]["components"][0]["floor"] == "1F",
          r["input"]["components"][0])

    core = os.path.join(tmp, "rebound_core.xlsx")
    write_xlsx(core, [
        ["楼层", "构件类型", "构件编号", "轴线", "设计强度等级", "芯样直径",
         "测区1", "测区2", "芯样实测强度1", "对应测区值1", "芯样实测强度2", "对应测区值2"],
        ["1F", "墙", "Q1", "1/A", "C30", 100, 35.2, 34.8, 36.1, 35.0, 35.8, 34.9],
    ])
    rc = import_rebound_core_input(core)
    comp = rc["input"]["components"][0]
    check("回弹钻芯原始数据导入", comp["diameter"] == 100.0
          and len(comp["cores"]) == 2, comp)
    check("回弹钻芯成对值", comp["cores"][0] == {"actual": 36.1, "zone": 35.0},
          comp["cores"][0])

    fam = import_assessment_input(rebound, "rebound")
    check("评定原始数据分发", fam["components"] == 2, fam["components"])

    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
