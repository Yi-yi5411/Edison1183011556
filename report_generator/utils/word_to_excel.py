# -*- coding: utf-8 -*-
"""Word 回弹法检测记录 -> 恩施格式 Excel 转换模块。

将 `省检测中心回弹记录.doc`（实际为 OOXML 压缩包，扩展名为 .doc）解析为
16 个构件的回弹记录，并按 `恩施格式.xlsx` 模板逐页写入，实现字段一一对应
与格式转换。运行时仅依赖 openpyxl，无需 Office / Word COM / xlrd。

模板文件由 `tools/xls_to_xlsx_template.py` 在开发期生成，随项目发布：
    report_generator/assets/恩施格式.xlsx
"""
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from lxml import etree

# 确保可使用项目内置的 openpyxl（框架入口已设置 sys.path，此处兜底）
_BASE = Path(__file__).resolve().parent.parent
_LIBS = _BASE / "libs"
if str(_LIBS) not in sys.path and _LIBS.is_dir():
    sys.path.insert(0, str(_LIBS))
# 静态资源统一入口（框架入口已添加父目录到 sys.path，此处兜底）
_FRAMEWORK_PARENT = str(_BASE)
if _FRAMEWORK_PARENT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_PARENT)
try:
    from framework.resources import get_asset  # noqa: E402
except Exception:  # 作为独立脚本被调用时降级为相对路径
    get_asset = None  # type: ignore

from openpyxl import load_workbook  # noqa: E402

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_PAGE_ROWS = 29
_MAX_PAGES = 16


class WordToExcelError(Exception):
    """Word 转 Excel 过程中的业务异常。"""


def _cell_text(tc):
    parts = []
    for node in tc.iter():
        if node.tag == _W + "t":
            parts.append(node.text or "")
    return "".join(parts).strip()


def _expand_row(tr):
    """返回一行中每个逻辑单元格的文本（忽略 gridSpan，按逻辑列一一对应）。"""
    return [_cell_text(tc) for tc in tr.findall(_W + "tc")]


def _norm(text):
    """归一化标签文本：去空白与全角冒号等。"""
    text = str(text or "")
    text = text.replace("\u3000", "").replace(" ", "").replace("\t", "")
    return text


def _to_float(text):
    """从文本中提取一个数值，失败返回 None。"""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    if s in ("--", "-", "/", "—", "／"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _parse_date(text):
    """解析常见中文日期（YYYY年M月D日 / YYYY-M-D）。失败返回 None。"""
    if not text:
        return None
    s = str(text).strip()
    m = re.search(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})", s)
    if not m:
        m = re.search(r"(\d{4})(\d{2})(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _days_between(start_text, end_text):
    start = _parse_date(start_text)
    end = _parse_date(end_text)
    if start and end:
        return (end.date() - start.date()).days
    return None


def _extract_kv(table, labels):
    """扫描表格单元格，返回 归一化标签 -> 后继单元格值 的映射。"""
    result = {}
    label_set = {_norm(k) for k in labels}
    for tr in table.findall(_W + "tr"):
        cells = _expand_row(tr)
        for idx, cell in enumerate(cells):
            if _norm(cell) in label_set and idx + 1 < len(cells):
                result[_norm(cell)] = cells[idx + 1].strip()
    return result


def _parse_component_table(table):
    """解析单个构件表，返回构件记录 dict。"""
    rows = table.findall(_W + "tr")
    if len(rows) < 14:
        return None

    kv = _extract_kv(table, [
        "检测设备编号", "设计强度等级", "浇筑日期", "构件名称", "泵送混凝土", "检测日期",
    ])

    header_cells = _expand_row(rows[2]) if len(rows) > 2 else []
    # 数据行：表头下两行之后（R4~R13，共 10 行）
    zones = []
    for tr in rows[4:14]:
        cells = _expand_row(tr)
        if len(cells) < 27:
            continue
        zone_no = _to_float(cells[1]) or 0
        rebound = []
        for c in cells[2:18]:
            val = _to_float(c)
            rebound.append(int(val) if val is not None and float(val).is_integer() else (val if val is not None else ""))
        rm = _to_float(cells[18]) if len(cells) > 18 else None
        d_mean = _to_float(cells[22]) if len(cells) > 22 else None
        angle = _to_float(cells[24]) if len(cells) > 24 else 0.0
        casting = _to_float(cells[25]) if len(cells) > 25 else 0.0
        strength = _to_float(cells[26]) if len(cells) > 26 else None
        zones.append({
            "zone": int(zone_no),
            "rebound": rebound,
            "rm": rm,
            "carbonation": d_mean,
            "angle": angle if angle is not None else 0.0,
            "casting": casting if casting is not None else 0.0,
            "strength": strength,
        })

    # 统计行 R14：测区状态/测试角度 + fcu,e / 平均值 / 标准差 / 最小值
    stats = {}
    if len(rows) > 14:
        stat_cells = _expand_row(rows[14])
        if len(stat_cells) >= 8:
            status = stat_cells[1]
            stats["status"] = status
            stats["dry"] = "干燥" if "干燥" in status else ""
            stats["angle_label"] = "水平" if "水平" in status else ""
            stats["fcu_e"] = _to_float(stat_cells[4])
            stats["mean"] = _to_float(stat_cells[5])
            stats["std"] = _to_float(stat_cells[6])
            stats["min"] = _to_float(stat_cells[7])

    return {
        "device_no": kv.get(_norm("检测设备编号"), ""),
        "design_strength": kv.get(_norm("设计强度等级"), ""),
        "cast_date": kv.get(_norm("浇筑日期"), "") or kv.get(_norm("施工日期"), ""),
        "component_name": kv.get(_norm("构件名称"), ""),
        "pumping": kv.get(_norm("泵送混凝土"), ""),
        "test_date": kv.get(_norm("检测日期"), ""),
        "zones": zones,
        "stats": stats,
    }


def parse_rebound_doc(doc_path):
    """解析回弹记录 Word 文档，返回全局信息与构件记录列表。"""
    doc_path = Path(doc_path)
    if not doc_path.exists():
        raise WordToExcelError(f"文件不存在：{doc_path}")

    try:
        archive = zipfile.ZipFile(doc_path)
    except zipfile.BadZipFile as exc:
        raise WordToExcelError(
            "无法解析该 Word 文件：文件不是标准的 .docx/OOXML 格式。\n"
            "请先在 Word 中另存为 .docx 后再导入。"
        ) from exc

    try:
        document = archive.read("word/document.xml")
    except KeyError as exc:
        raise WordToExcelError("Word 文档中缺少 document.xml，无法读取表格。") from exc

    root = etree.fromstring(document)
    tables = root.findall(".//" + _W + "tbl")
    if not tables:
        raise WordToExcelError("Word 文档中未找到表格，无法提取回弹记录。")

    global_info = _extract_kv(tables[0], [
        "工程名称", "委托单位", "建设单位", "施工单位", "见证单位", "检测依据",
        "设计强度等级", "施工日期", "检测设备", "检测地点", "检测环境温度",
        "见证人", "泵送混凝土", "检测日期", "检测原因", "检测性质",
        "构件名称", "养护方法",
    ])

    components = []
    for table in tables[1:]:
        comp = _parse_component_table(table)
        if comp and comp.get("zones"):
            components.append(comp)

    if not components:
        raise WordToExcelError("未能从 Word 文档中提取到任何构件的回弹记录。")

    return {"global": global_info, "components": components}


def _parse_design_strength(text):
    """从 'C35' 等文本中提取强度数值。"""
    m = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
    return float(m.group(1)) if m else None


def _fill_page(ws, base_row, component, global_info):
    """按模板格式写入单个构件页（base_row 为 0-based 页起始行）。"""
    g = global_info or {}
    design_text = component.get("design_strength") or g.get(_norm("设计强度等级"), "")
    pumping = component.get("pumping") or g.get(_norm("泵送混凝土"), "")
    cast_date = component.get("cast_date") or g.get(_norm("施工日期"), "")
    test_date = component.get("test_date") or g.get(_norm("检测日期"), "")
    equipment = g.get(_norm("检测设备"), "")

    def set_cell(row_offset, col, value):
        ws.cell(row=base_row + row_offset, column=col, value=value)

    # ---- 头部信息（模板第 4~10 行） ----
    set_cell(4, 20, "")  # 报告编号：源文档未提供
    set_cell(5, 5, g.get(_norm("施工单位"), ""))
    set_cell(6, 5, g.get(_norm("工程名称"), ""))
    set_cell(7, 5, component.get("component_name", ""))
    set_cell(7, 18, "JGJ/T 23-2011")  # 试验依据
    set_cell(8, 5, "测面干燥、光洁、干净")  # 样品描述
    set_cell(8, 18, "设计文件")  # 判定依据
    set_cell(9, 5, f"回弹仪（{equipment}）" if equipment else "回弹仪（HT-225J）")
    set_cell(10, 4, _days_between(cast_date, test_date))
    set_cell(10, 18, "是" if "泵送" in pumping else "否")

    # ---- 10 个测区数据（模板第 13~22 行） ----
    for zone in component["zones"]:
        row_offset = 12 + zone["zone"]  # 测区 1 -> 第 13 行
        if zone["zone"] < 1 or zone["zone"] > 10:
            continue
        set_cell(row_offset, 1, zone["zone"])
        for i, val in enumerate(zone["rebound"][:16], start=2):
            set_cell(row_offset, i, val if val != "" else None)
        rm = zone.get("rm") or 0.0
        angle = zone.get("angle") or 0.0
        casting = zone.get("casting") or 0.0
        strength = zone.get("strength") or 0.0
        carbonation = zone.get("carbonation")
        set_cell(row_offset, 18, f"{rm:.1f}")  # 回弹平均值
        set_cell(row_offset, 19, f"{angle:.1f}")  # 角度修正值
        set_cell(row_offset, 20, f"{rm + angle:.1f}")  # 角度修正后
        set_cell(row_offset, 21, f"{casting:.1f}")  # 浇筑面修正值
        set_cell(row_offset, 22, f"{rm + angle + casting:.1f}")  # 浇筑面修正后
        set_cell(row_offset, 23, f"{carbonation:.1f}" if carbonation is not None else "/")  # 碳化深度
        set_cell(row_offset, 24, f"{strength:.1f}")  # 强度换算值
        set_cell(row_offset, 25, "0.0")  # 泵送砼修正值
        set_cell(row_offset, 26, strength)  # 测区强度值

    # ---- 统计评定区 ----
    stats = component.get("stats") or {}
    mean = stats.get("mean")
    std = stats.get("std")
    min_val = stats.get("min")
    fcu_e = stats.get("fcu_e")
    design_num = _parse_design_strength(design_text)

    # 按 JGJ/T 23-2011 批量推定值 fcu,e = 平均值 - 1.645 * 标准差，
    # 用未四舍五入的精确值判定，避免“恰好等于设计值”时误判。
    fcu_e_precise = None
    if mean is not None and std is not None:
        fcu_e_precise = mean - 1.645 * std
        fcu_e = round(fcu_e_precise, 1)
    else:
        fcu_e_precise = fcu_e
    if fcu_e is None and component["zones"]:
        strengths = [z.get("strength") for z in component["zones"] if z.get("strength") is not None]
        if strengths:
            fcu_e = sum(strengths) / len(strengths)
            fcu_e_precise = fcu_e

    qualified = True
    if fcu_e_precise is not None and design_num is not None:
        qualified = fcu_e_precise >= design_num
    conclusion = (
        "经检测，试构件强度符合设计文件的要求。"
        if qualified else
        "经检测，试构件强度不符合设计文件的要求。"
    )

    set_cell(23, 20, stats.get("dry", "") or "干燥")  # 测面状态
    set_cell(24, 3, mean)  # 平均值
    set_cell(24, 7, std)  # 标准差
    set_cell(24, 14, min_val)  # 构件测区最小值
    set_cell(24, 20, stats.get("angle_label", "") or "水平")  # 测试角度
    set_cell(25, 7, fcu_e)  # 强度推定值
    set_cell(25, 20, f"{fcu_e:.1f}MPa" if fcu_e is not None else "")  # 强度推定值(带单位)
    set_cell(26, 4, f"{fcu_e:.1f}MPa" if fcu_e is not None else "")  # 构件强度
    set_cell(26, 12, design_text)  # 设计强度
    set_cell(26, 20, "合格" if qualified else "不合格")  # 结果判定
    set_cell(27, 3, conclusion)  # 检测结论


def _clear_page(ws, base_row):
    """清空未使用构件页的可填写区域，避免残留模板示例数据。"""
    ws.cell(row=base_row + 4, column=20, value=None)          # 报告编号
    for row_offset in range(5, 10):
        ws.cell(row=base_row + row_offset, column=5, value=None)  # 施工单位/工程名称/部位/样品描述/仪器
    ws.cell(row=base_row + 7, column=18, value=None)          # 试验依据
    ws.cell(row=base_row + 8, column=18, value=None)          # 判定依据
    ws.cell(row=base_row + 10, column=4, value=None)          # 龄期
    ws.cell(row=base_row + 10, column=18, value=None)         # 泵送混凝土
    for zone in range(1, 11):
        row_offset = 12 + zone
        for col in range(1, 27):
            ws.cell(row=base_row + row_offset, column=col, value=None)
    for row_offset, cols in [(23, [20]), (24, [3, 7, 14, 20]), (25, [7, 20]), (26, [4, 12, 20]), (27, [3])]:
        for col in cols:
            ws.cell(row=base_row + row_offset, column=col, value=None)


def convert_word_to_excel(word_path, output_path=None, template_path=None):
    """将 Word 回弹记录转换为恩施格式 xlsx。

    :param word_path: 源 .doc/.docx 文件路径。
    :param output_path: 输出 .xlsx 路径；默认与源文件同名。
    :param template_path: 模板路径；默认使用随项目发布的恩施格式模板。
    """
    data = parse_rebound_doc(word_path)
    components = data["components"]

    # 优先通过 framework.resources 统一解析路径；脚本独立运行时降级为相对定位
    if template_path is None:
        if get_asset is not None:
            template_path = get_asset("恩施格式.xlsx")
        else:
            template_path = _BASE / "assets" / "恩施格式.xlsx"
    else:
        template_path = Path(template_path)
    if not template_path.exists():
        raise WordToExcelError(f"模板文件不存在：{template_path}")

    if output_path is None:
        output_path = Path(word_path).with_suffix(".xlsx")
    else:
        output_path = Path(output_path)

    wb = load_workbook(template_path)
    if "回弹表" not in wb.sheetnames:
        raise WordToExcelError("模板中缺少“回弹表”工作表。")
    ws = wb["回弹表"]

    n = len(components)
    for i in range(_MAX_PAGES):
        base_row = i * _PAGE_ROWS
        if i < n:
            _fill_page(ws, base_row, components[i], data["global"])
        else:
            _clear_page(ws, base_row)

    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Word 回弹记录转恩施格式 Excel")
    parser.add_argument("word", help="源 .doc/.docx 文件路径")
    parser.add_argument("-o", "--output", help="输出 .xlsx 路径")
    args = parser.parse_args()

    out = convert_word_to_excel(args.word, args.output)
    print(f"转换完成：{out}")
