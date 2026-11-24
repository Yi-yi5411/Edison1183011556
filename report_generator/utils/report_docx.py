# -*- coding: utf-8 -*-
"""《检测报告》底层 docx 操作原语（纯函数，无 Qt 依赖）。

供 report_chapters.py（章节构建）与 word_report.py（编排）共用的
非耦合工具层：章节拼装、占位符替换、封面/首页回填、结果一览表
列匹配与填充、结论句插入、COM 页数后处理。

注意约定：
  - ``_append_chapter`` 是 deepcopy，必须先填充源 Document 再拼装；
  - ``_replace_in_paragraph`` 的 mapping key 是待替换的完整子串，
    {{占位符}}名由调用处自行包 ``{{%s}}`` 后再传。
"""
import difflib
import re
from copy import deepcopy

from docx import Document
from docx.document import Document as DocumentObj
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph

# 封面人员/编号字段的归一化标签 → 抬头信息键
_PERSONNEL_LABELS = {
    "报告编号": "report_no",
    "检测人": "tester",
    "报告编写人": "writer",
    "复核人": "checker",
    "审核人": "reviewer",
    "批准人": "approver",
}
# 首页信息表行标签 → 抬头信息键
_HOME_INFO_LABELS = {
    "工程名称": "project_name",
    "工程地点": "project_location",
    "委托单位": "client",
    "见证单位": "witness",
    "检测日期": "test_date",
    "建设单位": "construction_unit",
    "施工单位": "contractor",
    "设计单位": "design_unit",
    "监理单位": "supervision_unit",
    "勘察单位": "survey_unit",
    "结构类型": "structure_type",
    "建筑面积": "building_area",
    "层数": "floor_count",
    "建筑高度": "building_height",
    "开工日期": "start_date",
    "竣工日期": "completion_date",
    "检测目的": "inspection_purpose",
}

_FULLWIDTH = {"（": "(", "）": ")", "：": ":", "，": ",", "；": ";"}
# 允许录入但报告一览表模板不一定包含的列（不产生“未写入”警告）
_OPTIONAL_GUI_LABELS = {"楼层"}


def _norm(text):
    """表头归一化：全角→半角、去空白、去括号内单位。"""
    s = str(text or "")
    for a, b in _FULLWIDTH.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\([^()]*\)", "", s)
    s = s.replace("/", "").replace("\\", "").replace("、", "")
    return s


# ═══════════════════════════════════════════════════════════
#  章节拼装
# ═══════════════════════════════════════════════════════════
def _merge_missing_styles(base_doc, src_doc):
    """把源文档中基准文档缺失的 style 定义补进基准，避免样式漂移。"""
    base_ids = {
        s.get(qn("w:styleId"))
        for s in base_doc.styles.element.findall(qn("w:style"))
    }
    for style in src_doc.styles.element.findall(qn("w:style")):
        if style.get(qn("w:styleId")) not in base_ids:
            base_doc.styles.element.append(deepcopy(style))


def _drop_trailing_empty(children):
    """返回去掉尾部连续空段落后的元素列表（防止与下一章段前分页叠加出空白页）。"""
    out = list(children)
    while out:
        el = out[-1]
        if el.tag != qn("w:p"):
            break
        text = "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()
        if text or el.findall(".//" + qn("w:drawing")):
            break
        out.pop()
    return out


def _strip_empty_paragraphs(doc):
    """删除章节模板中的纯空段落，避免标题与正文被空行/空页拆开。"""
    for para in list(doc.paragraphs):
        if para.text.strip():
            continue
        if para._p.findall(".//" + qn("w:drawing")):
            continue
        p_pr = para._p.find(qn("w:pPr"))
        if p_pr is not None:
            pgb = p_pr.find(qn("w:pageBreakBefore"))
            if pgb is not None and pgb.get(qn("w:val"), "1") not in ("0", "false"):
                continue
            if p_pr.find(qn("w:sectPr")) is not None:
                continue
        if any(br.get(qn("w:type")) == "page"
               for br in para._p.iter(qn("w:br"))):
            continue
        parent = para._p.getparent()
        if parent is not None:
            parent.remove(para._p)


def _trim_base_tail(doc):
    """清理基准文档（封面）尾部连续空段。"""
    body = doc.element.body
    kids = [c for c in body if c.tag != qn("w:sectPr")]
    keep = _drop_trailing_empty(kids)
    for el in kids:
        if el not in keep:
            body.remove(el)


def _append_chapter(base_doc, chapter, page_break=True, keep_section_break=False):
    """把章节文档的 body 子元素（跳过顶层 sectPr）追加到基准文档末尾。

    keep_section_break=True 用于“首页”章节：保留其分节符，使正文页码从
    首页重新从 1 开始；同时去掉模板自带的页眉页脚引用，改为继承前一节，
    避免出现空白页眉页脚。
    """
    src = chapter if isinstance(chapter, DocumentObj) else Document(str(chapter))
    _merge_missing_styles(base_doc, src)
    body = base_doc.element.body
    sect_pr = body.find(qn("w:sectPr"))
    appended_first_para = None
    children = _drop_trailing_empty(
        [c for c in src.element.body if c.tag != qn("w:sectPr")])
    for el in children:
        el = deepcopy(el)
        # 章节模板里的分节符默认不复制；首页章节例外，保留一个干净的
        # 分节符（去掉模板页眉页脚引用），让正文页码可以从 1 开始。
        for para in [el] + list(el.iter(qn("w:p"))):
            p_pr = para.find(qn("w:pPr"))
            if p_pr is None:
                continue
            for sect in list(p_pr.findall(qn("w:sectPr"))):
                if keep_section_break:
                    for ref in list(sect):
                        if ref.tag in (qn("w:headerReference"),
                                       qn("w:footerReference")):
                            sect.remove(ref)
                else:
                    p_pr.remove(sect)
        if sect_pr is not None:
            sect_pr.addprevious(el)
        else:
            body.append(el)
        if appended_first_para is None and el.tag == qn("w:p"):
            appended_first_para = el
    if page_break and appended_first_para is not None:
        p_pr = appended_first_para.find(qn("w:pPr"))
        if p_pr is None:
            p_pr = OxmlElement("w:pPr")
            appended_first_para.insert(0, p_pr)
        if p_pr.find(qn("w:pageBreakBefore")) is None:
            p_pr.insert(0, OxmlElement("w:pageBreakBefore"))
    return src


# ═══════════════════════════════════════════════════════════
#  占位符 / 文本写入
# ═══════════════════════════════════════════════════════════
def _replace_in_paragraph(paragraph, mapping):
    """跨 run 替换：key 为待替换的完整子串，整段合并文本后重写，保留首 run 格式。"""
    full = "".join(r.text or "" for r in paragraph.runs)
    new = full
    for key, value in mapping.items():
        new = new.replace(key, str(value))
    if new == full:
        return False
    for i, run in enumerate(paragraph.runs):
        run.text = new if i == 0 else ""
    return True


def _replace_placeholders(doc, mapping):
    """替换全文（正文段落 + 各级表格内段落）中的 {{占位符}}。"""
    tokens = {("{{%s}}" % key): value for key, value in mapping.items()}
    for para in doc.paragraphs:
        _replace_in_paragraph(para, tokens)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _replace_in_paragraph(para, tokens)


def _set_run_font(run, size=12, name="宋体"):
    """设置 run 字号与中英文字体（含东亚字体）。"""
    run.font.name = name
    run.font.size = Pt(size)
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    r_fonts.set(qn("w:eastAsia"), name)


def _format_report_value(label, value):
    """结果表数值格式化：强度 1 位、偏差/均值 2 位、合格率/降低率为百分比。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("#"):
        return ""
    # 表头已经带单位时，数据里重复的 kN 去掉，避免“检验荷载（kN）”下再写“7.3 kN”
    if "kn" in str(label).lower() and text.lower().endswith("kn"):
        text = text[:-2].strip()
    try:
        num = float(text)
    except (TypeError, ValueError):
        return text
    label_n = _norm(label)
    # 宽表里的单个偏差列用整数（5 / -7），避免 1cm 列宽被 "5.00" 撑裂
    if re.match(r"^(实测)?偏差值\d+$", label_n):
        if abs(num - round(num)) < 1e-9:
            return str(int(round(num)))
        return "%.1f" % num
    if "降低率" in label_n:
        if 0 <= num <= 1:
            return "%.2f%%" % (num * 100.0)
        return "%.2f%%" % num
    if "合格点率" in label_n or "合格率" in label_n:
        if 0 <= num <= 1:
            return "%.2f%%" % (num * 100.0)
        return "%.2f%%" % num
    if "标准差" in label_n:
        return "%.2f" % num
    if "荷载" in label_n:
        return "%.1f" % num
    if "强度" in label_n or "推定值" in label_n:
        return "%.1f" % num
    if ("偏差" in label_n or "平均值" in label_n or "均值" in label_n
            or "截面积" in label_n or "荷载" in label_n):
        return "%.2f" % num
    return text


def _set_cell_text(cell, value, size=None):
    """写单元格文本，数据行收敛为单行，尽量保留原格式。"""
    value = _normalize_cell_text(value) if value is not None else ""
    if not cell.paragraphs:
        cell.text = value
        if size and cell.paragraphs and cell.paragraphs[0].runs:
            _set_run_font(cell.paragraphs[0].runs[0], size)
        return
    para = cell.paragraphs[0]
    if para.runs:
        para.runs[0].text = value
        if size:
            _set_run_font(para.runs[0], size)
        for run in para.runs[1:]:
            run.text = ""
    else:
        run = para.add_run(value)
        if size:
            _set_run_font(run, size)


def normalize_table_paragraphs(doc):
    """报告落盘前清掉所有表格单元格里的空段落，避免多行空白。"""
    for table in doc.tables:
        _strip_empty_table_paragraphs(table)


def _clean_template_notes(doc):
    """删除模板自带的填写提示行（如"（如无必备参数，删掉此行）"）。"""
    for para in list(doc.paragraphs):
        if "如无必备参数" in para.text or "删掉此行" in para.text:
            para._p.getparent().remove(para._p)


# ═══════════════════════════════════════════════════════════
#  封面 / 首页回填
# ═══════════════════════════════════════════════════════════
def _fill_cover_personnel(doc, report_info):
    """封面"报告编号："等段落按归一化标签匹配后追加值。"""
    for para in doc.paragraphs:
        text = "".join(r.text or "" for r in para.runs)
        compact = re.sub(r"\s+", "", text).replace("：", ":")
        for label, key in _PERSONNEL_LABELS.items():
            value = str(report_info.get(key) or "").strip()
            if not value or not compact.startswith(label + ":"):
                continue
            # 标签冒号后已有内容则不覆盖
            rest = compact[len(label) + 1:].strip()
            if rest:
                break
            para.runs[-1].text = para.runs[-1].text.rstrip() + value
            break


def _fill_home_info_table(table, report_info):
    """首页信息表按行标签回填右侧单元格。"""
    for row in table.rows:
        cells = row.cells
        if len(cells) < 2:
            continue
        label = _norm(cells[0].text)
        key = _HOME_INFO_LABELS.get(label)
        if not key:
            continue
        value = str(report_info.get(key) or "").strip()
        if value:
            _set_cell_text(cells[1], value)


# ═══════════════════════════════════════════════════════════
#  结果一览表填充
# ═══════════════════════════════════════════════════════════
def _table_col_labels(table, header_rows):
    """按列归并多行表头文本（去纵向合并的重复段）。"""
    labels = []
    for c in range(len(table.columns)):
        parts = []
        for r in range(header_rows):
            try:
                txt = table.cell(r, c).text
            except IndexError:
                txt = ""
            txt = txt.replace("\n", "").strip()
            if txt and txt not in parts:
                parts.append(txt)
        labels.append("".join(parts))
    return labels


def _match_columns(tpl_labels, gui_cols, aliases):
    """两级列匹配：归一化精确/别名 → difflib 相似度兜底。

    difflib 阶段只考虑尚未被占用的录入列，避免同一录入列被多个
    模板列重复引用（如"构件编号"误配"构件轴号"）。
    返回 (col_map{tpl_idx: gui_idx}, unmatched_tpl_labels, unused_gui_idxs)。
    """
    gui_norm = [_norm(c) for c in gui_cols]
    col_map = {}
    unmatched = []
    used = set()

    # 别名键/值也归一化，便于自定义模板 manifest 直接写带单位的中文表头
    norm_aliases = {}
    for key, values in (aliases or {}).items():
        nk = _norm(key)
        if not nk:
            continue
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple)):
            values = [values]
        norm_aliases[nk] = [
            _norm(v) for v in values if str(v or "").strip()]

    def find_free_exact(target):
        for gi, gn in enumerate(gui_norm):
            if gn and gn == target and gi not in used:
                return gi
        return None

    # 第一阶段：精确 + 别名
    pending = []
    for ti, label in enumerate(tpl_labels):
        nl = _norm(label)
        gi = find_free_exact(nl)
        if gi is None:
            for alias in norm_aliases.get(nl, []):
                gi = find_free_exact(alias)
                if gi is not None:
                    break
        if gi is not None:
            col_map[ti] = gi
            used.add(gi)
        else:
            pending.append((ti, label))

    # 第二阶段：difflib 兜底，候选仅为未占用列
    free = [(gi, gn) for gi, gn in enumerate(gui_norm) if gn and gi not in used]
    for ti, label in pending:
        nl = _norm(label)
        gi = None
        if nl and free:
            close = difflib.get_close_matches(
                nl, [gn for _gi, gn in free], n=1, cutoff=0.6)
            if close:
                gi = next(g for g, gn in free if gn == close[0])
        if gi is not None:
            col_map[ti] = gi
            used.add(gi)
            free = [(g, gn) for g, gn in free if g != gi]
        else:
            unmatched.append(label)
    return col_map, unmatched, sorted(set(range(len(gui_cols))) - used)


def _result_table_font_size(table):
    """取模板中出现最多的正文字号；没有显式字号时用 11pt。"""
    sizes = []
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    if run.font.size is not None:
                        try:
                            sizes.append(round(float(run.font.size.pt), 1))
                        except (TypeError, ValueError):
                            pass
    if not sizes:
        return 11.0
    counts = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    return max(counts, key=counts.get)


def _template_table_font_name(table):
    """取模板中出现最多的中文字体，保留原模板字体风格。"""
    names = []
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    r_pr = run._element.find(qn("w:rPr"))
                    if r_pr is None:
                        continue
                    r_fonts = r_pr.find(qn("w:rFonts"))
                    if r_fonts is None:
                        continue
                    name = r_fonts.get(qn("w:eastAsia")) or r_fonts.get(qn("w:ascii"))
                    if name:
                        names.append(name)
    if not names:
        return "宋体"
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get)


def _normalize_cell_text(text, header=False):
    """单元格文本收敛：表头最多一个换行，数据行一律单行。"""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t\u00a0]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    if header:
        value = re.sub(r"\n{2,}", "\n", value)
    else:
        value = re.sub(r"\n+", " ", value)
    return value.strip()


def _set_table_cell_margins(table, left_cm=0.08, right_cm=0.08):
    """压缩结果表左右单元格边距，给钢保/间距的窄列腾空间。"""
    tbl_pr = table._tbl.tblPr
    if tbl_pr is None:
        return
    mar = tbl_pr.find(qn("w:tblCellMar"))
    if mar is None:
        mar = OxmlElement("w:tblCellMar")
        tbl_pr.append(mar)
    for tag, cm in (("w:left", left_cm), ("w:right", right_cm)):
        el = mar.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            mar.append(el)
        el.set(qn("w:w"), str(int(cm * 567)))
        el.set(qn("w:type"), "dxa")


def fit_result_table_width(table, target_cm):
    """按目标宽度等比缩放列宽（用于 A4 纵向结果表页）。"""
    if not table.columns:
        return
    current = [c.width.cm if c.width else target_cm / len(table.columns)
               for c in table.columns]
    total = sum(current) or target_cm
    widths = [target_cm * w / total for w in current]
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, width in enumerate(widths):
        table.columns[i].width = Cm(width)
        for cell in table.columns[i].cells:
            cell.width = Cm(width)
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(int(target_cm * 567)))
    tbl_w.set(qn("w:type"), "dxa")


def _apply_result_table_fonts(table, header_rows, size, font_name="宋体"):
    """统一结果表字体、字号、居中、行距；表头加粗，数据不加粗。"""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    seen_cells = set()
    for ri, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(OxmlElement("w:cantSplit"))
        if ri < header_rows and tr_pr.find(qn("w:tblHeader")) is None:
            tr_pr.append(OxmlElement("w:tblHeader"))
        for cell in row.cells:
            key = id(cell._tc)
            if key not in seen_cells:
                seen_cells.add(key)
                # 数据行模板常带多个空段落（例如设计等级合并列）；删空段落，
                # 但不动表头模板的换行和文字。
                if ri >= header_rows:
                    for para in list(cell.paragraphs[1:]):
                        if not para.text.strip():
                            para._element.getparent().remove(para._element)
                elif len(cell.paragraphs) > 1:
                    # 表头模板常把“芯样砼/抗压强度/测试值/（MPa）”拆成多个段落，
                    # 合并为一个段落，由列宽自动换行，避免单元格里多个换行符。
                    joined = "".join(part.text.strip() for part in cell.paragraphs if part.text.strip())
                    if joined:
                        _set_cell_text(cell, joined, size=size)
                        for para in list(cell.paragraphs[1:]):
                            para._element.getparent().remove(para._element)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for para in cell.paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pf = para.paragraph_format
                pf.space_before = Pt(0)
                pf.space_after = Pt(0)
                pf.line_spacing = 1.0
                for run in para.runs:
                    _set_run_font(run, size, font_name)
                    run.bold = bool(ri < header_rows)


def _strip_empty_table_paragraphs(table):
    """删除单元格中的空段落，避免合并后出现一串换行。"""
    seen = set()
    for row in table.rows:
        for cell in row.cells:
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            paragraphs = cell.paragraphs
            for para in list(paragraphs[1:]):
                if not para.text.strip():
                    para._element.getparent().remove(para._element)


def _tr_grid_span(tr):
    """返回表格行首单元格的 gridSpan（用于识别整行合并的备注行）。"""
    tc = tr.find(qn("w:tc"))
    if tc is None:
        return 1
    tc_pr = tc.find(qn("w:tcPr"))
    if tc_pr is None:
        return 1
    gs = tc_pr.find(qn("w:gridSpan"))
    if gs is None:
        return 1
    try:
        return int(gs.get(qn("w:val")) or 1)
    except (TypeError, ValueError):
        return 1


_MERGE_LABELS = {
    "构件编号", "构件名称", "构件位置及名称", "构件名称及轴号",
    "构件轴号", "构件轴线编号", "轴线编号", "设计强度等级", "设计等级",
    "合格点率", "标准要求", "批次", "楼栋", "楼层",
    "设计值", "钢筋牌号", "批混凝土强度推定值",
}


def _auto_merge_result_table(table, header_rows, font_size=11.0):
    """智能纵向合并 Word 结果表的分组列。

    与表格页的智能合并保持同一口径：
    - 空值按列向下继承（批次/位置/轴线通常只在首行写一次）；
    - 每列独立按“连续相同值”分段合并，不再用一个构件分组去限制
      批次、设计等级、批推定值等整批列；
    - 兼容多行表头、整行备注页脚，以及 25 行以上长表。
    """
    ncols = len(table.columns)
    if ncols < 2:
        return
    all_rows = table.rows
    footer_start = len(all_rows)
    for i in range(header_rows, len(all_rows)):
        if _tr_grid_span(all_rows[i]._tr) >= ncols:
            footer_start = i
            break
    data_start, data_end = header_rows, footer_start - 1
    if data_end <= data_start:
        return
    labels = _table_col_labels(table, header_rows)
    merge_cols = [i for i, label in enumerate(labels)
                  if _norm(label) in _MERGE_LABELS]
    for ci in merge_cols:
        raw = [str(table.cell(r, ci).text).strip()
               for r in range(data_start, data_end + 1)]
        effective = []
        last = ""
        for cell_text in raw:
            if cell_text:
                last = cell_text
            effective.append(last)

        start = 0
        while start < len(effective):
            value = effective[start]
            end = start
            while (end + 1 < len(effective)
                   and effective[end + 1] == value
                   and value):
                end += 1
            if end > start:
                first_row = data_start + start
                last_row = data_start + end
                first_cell = table.cell(first_row, ci)
                last_cell = table.cell(last_row, ci)
                _set_cell_text(first_cell, value, size=font_size)
                for r in range(first_row + 1, last_row + 1):
                    cell = table.cell(r, ci)
                    if cell._tc is not first_cell._tc:
                        _set_cell_text(cell, "", size=font_size)
                try:
                    first_cell.merge(last_cell)
                except Exception:  # noqa: BLE001
                    pass
            start = end + 1

def _fill_result_table(table, rows, gui_cols, header_rows, aliases, warnings,
                       sheet_key):
    """把 GUI 行数据写入模板表格（不处理合并，行不足自动扩展）。"""
    table.autofit = False
    _set_table_cell_margins(table)
    font_size = _result_table_font_size(table)
    tpl_labels = _table_col_labels(table, header_rows)
    col_map, unmatched, unused = _match_columns(tpl_labels, gui_cols, aliases)

    # 模板把“构件名称及轴号”合并成一列时，用录入的“构件位置及名称 + 轴线编号”合成
    gui_norm = [_norm(c) for c in gui_cols]
    def _find_gui(*names):
        for name in names:
            target = _norm(name)
            for i, gn in enumerate(gui_norm):
                if gn == target:
                    return i
        return None

    pos_idx = _find_gui("构件位置及名称", "构件名称")
    axis_idx = _find_gui("轴线编号", "构件轴线编号", "构件轴号")
    combo_cols = [ti for ti, label in enumerate(tpl_labels)
                  if _norm(label) == "构件名称及轴号"]
    if combo_cols and pos_idx is not None:
        if len(combo_cols) >= 2 and axis_idx is not None:
            # 模板把“构件名称及轴号”横跨两列：分别写名称/轴号，避免两列重复同一串
            col_map[combo_cols[0]] = pos_idx
            col_map[combo_cols[1]] = axis_idx
        else:
            for ti in combo_cols:
                col_map[ti] = ("composite", pos_idx, axis_idx)
        unmatched = [u for u in unmatched if _norm(u) != "构件名称及轴号"]
    used = set()
    for value in col_map.values():
        if isinstance(value, tuple):
            used.update(i for i in value[1:] if i is not None)
        elif isinstance(value, int):
            used.add(value)
    unused = [i for i in range(len(gui_cols)) if i not in used]

    if unmatched:
        warnings.append(
            f"{sheet_key}: 模板列未匹配到录入列（留空）：%s"
            % "、".join(unmatched))
    unused_required = [i for i in unused
                       if _norm(gui_cols[i]) not in _OPTIONAL_GUI_LABELS]
    if unused_required:
        warnings.append(
            f"{sheet_key}: 以下录入列未写入报告（模板中无对应列）：%s"
            % "、".join(str(gui_cols[i]) for i in unused_required))

    # 整行合并的备注/说明行不是数据行：先摘除，填完数据再放回末尾
    tbl = table._tbl
    ncols = len(table.columns)
    all_trs = list(tbl.findall(qn("w:tr")))[header_rows:]
    footer_trs = [tr for tr in all_trs if _tr_grid_span(tr) >= ncols]
    data_trs = [tr for tr in all_trs if tr not in footer_trs]
    for tr in footer_trs:
        tbl.remove(tr)
    need = len(rows)
    while len(data_trs) < need:
        new_tr = deepcopy(data_trs[-1]) if data_trs else None
        if new_tr is None:
            break
        tbl.append(new_tr)
        data_trs.append(new_tr)
    while len(data_trs) > need:
        tbl.remove(data_trs.pop())

    # 模板数据行可能带纵向合并（如截面尺寸表首列把多行并成一格），
    # 逐行写值时先拆开 continue 单元格，否则后写的值会覆盖前面所有行。
    for tr in data_trs:
        for tc in tr.tc_lst:
            tc_pr = tc.tcPr
            if tc_pr is None:
                continue
            v_merge = tc_pr.find(qn("w:vMerge"))
            if v_merge is not None and (v_merge.get(qn("w:val")) or "continue") == "continue":
                tc_pr.remove(v_merge)

    for ri, row_data in enumerate(rows):
        cells = table.rows[header_rows + ri].cells
        for ti, gi in col_map.items():
            if ti >= len(cells):
                continue
            if isinstance(gi, tuple):
                parts = []
                for idx in gi[1:]:
                    if idx is not None and idx < len(row_data):
                        text = str(row_data[idx]).strip()
                        if text:
                            parts.append(text)
                _set_cell_text(cells[ti], _format_report_value(
                    tpl_labels[ti], " ".join(parts)), size=font_size)
            elif gi < len(row_data):
                _set_cell_text(cells[ti], _format_report_value(
                    tpl_labels[ti], row_data[gi]), size=font_size)

    # 钢筋间距模板带“结论”列，按方向平均偏差补“符合规范/不符合规范”
    if sheet_key.startswith(("现浇板钢筋间距", "剪力墙构件钢筋间距")):
        conclusion_ti = next((ti for ti, label in enumerate(tpl_labels)
                              if _norm(label) == "结论"), None)
        dev_gi = next((i for i, label in enumerate(gui_cols)
                       if _norm(label) in ("偏差值平均值", "实测偏差平均值")), None)
        if conclusion_ti is not None and dev_gi is not None:
            for ri, row_data in enumerate(rows):
                try:
                    value = float(str(row_data[dev_gi]).strip())
                except (IndexError, TypeError, ValueError):
                    continue
                text = "符合规范" if -10.0 <= value <= 10.0 else "不符合规范"
                cells = table.rows[header_rows + ri].cells
                if conclusion_ti < len(cells):
                    _set_cell_text(cells[conclusion_ti], text, size=font_size)
            unmatched = [u for u in unmatched if _norm(u) != "结论"]

    for tr in footer_trs:
        tbl.append(tr)
    _auto_merge_result_table(table, header_rows, font_size)
    _apply_result_table_fonts(table, header_rows, font_size, _template_table_font_name(table))
    _strip_empty_table_paragraphs(table)


def _clean_rows(rows):
    """过滤整行全空的行。"""
    return [r for r in rows
            if any(str(v).strip() for v in r)]


# ═══════════════════════════════════════════════════════════
#  检测内容清单 / 结论
# ═══════════════════════════════════════════════════════════
def _format_cn_date(value):
    """把 2026-11-10 / 2026/11/10 转成 2026年11月10日。"""
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", text)
    if match:
        return "%s年%s月%s日" % (
            match.group(1), int(match.group(2)), int(match.group(3)))
    return text


def _fill_test_date(src, test_date):
    """替换“五、检测结果”概述中的检测日期占位；支持单日或日期区间。"""
    raw = str(test_date or "").strip()
    if not raw:
        return
    parts = re.split(r"\s*[~～至]\s*", raw, maxsplit=1)
    if len(parts) == 2:
        text = "%s~%s" % (_format_cn_date(parts[0]),
                          _format_cn_date(parts[1]))
    else:
        text = _format_cn_date(raw)
    pat = re.compile(r"xxx年xxx月xxx日[~～\-—]{0,3}xxx日")
    for para in src.paragraphs:
        full = "".join(r.text or "" for r in para.runs)
        match = pat.search(full)
        if match:
            _replace_in_paragraph(para, {match.group(): text})


def append_body_paragraph(doc, text, bold=False, indent=True, size=14):
    """向正文追加 14pt 宋体段落（首行缩进 2 字符）。"""
    para = doc.add_paragraph()
    run = para.add_run(str(text))
    _set_run_font(run, size)
    run.bold = bool(bold)
    pf = para.paragraph_format
    pf.first_line_indent = Pt(size * 2) if indent else Pt(0)
    pf.line_spacing = Pt(24)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    return para


_TOC_CHAPTERS = [
    ("首  页", "首页", "_TocHome"),
    ("一、工程概况", "一、工程概况", "_TocOverview"),
    ("二、主要检测依据", "二、主要检测依据", "_TocBasis"),
    ("三、主要检测设备", "三、主要检测设备", "_TocEquipment"),
    ("四、检测内容", "四、检测内容", "_TocContent"),
    ("五、检测结果", "五、检测结果", "_TocResults"),
    ("六、检测结论", "六、检测结论", "_TocConclusion"),
]


def split_section_before_home(doc, start=1):
    """在“首  页”前插入分节符，并让首页所在节从第 1 页开始。"""
    from docx.oxml import OxmlElement
    body = doc.element.body
    children = list(body)
    home_index = None
    for index, el in enumerate(children):
        if el.tag != qn("w:p"):
            continue
        text = "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()
        if text == "首  页":
            home_index = index
            break
    if home_index is None:
        return False
    next_sect = None
    for el in children[home_index + 1:]:
        if el.tag != qn("w:p"):
            continue
        p_pr = el.find(qn("w:pPr"))
        if p_pr is not None and p_pr.find(qn("w:sectPr")) is not None:
            next_sect = p_pr.find(qn("w:sectPr"))
            break
    if next_sect is None:
        return False
    # 复制一个分节符，结束“敬告页”所在节；首页进入新节
    break_p = OxmlElement("w:p")
    p_pr = OxmlElement("w:pPr")
    sect = deepcopy(next_sect)
    for pgn in list(sect.findall(qn("w:pgNumType"))):
        sect.remove(pgn)
    for typ in list(sect.findall(qn("w:type"))):
        sect.remove(typ)
    type_el = OxmlElement("w:type")
    type_el.set(qn("w:val"), "nextPage")
    sect.append(type_el)
    p_pr.append(sect)
    break_p.append(p_pr)
    children[home_index].addprevious(break_p)
    # 原“首页/TOC”节从 1 开始；后续 TOC/正文节继续编号
    pgn = next_sect.find(qn("w:pgNumType"))
    if pgn is None:
        pgn = OxmlElement("w:pgNumType")
        next_sect.append(pgn)
    pgn.set(qn("w:start"), str(int(start)))
    return True


def adopt_template_footer(doc, section_index, template_path):
    """把正文模板的页脚（含 PAGE/SECTIONPAGES 域）复制到指定节。"""
    src = Document(str(template_path))
    if not src.sections:
        return False
    source = src.sections[0].footer
    target = doc.sections[section_index].footer
    target.is_linked_to_previous = False
    for child in list(target._element):
        target._element.remove(child)
    for child in source._element:
        target._element.append(deepcopy(child))
    # 模板原来用 SECTIONPAGES（本节页数）；多节报告中会变成“共1页”，
    # 改为 NUMPAGES，使所有页脚的“共 X 页”与全文页数一致。
    for instr in target._element.iter(qn("w:instrText")):
        if "SECTIONPAGES" in (instr.text or ""):
            instr.text = " NUMPAGES \\* MERGEFORMAT "
    return True


def set_home_page_start(doc, start=1):
    """让“首  页”所在节从第 1 页开始，封面/敬告页不参与正文页码。"""
    if len(doc.sections) < 2:
        return False
    section = doc.sections[1]
    pgn = section._sectPr.find(qn("w:pgNumType"))
    if pgn is None:
        pgn = OxmlElement("w:pgNumType")
        section._sectPr.append(pgn)
    pgn.set(qn("w:start"), str(int(start)))
    return True


def add_toc_page_fields(doc):
    """给目录条目加 PAGEREF 域，并由 Word 更新为真实页码。"""
    bookmark_ids = 9000
    for heading, toc_prefix, bookmark in _TOC_CHAPTERS:
        target = None
        toc = None
        for para in doc.paragraphs:
            text = para.text.strip()
            if (text == heading
                    or (text.startswith(heading) and len(text) <= 20
                        and "…" not in text and "..." not in text)):
                target = para
                break
        for para in doc.paragraphs:
            text = para.text.strip()
            if text.startswith(toc_prefix) and "…" in text:
                toc = para
                break
        if target is None or toc is None:
            continue
        bookmark_ids += 1
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_ids))
        start.set(qn("w:name"), bookmark)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(bookmark_ids))
        p_pr = target._p.find(qn("w:pPr"))
        target._p.insert(1 if p_pr is not None else 0, start)
        target._p.append(end)
        toc.add_run("  ")
        fld = OxmlElement("w:fldSimple")
        fld.set(qn("w:instr"), " PAGEREF %s \\h " % bookmark)
        run = OxmlElement("w:r")
        text = OxmlElement("w:t")
        text.text = "1"
        run.append(text)
        fld.append(run)
        toc._p.append(fld)


def fill_home_conclusion(doc, sentences):
    """把最终检测结论写入首页表格的“检测结论”行。"""
    for table in doc.tables:
        for row in table.rows:
            if not row.cells:
                continue
            if "检测结论" not in row.cells[0].text:
                continue
            cell = row.cells[0]
            paras = list(cell.paragraphs)
            if not paras:
                label = cell.add_paragraph()
            else:
                label = paras[0]
                for para in paras[1:]:
                    para._p.getparent().remove(para._p)
            if label.runs:
                label.runs[0].text = "检测结论："
                for run in label.runs[1:]:
                    run.text = ""
            else:
                label.add_run("检测结论：")
            for sentence in sentences or []:
                para = cell.add_paragraph()
                run = para.add_run(str(sentence))
                _set_run_font(run, 14)
                pf = para.paragraph_format
                pf.space_before = Pt(0)
                pf.space_after = Pt(0)
                pf.line_spacing = 1.2
                pf.first_line_indent = Pt(0)
            return True
    return False


def _append_content_list(doc, checked_order):
    """四、检测内容末尾追加本次检测项目清单（模板正文已自带引导句）。"""
    try:
        from report_generator.utils.report_items import content_groups
    except ImportError:  # 以 report_generator/ 为工作目录导入时
        from utils.report_items import content_groups
    for category_no, group in enumerate(content_groups(checked_order), 1):
        category_para = doc.add_paragraph()
        category_run = category_para.add_run(
            f"{category_no}．{group['category']}")
        _set_run_font(category_run, 14)
        category_run.bold = True
        pf = category_para.paragraph_format
        pf.first_line_indent = Pt(28)
        pf.line_spacing = Pt(24)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

        for sub_no, name in enumerate(group.get("items") or [], 1):
            para = doc.add_paragraph()
            _set_run_font(para.add_run(
                f"{category_no}.{sub_no}  {name}"), 14)
            pf = para.paragraph_format
            pf.first_line_indent = Pt(56)
            pf.line_spacing = Pt(24)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)


def _append_conclusions(doc, sentences):
    """把结论句插入"六、检测结论："标题段之后。

    注意跳过首页目录条目（"六、检测结论………"文本很长），只定位
    正文中的真标题（短文本，带冒号）。返回实际插入的句子数量。
    """
    if not sentences:
        return 0
    heading = None
    for para in doc.paragraphs:
        t = para.text.strip()
        if t.startswith("六、检测结论") and len(t) <= 15:
            heading = para
    if heading is None:
        return 0
    # 逆序 addnext，保持句子顺序
    anchor = heading._p
    inserted = 0
    for sentence in reversed(sentences):
        new_p = OxmlElement("w:p")
        anchor.addnext(new_p)
        para = Paragraph(new_p, heading._parent)
        _set_run_font(para.add_run(sentence), 14)
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf = para.paragraph_format
        pf.first_line_indent = Pt(28)
        pf.line_spacing = Pt(24)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        inserted += 1
    return inserted


# ═══════════════════════════════════════════════════════════
#  页数后处理（可选，COM 失败静默）
# ═══════════════════════════════════════════════════════════
def _fill_page_count_via_com(path, retries=2):
    """用 Word/WPS COM 统计页数后回填正文中的 {page}；失败静默跳过。"""
    try:
        import win32com.client
    except ImportError:
        return
    except Exception:  # noqa: BLE001 - pywin32 已装但 gencache/COM 初始化失败
        return
    try:
        import pythoncom
    except ImportError:  # noqa: BLE001
        pythoncom = None
    pages = None
    for attempt in range(retries):
        app = None
        com_ready = False
        try:
            if pythoncom is not None:
                pythoncom.CoInitialize()
                com_ready = True
            for prog_id in ("Word.Application", "Kwps.Application",
                            "wps.Application"):
                try:
                    app = win32com.client.DispatchEx(prog_id)
                    break
                except Exception:
                    continue
            if app is None:
                return
            try:
                doc = app.Documents.Open(str(path))
                try:
                    doc.Repaginate()
                    for _ in range(2):
                        doc.Fields.Update()
                        for section in doc.Sections:
                            for story in (section.Headers, section.Footers):
                                for item in story:
                                    try:
                                        item.Range.Fields.Update()
                                    except Exception:
                                        pass
                        doc.Repaginate()
                    try:
                        if doc.TablesOfContents.Count:
                            doc.TablesOfContents(1).Update()
                            doc.Repaginate()
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    doc.Save()
                except Exception:
                    pass
                pages = doc.ComputeStatistics(2)  # wdStatisticPages
                doc.Close(False)
            finally:
                try:
                    app.Quit()
                except Exception:
                    pass
                try:
                    if com_ready and pythoncom is not None:
                        pythoncom.CoUninitialize()
                        com_ready = False
                except Exception:
                    pass
            break
        except Exception:
            pages = None
            try:
                if com_ready and pythoncom is not None:
                    pythoncom.CoUninitialize()
            except Exception:
                pass
            continue
    if pages is None:
        return
    try:
        d = Document(str(path))
        for para in d.paragraphs:
            full = "".join(r.text or "" for r in para.runs)
            if "{page}" not in full:
                continue
            new = full.replace("{page}", str(pages))
            for i, run in enumerate(para.runs):
                run.text = new if i == 0 else ""
        d.save(str(path))
    except Exception:
        pass
