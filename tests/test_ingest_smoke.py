# -*- coding: utf-8 -*-
"""统一采集入口冒烟（P2）：文件识别 + 按格式导入 + .doc 降级提示。

全程直接调用 backend/ingest 与 sheet_apply 的函数，不启动后端、不写磁盘工程
（get_state 只读取 autosave，apply_rows_to_sheet 不落盘）。

运行：python test_ingest_smoke.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp"))
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

from docx import Document  # noqa: E402
from openpyxl import Workbook  # noqa: E402

from framework.models import ITEM_COLUMNS  # noqa: E402

import ingest  # noqa: E402
from sheet_apply import apply_rows_to_sheet  # noqa: E402

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


def write_docx_table(path, rows):
    doc = Document()
    doc.add_paragraph("主体结构检测原始记录")
    table = doc.add_table(rows=0, cols=len(rows[0]))
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = "" if value is None else str(value)
    doc.save(path)


def thickness_rows():
    cols = ITEM_COLUMNS["剪力墙厚度检测"]
    row = ["1#", "2层墙Q1", "1/A", 200, 201, 202, 199,
           "", "", "", "", "", "", "", "1F"]
    return [cols, row]


def main():
    import shutil
    tmp = tempfile.mkdtemp(prefix="ingest_smoke_")
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp):

    # 1. Excel 识别出检测项目
    xlsx = os.path.join(tmp, "thickness.xlsx")
    write_xlsx(xlsx, thickness_rows())
    info = ingest.classify_file(xlsx)
    check("Excel 识别为表格", info.get("kind") == "table", info.get("kind"))
    items = [c["item"] for c in info.get("candidates") or []]
    check("Excel 首选剪力墙厚度检测", items[:1] == ["剪力墙厚度检测"], items[:3])
    check("Excel 给出建议工作表键",
          str(info.get("suggested_sheet_key") or "").startswith("剪力墙厚度检测"),
          info.get("suggested_sheet_key"))
    check("Excel 表头与预览可用",
          len(info.get("header") or []) > 5 and len(info.get("preview") or []) == 1,
          [len(info.get("header") or []), len(info.get("preview") or [])])
    check("普通表不误判为回弹原始数据",
          info.get("assessment_family") == "", info.get("assessment_family"))

    # 2. Word 表格同样能识别
    docx = os.path.join(tmp, "thickness.docx")
    write_docx_table(docx, thickness_rows())
    info_docx = ingest.classify_file(docx)
    check("Word 识别为表格", info_docx.get("kind") == "table", info_docx.get("kind"))
    check("Word 首选检测项目一致",
          [c["item"] for c in info_docx.get("candidates") or []][:1]
          == ["剪力墙厚度检测"],
          [c["item"] for c in info_docx.get("candidates") or []][:3])

    # 3. 回弹原始记录识别（含测区列）
    rebound = os.path.join(tmp, "rebound.xlsx")
    write_xlsx(rebound, [
        ["楼层", "构件类型", "构件编号", "轴线", "设计强度等级",
         "测区1", "测区2", "测区3"],
        ["1F", "墙", "Q1", "1/A", "C30", 35.2, 34.8, 36.1],
    ])
    info_rebound = ingest.classify_file(rebound)
    check("回弹原始数据识别为 rebound",
          info_rebound.get("assessment_family") == "rebound",
          info_rebound.get("assessment_family"))

    # 4. 导入到工作表：覆盖 + 追加 + 自动勾选 + 重算
    from deps import get_state  # noqa: E402
    state = get_state()
    key = "剪力墙厚度检测"
    state.sheet_data[key] = []
    state.checked_items = [k for k in (state.checked_items or []) if k != key]

    first = ingest.import_into_sheet(docx, key)
    check("Word 导入行数", first["imported"] == 1, first["imported"])
    check("导入后进入勾选项", key in state.checked_items, state.checked_items)
    check("导入后行落在工程状态", len(state.sheet_data.get(key) or []) == 1,
          len(state.sheet_data.get(key) or []))
    check("导入结果带列匹配数", int(first.get("matched_columns") or 0) >= 10,
          first.get("matched_columns"))

    second = ingest.import_into_sheet(docx, key, append=True)
    check("追加导入后累计 2 行", second["rows"] == 2, second["rows"])

    third = ingest.import_into_sheet(docx, key)
    check("覆盖导入后回到 1 行", third["rows"] == 1, third["rows"])

    # 5. CSV 也走同一条路
    csv_path = os.path.join(tmp, "thickness.csv")
    cols, row = thickness_rows()
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(",".join(str(c) for c in cols) + "\n")
        fh.write(",".join(str(c) for c in row) + "\n")
    csv_result = ingest.import_into_sheet(csv_path, key)
    check("CSV 导入成功", csv_result["imported"] == 1, csv_result["imported"])

    # 6. .doc：真实文件能转换；坏文件给出可读原因而不是栈
    real_doc = os.path.join(
        ROOT, "original_record", "word",
        "005混凝土抗压强度（回弹法）检测原始记录（JJ0224005）_1733543259775.doc")
    if os.path.isfile(real_doc):
        try:
            converted, warns = ingest.ensure_docx(real_doc)
            ok = (converted.lower().endswith(".docx")
                  and os.path.isfile(converted) and bool(warns))
            check("真实 .doc 转 .docx", ok, os.path.basename(converted))
        except ingest.IngestError as e:
            print("SKIP 真实 .doc 转 .docx ->", str(e)[:100])
    else:
        print("SKIP 真实 .doc 转 .docx -> 样本文件缺失")

    fake_doc = os.path.join(tmp, "legacy.doc")
    with open(fake_doc, "wb") as fh:
        fh.write(b"not-a-real-doc")
    try:
        ingest.classify_file(fake_doc)
        check("坏 .doc 不崩且给出可读原因", False, "未抛错")
    except ingest.IngestError as e:
        message = str(e)
        check("坏 .doc 不崩且给出可读原因",
              bool(message) and ("表格" in message or ".doc" in message),
              message[:120])

    # 6b. 不存在的 .doc
    try:
        ingest.ensure_docx(os.path.join(tmp, "missing.doc"))
        check("不存在的 .doc 报文件不存在", False, "未抛错")
    except ingest.IngestError as e:
        check("不存在的 .doc 报文件不存在", "不存在" in str(e), str(e)[:80])

    # 7. 知识文本与扫描件分流
    md = os.path.join(tmp, "note.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("# 回弹法操作要点\n\n测区布置……")
    wiki_info = ingest.classify_file(md)
    check("Markdown 识别为知识文件", wiki_info.get("kind") == "knowledge",
          wiki_info.get("kind"))

    png = os.path.join(tmp, "scan.png")
    with open(png, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    scan_info = ingest.classify_file(png)
    check("图片识别为扫描件", scan_info.get("kind") == "scan", scan_info.get("kind"))
    check("扫描件提示走 scan_submit",
          (scan_info.get("next") or {}).get("tool") == "scan_submit",
          scan_info.get("next"))

    # 8. 不支持的扩展名
    bad = os.path.join(tmp, "x.zip")
    with open(bad, "wb") as fh:
        fh.write(b"x")
    try:
        ingest.classify_file(bad)
        check("拒绝不支持的扩展名", False, "未抛错")
    except ingest.IngestError as e:
        check("拒绝不支持的扩展名", "不支持" in str(e), str(e)[:100])

    # 9. apply_rows_to_sheet 的合并保留规则（钻芯法同结构回导）
    class _State(object):
        def __init__(self):
            self.sheet_data = {"钻芯法检测（梁）": [[1], [2]]}
            self.merges = {"钻芯法检测（梁）": [(0, 0, 2, 1)]}
            self.merge_formats = {"钻芯法检测（梁）": {}}
            self.cell_formats = {"钻芯法检测（梁）": {}}
            self.cd_params = {"钻芯法检测（梁）": {"building": "1#"}}
            self.checked_items = []

    fake = _State()
    apply_rows_to_sheet(fake, "钻芯法检测（梁）", [[3], [4]])
    check("同结构回导保留合并",
          fake.merges["钻芯法检测（梁）"] == [(0, 0, 2, 1)],
          fake.merges["钻芯法检测（梁）"])
    apply_rows_to_sheet(fake, "钻芯法检测（梁）", [[3], [4], [5]])
    check("不同结构重导清空合并",
          fake.merges["钻芯法检测（梁）"] == [],
          fake.merges["钻芯法检测（梁）"])

    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
