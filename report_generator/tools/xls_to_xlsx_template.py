import os
import sys
from pathlib import Path
import xlrd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
import xlrd.xldate as xldate

# 项目静态资源统一入口（tools 脚本单独运行时兜底加入 sys.path）
_RG_PARENT = Path(__file__).resolve().parent.parent.parent  # structural_inspection 根目录
_RG_DIR = _RG_PARENT / "report_generator"
if str(_RG_PARENT) not in sys.path:
    sys.path.insert(0, str(_RG_PARENT))
try:
    from report_generator.framework.resources import resolve_path, get_asset
except Exception:  # 独立脚本运行兜底
    def resolve_path(*parts, must_exist=False):
        p = _RG_PARENT.joinpath(*parts)
        if must_exist and not p.exists():
            raise FileNotFoundError(p)
        return p
    def get_asset(*parts, must_exist=False):
        p = _RG_DIR / "assets"
        for part in parts:
            p = p / part
        if must_exist and not p.exists():
            raise FileNotFoundError(p)
        return p

# 所有模板/静态资源统一存放在 report_generator/assets/ 下
XLS_PATH = resolve_path("恩施格式.xls")          # 源：项目根目录（历史遗留）
OUT_PATH = get_asset("恩施格式.xlsx")             # 输出：静态资源集中目录

BORDER_STYLES = {
    0: None,
    1: "thin",
    2: "medium",
    3: "dashed",
    4: "dotted",
    5: "thick",
    6: "double",
    7: "hair",
    8: "mediumDashed",
    9: "dashDot",
    10: "mediumDashDot",
    11: "dashDotDot",
    12: "mediumDashDotDot",
    13: "slantDashDot",
}
H_ALIGN = {
    0: "general", 1: "left", 2: "center", 3: "right",
    4: "fill", 5: "justify", 6: "centerContinuous", 7: "distributed",
}
V_ALIGN = {
    0: "top", 1: "center", 2: "bottom", 3: "justify", 4: "distributed",
}

def colour(idx, book):
    if idx is None or idx == 32767:
        return None
    rgb = book.colour_map.get(idx)
    if not rgb:
        return None
    return "{:02X}{:02X}{:02X}".format(*rgb)

def convert_font(xf, book):
    fo = book.font_list[xf.font_index]
    size = max(1, int(round(fo.height / 20.0)))
    return Font(
        name=fo.name or "宋体",
        size=size,
        bold=bool(fo.bold),
        italic=bool(fo.italic),
        underline=None if not getattr(fo, "underline_type", 0) else "single",
        color=colour(getattr(fo, "colour_index", None), book),
    )

def convert_fill(xf, book):
    bg = xf.background
    pattern = getattr(bg, "fill_pattern", 0)
    if pattern == 1:
        fg = colour(getattr(bg, "pattern_colour_index", None), book)
        return PatternFill(patternType="solid", fgColor=fg or "00000000")
    if pattern == 0:
        return PatternFill(fill_type=None)
    # preserve other patterns as their foreground colour if available
    fg = colour(getattr(bg, "pattern_colour_index", None), book)
    return PatternFill(patternType="solid", fgColor=fg) if fg else PatternFill(fill_type=None)

def convert_border(xf, book):
    b = xf.border
    def side(style_idx, colour_idx):
        style = BORDER_STYLES.get(getattr(b, style_idx, 0))
        if not style:
            return Side(style=None)
        col = colour(getattr(b, colour_idx, None), book)
        return Side(style=style, color=col)
    return Border(
        left=side("left_line_style", "left_colour_index"),
        right=side("right_line_style", "right_colour_index"),
        top=side("top_line_style", "top_colour_index"),
        bottom=side("bottom_line_style", "bottom_colour_index"),
    )

def convert_alignment(xf):
    a = xf.alignment
    return Alignment(
        horizontal=H_ALIGN.get(getattr(a, "hor_align", 0), "general"),
        vertical=V_ALIGN.get(getattr(a, "vert_align", 1), "center"),
        wrap_text=bool(getattr(a, "text_wrapped", 0)),
        textRotation=getattr(a, "rotation", 0),
    )

def cell_value(ws, r, c, book):
    cell = ws.cell(r, c)
    ct = cell.ctype
    if ct == xlrd.XL_CELL_EMPTY or ct == xlrd.XL_CELL_BLANK:
        return None
    if ct == xlrd.XL_CELL_TEXT:
        return cell.value
    if ct == xlrd.XL_CELL_NUMBER:
        return cell.value
    if ct == xlrd.XL_CELL_DATE:
        return xldate.xldate_as_datetime(cell.value, book.datemode)
    if ct == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if ct == xlrd.XL_CELL_ERROR:
        return str(cell.value)
    return cell.value

def main():
    book = xlrd.open_workbook(XLS_PATH, formatting_info=True)
    wb = Workbook()
    wb.remove(wb.active)

    used_names = set()
    for sheet in book.sheets():
        name = sheet.name[:31].replace("/", "_").replace("\\", "_").replace("?", "_").replace("*", "_").replace("[", "_").replace("]", "_")
        base = name
        i = 2
        while name in used_names:
            name = f"{base[:28]}_{i}"
            i += 1
        used_names.add(name)
        ws = wb.create_sheet(title=name)
        print("converting sheet:", sheet.name, "->", name, sheet.nrows, sheet.ncols)

        # column widths (xlrd width = chars*256)
        for c in range(sheet.ncols):
            info = sheet.colinfo_map.get(c)
            if info is not None:
                ws.column_dimensions[get_column_letter(c + 1)].width = info.width / 256.0

        # row heights (xlrd twips -> points /20)
        for r in range(sheet.nrows):
            info = sheet.rowinfo_map.get(r)
            if info is not None and info.height:
                ws.row_dimensions[r + 1].height = info.height / 20.0

        # values + styles
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                xfi = sheet.cell_xf_index(r, c)
                xf = book.xf_list[xfi]
                value = cell_value(sheet, r, c, book)
                oc = ws.cell(row=r + 1, column=c + 1)
                if value is not None:
                    oc.value = value
                oc.font = convert_font(xf, book)
                oc.fill = convert_fill(xf, book)
                oc.border = convert_border(xf, book)
                oc.alignment = convert_alignment(xf)
                fmt = book.format_map.get(xf.format_key)
                if fmt is not None and fmt.format_str and fmt.format_str != "General":
                    oc.number_format = fmt.format_str

        # merged cells
        for rlo, rhi, clo, chi in sheet.merged_cells:
            try:
                ws.merge_cells(start_row=rlo + 1, start_column=clo + 1, end_row=rhi, end_column=chi)
            except Exception as e:
                print("  merge skip", (rlo, rhi, clo, chi), e)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    wb.save(OUT_PATH)
    print("saved", OUT_PATH)

if __name__ == "__main__":
    main()
