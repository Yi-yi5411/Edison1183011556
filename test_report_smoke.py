# -*- coding: utf-8 -*-
"""离线冒烟：验证《检测报告》Word 生成引擎（utils/word_report.py）。

构造回弹法（墙）/钻芯法（梁）/剪力墙钢筋间距/无模板项目四类假数据，
生成报告后用 python-docx 重新打开断言章节、一览表、占位符、结论与
封面人员信息；同时验证项目状态的 report_info 序列化往返。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from utils.word_report import generate_report  # noqa: E402
from core.app_controller import AppController  # noqa: E402

results = []


def check(desc, ok, got=None):
    results.append((desc, ok))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


# ── 假数据 ──
REBOUND_COLS = ['构件名称', '构件轴号', '设计强度等级', '平均强度值(MPa)',
                '标准差(MPa)', '最小测区强度值(MPa)', '强度推定值(MPa)', '龄期(d)']
rebound_rows = [
    ['-1FL梁', '2-3/A-C', 'C30', '35.2', '1.8', '32.1', '32.4', '28'],
    ['1FL梁', '4-5/B-D', 'C30', '36.1', '2.0', '32.8', '33.0', '28'],
    ['2FL梁', '6-7/A-C', 'C30', '34.9', '1.6', '31.9', '32.2', '28'],
    ['3FL梁', '8-9/B-D', 'C30', '35.7', '1.9', '32.5', '32.8', '28'],
    ['4FL梁', '10-11/A-C', 'C30', '36.3', '1.7', '33.1', '33.5', '28'],
]

CORE_COLS = ['楼栋', '批次', '构件编号', '构件位置及名称', '轴线编号', '序号',
             '芯样直径(mm)', '截面积(mm²)', '测试荷载(kN)', '测试强度(MPa)',
             '推定值(MPa)', '批评定值(MPa)', '设计等级']
core_rows = [
    ['1#楼', '1', 'KL-1', '1层框架梁', '2-3/A-C', '1', '76.4', '4584.2', '136.5', '29.77', '29.77', '29.77', 'C30'],
    ['1#楼', '1', 'KL-1', '1层框架梁', '2-3/A-C', '2', '76.4', '4584.2', '140.2', '30.58', '29.77', '29.77', 'C30'],
    ['1#楼', '1', 'KL-1', '1层框架梁', '2-3/A-C', '3', '76.4', '4584.2', '138.9', '30.30', '29.77', '29.77', 'C30'],
    ['1#楼', '1', 'KL-2', '1层框架梁', '4-5/B-D', '4', '76.4', '4584.2', '142.0', '30.97', '30.58', '29.77', 'C30'],
    ['1#楼', '1', 'KL-2', '1层框架梁', '4-5/B-D', '5', '76.4', '4584.2', '141.3', '30.82', '30.58', '29.77', 'C30'],
    ['1#楼', '1', 'KL-2', '1层框架梁', '4-5/B-D', '6', '76.4', '4584.2', '143.1', '31.22', '30.58', '29.77', 'C30'],
    ['', '', '', '', '', '', '', '', '', '', '', '', ''],  # 整行空行应被过滤
]

REBAR_COLS = ['楼栋', '构件位置及名称', '轴线编号', '方向', '设计值',
              '实测值1', '实测值2', '实测值3', '实测值4', '实测值5', '实测值6',
              '实测值平均值', '偏差值1', '偏差值2', '偏差值3', '偏差值4',
              '偏差值5', '偏差值6', '偏差值平均值', '合格点率', '合格/不合格']
rebar_rows = [
    ['1#楼', '2层墙体', '1-2/A', '水平', '200', '201', '200', '199', '202', '200', '198', '200.0',
     '1', '0', '-1', '2', '0', '-2', '1.0', '100%', '合格'],
    ['1#楼', '2层墙体', '3-4/A', '水平', '200', '200', '201', '200', '199', '201', '200', '200.2',
     '0', '1', '0', '-1', '1', '0', '0.2', '100%', '合格'],
    ['1#楼', '2层墙体', '5-6/A', '竖直', '200', '200', '200', '201', '200', '202', '201', '200.7',
     '0', '0', '1', '0', '2', '1', '0.7', '100%', '合格'],
]

STEEL_COLS = ['楼栋', '构件位置及名称', '焊缝编号', '检测部位', '实测值', '结论']
steel_rows = [['1#楼', '钢梁GJ-1', 'HF-1', '跨中', '合格', 'I级']]

sheet_data = {
    '回弹法检测（墙）': rebound_rows,
    '钻芯法检测（梁）': core_rows,
    '剪力墙构件钢筋间距检测': rebar_rows,
    '焊缝超声波探伤检测': steel_rows,   # 无模板 → skipped
}
columns_map = {
    '回弹法检测（墙）': REBOUND_COLS,
    '钻芯法检测（梁）': CORE_COLS,
    '剪力墙构件钢筋间距检测': REBAR_COLS,
    '焊缝超声波探伤检测': STEEL_COLS,
}
report_info = {
    'project_name': '测试工程一号楼',
    'project_location': '武汉市测试区测试路1号',
    'client': '测试委托单位',
    'witness': '测试见证单位',
    'report_no': 'HBJG-2026-001',
    'tester': '张三',
    'test_date': '2026年09月20日~22日',
    'report_date': '2026年09月23日',
}

# ── 生成报告 ──
out_path = os.path.join(tempfile.mkdtemp(prefix='report_smoke_'), '测试报告.docx')
logs = []
result = generate_report(
    '测试工程一号楼', report_info, sheet_data, columns_map,
    checked_order=list(sheet_data.keys()), output_path=out_path,
    on_log=logs.append,
)
print('logs:', logs)
print('result:', result)

check('生成 3 张一览表', result['tables'] == 3, result['tables'])
check('无模板项目被跳过',
      any('焊缝超声波探伤检测' in s for s in result['skipped']),
      result['skipped'])

# ── 重新打开断言 ──
from docx import Document  # noqa: E402

doc = Document(out_path)
all_paras = [p.text for p in doc.paragraphs]
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            all_paras.extend(p.text for p in cell.paragraphs)
full_text = '\n'.join(all_paras)

for heading in ['一、工程概况', '二、主要检测依据', '三、主要检测设备',
                '四、检测内容：', '五、检测结果：', '六、检测结论：']:
    check(f'章节存在：{heading}', any(heading in t for t in all_paras))

check('无残留 {{ 占位符', '{{' not in full_text,
      [t for t in all_paras if '{{' in t][:3])

# 结论句（规则推理：推定值与设计等级比对）
check('回弹法结论句', '经回弹法检测，混凝土墙构件抗压强度推定值为32.2~33.5MPa' in full_text)
check('钻芯法结论句', '经钻芯法检测，混凝土梁构件芯样抗压强度' in full_text)
check('钢筋间距结论句', '经检测，剪力墙构件钢筋间距偏差满足规范允许偏差要求' in full_text)
check('回弹法推理：推定值≥设计C30 → 满足',
      '推定值为32.2~33.5MPa，满足设计强度等级要求' in full_text)
check('钻芯法推理：推定值29.77<设计C30 → 不满足',
      '芯样抗压强度为29.77~30.58MPa，不满足设计强度等级要求，应进行复核处理' in full_text)

# 一览表数量：首页信息表 + 设备表 + 3 张结果表 = 5
check('文档表格数 = 5', len(doc.tables) == 5, len(doc.tables))

# 回弹法一览表：1 表头行 + 5 数据行；真实列序：构件编号(无对应留空)/构件名称/构件轴号/设计等级/平均/标准差/最小测区/推定值
rebound_tbl = next(t for t in doc.tables
                   if any('平均' in c.text and '强度值' in c.text
                          for c in t.rows[0].cells))
check('回弹法表行数 = 6', len(rebound_tbl.rows) == 6, len(rebound_tbl.rows))
check('回弹法表数据写入',
      rebound_tbl.rows[1].cells[0].text.strip() == ''
      and rebound_tbl.rows[1].cells[1].text.strip() == '-1FL梁'
      and rebound_tbl.rows[1].cells[7].text.strip() == '32.4',
      [c.text for c in rebound_tbl.rows[1].cells])
core_tbl = next(t for t in doc.tables
                if any('芯样' in c.text for c in t.rows[0].cells))
check('钻芯法表行数 = 7', len(core_tbl.rows) == 7, len(core_tbl.rows))
check('钻芯法测试强度列对齐',
      core_tbl.rows[1].cells[5].text.strip() == '29.77',
      [c.text for c in core_tbl.rows[1].cells])

# 首页信息表回填（先填充后拼装）
check('首页信息表回填',
      any('测试工程一号楼' in c.text for c in doc.tables[0].rows[0].cells)
      and any('武汉市测试区测试路1号' in c.text for c in doc.tables[0].rows[1].cells),
      [c.text for c in doc.tables[0].rows[0].cells])

# 钢筋间距表：偏差平均值列应为偏差值平均值(1.0)而非实测值平均值，结论列=合格
rebar_tbl = next(t for t in doc.tables
                 if any('实测偏差' in c.text for c in t.rows[0].cells))
check('钢筋间距偏差平均值/结论列对齐',
      any('1.0' in c.text for c in rebar_tbl.rows[2].cells)
      and any(c.text.strip() == '合格' for c in rebar_tbl.rows[2].cells),
      [c.text for c in rebar_tbl.rows[2].cells])

# 封面人员信息回填
check('封面报告编号回填', any('报告编号：HBJG-2026-001' in t for t in all_paras))
check('封面工程名替换', any('测试工程一号楼' in t for t in all_paras[:6]))
# 检测日期区间占位替换（五、检测结果概述）
check('检测日期区间替换',
      any('本公司于2026年09月20日~22日派技术人员' in t for t in all_paras))
check('结论日期替换', '2026年09月23日' in full_text)

# 检测内容清单
check('检测内容清单生成', any('1．回弹法检测（墙）' in t for t in all_paras))

# ── report_info 序列化往返 ──
state = AppController.serialize(
    '测试工程一号楼', sheet_data, {}, {}, {}, {}, None, None,
    report_info=report_info)
check('serialize 含 report_info', state.get('report_info') == report_info)
(_pn, _sd, _m, _mf, _cf, _cd, _notes, _ci, rt_info) = AppController.deserialize(state)
check('deserialize 还原 report_info', rt_info == report_info, rt_info)
# 旧项目文件无 report_info 时向后兼容
(_pn, _sd, _m, _mf, _cf, _cd, _notes, _ci, rt_info2) = AppController.deserialize(
    {'data': {}})
check('旧文件 report_info 默认 {}', rt_info2 == {}, rt_info2)

fails = [d for d, ok in results if not ok]
print('=' * 50)
print(f'{len(results) - len(fails)}/{len(results)} PASS')
if fails:
    print('FAILED:', fails)
    sys.exit(1)
print('报告输出：', out_path)
