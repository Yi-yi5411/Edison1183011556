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
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
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
}

_FULLWIDTH = {"（": "(", "）": ")", "：": ":", "，": ",", "；": ";"}


def _norm(text):
    """表头归一化：全角→半角、去空白、去括号内单位。"""
    s = str(text or "")
    for a, b in _FULLWIDTH.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\([^()]*\)", "", s)
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


def _trim_base_tail(doc):
    """清理基准文档（封面）尾部连续空段。"""
    body = doc.element.body
    kids = [c for c in body if c.tag != qn("w:sectPr")]
    keep = _drop_trailing_empty(kids)
    for el in kids:
        if el not in keep:
            body.remove(el)


def _append_chapter(base_doc, chapter, page_break=True):
    """把章节文档的 body 子元素（跳过 sectPr）追加到基准文档末尾。

    chapter 可传模板路径，也可传已加载（可能已填充）的 Document 对象；
    传对象时追加的就是内存中的内容，不会从磁盘重读。
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


def _set_cell_text(cell, value):
    """写单元格文本，尽量保留原格式（首 run 赋值，其余清空）。"""
    value = "" if value is None else str(value)
    if not cell.paragraphs:
        cell.text = value
        return
    para = cell.paragraphs[0]
    if para.runs:
        para.runs[0].text = value
        for run in para.runs[1:]:
            run.text = ""
    else:
        para.add_run(value)


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
            for alias in aliases.get(nl, []):
                gi = find_free_exact(_norm(alias))
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


def _fill_result_table(table, rows, gui_cols, header_rows, aliases, warnings,
                       sheet_key):
    """把 GUI 行数据写入模板表格（不处理合并，行不足自动扩展）。"""
    tpl_labels = _table_col_labels(table, header_rows)
    col_map, unmatched, unused = _match_columns(tpl_labels, gui_cols, aliases)
    if unmatched:
        warnings.append(
            f"{sheet_key}: 模板列未匹配到录入列（留空）：%s"
            % "、".join(unmatched))
    if unused:
        warnings.append(
            f"{sheet_key}: 以下录入列未写入报告（模板中无对应列）：%s"
            % "、".join(str(gui_cols[i]) for i in unused))

    # 数据行数量对齐：不足 deepcopy 末行扩展，多余删除
    data_trs = [tr for tr in table._tbl.findall(qn("w:tr"))][header_rows:]
    need = len(rows)
    tbl = table._tbl
    while len(data_trs) < need:
        new_tr = deepcopy(data_trs[-1]) if data_trs else None
        if new_tr is None:
            break
        tbl.append(new_tr)
        data_trs.append(new_tr)
    while len(data_trs) > need:
        tbl.remove(data_trs.pop())

    for ri, row_data in enumerate(rows):
        tr = data_trs[ri]
        cells = table.rows[header_rows + ri].cells
        for ti, gi in col_map.items():
            if gi < len(row_data) and ti < len(cells):
                _set_cell_text(cells[ti], row_data[gi])


def _clean_rows(rows):
    """过滤整行全空的行。"""
    return [r for r in rows
            if any(str(v).strip() for v in r)]


# ═══════════════════════════════════════════════════════════
#  检测内容清单 / 结论
# ═══════════════════════════════════════════════════════════
def _fill_test_date(src, test_date):
    """替换"五、检测结果"概述中的检测日期区间占位（xxx年xxx月xxx日~xxx日）。

    test_date 为空时保留占位原文（用户在 Word 中手填）。
    """
    if not str(test_date or "").strip():
        return
    pat = re.compile(r"xxx年xxx月xxx日[~～\-—]{0,3}xxx日")
    for para in src.paragraphs:
        full = "".join(r.text or "" for r in para.runs)
        if pat.search(full):
            _replace_in_paragraph(para, {pat.search(full).group(): str(test_date).strip()})


def _append_content_list(doc, checked_order):
    """四、检测内容末尾追加本次检测项目清单（模板正文已自带引导句）。"""
    for i, key in enumerate(checked_order, 1):
        doc.add_paragraph(f"{i}．{key}")


def _append_conclusions(doc, sentences):
    """把结论句插入"六、检测结论："标题段之后。

    注意跳过首页目录条目（"六、检测结论………"文本很长），只定位
    正文中的真标题（短文本，带冒号）。
    """
    if not sentences:
        return
    heading = None
    for para in doc.paragraphs:
        t = para.text.strip()
        if t.startswith("六、检测结论") and len(t) <= 15:
            heading = para
    if heading is None:
        return
    # 逆序 addnext，保持句子顺序
    anchor = heading._p
    for sentence in reversed(sentences):
        new_p = OxmlElement("w:p")
        anchor.addnext(new_p)
        Paragraph(new_p, heading._parent).add_run(sentence)


# ═══════════════════════════════════════════════════════════
#  页数后处理（可选，COM 失败静默）
# ═══════════════════════════════════════════════════════════
def _fill_page_count_via_com(path, retries=2):
    """用 Word/WPS COM 统计页数后回填正文中的 {page}；失败静默跳过。"""
    try:
        import win32com.client
    except ImportError:
        return
    pages = None
    for attempt in range(retries):
        app = None
        try:
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
                pages = doc.ComputeStatistics(2)  # wdStatisticPages
                doc.Close(False)
            finally:
                try:
                    app.Quit()
                except Exception:
                    pass
            break
        except Exception:
            pages = None
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
