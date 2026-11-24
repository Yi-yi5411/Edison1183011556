# -*- coding: utf-8 -*-
"""导入 DOCX 原始记录模板的自动填充（纯函数，无 Qt 依赖）。

约定（上传模板时可参考内置空白模板）：
  1. 占位符：{{project_name}}、{{report_no}}、{{test_date}}、{{client}}……
     也支持 {{工程名称}}、{{检测编号}} 等中文占位符；
  2. 表头信息：表格中“工程名称/委托单位/检测日期/检测编号……”标签
     右侧单元格会自动填入抬头值；
  3. 数据表：选择表头与检测项目列匹配度最高的表格，按列写数据并
     自动扩展数据行（复用报告结果一览表的列匹配/扩行逻辑）。
"""
import os
import re
from datetime import datetime

from docx import Document

try:
    from report_generator.framework.resources import resolve_path
    from report_generator.utils.original_record import (
        _default_output_dir,
        _safe_filename,
    )
    from report_generator.utils.report_docx import (
        _clean_rows,
        _fill_result_table,
        _match_columns,
        _norm,
        _replace_placeholders,
        _set_cell_text,
        _table_col_labels,
    )
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from framework.resources import resolve_path
    from utils.original_record import _default_output_dir, _safe_filename
    from utils.report_docx import (
        _clean_rows,
        _fill_result_table,
        _match_columns,
        _norm,
        _replace_placeholders,
        _set_cell_text,
        _table_col_labels,
    )

_PLACEHOLDER_RE = re.compile(r"{{([^{}]+)}}")

# 模板表头标签 → 报告抬头键（归一化后匹配）
_HEADER_LABELS = {
    "工程名称": "project_name",
    "工程地点": "project_location",
    "检测地点": "project_location",
    "委托单位": "client",
    "见证单位": "witness",
    "检测编号": "report_no",
    "报告编号": "report_no",
    "检测日期": "test_date",
    "报告日期": "report_date",
    "检测人": "tester",
    "报告编写人": "writer",
    "编写人": "writer",
    "记录人": "writer",
    "复核人": "checker",
    "审核人": "reviewer",
    "批准人": "approver",
    "检测依据": "basis",
    "检测设备": "equipment",
    "检测项目": "detection_item",
    "检测类别": "detection_category",
}
_HEADER_LABELS = {_norm(key): value for key, value in _HEADER_LABELS.items()}


def _info_mapping(info):
    """生成占位符替换映射（英文键 + 常用中文标签）。"""
    info = dict(info or {})
    mapping = {}
    for key in ("project_name", "report_no", "project_location", "client",
                "witness", "tester", "writer", "checker", "reviewer",
                "approver", "test_date", "report_date", "detection_item",
                "basis", "equipment", "detection_category"):
        mapping[key] = str(info.get(key) or "")
    mapping.update({
        "工程名称": mapping["project_name"],
        "报告编号": mapping["report_no"],
        "检测编号": mapping["report_no"],
        "工程地点": mapping["project_location"],
        "委托单位": mapping["client"],
        "见证单位": mapping["witness"],
        "检测日期": mapping["test_date"],
        "报告日期": mapping["report_date"],
        "检测人": mapping["tester"],
        "报告编写人": mapping["writer"],
        "复核人": mapping["checker"],
        "审核人": mapping["reviewer"],
        "批准人": mapping["approver"],
        "检测项目": mapping["detection_item"],
        "检测依据": mapping["basis"],
        "检测设备": mapping["equipment"],
    })
    return mapping


def _fill_header_fields(doc, info):
    """按“标签单元格 → 右侧单元格”填充表头信息；返回填充数量。"""
    info = dict(info or {})
    count = 0
    for table in doc.tables:
        for row in table.rows:
            cells = row.cells
            if len(cells) < 2:
                continue
            for i, cell in enumerate(cells[:-1]):
                label = str(cell.text or "").strip().rstrip("：:")
                key = _HEADER_LABELS.get(_norm(label))
                if not key:
                    continue
                value = info.get(key)
                if value is None or str(value).strip() == "":
                    continue
                target = cells[i + 1]
                _set_cell_text(target, str(value))
                count += 1
    return count


def _find_best_table(doc, columns, aliases):
    """找表头匹配得分最高的表格，返回 (table, header_rows, score) 或 None。"""
    best = None
    for table in doc.tables:
        if not table.rows:
            continue
        for header_rows in (1, 2, 3):
            if header_rows >= len(table.rows):
                continue
            try:
                labels = _table_col_labels(table, header_rows)
            except Exception:  # noqa: BLE001 - 异常模板跳过
                continue
            if not any(str(x).strip() for x in labels):
                continue
            col_map, _unmatched, _unused = _match_columns(
                labels, columns, aliases or {})
            score = len(col_map)
            if best is None or score > best[2]:
                best = (table, header_rows, score)
    if best is None or best[2] <= 0:
        return None
    return best


def _default_name(sheet_key, info):
    serial = (info or {}).get("report_no") or (info or {}).get("project_name") or "未编号"
    return "原始记录_%s_%s_%s.docx" % (
        _safe_filename(sheet_key), _safe_filename(serial, 30),
        datetime.now().strftime("%Y%m%d_%H%M%S"))


def fill_imported_record(template_path, sheet_key, columns, rows, info,
                         output_path=None):
    """把检测数据填入导入的 .docx 原始记录模板。

    :return: (生成文件路径, warnings 列表)
    """
    template_path = os.path.abspath(str(template_path))
    if not template_path.lower().endswith(".docx"):
        raise RuntimeError("仅支持 .docx 模板，请先用 WPS/Word 将 .doc 另存为 .docx")
    if not os.path.isfile(template_path):
        raise RuntimeError("模板文件不存在：%s" % template_path)

    warnings = []
    rows = _clean_rows(rows)
    info = dict(info or {})
    info["detection_item"] = info.get("detection_item") or sheet_key
    doc = Document(template_path)

    # 1) 占位符
    try:
        _replace_placeholders(doc, _info_mapping(info))
    except Exception as e:  # noqa: BLE001
        warnings.append("占位符替换失败：%s" % e)

    # 2) 表头字段
    try:
        _fill_header_fields(doc, info)
    except Exception as e:  # noqa: BLE001
        warnings.append("表头字段填充失败：%s" % e)

    # 3) 数据表
    best = _find_best_table(doc, columns, {})
    if best is None:
        warnings.append("未找到与检测列匹配的数据表，仅填充表头/占位符")
    else:
        table, header_rows, score = best
        try:
            _fill_result_table(table, rows, columns, header_rows, {},
                               warnings, sheet_key)
        except Exception as e:  # noqa: BLE001
            warnings.append("数据表填充失败：%s" % e)
        if score < min(3, max(1, len(columns))):
            warnings.append(
                "数据表仅匹配到 %d 列，请核对模板表头与检测项目列是否一致" % score)

    if not output_path:
        output_path = os.path.join(_default_output_dir(),
                                   _default_name(sheet_key, info))
    output_path = os.path.abspath(str(output_path))
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    doc.save(output_path)
    return output_path, warnings


def inspect_docx(path):
    """预览导入模板：段落、表格文本、占位符。"""
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if str(p.text).strip()]
    tables = []
    for table in doc.tables:
        table_rows = []
        for row in table.rows:
            table_rows.append([str(cell.text or "").strip()
                               for cell in row.cells])
        tables.append(table_rows)
    placeholders = []
    seen = set()
    for text in paragraphs + [c for t in tables for row in t for c in row]:
        for match in _PLACEHOLDER_RE.findall(text or ""):
            if match not in seen:
                seen.add(match)
                placeholders.append(match)
    return {
        "paragraphs": paragraphs[:80],
        "tables": tables[:10],
        "placeholders": placeholders,
    }
