# -*- coding: utf-8 -*-
"""系统原生 DOCX 原始记录生成（纯函数，无 Qt 依赖）。

不依赖 WPS/Word：用 python-docx 直接生成“表头信息 + 数据表 + 签字栏”
的电子原始记录。官方 .doc 模板只作为参考文件下载，不在本模块填充。
"""
import os
import re
from datetime import datetime

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

try:
    from report_generator.framework.resources import resolve_path
    from report_generator.utils.report_docx import _clean_rows, _norm
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from framework.resources import resolve_path
    from utils.report_docx import _clean_rows, _norm

_INVALID_FILENAME = re.compile(r'[\\/:*?"<>|]+')


def _safe_filename(text, limit=48):
    """Windows 文件名安全化（去非法字符、限长）。"""
    s = _INVALID_FILENAME.sub("_", str(text or "")).strip(" ._")
    s = re.sub(r"\s+", "", s)
    return (s[:limit] or "未命名")


def _display_width(columns):
    """按列数估算字号（列越多字越小）。"""
    n = len(columns)
    if n <= 10:
        return 9
    if n <= 15:
        return 8
    if n <= 20:
        return 7
    return 6.5


def _set_run_font(run, size=9, bold=False):
    """设置中英文字体与字号。"""
    run.font.name = "宋体"
    run.font.size = Pt(size)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rpr.rFonts.set(qn("w:eastAsia"), "宋体")


def _cell_text(cell, text, size=9, bold=False,
               align=WD_ALIGN_PARAGRAPH.CENTER):
    """写单元格并统一字体/对齐（保留 Table Grid 样式）。"""
    cell.text = ""
    para = cell.paragraphs[0]
    para.alignment = align
    run = para.add_run("" if text is None else str(text))
    _set_run_font(run, size=size, bold=bold)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _shade_cell(cell, fill="D9E2F3"):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _page_setup(doc, landscape):
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    if landscape:
        section.page_width, section.page_height = Cm(29.7), Cm(21.0)
    else:
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    margin = Cm(1.2) if landscape else Cm(1.6)
    section.top_margin = section.bottom_margin = margin
    section.left_margin = section.right_margin = margin


def _pick_columns(all_columns, wanted):
    """按模板定义挑选列；返回 ([(idx, label)], missing)。

    wanted == "all" / None / [] 时使用全部列；否则先精确匹配，再按前缀匹配
    （例如 wanted 中写“实测值”可命中“实测值1”~“实测值10”）。
    结果保持模板定义的顺序；未命中的 wanted 记入 missing。
    """
    all_columns = [str(c) for c in (all_columns or [])]
    if wanted in (None, "", "all", []):
        return [(i, label) for i, label in enumerate(all_columns)], []
    normalized = [_norm(c) for c in all_columns]
    used = set()
    picked = []
    missing = []
    for raw in wanted:
        target = _norm(raw)
        if not target:
            continue
        idx = None
        for i, label in enumerate(normalized):
            if i not in used and label == target:
                idx = i
                break
        if idx is None:
            for i, label in enumerate(normalized):
                if i not in used and label.startswith(target):
                    idx = i
                    break
        if idx is None:
            missing.append(str(raw))
            continue
        used.add(idx)
        picked.append((idx, all_columns[idx]))
    return picked, missing


def _info_pairs(info):
    """生成表头信息 (标签, 值) 列表。"""
    info = dict(info or {})
    return [
        ("工程名称", info.get("project_name") or ""),
        ("检测编号", info.get("report_no") or ""),
        ("委托单位", info.get("client") or ""),
        ("检测日期", info.get("test_date") or ""),
        ("工程地点", info.get("project_location") or ""),
        ("见证单位", info.get("witness") or ""),
        ("检测依据", info.get("basis") or ""),
        ("检测设备", info.get("equipment") or ""),
    ]


def _add_info_table(doc, info):
    rows = len(_info_pairs(info)) // 2
    table = doc.add_table(rows=rows, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    pairs = _info_pairs(info)
    for r in range(rows):
        for c in range(2):
            idx = r * 2 + c
            if idx >= len(pairs):
                continue
            label, value = pairs[idx]
            label_cell = table.cell(r, c * 2)
            value_cell = table.cell(r, c * 2 + 1)
            _cell_text(label_cell, label, size=9, bold=True)
            _shade_cell(label_cell, "F2F2F2")
            _cell_text(value_cell, value, size=9,
                       align=WD_ALIGN_PARAGRAPH.LEFT)
    doc.add_paragraph()


def _add_data_table(doc, picked, rows):
    n_cols = max(1, len(picked))
    size = _display_width(picked)
    table = doc.add_table(rows=1, cols=n_cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    header = table.rows[0]
    for c, (_idx, label) in enumerate(picked):
        _cell_text(header.cells[c], label, size=size, bold=True)
        _shade_cell(header.cells[c], "D9E2F3")
    _repeat_header(header)

    for row in rows:
        cells = table.add_row().cells
        for c, (idx, _label) in enumerate(picked):
            value = row[idx] if idx < len(row) else ""
            _cell_text(cells[c], value, size=size)
    return table


def _add_signature(doc, info):
    info = dict(info or {})
    doc.add_paragraph()
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    text = "检测人：%s          记录人：%s          校核人：%s          日期：%s" % (
        info.get("tester") or "",
        info.get("writer") or "",
        info.get("checker") or "",
        info.get("report_date") or info.get("test_date") or "",
    )
    run = para.add_run(text)
    _set_run_font(run, size=10)


def _add_footer(doc):
    """页脚：系统生成说明（不依赖域代码）。"""
    section = doc.sections[0]
    footer = section.footer
    para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run("本记录由工程检测harness自动生成")
    _set_run_font(run, size=8)


def _default_output_dir():
    out = resolve_path("original_record", "word", "generated")
    os.makedirs(str(out), exist_ok=True)
    return str(out)


def generate_native_record(definition, sheet_key, columns, rows, info,
                           output_path=None, blank=False):
    """生成一份原生 DOCX 原始记录。

    :param definition: 内置模板定义 dict（见 original_record_templates.py）
    :param sheet_key: 工作表键（写入标题/文件名/备注）
    :param columns: 该检测项目的完整列头
    :param rows: 二维数组数据行
    :param info: 报告抬头（project_name/report_no/client/...）
    :param output_path: 输出路径；None 时落到 original_record/word/generated
    :param blank: True 生成空白模板（不含数据行）
    :return: (生成文件路径, warnings 列表)
    """
    definition = dict(definition or {})
    warnings = []
    rows = [] if blank else _clean_rows(rows)
    picked, missing = _pick_columns(columns, definition.get("columns", "all"))
    if missing:
        warnings.append("模板列未找到，已跳过：%s" % "、".join(missing))
    if not picked:
        all_cols = [str(c) for c in (columns or [])]
        picked = [(i, label) for i, label in enumerate(all_cols)]
        warnings.append("模板未匹配到任何列，已改用该检测项目全部列")

    landscape = definition.get("orientation") == "landscape"
    if definition.get("orientation") in (None, "", "auto"):
        landscape = len(picked) > 10

    doc = Document()
    _page_setup(doc, landscape)

    # 标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(definition.get("name") or "检测原始记录")
    _set_run_font(run, size=16, bold=True)

    # 表头信息
    _add_info_table(doc, info)

    # 数据表
    if blank and not rows:
        # 空白模板给 5 行手写空间
        empty_row = ["" for _ in columns or []]
        rows = [list(empty_row) for _ in range(5)]
    _add_data_table(doc, picked, rows)

    # 备注
    notes = str(definition.get("notes") or "").strip()
    if notes:
        para = doc.add_paragraph()
        run = para.add_run("备注：%s" % notes)
        _set_run_font(run, size=9)

    _add_signature(doc, info)
    _add_footer(doc)

    if not output_path:
        name = definition.get("name") or sheet_key or "检测原始记录"
        serial = info.get("report_no") or info.get("project_name") or "未编号"
        prefix = "空白模板_" if blank else "原始记录_"
        filename = "%s%s_%s_%s.docx" % (
            prefix, _safe_filename(name), _safe_filename(serial, 30),
            datetime.now().strftime("%Y%m%d_%H%M%S"))
        output_path = os.path.join(_default_output_dir(), filename)
    output_path = os.path.abspath(str(output_path))
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    doc.save(output_path)
    return output_path, warnings
