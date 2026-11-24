# -*- coding: utf-8 -*-
"""生成后 .docx 报告的读取/编辑/另存（纯函数，无 Qt 依赖）。

只编辑正文段落与表格单元格文本；页眉页脚、图片、域代码保留但不改。
路径限制在项目根内，且禁止直接编辑 report_template/ 与 data/templates/。
"""
import os
import re
import shutil
from datetime import datetime

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

try:
    from report_generator.framework.resources import PROJECT_ROOT
    from report_generator.utils.report_docx import (
        _replace_in_paragraph,
        _set_cell_text,
    )
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from framework.resources import PROJECT_ROOT
    from utils.report_docx import _replace_in_paragraph, _set_cell_text

_HEADING_RE = re.compile(
    r"^(?:[一二三四五六七八九十]+、|第[一二三四五六七八九十]+[章节]|表\s*\d)")


def _root():
    return os.path.abspath(str(PROJECT_ROOT))


def _check_under_root(path):
    root = _root()
    try:
        common = os.path.commonpath([root, os.path.abspath(path)])
    except ValueError:
        raise RuntimeError("文件路径不在项目目录内：%s" % path)
    if common != root:
        raise RuntimeError("只能编辑项目目录内的 .docx 文件：%s" % path)


def _ensure_docx_path(path):
    """校验输入 .docx 路径；返回绝对路径。"""
    text = str(path or "").strip()
    if not text:
        raise RuntimeError("缺少报告文件路径")
    abs_path = os.path.abspath(text)
    if not abs_path.lower().endswith(".docx"):
        raise RuntimeError("仅支持 .docx 报告文件（.doc 请先另存为 .docx）")
    if not os.path.isfile(abs_path):
        raise RuntimeError("报告文件不存在：%s" % abs_path)
    _check_under_root(abs_path)
    parts = [p.lower() for p in abs_path.split(os.sep)]
    if "report_template" in parts:
        raise RuntimeError("报告模板目录受保护，不能直接编辑模板文件")
    if "templates" in parts and "data" in parts:
        raise RuntimeError("模板库目录受保护，不能直接编辑模板文件")
    return abs_path


def _ensure_output_path(path, fallback):
    text = str(path or "").strip()
    target = os.path.abspath(text) if text else fallback
    if not target.lower().endswith(".docx"):
        target += ".docx"
    _check_under_root(target)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return target


def _is_heading(paragraph, text):
    try:
        style = (paragraph.style.name or "") if paragraph.style else ""
    except Exception:  # noqa: BLE001 - 样式缺失时忽略
        style = ""
    if style.lower().startswith("heading"):
        return True
    ppr = paragraph._p.pPr
    if ppr is not None and ppr.find(qn("w:outlineLvl")) is not None:
        return True
    return bool(_HEADING_RE.match(str(text or "").strip()))


def _body_paragraphs(doc):
    """按文档正文顺序返回 body 级段落对象。"""
    return [Paragraph(child, doc)
            for child in doc.element.body.iterchildren()
            if child.tag == qn("w:p")]


def _body_blocks(doc):
    """按文档正文顺序返回 ('p', Paragraph) / ('tbl', Table)。"""
    blocks = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            blocks.append(("p", Paragraph(child, doc)))
        elif child.tag == qn("w:tbl"):
            blocks.append(("tbl", Table(child, doc)))
    return blocks


def _set_paragraph_text(paragraph, text):
    """写段落文本，保留首个 run 的字体格式。"""
    value = "" if text is None else str(text)
    if paragraph.runs:
        paragraph.runs[0].text = value
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(value)


def load_report_document(filepath):
    """加载报告并返回段落/表格块（用于前端编辑）。"""
    path = _ensure_docx_path(filepath)
    doc = Document(path)
    paragraphs = []
    tables = []
    blocks = []
    p_index = 0
    t_index = 0

    for kind, obj in _body_blocks(doc):
        if kind == "p":
            text = obj.text or ""
            try:
                style = (obj.style.name or "") if obj.style else ""
            except Exception:  # noqa: BLE001
                style = ""
            try:
                alignment = (obj.alignment.name.lower()
                             if obj.alignment is not None else "")
            except Exception:  # noqa: BLE001
                alignment = ""
            size = None
            bold = None
            try:
                if obj.runs:
                    if obj.runs[0].font.size:
                        size = round(float(obj.runs[0].font.size.pt), 1)
                    bold = obj.runs[0].bold
            except Exception:  # noqa: BLE001
                pass
            paragraphs.append({
                "index": p_index,
                "text": text,
                "style": style,
                "heading": _is_heading(obj, text),
                "alignment": alignment,
                "size": size,
                "bold": bold,
            })
            blocks.append({"type": "paragraph", "index": p_index})
            p_index += 1
            continue

        # 表格：按 tc 路径去重（合并单元格只返回首次出现的原点格）
        seen = set()
        rows = []
        for r, row in enumerate(obj.rows):
            row_cells = []
            for c, cell in enumerate(row.cells):
                try:
                    key = cell._tc.getroottree().getpath(cell._tc)
                except Exception:  # noqa: BLE001
                    key = id(cell._tc)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    colspan = int(cell.grid_span or 1)
                except Exception:  # noqa: BLE001
                    colspan = 1
                rowspan = 1
                for rr in range(r + 1, len(obj.rows)):
                    try:
                        other = obj.cell(rr, c)._tc
                        other_key = other.getroottree().getpath(other)
                    except Exception:  # noqa: BLE001
                        break
                    if other_key == key:
                        rowspan += 1
                    else:
                        break
                text = cell.text or ""
                if rowspan > 1:
                    lines = [line.strip() for line in text.splitlines()
                             if line.strip()]
                    if lines and len(set(lines)) == 1:
                        text = lines[0]
                row_cells.append({
                    "row": r,
                    "col": c,
                    "text": text,
                    "colspan": colspan,
                    "rowspan": rowspan,
                    "merged": colspan > 1 or rowspan > 1,
                })
            rows.append(row_cells)
        tables.append({"index": t_index, "rows": rows})
        blocks.append({"type": "table", "index": t_index})
        t_index += 1

    stat = os.stat(path)
    return {
        "filepath": path,
        "filename": os.path.basename(path),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"),
        "paragraphs": paragraphs,
        "tables": tables,
        "blocks": blocks,
        "paragraph_count": len(paragraphs),
        "table_count": len(tables),
    }


def _apply_paragraph_edits(doc, edits):
    paragraphs = _body_paragraphs(doc)
    changed = 0
    for edit in edits or []:
        try:
            index = int(edit.get("index"))
        except (TypeError, ValueError, AttributeError):
            continue
        if index < 0 or index >= len(paragraphs):
            raise RuntimeError("段落索引越界（%s），文档可能已被修改，请重新加载" % index)
        _set_paragraph_text(paragraphs[index], edit.get("text", ""))
        changed += 1
    return changed


def _apply_cell_edits(doc, edits):
    changed = 0
    for edit in edits or []:
        try:
            t_index = int(edit.get("table"))
            row = int(edit.get("row"))
            col = int(edit.get("col"))
        except (TypeError, ValueError, AttributeError):
            continue
        if t_index < 0 or t_index >= len(doc.tables):
            raise RuntimeError("表格索引越界（%s），文档可能已被修改，请重新加载" % t_index)
        table = doc.tables[t_index]
        try:
            cell = table.cell(row, col)
        except Exception:
            raise RuntimeError("单元格越界（表%d 行%d 列%d），请重新加载" % (
                t_index, row, col))
        _set_cell_text(cell, edit.get("text", ""))
        changed += 1
    return changed


def _default_output_path(source_path):
    stem, ext = os.path.splitext(source_path)
    return "%s_修改_%s%s" % (
        stem, datetime.now().strftime("%Y%m%d_%H%M%S"), ext or ".docx")


def _save_doc(doc, source_path, output_path, overwrite):
    backup = ""
    if overwrite:
        target = source_path
        backup = os.path.splitext(source_path)[0] + ".bak.docx"
        try:
            shutil.copy2(source_path, backup)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("备份原报告失败：%s" % e)
    else:
        target = _ensure_output_path(output_path, _default_output_path(source_path))
    try:
        doc.save(target)
    except PermissionError:
        raise RuntimeError("报告文件被占用，请先在 Word/WPS 中关闭后重试：%s" % target)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("保存报告失败：%s" % e)
    return target, backup


def save_report_document(filepath, paragraphs=None, cells=None,
                         output_path=None, overwrite=False):
    """保存段落/单元格修改；默认另存新文件，overwrite=True 先备份再覆盖。"""
    path = _ensure_docx_path(filepath)
    doc = Document(path)
    changed_paragraphs = _apply_paragraph_edits(doc, paragraphs)
    changed_cells = _apply_cell_edits(doc, cells)
    changed = changed_paragraphs + changed_cells
    if changed <= 0 and not overwrite and not output_path:
        return {
            "filepath": path,
            "saved": False,
            "changed_paragraphs": 0,
            "changed_cells": 0,
            "backup": "",
            "message": "没有检测到修改",
        }
    target, backup = _save_doc(doc, path, output_path, overwrite)
    return {
        "filepath": target,
        "saved": True,
        "changed_paragraphs": changed_paragraphs,
        "changed_cells": changed_cells,
        "backup": backup,
        "message": "报告已保存",
    }


def replace_report_text(filepath, find, replace, output_path=None,
                        overwrite=False):
    """全文查找替换（正文段落 + 表格单元格）；返回替换次数与新文件路径。"""
    path = _ensure_docx_path(filepath)
    find = str(find or "")
    if not find:
        raise RuntimeError("查找内容不能为空")
    replace = "" if replace is None else str(replace)
    doc = Document(path)
    count = 0
    for paragraph in doc.paragraphs:
        if _replace_in_paragraph(paragraph, {find: replace}):
            count += 1
    seen = set()
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                key = id(cell._tc)
                if key in seen:
                    continue
                seen.add(key)
                for paragraph in cell.paragraphs:
                    if _replace_in_paragraph(paragraph, {find: replace}):
                        count += 1
    if count <= 0 and not overwrite and not output_path:
        return {
            "filepath": path,
            "saved": False,
            "replacements": 0,
            "backup": "",
            "message": "未找到要替换的内容",
        }
    target, backup = _save_doc(doc, path, output_path, overwrite)
    return {
        "filepath": target,
        "saved": True,
        "replacements": count,
        "backup": backup,
        "message": "已替换 %d 处" % count,
    }
