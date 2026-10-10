import re
import tempfile
from pathlib import Path

import docx
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, Border, Side

# ---------- 可选：.doc 转 .docx 支持（仅 Windows + 已安装 Word）----------
try:
    import win32com.client
    WIN32COM_AVAILABLE = True
except ImportError:
    WIN32COM_AVAILABLE = False


def doc_to_docx(doc_path, docx_path=None):
    """使用 Word 应用程序将 .doc 转为 .docx"""
    if not WIN32COM_AVAILABLE:
        raise ImportError("请安装 pywin32 (pip install pywin32) 或手动将 .doc 另存为 .docx")
    if docx_path is None:
        docx_path = str(Path(doc_path).with_suffix(".docx"))
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Open(doc_path)
    doc.SaveAs(docx_path, FileFormat=16)  # 16 = wdFormatXMLDocument
    doc.Close()
    word.Quit()
    return docx_path


# ---------- 核心解析模块 ----------
def parse_word_to_data(docx_path):
    """
    解析 Word 中的回弹记录，返回结构化数据列表。
    每个元素为 dict：{构件名称, 设计强度, 浇筑日期, 检测日期, 测区列表}
    """
    doc = docx.Document(docx_path)
    all_components = []

    # 遍历所有表格
    for table in doc.tables:
        # 1. 检查该表是否为回弹数据表（寻找“测区”表头）
        header_row_index = None
        header_cells_text = []
        for idx, row in enumerate(table.rows):
            texts = [cell.text.strip() for cell in row.cells]
            row_str = " ".join(texts)
            if "测区" in row_str and ("回弹" in row_str or "Rm" in row_str):
                header_row_index = idx
                header_cells_text = texts
                break
        if header_row_index is None:
            continue

        # 2. 提取构件元数据（从表格内或附近段落）
        comp_name = ""
        design_strength = ""
        cast_date = ""
        test_date = ""

        # 方法 A：从表格所有单元格中扫描标签
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if "构件名称" in text:
                    parts = re.split(r'[:：]', text, maxsplit=1)
                    if len(parts) > 1:
                        comp_name = parts[1].strip()
                if "设计强度等级" in text or "设计强度" in text:
                    parts = re.split(r'[:：]', text, maxsplit=1)
                    if len(parts) > 1:
                        design_strength = parts[1].strip()
                if "浇筑日期" in text or "施工日期" in text:
                    parts = re.split(r'[:：]', text, maxsplit=1)
                    if len(parts) > 1:
                        cast_date = parts[1].strip()
                if "检测日期" in text:
                    parts = re.split(r'[:：]', text, maxsplit=1)
                    if len(parts) > 1:
                        test_date = parts[1].strip()

        # 方法 B：如果未从单元格获取，从表格前 3 个段落中获取
        if not comp_name:
            for para in doc.paragraphs:
                if "构件名称" in para.text:
                    comp_name = para.text.split("：")[-1].strip() if "：" in para.text else ""
                    break

        # 3. 确定各列索引（基于表头文字）
        # 期望表头：测区, 1,2,3,...,16, Rm/Rm平均值, d1, d2, d3, d平均值, ...
        col_index = {
            "zone": 0,
            "R": [],   # 1~16 的列索引
            "Rm": None,
            "d1": None,
            "d2": None,
            "d3": None,
            "d_mean": None,
            "angle_corr": None,
            "casting_corr": None,
            "strength": None
        }
        for idx, cell_text in enumerate(header_cells_text):
            text = cell_text.strip()
            # 检测回弹值列（1~16）
            if text.isdigit() and 1 <= int(text) <= 16:
                col_index["R"].append(idx)
            elif "Rm" in text or "平均值" in text:
                # 如果已经有 Rm，可能第二个是强度平均值，暂存
                if col_index["Rm"] is None:
                    col_index["Rm"] = idx
            elif "d1" in text or "碳化" in text and "1" in text:
                if col_index["d1"] is None:
                    col_index["d1"] = idx
            elif "d2" in text:
                col_index["d2"] = idx
            elif "d3" in text:
                col_index["d3"] = idx
            elif "d平均" in text or "d平均值" in text or "碳化平均值" in text:
                col_index["d_mean"] = idx
            elif "角度" in text:
                col_index["angle_corr"] = idx
            elif "浇筑面" in text:
                col_index["casting_corr"] = idx
            elif "强度值" in text or "换算值" in text:
                col_index["strength"] = idx

        # 如果没找到 Rm，尝试使用“R~m~”等变体（降级方案）
        if col_index["Rm"] is None:
            for idx, text in enumerate(header_cells_text):
                if "Rm" in text or "R~m~" in text:
                    col_index["Rm"] = idx
                    break

        # 4. 提取数据行（从表头下一行开始，直到遇到非数字测区或结束）
        data_rows = []
        for row in table.rows[header_row_index + 1:]:
            first_cell = row.cells[0].text.strip()
            # 判断是否为测区行：以数字开头
            if first_cell and first_cell.lstrip('-').isdigit():
                data_rows.append(row)
            else:
                # 如果碰到“测区状态”等描述，停止
                row_str = " ".join(cell.text.strip() for cell in row.cells)
                if "测区状态" in row_str or "测试角度" in row_str:
                    break
                # 有些表格中间有空行，跳过
                if first_cell == "":
                    continue
                # 如果既不是数字也不是空，可能表头结束，停止
                break

        # 5. 组装测区数据
        zones = []
        for row in data_rows:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) < max(col_index["R"] + [0]) + 1:
                continue

            # 测区号
            zone_num = int(cells[0]) if cells[0].lstrip('-').isdigit() else None
            if zone_num is None:
                continue

            # 回弹值 1~16
            rebound_vals = []
            for idx in col_index["R"]:
                if idx < len(cells) and cells[idx]:
                    try:
                        rebound_vals.append(float(cells[idx]))
                    except ValueError:
                        rebound_vals.append(None)
                else:
                    rebound_vals.append(None)

            # 其他数值
            def safe_float(idx):
                if idx is not None and idx < len(cells) and cells[idx]:
                    try:
                        return float(cells[idx])
                    except ValueError:
                        return None
                return None

            zone_data = {
                "测区号": zone_num,
                "回弹值": rebound_vals,
                "Rm": safe_float(col_index["Rm"]),
                "d1": safe_float(col_index["d1"]),
                "d2": safe_float(col_index["d2"]),
                "d3": safe_float(col_index["d3"]),
                "d_mean": safe_float(col_index["d_mean"]),
                "角度修正": safe_float(col_index["angle_corr"]),
                "浇筑面修正": safe_float(col_index["casting_corr"]),
                "测区强度": safe_float(col_index["strength"]),
            }
            zones.append(zone_data)

        # 6. 若该表提取到有效测区，则加入结果
        if zones:
            all_components.append({
                "构件名称": comp_name or "未知构件",
                "设计强度": design_strength or "C35",
                "浇筑日期": cast_date or "未知",
                "检测日期": test_date or "未知",
                "测区": zones
            })

    return all_components


# ---------- Excel 导出模块 ----------
def save_to_excel(components, output_path):
    """
    将解析结果导出为 Excel，每个构件一个 Sheet
    """
    wb = Workbook()
    # 删除默认空白 sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    center_align = Alignment(horizontal='center', vertical='center')

    for comp in components:
        # 构件名作为 sheet 名（清理非法字符）
        sheet_name = re.sub(r'[\\/*?:\[\]]', '_', comp["构件名称"])[:31]
        ws = wb.create_sheet(title=sheet_name)

        # ---- 写入标题信息 ----
        info_data = [
            ["构件名称", comp["构件名称"]],
            ["设计强度", comp["设计强度"]],
            ["浇筑日期", comp["浇筑日期"]],
            ["检测日期", comp["检测日期"]],
        ]
        for row_idx, row_data in enumerate(info_data, start=1):
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.alignment = center_align
                cell.font = Font(bold=True) if col_idx == 1 else Font()

        # ---- 空行 ----
        ws.append([])

        # ---- 数据表头 ----
        header = ["测区号"] + [f"R{i}" for i in range(1, 17)] + [
            "Rm", "d1", "d2", "d3", "d平均值", "角度修正", "浇筑面修正", "测区强度(MPa)"
        ]
        ws.append(header)
        # 表头样式
        for col_idx in range(1, len(header) + 1):
            cell = ws.cell(row=len(info_data) + 2, column=col_idx)
            cell.font = Font(bold=True)
            cell.alignment = center_align
            cell.border = thin_border

        # ---- 写入测区数据 ----
        for zone in sorted(comp["测区"], key=lambda x: x["测区号"]):
            row_data = [zone["测区号"]]
            # 16 个回弹值
            for i in range(16):
                val = zone["回弹值"][i] if i < len(zone["回弹值"]) else ""
                row_data.append(val)
            row_data.extend([
                zone.get("Rm", ""),
                zone.get("d1", ""),
                zone.get("d2", ""),
                zone.get("d3", ""),
                zone.get("d_mean", ""),
                zone.get("角度修正", ""),
                zone.get("浇筑面修正", ""),
                zone.get("测区强度", ""),
            ])
            ws.append(row_data)

        # 设置列宽
        for col in range(1, 20):
            col_letter = chr(64 + col) if col <= 26 else "A" + chr(64 + col - 26)
            ws.column_dimensions[col_letter].width = 6 if col >= 2 and col <= 17 else 12

    wb.save(output_path)
    print(f"✅ Excel 文件已生成：{output_path}")


# ---------- 主控制模块 ----------
def convert_word_to_excel(word_path, excel_path=None):
    """
    统一入口：自动识别 .doc 或 .docx，转换并导出 Excel
    """
    word_path = Path(word_path)
    if excel_path is None:
        excel_path = word_path.with_suffix(".xlsx")

    # 处理 .doc 文件
    if word_path.suffix.lower() == ".doc":
        print("检测到 .doc 格式，尝试自动转换为 .docx ...")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_docx = Path(tmpdir) / (word_path.stem + ".docx")
                doc_to_docx(str(word_path), str(tmp_docx))
                print("转换成功，开始解析...")
                data = parse_word_to_data(str(tmp_docx))
        except Exception as e:
            print(f"❌ 自动转换失败：{e}")
            print("💡 请手动将 .doc 另存为 .docx 后再运行本脚本。")
            return
    else:
        # 直接解析 .docx
        data = parse_word_to_data(str(word_path))

    if not data:
        print("⚠️ 未提取到任何有效数据，请检查 Word 文档格式是否匹配。")
        return

    save_to_excel(data, excel_path)


# ---------- 命令行入口 ----------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("使用方法：python word_to_excel.py <Word文件路径> [输出Excel路径]")
        print("示例：python word_to_excel.py 省检测中心回弹记录.doc")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    convert_word_to_excel(input_file, output_file)