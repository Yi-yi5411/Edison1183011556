# -*- coding: utf-8 -*-
"""模板库 / 报告模板切换 / 原始记录 / 报告修改 冒烟测试（无 GUI、无 COM）。

运行：
    python test_template_library_smoke.py

测试使用临时项目根 + 临时 SQLite，不修改真实 data/ 模板库；
报告修改测试需要把生成文件放在真实项目根内（满足路径白名单），
测试结束后删除该临时导出目录。
"""
import json
import os
import shutil
import sys
import tempfile
try:  # 控制台/重定向可能是 cp936，统一按 UTF-8 输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from docx import Document  # noqa: E402
from docx.shared import Cm  # noqa: E402

from core.app_controller import AppController  # noqa: E402
from utils.original_record import generate_native_record  # noqa: E402
from utils.original_record_fill import fill_imported_record  # noqa: E402
from utils.report_edit import (  # noqa: E402
    load_report_document,
    replace_report_text,
    save_report_document,
)
from utils.template_library import TemplateLibrary  # noqa: E402
from utils.word_report import generate_report  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


# ── 测试数据 ──
REBOUND_ITEM = "回弹法检测(主要来源为仪器数据，可选用)"
REBOUND_SHEET = REBOUND_ITEM + "（墙）"
REBOUND_COLS = ["构件名称", "构件轴号", "设计强度等级", "平均强度值(MPa)",
                "标准差(MPa)", "最小测区强度值(MPa)", "强度推定值(MPa)",
                "龄期(d)"]
REBOUND_ROWS = [
    ["-1FL墙", "2-3/A-C", "C30", "35.2", "1.8", "32.1", "32.4", "28"],
    ["1FL墙", "4-5/B-D", "C30", "36.1", "2.0", "32.8", "33.0", "28"],
]
COVER_SHEET = "混凝土梁保护层厚度检测"
COVER_COLS = ["楼栋", "构件位置及名称", "构件轴线编号", "设计值(mm)",
              "钢筋根数"] + ["实测值%d" % i for i in range(1, 11)] + ["合格点率"]
COVER_ROWS = [["1#楼", "2层梁", "1/A", 15.0, 2] + [15.5] * 10 + ["100%"]]
INFO = {
    "project_name": "模板库冒烟工程",
    "report_no": "SMOKE-2026-001",
    "client": "测试委托单位",
    "project_location": "测试地点",
    "witness": "测试见证单位",
    "test_date": "2026年11月07日",
    "report_date": "2026年11月08日",
    "tester": "张三",
    "writer": "李四",
    "checker": "王五",
    "reviewer": "赵六",
    "approver": "钱七",
}


def _new_docx(path, paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)


def _chapter_package(base_dir):
    """生成最小报告模板包（8 章节 + 1 结果表），返回 ZIP 路径。"""
    pkg = os.path.join(base_dir, "pkg")
    os.makedirs(pkg, exist_ok=True)
    chapters = {
        "cover_main": ["{{project_name}}", "检 测 报 告", "报告编号："],
        "cover_home": ["{{main_testing_items}}", "{{report_date}}"],
        "overview": ["一、工程概况", "自定义工程概况章节"],
        "basis": ["二、主要检测依据"],
        "equipment": ["三、主要检测设备"],
        "content": ["四、检测内容："],
        "result_intro": ["五、检测结果：", "xxx年xxx月xxx日~xxx日"],
        "conclusion": ["六、检测结论："],
    }
    for key, paras in chapters.items():
        _new_docx(os.path.join(pkg, key + ".docx"), paras)

    result_doc = Document()
    table = result_doc.add_table(rows=2, cols=4)
    table.style = "Table Grid"
    headers = ["构件名称", "构件轴号", "设计强度等级", "强度推定值(MPa)"]
    for i, text in enumerate(headers):
        table.cell(0, i).text = text
    table.cell(1, 0).text = "占位数据"
    result_doc.save(os.path.join(pkg, "result.docx"))

    manifest = {
        "schema": "report_template_v1",
        "name": "冒烟自定义报告模板",
        "description": "自定义章节标题用于断言",
        "chapters": {key: key + ".docx" for key in chapters},
        "result_tables": [{
            "base": "回弹法检测",
            "component": "墙",
            "file": "result.docx",
            "header_rows": 1,
            "aliases": {},
        }],
    }
    with open(os.path.join(pkg, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    zip_path = os.path.join(base_dir, "custom_report_template.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(pkg):
            for filename in files:
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, pkg).replace("\\", "/")
                zf.write(full, rel)
    return zip_path


def _imported_original_template(base_dir):
    """生成一个带表头/占位符/数据表的 .docx 原始记录模板。"""
    path = os.path.join(base_dir, "imported_original.docx")
    doc = Document()
    doc.add_paragraph("{{project_name}} 检测原始记录")
    doc.add_paragraph("报告编号：{{report_no}}")

    info_table = doc.add_table(rows=2, cols=4)
    info_table.style = "Table Grid"
    values = [["工程名称", "", "检测编号", ""],
              ["检测日期", "", "委托单位", ""]]
    for r, row in enumerate(values):
        for c, text in enumerate(row):
            info_table.cell(r, c).text = text

    doc.add_paragraph()
    table = doc.add_table(rows=2, cols=4)
    table.style = "Table Grid"
    headers = ["构件名称", "构件轴号", "设计强度等级", "强度推定值(MPa)"]
    for i, text in enumerate(headers):
        table.cell(0, i).text = text
    table.cell(1, 0).text = "占位数据"
    doc.save(path)
    return path


def main():
    tmp_root = tempfile.mkdtemp(prefix="tpl_smoke_")
    try:
        # 复制真实 report_template/ 到临时项目根，避免污染真实 data/
        shutil.copytree(
            os.path.join(ROOT, "report_template"),
            os.path.join(tmp_root, "report_template"),
            ignore=shutil.ignore_patterns("~$*"),
        )
        lib = TemplateLibrary(root=tmp_root)
        try:
            # ── 1. 种子 ──
            reports = lib.list_report_templates()
            originals = lib.list_original_templates()
            check("内置报告模板已种子", len(reports) >= 1,
                  [t["id"] for t in reports])
            check("内置报告模板可用", reports[0]["available"],
                  reports[0].get("missing"))
            check("内置原始记录模板 10 个", len(originals) == 10,
                  len(originals))
            defaults = lib.defaults_map()
            check("原始记录默认映射已种子",
                  defaults.get(REBOUND_ITEM) == "builtin_rebound", defaults)

            # ── 2. 内置报告模板生成 ──
            out1 = os.path.join(tmp_root, "out1.docx")
            ts = lib.get_report_template_set("builtin_standard")
            result = generate_report(
                INFO["project_name"], INFO,
                {REBOUND_SHEET: REBOUND_ROWS},
                {REBOUND_SHEET: REBOUND_COLS},
                checked_order=[REBOUND_SHEET], output_path=out1,
                template_set=ts)
            text1 = "\n".join(p.text for p in Document(out1).paragraphs)
            check("内置模板生成报告", os.path.isfile(out1) and result["tables"] == 1,
                  result)
            check("报告记录模板信息", result.get("template_id") == "builtin_standard",
                  result.get("template_id"))
            check("报告中文占位符已清理", "{{" not in text1)

            # ── 3. 自定义报告模板包导入/生成 ──
            zip_path = _chapter_package(tmp_root)
            custom, warnings = lib.import_report_package(zip_path)
            check("自定义报告模板包导入", custom["available"], warnings)
            lib.set_default_report_template(custom["id"])
            custom_set = lib.get_report_template_set(custom["id"])
            out2 = os.path.join(tmp_root, "out2.docx")
            result2 = generate_report(
                INFO["project_name"], INFO,
                {REBOUND_SHEET: REBOUND_ROWS},
                {REBOUND_SHEET: REBOUND_COLS},
                checked_order=[REBOUND_SHEET], output_path=out2,
                template_set=custom_set)
            text2 = "\n".join(p.text for p in Document(out2).paragraphs)
            check("自定义模板章节生效", "自定义工程概况章节" in text2)
            check("自定义模板结果表生成", result2["tables"] == 1, result2["tables"])

            # ── 4. 原生原始记录 ──
            rebound_view = lib.resolve_original_template(REBOUND_ITEM)
            path4 = os.path.join(tmp_root, "original_rebound.docx")
            path4, warnings4 = generate_native_record(
                rebound_view["config"], REBOUND_SHEET, REBOUND_COLS,
                REBOUND_ROWS, INFO, output_path=path4)
            doc4 = Document(path4)
            table_texts = [[c.text.strip() for c in row.cells]
                           for row in doc4.tables[1].rows]
            check("原生原始记录生成", os.path.isfile(path4), warnings4)
            check("原生原始记录标题",
                  "混凝土抗压强度（回弹法）检测原始记录" in "\n".join(
                      p.text for p in doc4.paragraphs))
            info_texts = [[c.text.strip() for c in row.cells]
                          for row in doc4.tables[0].rows]
            check("原生原始记录表头字段",
                  any("模板库冒烟工程" in row for row in info_texts)
                  and any("SMOKE-2026-001" in row for row in info_texts),
                  info_texts)
            check("原生原始记录数据行",
                  len(table_texts) >= 3
                  and table_texts[1][0] == "-1FL墙"
                  and "-1FL墙" in "\n".join(table_texts[1]),
                  table_texts)

            cover_view = lib.resolve_original_template(COVER_SHEET)
            path5 = os.path.join(tmp_root, "original_cover.docx")
            path5, _warnings5 = generate_native_record(
                cover_view["config"], COVER_SHEET, COVER_COLS,
                COVER_ROWS, INFO, output_path=path5)
            cover_headers = [c.text for c in Document(path5).tables[1].rows[0].cells]
            check("保护层原始记录按配置筛列",
                  "实测值1" in cover_headers and "偏差值1" not in cover_headers,
                  cover_headers)

            # ── 5. 导入 DOCX 原始记录 ──
            imported_path = _imported_original_template(tmp_root)
            imported = lib.import_original_template(
                imported_path, "冒烟导入原始记录", "SMOKE-ORIG",
                [REBOUND_ITEM], set_default=True)
            check("导入原始记录模板", imported["available"] and imported["fillable"],
                  imported)
            resolved = lib.resolve_original_template(REBOUND_ITEM)
            check("导入模板成为检测项默认", resolved["id"] == imported["id"],
                  resolved["id"])
            tpl_path = lib.get_original_file_path(imported["id"])
            out6 = os.path.join(tmp_root, "imported_filled.docx")
            out6, warnings6 = fill_imported_record(
                tpl_path, REBOUND_SHEET, REBOUND_COLS, REBOUND_ROWS,
                INFO, output_path=out6)
            doc6 = Document(out6)
            full6 = "\n".join(p.text for p in doc6.paragraphs)
            check("导入模板占位符替换", "模板库冒烟工程" in full6 and "SMOKE-2026-001" in full6,
                  full6[:120])
            check("导入模板表头字段", any(
                "模板库冒烟工程" in [c.text for c in row.cells]
                for row in doc6.tables[0].rows))
            data6 = [[c.text for c in row.cells] for row in doc6.tables[1].rows]
            check("导入模板数据表填充", len(data6) >= 3 and data6[1][0] == "-1FL墙",
                  data6)

            # ── 6. 报告修改（真实项目根内，满足路径白名单） ──
            export_dir = os.path.join(
                ROOT, "report_generator", "exports",
                "_template_smoke_%d" % os.getpid())
            os.makedirs(export_dir, exist_ok=True)
            try:
                edit_src = os.path.join(export_dir, "待修改报告.docx")
                ts_builtin = lib.get_report_template_set("builtin_standard")
                generate_report(
                    INFO["project_name"], INFO,
                    {REBOUND_SHEET: REBOUND_ROWS},
                    {REBOUND_SHEET: REBOUND_COLS},
                    checked_order=[REBOUND_SHEET], output_path=edit_src,
                    template_set=ts_builtin)
                loaded = load_report_document(edit_src)
                target = None
                for p in loaded["paragraphs"]:
                    if "经回弹法检测" in p["text"]:
                        target = p
                        break
                check("报告加载段落块", target is not None,
                      loaded["paragraph_count"])
                if target is not None:
                    new_text = target["text"] + "【修改标记】"
                    saved = save_report_document(
                        edit_src,
                        [{"index": target["index"], "text": new_text}], [])
                    check("报告修改另存", saved["saved"]
                          and os.path.isfile(saved["filepath"]), saved)
                    reopened = "\n".join(
                        p.text for p in Document(saved["filepath"]).paragraphs)
                    check("报告修改内容写回", "【修改标记】" in reopened)
                    replaced = replace_report_text(
                        saved["filepath"], "【修改标记】", "【替换标记】")
                    check("报告查找替换", replaced["replacements"] == 1,
                          replaced["replacements"])
                    final_text = "\n".join(
                        p.text for p in Document(replaced["filepath"]).paragraphs)
                    check("替换内容写回", "【替换标记】" in final_text)
            finally:
                shutil.rmtree(export_dir, ignore_errors=True)

            # ── 7. 项目序列化兼容 ──
            selection = {
                "report_template_id": "builtin_standard",
                "original_template_map": {REBOUND_SHEET: "builtin_rebound"},
            }
            state = AppController.serialize(
                "冒烟项目", {REBOUND_SHEET: REBOUND_ROWS}, {}, {}, {}, {},
                template_selection=selection)
            check("serialize 含 template_selection",
                  state.get("template_selection") == selection)
            unpacked = AppController.deserialize(state)
            check("deserialize 仍返回 9 元组且兼容", len(unpacked) == 9,
                  len(unpacked))
        finally:
            lib.close()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
