# -*- coding: utf-8 -*-
"""表格文件导入（工作表行 / 评定原始数据）。

支持 .xlsx/.xlsm/.csv/.docx；Excel 使用 openpyxl，CSV 使用标准库，
Word 使用 python-docx 读取第一张表。"""
import csv
import io
import os
import re
from datetime import date, datetime

from openpyxl import load_workbook

try:
    from report_generator.utils.report_docx import _norm
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_docx import _norm


class ExcelImportError(Exception):
    pass


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _read_csv(path):
    raw = None
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ExcelImportError("无法识别 CSV 文件编码")
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for row in csv.reader(io.StringIO(raw), dialect):
        rows.append([_cell(v) for v in row])
    return rows


def _read_docx_table(path):
    try:
        from docx import Document
    except ImportError as e:  # noqa: BLE001
        raise ExcelImportError("服务端未安装 python-docx，无法读取 Word") from e
    try:
        doc = Document(path)
    except Exception as e:  # noqa: BLE001
        raise ExcelImportError("无法读取 Word：%s" % e)
    if not doc.tables:
        raise ExcelImportError("Word 中没有可导入的表格")
    table = doc.tables[0]
    rows = []
    for row in table.rows:
        rows.append([_cell(cell.text.strip()) for cell in row.cells])
    return rows


def read_rows(path, sheet_name=None):
    path = os.path.abspath(str(path))
    if not os.path.isfile(path):
        raise ExcelImportError("文件不存在：%s" % path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return _read_csv(path)
    if ext == ".docx":
        return _read_docx_table(path)
    if ext not in (".xlsx", ".xlsm"):
        raise ExcelImportError("仅支持 .xlsx / .xlsm / .csv / .docx 文件")
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001
        raise ExcelImportError("无法读取 Excel：%s" % e)
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([_cell(v) for v in row])
        return rows
    finally:
        wb.close()


def _find_header_row(rows, target_labels, scan=15):
    best = None
    target_norm = [_norm(t) for t in target_labels if str(t).strip()]
    for i, row in enumerate(rows[:scan]):
        values = [_norm(v) for v in row if str(v).strip()]
        if not values:
            continue
        score = sum(1 for t in target_norm if t in values)
        if best is None or score > best[1]:
            best = (i, score)
    if best is None or best[1] < 2:
        raise ExcelImportError("未找到表头行（至少需要匹配 2 个列名）")
    return best[0]


_HEADER_ALIASES = {
    "构件位置及名称": ["构件名称", "构件位置", "位置及名称"],
    "构件名称": ["构件位置及名称"],
    "楼栋": ["楼栋号"],
    "楼栋号": ["楼栋"],
    "构件轴线编号": ["轴线编号", "构件轴号", "轴线"],
    "轴线编号": ["构件轴线编号", "构件轴号", "轴线"],
    "板号": ["板编号"],
}
_HEADER_ALIASES = {_norm(k): [_norm(a) for a in v]
                   for k, v in _HEADER_ALIASES.items()}

# 合并单元格/空白标识列：导入后按上一行向下填充
_FILL_FORWARD_LABELS = {
    "楼栋", "楼栋号", "构件位置及名称", "构件名称", "轴线编号",
    "构件轴线编号", "构件轴号", "构件编号", "批次", "楼层", "板号",
    "设计值", "设计值(mm)", "设计等级", "设计强度等级", "钢筋根数",
}


def _match_headers(source_headers, target_columns):
    source_norm = [_norm(h) for h in source_headers]
    mapping = {}
    used = set()
    for ti, target in enumerate(target_columns):
        tn = _norm(target)
        candidates = [tn] + _HEADER_ALIASES.get(tn, [])
        found = None
        for cand in candidates:
            for si, sn in enumerate(source_norm):
                if si in used:
                    continue
                if sn and sn == cand:
                    found = si
                    break
            if found is not None:
                break
        if found is None:
            for cand in candidates:
                for si, sn in enumerate(source_norm):
                    if si in used:
                        continue
                    if sn and (sn.startswith(cand) or cand.startswith(sn)):
                        found = si
                        break
                if found is not None:
                    break
        if found is not None:
            mapping[ti] = found
            used.add(found)
    return mapping


def _pick_sheet(path, columns, preferred_name=None, scan=15):
    """多工作表 Excel：优先同名工作表，否则按表头匹配度自动选择。"""
    wb = load_workbook(path, data_only=True, read_only=True)
    best = (None, 0)
    try:
        if preferred_name and preferred_name in wb.sheetnames:
            ws = wb[preferred_name]
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                rows.append([_cell(v) for v in row])
                if i >= scan:
                    break
            try:
                header_idx = _find_header_row(rows, columns, scan=scan)
            except ExcelImportError:
                header_idx = None
            if header_idx is not None:
                return preferred_name
        for name in wb.sheetnames:
            ws = wb[name]
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                rows.append([_cell(v) for v in row])
                if i >= scan:
                    break
            try:
                header_idx = _find_header_row(rows, columns, scan=scan)
            except ExcelImportError:
                continue
            mapping = _match_headers(rows[header_idx], columns)
            if len(mapping) > best[1]:
                best = (name, len(mapping))
    finally:
        wb.close()
    if not best[0] or best[1] < 2:
        raise ExcelImportError("工作簿中没有找到与当前工作表列匹配的工作表")
    return best[0]


# 供统一采集入口（webapp/backend/ingest.py）复用的匹配原语，
# 保证「文件表头怎么找、怎么对上列」只有一份实现。
match_headers = _match_headers
find_header_row = _find_header_row


def import_sheet_rows(path, columns, sheet_name=None, preferred_name=None):
    """把表格文件按列头匹配到工作表列。

    支持 Excel（多表自动选最匹配表）、CSV、Word 第一张表。
    """
    ext = os.path.splitext(str(path))[1].lower()
    if not sheet_name and ext in (".xlsx", ".xlsm"):
        sheet_name = _pick_sheet(path, columns, preferred_name)
    rows = read_rows(path, sheet_name)
    if not rows:
        raise ExcelImportError("文件为空")
    header_idx = _find_header_row(rows, columns)
    headers = rows[header_idx]
    mapping = _match_headers(headers, columns)
    if not mapping:
        raise ExcelImportError("文件表头与当前工作表列没有匹配项")
    warnings = []
    for ti, target in enumerate(columns):
        if ti not in mapping:
            warnings.append("源文件中未找到列：%s（导入后留空）" % target)
    matched_source = set(mapping.values())
    for si, header in enumerate(headers):
        if str(header).strip() and si not in matched_source:
            warnings.append("源文件列未导入：%s" % header)
    data_rows = []
    for row in rows[header_idx + 1:]:
        if not any(str(v).strip() for v in row):
            continue
        out = []
        for ti in range(len(columns)):
            si = mapping.get(ti)
            out.append(row[si] if si is not None and si < len(row) else "")
        data_rows.append(out)
    # 合并单元格在 Excel 中只有首行有值；对标识列向下填充
    fill_indices = [ti for ti, target in enumerate(columns)
                    if _norm(target) in _FILL_FORWARD_LABELS]
    last = {}
    filled = 0
    for row in data_rows:
        for ti in fill_indices:
            value = row[ti]
            if str(value).strip():
                last[ti] = value
            elif ti in last:
                row[ti] = last[ti]
                filled += 1
    if filled:
        warnings.append("已对合并/空白标识列向下填充 %d 处" % filled)
    return {"rows": data_rows, "warnings": warnings,
            "matched": len(mapping), "columns": list(columns)}


_REBOUND_FIELDS = {
    "floor": ["楼层", "层"],
    "component_type": ["构件类型", "构件类别", "类型"],
    "component_code": ["构件编号", "构件名称", "构件"],
    "axis": ["轴线", "轴线编号", "构件轴号", "构件轴线编号"],
    "grade": ["设计强度等级", "设计等级", "强度等级"],
    "diameter": ["芯样直径", "芯样直径(mm)", "直径", "直径(mm)"],
}


def _field_map(headers):
    source_norm = [_norm(h) for h in headers]
    out = {}
    for key, names in _REBOUND_FIELDS.items():
        for name in names:
            target = _norm(name)
            for i, sn in enumerate(source_norm):
                if sn == target:
                    out[key] = i
                    break
            if key in out:
                break
    return out


def _zone_columns(headers):
    """返回 [(index, order)]，支持“测区1/测区换算值/测区值”。"""
    out = []
    for i, header in enumerate(headers):
        text = str(header or "").strip()
        if not text:
            continue
        norm = _norm(text)
        if not norm.startswith("测区"):
            continue
        if "数" in norm and "值" not in norm:
            continue
        m = re.search(r"(\d+)$", norm)
        order = int(m.group(1)) if m else 0
        out.append((i, order))
    return sorted(out, key=lambda x: x[1])


def _parse_zone_cell(value, single):
    if single:
        text = str(value or "").replace("，", ",")
        parts = re.split(r"[,、;；\s]+", text)
    else:
        parts = [value]
    out = []
    for part in parts:
        if str(part).strip() in ("", "/", "—", "-"):
            continue
        try:
            out.append(float(part))
        except (TypeError, ValueError):
            continue
    return out


def import_rebound_input(path, sheet_name=None):
    """导入回弹法原始数据：楼层/构件类型/编号/轴号/等级/测区换算值。"""
    rows = read_rows(path, sheet_name)
    if not rows:
        raise ExcelImportError("Excel 为空")
    target_labels = []
    for names in _REBOUND_FIELDS.values():
        target_labels.extend(names)
    header_idx = _find_header_row(rows, target_labels)
    headers = rows[header_idx]
    fields = _field_map(headers)
    zones = _zone_columns(headers)
    if not zones:
        raise ExcelImportError("未找到“测区1/测区2…”或“测区换算值”列")
    single = len(zones) == 1
    warnings = []
    components = []
    last_values = {}
    for row_no, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if not any(str(v).strip() for v in row):
            continue
        values = []
        for idx, _order in zones:
            values.extend(_parse_zone_cell(row[idx] if idx < len(row) else "", single))
        if not values:
            warnings.append("第 %d 行没有有效测区值，已跳过" % row_no)
            continue
        def get(key):
            idx = fields.get(key)
            value = row[idx] if idx is not None and idx < len(row) else ""
            if str(value).strip():
                last_values[key] = value
            return value if str(value).strip() else last_values.get(key, "")
        components.append({
            "floor": str(get("floor") or "").strip(),
            "component_type": str(get("component_type") or "").strip(),
            "component_code": str(get("component_code") or "").strip(),
            "axis": str(get("axis") or "").strip(),
            "grade": str(get("grade") or "").strip(),
            "zones": values,
        })
    if not components:
        raise ExcelImportError("没有导入到有效构件（测区换算值列均为空）")
    return {"input": {"components": components}, "warnings": warnings,
            "components": len(components)}


def _core_columns(headers):
    """返回 [(actual_idx, zone_idx, order)]，支持芯样实测强度N + 对应测区值N。"""
    actual = {}
    zone = {}
    for i, header in enumerate(headers):
        text = str(header or "").strip()
        norm = _norm(text)
        if not norm:
            continue
        m = re.search(r"(\d+)$", norm)
        order = int(m.group(1)) if m else 0
        if ("芯样" in norm and ("强度" in norm or "实测" in norm)):
            actual[order] = i
        elif ("对应测区" in norm or "测区换算" in norm or "测区值" in norm):
            zone[order] = i
    pairs = []
    for order in sorted(set(actual) & set(zone)):
        pairs.append((actual[order], zone[order], order))
    return pairs


def import_rebound_core_input(path, sheet_name=None):
    rows = read_rows(path, sheet_name)
    if not rows:
        raise ExcelImportError("Excel 为空")
    target_labels = []
    for names in _REBOUND_FIELDS.values():
        target_labels.extend(names)
    header_idx = _find_header_row(rows, target_labels)
    headers = rows[header_idx]
    fields = _field_map(headers)
    zones = _zone_columns(headers)
    cores = _core_columns(headers)
    if not zones:
        raise ExcelImportError("未找到测区换算值列")
    if not cores:
        raise ExcelImportError("未找到成对芯样列（如“芯样实测强度1”+“对应测区值1”）")
    warnings = []
    components = []
    last_values = {}
    for row_no, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if not any(str(v).strip() for v in row):
            continue
        values = []
        for idx, _order in zones:
            values.extend(_parse_zone_cell(row[idx] if idx < len(row) else "", len(zones) == 1))
        core_pairs = []
        for ai, zi, _order in cores:
            try:
                actual = float(row[ai])
                zone = float(row[zi])
            except (TypeError, ValueError, IndexError):
                continue
            if abs(zone) > 1e-9:
                core_pairs.append({"actual": actual, "zone": zone})
        if not values:
            warnings.append("第 %d 行没有有效测区值，已跳过" % row_no)
            continue
        def get(key):
            idx = fields.get(key)
            value = row[idx] if idx is not None and idx < len(row) else ""
            if str(value).strip():
                last_values[key] = value
            return value if str(value).strip() else last_values.get(key, "")
        try:
            diameter = float(get("diameter"))
        except (TypeError, ValueError):
            diameter = None
        components.append({
            "floor": str(get("floor") or "").strip(),
            "component_type": str(get("component_type") or "").strip(),
            "component_code": str(get("component_code") or "").strip(),
            "axis": str(get("axis") or "").strip(),
            "grade": str(get("grade") or "").strip(),
            "zones": values,
            "cores": core_pairs,
            "diameter": diameter,
        })
    if not components:
        raise ExcelImportError("没有导入到有效构件")
    return {"input": {"components": components}, "warnings": warnings,
            "components": len(components)}


def import_assessment_input(path, family, sheet_name=None):
    if family == "rebound":
        return import_rebound_input(path, sheet_name)
    if family == "rebound_core":
        return import_rebound_core_input(path, sheet_name)
    raise ExcelImportError("该检测项不使用原始数据 Excel 导入，请用工作表导入")
