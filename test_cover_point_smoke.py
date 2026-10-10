# -*- coding: utf-8 -*-
"""离屏冒烟：钢筋保护层测点录入功能全链路验证。

1. CoverPointEntryDialog：读数→平均值自动计算 / 无效组(差>1mm)标红统计 /
   添加构件 / get_records / get_header；
2. CoverThicknessMixin._open_cover_point_entry：stub 对话框与 COM，
   验证"定位工作表→追加平均值行→自动计算→生成记录"流程；
3. word_record.fill_cover_original_record：真实 WPS/Word COM 填充模板
   （COM 不可用时 SKIP，不判失败）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from modules.cover_thickness import point_dialog as pd_mod  # noqa: E402
from modules.cover_thickness import word_record as wr_mod  # noqa: E402
from modules.cover_thickness.handlers import CoverThicknessMixin  # noqa: E402
from modules.cover_thickness.point_dialog import CoverPointEntryDialog  # noqa: E402
from framework.resources import get_asset  # noqa: E402

results = []


def check(desc, ok):
    results.append((desc, ok))
    print(("PASS" if ok else "FAIL"), desc)


# ═══ 1. 对话框逻辑 ═══
PROJECTS = ["混凝土梁保护层厚度检测", "剪力墙保护层厚度检测"]
dlg = CoverPointEntryDialog(PROJECTS, defaults={"工程名称": "测试工程", "楼栋": "1#"})
check("对话框构建（项目下拉/默认值）",
      dlg.cmb_project.count() == 2
      and dlg.ed_project_name.text() == "测试工程"
      and dlg.ed_building.text() == "1#")

dlg.cmb_project.setCurrentIndex(0)
dlg.ed_position.setText("2层FL-3")
dlg.ed_axis.setText("1/A")
dlg.sp_design.setValue(15.0)
dlg.sp_rebars.setValue(2)
readings = [
    ["15.0", "15.4", "16.0", "16.2", "15.5", "15.3"],   # 均值 15.57→15.6
    ["20.5", "21.5", "22.0", "22.4", "21.0", "21.2"],   # 均值 21.43→21.4
]
from PyQt5.QtWidgets import QTableWidgetItem  # noqa: E402

for r, row in enumerate(readings):
    for c, v in enumerate(row):
        if dlg.table.item(r, c) is None:   # 空白读数格无 item，程序化填入需先创建
            dlg.table.setItem(r, c, QTableWidgetItem())
        dlg.table.item(r, c).setText(v)
for r in range(2):
    dlg._refresh_row(r)   # 离屏下 currentRow 不随编辑移动，显式刷新
check("平均值自动计算",
      dlg.table.item(0, 6).text() == "15.6"
      and dlg.table.item(1, 6).text() == "21.4")

# 无效组：第0行 端部① 两读数差 >1mm
dlg.table.item(0, 0).setText("15.0")
dlg.table.item(0, 1).setText("17.0")
check("无效组(差>1mm)统计", dlg._invalid_group_count() == 1)
# 还原有效读数
dlg.table.item(0, 1).setText("15.4")
check("无效组还原后清零", dlg._invalid_group_count() == 0)

pd_mod.QMessageBox.question = staticmethod(lambda *a, **k: pd_mod.QMessageBox.Yes)
dlg._add_component()
check("添加构件→get_records",
      len(dlg.get_records()) == 1
      and dlg.get_records()[0]["project"] == "混凝土梁保护层厚度检测"
      and dlg.get_records()[0]["position"] == "2层FL-3"
      and dlg.get_records()[0]["axis"] == "1/A"
      and dlg.get_records()[0]["design"] == 15.0
      and dlg.get_records()[0]["n_rebars"] == 2
      and dlg.get_records()[0]["averages"] == ["15.6", "21.4"]
      and len(dlg.get_records()[0]["readings"]) == 2)
check("添加后测点表清空（连续录入）",
      all((dlg.table.item(r, c).text() if dlg.table.item(r, c) else "") == ""
          for r in range(dlg.table.rowCount()) for c in range(6)))
check("get_header", dlg.get_header()["工程名称"] == "测试工程")

# ═══ 2. 处理器流程（stub 对话框 + COM）═══
records = [
    {"project": "混凝土梁保护层厚度检测", "building": "1#",
     "component_name": "1#楼2层框架梁", "position": "2层FL-3", "axis": "1/A",
     "design": 15.0, "n_rebars": 2,
     "readings": [["15.0", "15.4", "16.0", "16.2", "15.5", "15.3"],
                  ["20.5", "21.5", "22.0", "22.4", "21.0", "21.2"]],
     "averages": ["15.6", "21.4"]},
    {"project": "剪力墙保护层厚度检测", "building": "1#",
     "component_name": "1#楼墙", "position": "3层Q1", "axis": "2-3/B",
     "design": 15.0, "n_rebars": 1,
     "readings": [["12.0", "12.2", "12.5", "12.3", "12.1", "12.4"]],
     "averages": ["12.3"]},
]


class StubDialog:
    def __init__(self, project_keys, parent=None, defaults=None):
        pass

    def exec_(self):
        return 1  # Accepted

    def get_records(self):
        return records

    def get_header(self):
        return {"检测编号": "JJ0226014", "工程名称": "测试工程",
                "检测日期": "2026年09月21日"}


pd_mod.CoverPointEntryDialog = StubDialog
com_calls = []
real_fill = wr_mod.fill_cover_original_record   # 保存真函数供第3部分 COM 冒烟用
wr_mod.fill_cover_original_record = (
    lambda tpl, comps, header=None: (com_calls.append((tpl, comps, header))
                                     or ("OUT.doc", [])) or "OUT.doc")
from PyQt5.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)

mixin = object.__new__(CoverThicknessMixin)
mixin.win = None
mixin.sheet_data = {}
mixin.current_item = None
mixin._resolve_fill_target = (
    lambda name: "混凝土梁保护层厚度检测" if "梁" in name else "剪力墙保护层厚度检测")
mixin._sync_table_to_data = lambda: None
mixin._trim_empty_tail_rows = lambda data: list(data)
mixin._load_item = lambda key: setattr(mixin, "current_item", key)
mixin._run_current_calc = lambda: setattr(mixin, "calc_ran", True)
mixin._status = lambda msg: setattr(mixin, "last_status", msg)

mixin._open_cover_point_entry()

beam = mixin.sheet_data.get("混凝土梁保护层厚度检测", [])
wall = mixin.sheet_data.get("剪力墙保护层厚度检测", [])
check("回填梁行：楼栋/位置/轴号/设计值/根数+2均值+空偏差区",
      len(beam) == 1 and beam[0][:5] == ["1#", "2层FL-3", "1/A", 15.0, 2]
      and beam[0][5:7] == [15.6, 21.4]
      and all(v == "" for v in beam[0][7:26]))
check("回填墙行", len(wall) == 1 and wall[0][5:6] == [12.3])
check("自动计算已触发", getattr(mixin, "calc_ran", False))
check("COM stub 被调用（模板存在+2构件+抬头）",
      len(com_calls) == 1
      and os.path.isfile(str(com_calls[0][0]))
      and len(com_calls[0][1]) == 2
      and com_calls[0][2]["检测编号"] == "JJ0226014")
check("状态栏提示", "回填 2" in getattr(mixin, "last_status", ""))

# ═══ 3. 真实 COM 冒烟（WPS/Word 可用时）═══
try:
    template = get_asset(*wr_mod.TEMPLATE_ASSET, must_exist=True)
    out_path, warnings = real_fill(
        str(template), records[:1],
        header={"检测编号": "JJ0226014", "工程名称": "冒烟测试工程",
                "检测日期": "2026年09月21日"})
    ok = os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    check("COM 生成原始记录 .doc（%s, %d字节, 警告%d条）"
          % (os.path.basename(out_path),
             os.path.getsize(out_path) if os.path.isfile(out_path) else 0,
             len(warnings)), ok)
    for w in warnings:
        print("   warn:", w)

    # 重新打开生成文件，逐格验证
    app2 = wr_mod._dispatch_app()
    app2.Visible = False
    doc2 = app2.Documents.Open(os.path.abspath(out_path), ReadOnly=True)
    try:
        t1 = doc2.Tables(1)
        rows = wr_mod._rows_map(t1)
        texts = {ri: wr_mod._texts(cells) for ri, cells in rows.items()}
        check("信息区：工程名称/检测日期填充",
              "冒烟测试工程" in texts.get(1, [])
              and "2026年09月21日" in texts.get(3, []))
        check("构件组首行(13格)：信息+读数+平均+偏差+合格点率",
              texts.get(12, []) == ['1#楼2层框架梁', '2层FL-3', '15', '2',
                                    '15', '15.4', '16', '16.2', '15.5',
                                    '15.3', '15.6', '+0.6', '100.0%/+6.4'])
        check("续行(8格)：读数+平均+偏差",
              texts.get(13, []) == ['20.5', '21.5', '22', '22.4', '21',
                                    '21.2', '21.4', '+6.4'])
        check("组合并生效：第13行失去信息列(8格)、空行14保持13格",
              len(rows.get(13, [])) == 8 and len(rows.get(14, [])) == 13)
    finally:
        doc2.Close(SaveChanges=False)
        app2.Quit()
except Exception as e:  # noqa: BLE001 - 本机无 WPS/Word 时跳过
    print("SKIP COM 冒烟：", e)

fails = [d for d, ok in results if not ok]
print("\n%d/%d 项通过" % (len(results) - len(fails), len(results)))
sys.exit(1 if fails else 0)
