# -*- coding: utf-8 -*-
"""Excel 生成器 — 多 Sheet 导出辅助（独立使用）"""
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from collections import OrderedDict

HEADER_FONT = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
CELL_FONT = Font(name="Microsoft YaHei", size=10)
TITLE_FONT = Font(name="Microsoft YaHei", size=14, bold=True)
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
ALT_FILL = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

# 数字格式映射（与 gui_qt.py 中 _set_number_format 保持一致）
NUM_FORMAT_MAP = {
    "general": "General",
    "int": "0",
    "dec2": "0.00",
    "percent": "0.00%",
    "thousands": "#,##0.00",
}

# 边框样式映射（与 gui_qt.py 中 _set_border 保持一致）
BORDER_STYLE_MAP = {
    "thin": Side(style="thin", color="000000"),
    "medium": Side(style="medium", color="000000"),
    "thick": Side(style="thick", color="000000"),
    "dashed": Side(style="dashed", color="000000"),
    "dotted": Side(style="dotted", color="000000"),
    "double": Side(style="double", color="000000"),
}


def _build_font(base_font, bold=False, italic=False, underline=False):
    """在基础字体上叠加粗体/斜体/下划线"""
    ul_val = None
    if underline:
        ul_val = 'single'
    return Font(
        name=base_font.name,
        size=base_font.size,
        bold=base_font.bold or bold,
        italic=base_font.italic or italic,
        underline=ul_val or base_font.underline,
        color=base_font.color,
    )


def _build_border(border_dict):
    """根据 gui_qt.py 中的 border dict 构建 openpyxl Border。
    border_dict 示例: {"top": "thin", "bottom": "thin", "left": "medium", "right": "thick"}
    """
    if not border_dict:
        return None
    top = BORDER_STYLE_MAP.get(border_dict.get("top", ""))
    bottom = BORDER_STYLE_MAP.get(border_dict.get("bottom", ""))
    left = BORDER_STYLE_MAP.get(border_dict.get("left", ""))
    right = BORDER_STYLE_MAP.get(border_dict.get("right", ""))
    if top or bottom or left or right:
        return Border(left=left, right=right, top=top, bottom=bottom)
    return None


def _apply_cell_format(openpyxl_cell, fmt_dict, base_font=CELL_FONT, base_alignment=CENTER):
    """将 gui_qt.py 的格式 dict 应用到 openpyxl 单元格"""
    if not fmt_dict:
        return
    bold = fmt_dict.get("bold", False)
    italic = fmt_dict.get("italic", False)
    underline = fmt_dict.get("underline", False)
    if bold or italic or underline:
        openpyxl_cell.font = _build_font(base_font, bold, italic, underline)
    align = fmt_dict.get("align")
    if align:
        h_map = {"left": "left", "center": "center", "right": "right"}
        openpyxl_cell.alignment = Alignment(
            horizontal=h_map.get(align, "center"),
            vertical="center",
            wrap_text=True,
        )
    bg = fmt_dict.get("bg")
    if bg:
        openpyxl_cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
    fg = fmt_dict.get("fg")
    if fg:
        f = openpyxl_cell.font or base_font
        openpyxl_cell.font = Font(
            name=f.name, size=f.size, bold=f.bold, italic=f.italic,
            underline=f.underline, color=fg,
        )
    numfmt = fmt_dict.get("numfmt")
    if numfmt and numfmt in NUM_FORMAT_MAP:
        openpyxl_cell.number_format = NUM_FORMAT_MAP[numfmt]
    border = fmt_dict.get("border")
    if border:
        b = _build_border(border)
        if b:
            openpyxl_cell.border = b


def generate_excel(project_name, sheet_data, item_columns, filepath, cell_formats=None, merge_formats=None):
    """
    从内存数据生成多 Sheet Excel。

    sheet_data: {item_name: [[cell_values, ...]], ...}
    item_columns: {item_name: [column_headers], ...}
    cell_formats: {item_name: {(row, col): {bold,italic,underline,align,bg,fg,numfmt,border}}}
    merge_formats: {item_name: {(row, col): {align,bold,bg,fg}}}
    """
    if not sheet_data or not any(v for v in sheet_data.values()):
        raise ValueError("没有数据可导出")

    wb = Workbook()
    wb.remove(wb.active)

    for item_name in sheet_data:
        rows = sheet_data[item_name]
        columns = item_columns.get(item_name, ["数据"])
        sheet_name = item_name[:31]
        ws = wb.create_sheet(title=sheet_name)

        # 标题
        ws.merge_cells(start_row=1, start_column=1,
                       end_row=1, end_column=len(columns))
        c = ws.cell(row=1, column=1,
                    value=f"{project_name} — {item_name}")
        c.font = TITLE_FONT
        c.alignment = CENTER
        ws.row_dimensions[1].height = 32

        # 日期
        ws.merge_cells(start_row=2, start_column=1,
                       end_row=2, end_column=len(columns))
        c = ws.cell(row=2, column=1,
                    value=f"导出日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.font = Font(name="Microsoft YaHei", size=9, italic=True, color="666666")
        c.alignment = Alignment(horizontal="left", vertical="center")

        # 表头
        for i, h in enumerate(columns):
            c = ws.cell(row=4, column=i + 1, value=h)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.alignment = CENTER
            c.border = THIN_BORDER
            col_letter = get_column_letter(i + 1)
            ws.column_dimensions[col_letter].width = 14

        # 数据起始偏移（标题+日期+表头 = 3 行）
        DATA_ROW_OFFSET = 4  # 1-indexed，第 5 行开始 = row_offset 4

        # 数据
        item_cell_fmts = cell_formats.get(item_name, {}) if cell_formats else {}
        item_merge_fmts = merge_formats.get(item_name, {}) if merge_formats else {}

        for ri, row_data in enumerate(rows):
            for ci, val in enumerate(row_data[:len(columns)]):
                excel_row = DATA_ROW_OFFSET + ri + 1  # 1-indexed
                excel_col = ci + 1
                c = ws.cell(row=excel_row, column=excel_col,
                            value=val if val else "")
                c.font = CELL_FONT
                c.alignment = CENTER
                c.border = THIN_BORDER
                if ri % 2 == 0:
                    c.fill = ALT_FILL

                # 应用单元格级别的自定义格式
                py_row, py_col = ri, ci
                fmt = item_cell_fmts.get((py_row, py_col))
                if fmt:
                    _apply_cell_format(c, fmt, CELL_FONT, CENTER)

                # 应用合并单元格格式（anchor 单元格）
                mfmt = item_merge_fmts.get((py_row, py_col))
                if mfmt:
                    _apply_cell_format(c, mfmt, CELL_FONT, CENTER)

        ws.freeze_panes = "A5"

    wb.save(filepath)
    return filepath

def apply_merges_to_excel(filepath, merges, checked_keys=None):
    """Append user-created merged cells to an already generated workbook.

    :param filepath: Path to the .xlsx produced by :func:`generate_excel`.
    :param merges: ``{sheet_key: [(row, col, row_span, col_span), ...]}``
    :param checked_keys: Optional iterable of sheet keys to include. When omitted,
        every key in *merges* is processed.
    """
    from openpyxl import load_workbook

    wb = load_workbook(filepath)
    checked = None if checked_keys is None else set(checked_keys)

    for sheet_key, ranges in merges.items():
        if checked is not None and sheet_key not in checked:
            continue
        sheet_name = sheet_key[:31]
        if sheet_name not in wb.sheetnames:
            continue

        ws = wb[sheet_name]
        # generate_excel data starts at row 5 (1-indexed), column 1.
        for (r, c, rs, cs) in ranges:
            try:
                ws.merge_cells(
                    start_row=5 + r, start_column=1 + c,
                    end_row=5 + r + rs - 1, end_column=1 + c + cs - 1,
                )
            except Exception as e:
                import warnings
                warnings.warn(f"merge failed ({sheet_key} r={r} c={c}): {e}")

    wb.save(filepath)
    return filepath


def export_workbook(project_name, sheet_data, item_columns, filepath,
                    cell_formats=None, merge_formats=None, merges=None,
                    checked_keys=None):
    """High-level Excel export orchestration.

    Generates the multi-sheet workbook and then restores user merges. Keeping this
    flow here means the UI only decides *what* to export, not *how* Excel is built.
    """
    generate_excel(
        project_name,
        sheet_data,
        item_columns,
        filepath,
        cell_formats=cell_formats,
        merge_formats=merge_formats,
    )
    if merges:
        apply_merges_to_excel(filepath, merges, checked_keys=checked_keys)
    return filepath

