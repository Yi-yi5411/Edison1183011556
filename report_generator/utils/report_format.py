# -*- coding: utf-8 -*-
"""《检测报告》统一排版工具（纯函数，无 Qt 依赖）。

提供页面设置、页脚页码、字体字号、段落格式、表格字体的统一
排版函数；``apply_report_format`` 为一键编排入口，各开关默认
关闭（模板自带排版优先），按需开启，互不耦合。

典型用法::

    from utils.report_format import apply_report_format

    # 只加页脚页码（已有页脚的节自动跳过）
    apply_report_format(doc, page_number_footer=True)

    # 统一页面边距 + 正文/表格字体
    apply_report_format(doc, page_setup=True, fonts=True, table_fonts=True)
"""
import re

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ── 排版规范常量（按需调整，全部函数的默认值来源）──
FONT_SONG = "宋体"          # 正文
FONT_HEI = "黑体"           # 章标题
FONT_KAI = "楷体"           # 引文/批注
FONT_FANGSONG = "仿宋"      # 公文正文
FONT_ASCII = "Times New Roman"  # 西文/数字

SIZE_H1_PT = 16.0           # 三号：章标题（一、工程概况）
SIZE_H2_PT = 14.0           # 四号：节标题
SIZE_BODY_PT = 12.0         # 小四：正文
SIZE_TABLE_PT = 10.5        # 五号：模板表格默认字号（结果表单独用 11pt）
SIZE_FOOTER_PT = 9.0        # 小五：页脚

PAGE_WIDTH_CM = 21.0        # A4 纵向
PAGE_HEIGHT_CM = 29.7
MARGINS_CM = {"top": 2.5, "bottom": 2.5, "left": 3.0, "right": 2.5}

# 章标题识别（"一、工程概况"…"六、检测结论"）
_HEADING_RE = re.compile(r"^[一二三四五六七八九十]+\s*、")

_ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


# ═══════════════════════════════════════════════════════════
#  字体 / 字号
# ═══════════════════════════════════════════════════════════
def set_run_font(run, east_asia=None, ascii_font=None, size_pt=None,
                 bold=None, color=None):
    """设置单个 run 的中英文字体、字号（pt）、加粗与颜色。

    只传入的项才修改；中文字体写入 w:rFonts/@eastAsia，西文写入
    @ascii/@hAnsi，字号同时写 sz 与 szCs（半点值）。
    """
    r_pr = run._element.get_or_add_rPr()
    if east_asia or ascii_font:
        fonts = r_pr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            r_pr.insert(0, fonts)
        if ascii_font:
            fonts.set(qn("w:ascii"), ascii_font)
            fonts.set(qn("w:hAnsi"), ascii_font)
        if east_asia:
            fonts.set(qn("w:eastAsia"), east_asia)
    if size_pt is not None:
        half = str(int(round(size_pt * 2)))
        for tag in ("w:sz", "w:szCs"):
            el = r_pr.find(qn(tag))
            if el is None:
                el = OxmlElement(tag)
                r_pr.append(el)
            el.set(qn("w:val"), half)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def set_paragraph_font(para, east_asia=None, ascii_font=None, size_pt=None,
                       bold=None, color=None):
    """把统一字体应用到段落的全部 run。"""
    for run in para.runs:
        set_run_font(run, east_asia=east_asia, ascii_font=ascii_font,
                     size_pt=size_pt, bold=bold, color=color)


def uniform_table_fonts(table, east_asia=FONT_SONG, ascii_font=FONT_ASCII,
                        size_pt=SIZE_TABLE_PT, bold_first_row=False):
    """统一表格内全部单元格字体（默认五号宋体），可选首行加粗。"""
    for ri, row in enumerate(table.rows):
        for cell in row.cells:
            for para in cell.paragraphs:
                set_paragraph_font(para, east_asia=east_asia,
                                   ascii_font=ascii_font, size_pt=size_pt,
                                   bold=True if (bold_first_row and ri == 0)
                                   else None)


def uniform_fonts(doc, body_east_asia=FONT_SONG, heading_east_asia=FONT_HEI,
                  ascii_font=FONT_ASCII, body_size_pt=SIZE_BODY_PT,
                  heading_size_pt=SIZE_H1_PT, include_tables=False,
                  table_size_pt=SIZE_TABLE_PT):
    """统一全文正文字体字号；"一、二、…"章标题用标题字体加粗。

    include_tables=True 时表格单元格同步统一为表格字号。
    返回处理的段落数（供日志）。
    """
    count = 0
    for para in doc.paragraphs:
        if _HEADING_RE.match(para.text.strip()):
            set_paragraph_font(para, east_asia=heading_east_asia,
                               ascii_font=ascii_font,
                               size_pt=heading_size_pt, bold=True)
        else:
            set_paragraph_font(para, east_asia=body_east_asia,
                               ascii_font=ascii_font, size_pt=body_size_pt)
        count += 1
    if include_tables:
        for table in doc.tables:
            uniform_table_fonts(table, east_asia=body_east_asia,
                                ascii_font=ascii_font, size_pt=table_size_pt)
    return count


# ═══════════════════════════════════════════════════════════
#  段落格式
# ═══════════════════════════════════════════════════════════
def format_paragraph(para, align=None, line_spacing=None, space_before_pt=None,
                     space_after_pt=None, first_line_indent_pt=None,
                     keep_with_next=None):
    """统一段落格式：对齐、行距（倍数或 Pt）、段前/段后距（pt）、首行缩进（pt）。"""
    pf = para.paragraph_format
    if align is not None:
        pf.alignment = _ALIGN_MAP.get(align, align)
    if line_spacing is not None:
        pf.line_spacing = line_spacing
    if space_before_pt is not None:
        pf.space_before = Pt(space_before_pt)
    if space_after_pt is not None:
        pf.space_after = Pt(space_after_pt)
    if first_line_indent_pt is not None:
        pf.first_line_indent = Pt(first_line_indent_pt)
    if keep_with_next is not None:
        pf.keep_with_next = keep_with_next


# ═══════════════════════════════════════════════════════════
#  页面设置 / 页脚
# ═══════════════════════════════════════════════════════════
def set_page_setup(section, margins_cm=None, page_size_cm=None):
    """设置单节的页面尺寸与页边距（cm）；不传的项保持原值。"""
    if page_size_cm:
        section.page_width = Cm(page_size_cm[0])
        section.page_height = Cm(page_size_cm[1])
    if margins_cm:
        section.top_margin = Cm(margins_cm.get("top", 2.5))
        section.bottom_margin = Cm(margins_cm.get("bottom", 2.5))
        section.left_margin = Cm(margins_cm.get("left", 3.0))
        section.right_margin = Cm(margins_cm.get("right", 2.5))


def uniform_page_setup(doc, margins_cm=None, page_size_cm=(PAGE_WIDTH_CM,
                                                           PAGE_HEIGHT_CM)):
    """把全部节统一为相同页面尺寸/边距，返回处理的节数。"""
    n = 0
    for section in doc.sections:
        set_page_setup(section, margins_cm=margins_cm,
                       page_size_cm=page_size_cm)
        n += 1
    return n


def _add_field_run(para, instr):
    """在段落末尾插入 Word 域（PAGE / NUMPAGES）的 run 序列。"""
    def _run(child_tag=None, text=None, **attrs):
        r = OxmlElement("w:r")
        if child_tag:
            el = OxmlElement(child_tag)
            for k, v in attrs.items():
                el.set(qn(k), v)
            if text is not None:
                el.text = text
            r.append(el)
        para._p.append(r)
        return r

    _run("w:fldChar", **{"w:fldCharType": "begin"})
    instr_run = _run("w:instrText", text=" %s " % instr)
    instr_run[0].set(qn("xml:space"), "preserve")
    _run("w:fldChar", **{"w:fldCharType": "separate"})
    _run("w:t", text="1")  # 占位结果，Word 打开时自动刷新
    _run("w:fldChar", **{"w:fldCharType": "end"})


def _footer_text(section):
    """读节的页脚文本（含继承自前一节的内容）；引用异常时返回 None。

    经 Word/WPS COM 回写的文档可能出现 sectPr 页脚引用指向非页脚
    部件的情况（'Part' object has no attribute 'element'），此时
    返回 None 表示"无法读写，调用方跳过"。
    """
    try:
        return " | ".join(
            p.text for p in section.footer.paragraphs if p.text.strip())
    except Exception:
        return None


def set_page_number_footer(section, fmt="第 {PAGE} 页　共 {NUMPAGES} 页",
                           east_asia=FONT_SONG, ascii_font=FONT_ASCII,
                           size_pt=SIZE_FOOTER_PT, overwrite=False):
    """给节页脚添加居中页码域（"第 X 页　共 Y 页"）。

    页脚（含继承内容）已有文字时默认跳过（返回 False），仅
    overwrite=True 才清空重写；链接到前一节的空页脚会先断开
    链接再写入，避免污染共享页脚。
    """
    existing = _footer_text(section)
    if existing is None:
        return False  # 页脚引用异常（COM 回写文档），跳过不处理
    if existing and not overwrite:
        return False
    try:
        footer = section.footer
        if footer.is_linked_to_previous:
            footer.is_linked_to_previous = False
        # 清空现有段落，只留一个
        for p in list(footer.paragraphs)[1:]:
            p._p.getparent().remove(p._p)
        para = footer.paragraphs[0]
        for run in list(para.runs):
            run._element.getparent().remove(run._element)
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        def _text(text):
            if not text:
                return
            run = para.add_run(text)
            set_run_font(run, east_asia=east_asia, ascii_font=ascii_font,
                         size_pt=size_pt)

        parts = fmt.split("{PAGE}")
        _text(parts[0])
        _add_field_run(para, "PAGE")
        rest = "{PAGE}".join(parts[1:]).split("{NUMPAGES}")
        _text(rest[0])
        _add_field_run(para, "NUMPAGES")
        _text(rest[1] if len(rest) > 1 else "")
        return True
    except Exception:
        return False


def uniform_page_number_footers(doc, fmt="第 {PAGE} 页　共 {NUMPAGES} 页",
                                skip_first=True, **kw):
    """给全文各节统一添加页码页脚；已有页脚的节自动跳过。

    skip_first=True 时跳过第一节（封面通常不编页码）。
    返回实际添加页码的节数。
    """
    n = 0
    for i, section in enumerate(doc.sections):
        if skip_first and i == 0:
            continue
        if set_page_number_footer(section, fmt=fmt, **kw):
            n += 1
    return n


# ═══════════════════════════════════════════════════════════
#  一键编排 / 排版概览
# ═══════════════════════════════════════════════════════════
def apply_report_format(doc, page_setup=False, page_number_footer=False,
                        fonts=False, table_fonts=False, margins_cm=None):
    """一键统一排版；各开关默认关闭（不改动模板自带排版）。

    :param page_setup: 统一页面为 A4 + 标准边距（margins_cm 可覆盖）
    :param page_number_footer: 给无页脚的节添加"第 X 页　共 Y 页"
    :param fonts: 统一正文字体字号（章标题黑体三号加粗）
    :param table_fonts: 统一表格字体为五号宋体
    :return: 已应用的排版项描述列表（可写日志）
    """
    applied = []
    if page_setup:
        n = uniform_page_setup(doc, margins_cm=margins_cm or MARGINS_CM)
        applied.append(f"页面设置×{n}节")
    if page_number_footer:
        n = uniform_page_number_footers(doc)
        applied.append(f"页脚页码×{n}节")
    if fonts:
        n = uniform_fonts(doc)
        applied.append(f"正文/标题字体×{n}段")
    if table_fonts:
        for table in doc.tables:
            uniform_table_fonts(table)
        applied.append(f"表格字体×{len(doc.tables)}表")
    return applied


def describe_format(doc):
    """返回当前文档排版概览（节/页面/边距/页脚/首段字体），便于人工核对。"""
    lines = []
    for i, s in enumerate(doc.sections):
        footer_txt = _footer_text(s)
        if footer_txt is None:
            footer_txt = "<页脚引用异常，跳过>"
        lines.append(
            "节%d: %.1fx%.1fcm 边距上%.2f下%.2f左%.2f右%.2f 页脚=%r"
            % (i, s.page_width.cm, s.page_height.cm, s.top_margin.cm,
               s.bottom_margin.cm, s.left_margin.cm, s.right_margin.cm,
               footer_txt))
    return lines
