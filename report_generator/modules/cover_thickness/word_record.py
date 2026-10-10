# -*- coding: utf-8 -*-
"""钢筋保护层厚度检测原始记录生成（WPS/Word COM 填充 HBJG/JJ 0226014 模板）。

模板真实结构（经 COM 逆向确认，每页一个大表格）：
    信息区：每行 4 格 = [标签1, 值1, 标签2, 值2]，日期值格为"年 月 日"占位符；
    数据表头 3 行：构件名称|构件轴号(检验部位)|设计值|主筋数量|
        实测值(端部1/2 跨中1/2 端部1/2)|偏差值|合格点率/最大偏差值；
    数据区：每行 = 1 根主筋（13 格行或 8 格续行），其中列 1-4 与列 13
        纵向合并跨整个数据区（首行 13 格，续行 8 格：6 读数+平均值+偏差值）。

写入策略：先把数据区列 1-4/13 的纵向合并 Split 拆分为逐行单元格，
逐行写入读数/平均值/偏差值、组首行写入构件信息与合格点率，
再按构件把列 1-4/13 Merge 回纵向合并（跨该构件的全部主筋行）。

业务规则（模板备注）：
- 同一位置检测 2 次，两次读数差 >1mm 该组检测数据无效；
- 实测偏差值 = 实测平均值 - 设计值；合格点率 = 合格测点数÷总测点数；
- 不合格测点用下划线标明。
"""
import os
import re
from datetime import datetime

# 数据行 13 格布局的 0-based 位置（拆分后所有数据行统一 13 格）
POS_NAME = 0     # 构件名称
POS_AXIS = 1     # 构件轴号(检验部位)
POS_DESIGN = 2   # 保护层厚度设计值(mm)
POS_COUNT = 3    # 主筋数量(根)
POS_RD1 = 4      # 读数1~6 → 位置 4~9
POS_AVG = 10     # 平均值
POS_DEV = 11     # 实测偏差值(mm)
POS_RATE = 12    # 合格点率/最大偏差值
# 纵向合并的列位置（构件信息 + 合格点率）
MERGED_POSITIONS = (POS_NAME, POS_AXIS, POS_DESIGN, POS_COUNT, POS_RATE)

# 允许偏差区间（与 calc_rules.py 一致）：{类型关键词: (lower, upper)}
ALLOW_RANGES = [('剪力墙', (-5.0, 8.0)), ('板', (-5.0, 8.0)),
                ('梁', (-7.0, 10.0)), ('柱', (-7.0, 10.0))]

# 表头信息字段（模板信息区标签 → 回填键）
HEADER_LABELS = ('工程名称', '委托单位', '建设单位', '设计单位', '施工单位',
                 '见证单位', '施工日期', '委托日期', '检测日期', '检测类别',
                 '检测地点', '检测依据', '检测设备')

# 日期占位符（"       年    月    日"）视为可覆盖的空值
_DATE_PLACEHOLDER = re.compile(r'^[\s年月日]*$')

WD_UNDERLINE_SINGLE = 1
WD_FORMAT_DOC97 = 0

# 模板在 assets 下的相对路径（配合 framework.resources.get_asset 使用）
TEMPLATE_ASSET = ('原始记录模板',
                  '钢筋保护层厚度检测原始记录(HBJG-JJ0226014).doc')


def _default_out_dir():
    """默认输出目录：original_record/word/generated。"""
    from framework.resources import resolve_path
    out = resolve_path('original_record', 'word', 'generated')
    os.makedirs(str(out), exist_ok=True)
    return str(out)


def allow_range_for(project):
    """按检测项目名取允许偏差区间 (lower, upper)。"""
    name = str(project or '')
    for key, rng in ALLOW_RANGES:
        if key in name:
            return rng
    return (-7.0, 10.0)


def _clean(text):
    """去掉 Word 单元格结束符与空白。"""
    return str(text).replace('\r\x07', '').replace('\x07', '').strip()


def _fmt_num(value):
    """数值转显示文本（整数不带小数点，其余保留 1 位）。"""
    f = float(value)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return '%.1f' % f


def _fmt_signed(value):
    """偏差值带符号显示（+x / -x / 0）。"""
    f = float(value)
    s = _fmt_num(abs(f))
    if f > 1e-9:
        return '+' + s
    if f < -1e-9:
        return '-' + s
    return s


def _dispatch_app():
    """优先 WPS（模板由 WPS 制作），回退 Word；都不可用抛可读异常。"""
    import win32com.client
    last = None
    for prog_id in ('KWPS.Application', 'Word.Application'):
        try:
            return win32com.client.Dispatch(prog_id)
        except Exception as e:  # noqa: BLE001 - 记录最后一次失败原因
            last = e
    raise RuntimeError(
        '未找到可用的 WPS/Word COM 组件（KWPS.Application / Word.Application），'
        '请安装 WPS Office 或 Microsoft Word 后重试。原因：%s' % last)


# ── 表格结构读取（兼容垂直合并：只能用 Range.Cells 遍历）──
def _rows_map(table):
    """把表格所有单元格按行分组：{RowIndex: [Cell, ...] }（文档从左到右序）。

    表格含垂直合并时 Rows(r)/Cell(r,c) 会抛 COM 错误，Range.Cells 是唯一
    可靠入口；纵向合并的单元格归属其起始行。
    """
    rows = {}
    for cell in table.Range.Cells:
        rows.setdefault(cell.RowIndex, []).append(cell)
    return rows


def _texts(cells):
    return [_clean(c.Range.Text) for c in cells]


def _find_data_tables(doc):
    """定位各表数据区，返回 [(rows, data_start, data_end), ...]。

    数据表头 = 含"构件轴号"的行；其下第 3 行起为数据区（标签行 +
    端部/跨中行 + 1/2 行），直到单元格数不为 8/13 的行（结论/备注行）。
    """
    out = []
    for table in doc.Tables:
        rows = _rows_map(table)
        header_row = None
        for ri in sorted(rows):
            if any('构件轴号' in t for t in _texts(rows[ri])):
                header_row = ri
                break
        if header_row is None:
            continue
        start = header_row + 3
        end = None
        ri = start
        while ri in rows and len(rows[ri]) in (8, 13):
            end = ri
            ri += 1
        if end is not None:
            out.append((rows, start, end))
    if not out:
        raise RuntimeError('模板中未找到数据表（未定位到"构件轴号"表头）。')
    return out


def _fill_header_fields(doc, header, warnings):
    """填充信息区：标签右侧相邻单元格（空值或"年 月 日"占位符才写入）。"""
    targets = {}
    for key in HEADER_LABELS:
        val = str((header or {}).get(key) or '').strip()
        if val:
            targets[key] = val
    if not targets:
        return
    for table in doc.Tables:
        rows = _rows_map(table)
        for cells in rows.values():
            texts = _texts(cells)
            for i, text in enumerate(texts):
                key = text.rstrip('：:').strip()
                if key in targets and i + 1 < len(cells):
                    cur = texts[i + 1]
                    if cur == '' or _DATE_PLACEHOLDER.match(cur):
                        try:
                            cells[i + 1].Range.Text = targets[key]
                        except Exception as e:  # noqa: BLE001
                            warnings.append('表头字段「%s」填充失败：%s'
                                            % (key, e))


def _unmerge_data_area(rows, data_start, data_end):
    """把数据区列 1-4/13 的纵向合并拆成逐行单元格（Split）。

    模板每页数据区只有一个大合并块（首行 13 格、续行 8 格）；按组起止
    行数对 5 个合并单元格分别 Split(NumRows=跨度, NumColumns=1)。
    """
    group_starts = [ri for ri in sorted(rows)
                    if data_start <= ri <= data_end and len(rows[ri]) == 13]
    for gs in group_starts:
        nxt = [ri for ri in group_starts if ri > gs]
        span = (nxt[0] if nxt else data_end + 1) - gs
        if span <= 1:
            continue
        for pos in MERGED_POSITIONS:
            if pos < len(rows[gs]):
                try:
                    rows[gs][pos].Split(NumRows=span, NumColumns=1)
                except Exception as e:  # noqa: BLE001
                    raise RuntimeError(
                        '模板数据区拆分失败（第 %d 行第 %d 列）：%s'
                        % (gs, pos + 1, e))


def _write_component_group(rows, r, comp, warnings):
    """从 r 行起写入一个构件的主筋组（rows 已全部拆分为 13 格行）。"""
    rng = allow_range_for(comp.get('project'))
    n = len(comp['readings'])
    start_cells = rows[r]
    devs = []
    qualified = 0
    for i in range(n):
        rowcells = rows[r + i]
        if len(rowcells) < POS_DEV + 1:
            warnings.append('第 %d 行单元格结构异常（%d 格），跳过。'
                            % (r + i, len(rowcells)))
            continue
        readings = comp['readings'][i]
        # 同一位置两次读数差 >1mm → 该组无效（平均值/偏差留空并告警）
        invalid = False
        for a, b in ((0, 1), (2, 3), (4, 5)):
            try:
                if readings[a] != '' and readings[b] != '' \
                        and abs(float(readings[a]) - float(readings[b])) > 1.0:
                    invalid = True
            except (TypeError, ValueError):
                pass
        if invalid:
            warnings.append('构件「%s」第 %d 根主筋存在两次读数差>1mm 的检测组，'
                            '按模板规则该组数据无效，平均值/偏差留空。'
                            % (comp.get('position') or comp.get('axis'),
                               i + 1))
        blank = any(str(v).strip() == '' for v in readings)
        avg = comp['averages'][i] if not blank and not invalid else ''
        dev = ''
        fail = False
        if avg != '':
            dev = _fmt_signed(float(avg) - float(comp['design']))
            fdev = float(dev)
            devs.append(fdev)
            fail = not (rng[0] <= fdev <= rng[1])
            if not fail:
                qualified += 1
        try:
            for j, val in enumerate(readings):
                text = '' if str(val).strip() == '' else _fmt_num(val)
                rowcells[POS_RD1 + j].Range.Text = text
            rowcells[POS_AVG].Range.Text = '' if avg == '' else _fmt_num(avg)
            rowcells[POS_DEV].Range.Text = dev
            if fail:
                rowcells[POS_AVG].Range.Font.Underline = WD_UNDERLINE_SINGLE
                rowcells[POS_DEV].Range.Font.Underline = WD_UNDERLINE_SINGLE
        except Exception as e:  # noqa: BLE001
            warnings.append('第 %d 行填充失败：%s' % (r + i, e))
    # 构件组首行写 构件名称/轴号/设计值/根数/合格点率
    try:
        start_cells[POS_NAME].Range.Text = str(
            comp.get('component_name') or comp.get('building') or '')
        start_cells[POS_AXIS].Range.Text = str(comp.get('position') or '')
        start_cells[POS_DESIGN].Range.Text = _fmt_num(comp['design'])
        start_cells[POS_COUNT].Range.Text = _fmt_num(comp['n_rebars'])
    except Exception as e:  # noqa: BLE001
        warnings.append('构件信息填充失败：%s' % e)
    if devs:
        rate = 100.0 * qualified / len(devs)
        max_dev = max(devs, key=abs)
        try:
            start_cells[POS_RATE].Range.Text = \
                '%.1f%%/%s' % (rate, _fmt_signed(max_dev))
        except Exception as e:  # noqa: BLE001
            warnings.append('合格点率写入失败：%s' % e)


def _merge_component(rows, r, n, warnings):
    """把构件组的列 1-4/13 纵向合并（跨 n 行），续行单元格为空不丢内容。"""
    if n <= 1:
        return
    end = r + n - 1
    for pos in MERGED_POSITIONS:
        try:
            rows[r][pos].Merge(rows[end][pos])
        except Exception as e:  # noqa: BLE001
            warnings.append('构件组合并失败（第 %d 行第 %d 列）：%s'
                            % (r, pos + 1, e))


def fill_cover_original_record(template_path, components, header=None,
                               out_dir=None):
    """填充模板生成原始记录 .doc。

    :param template_path: 模板文件路径
    :param components: 构件列表（point_dialog.get_records() 的输出）
    :param header: 表头信息字段 {标签: 值}（工程名称/检测日期等）
    :param out_dir: 输出目录（默认 original_record/word/generated）
    :return: (生成文件路径, warnings 列表)
    """
    header = dict(header or {})
    warnings = []
    template_path = os.path.abspath(template_path)
    out_dir = os.path.abspath(out_dir or _default_out_dir())
    if not os.path.isfile(template_path):
        raise RuntimeError('模板文件不存在：%s' % template_path)
    os.makedirs(out_dir, exist_ok=True)
    serial = str(header.get('检测编号') or '').strip() or 'COVER'
    out_path = os.path.join(
        out_dir, '钢筋保护层厚度检测原始记录(%s)_%s.doc'
        % (serial, datetime.now().strftime('%Y%m%d%H%M%S')))

    rows_total = sum(len(comp['readings']) for comp in components)
    if rows_total == 0:
        raise RuntimeError('没有可写入的测点数据。')

    app = None
    doc = None
    try:
        app = _dispatch_app()
        try:
            app.DisplayAlerts = 0
        except Exception:  # noqa: BLE001
            pass
        app.Visible = False
        doc = app.Documents.Open(template_path, ReadOnly=True)
        _fill_header_fields(doc, header, warnings)
        found = _find_data_tables(doc)

        # 1) 拆分各表数据区纵向合并 → 全部数据行统一 13 格
        for rows, ds, de in found:
            _unmerge_data_area(rows, ds, de)
        # 2) 拆分后行内格数已变，重建映射（第 i 个 found 对应第 i 张表）
        tables = [(_rows_map(doc.Tables(i + 1)), ds, de)
                  for i, (_r, ds, de) in enumerate(found)]

        capacity = sum(de - ds + 1 for _r, ds, de in tables)
        if rows_total > capacity:
            raise RuntimeError(
                '模板数据行不足（共需 %d 行，模板容量 %d 行），'
                '请减少单次录入构件数或分批生成。' % (rows_total, capacity))

        # 2) 逐构件写入
        ti = 0
        cur = tables[0][1]
        for comp in components:
            n = len(comp['readings'])
            while ti < len(tables) and cur + n - 1 > tables[ti][2]:
                ti += 1
                if ti < len(tables):
                    cur = tables[ti][1]
            if ti >= len(tables):
                raise RuntimeError('模板数据行不足（共需 %d 行）。' % rows_total)
            rows, _ds, _de = tables[ti]
            _write_component_group(rows, cur, comp, warnings)
            _merge_component(rows, cur, n, warnings)
            cur += n

        doc.SaveAs(out_path, FileFormat=WD_FORMAT_DOC97)
        return out_path, warnings
    finally:
        try:
            if doc is not None:
                doc.Close(SaveChanges=False)
        finally:
            if app is not None:
                app.Quit()
