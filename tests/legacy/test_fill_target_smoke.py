# -*- coding: utf-8 -*-
"""离屏冒烟：验证 _resolve_fill_target 按识别类型定位检测项目的各条路径。

用 __new__ 跳过重量级构造，仅装配 _resolve_fill_target / _check_and_load_leaf
依赖的最小组件（controller / tree_panel / sheet_data / current_item），
并 stub 掉表格加载等无关重逻辑。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMainWindow  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from framework.models import DETECTION_DATA  # noqa: E402
from framework.ui.main_window import ReportGeneratorApp  # noqa: E402
from framework.ui.panels import TreePanel  # noqa: E402
from core.app_controller import AppController  # noqa: E402

results = []


def check(desc, got, want):
    ok = got == want
    results.append((desc, ok))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


# ── 最小装配 ──
win = ReportGeneratorApp.__new__(ReportGeneratorApp)
win.controller = AppController()
win.sheet_data = {}
win.current_item = None
win._loading = False
win._default_rows = 3
win.win = QMainWindow()
win.tree_panel = TreePanel()
win.tree_panel.populate(DETECTION_DATA, AppController.make_sheet_key)
win._load_item = lambda key: setattr(win, "current_item", str(key))
win._status = lambda msg: None
win._sync_tabs_to_data = lambda: None


def _fake_get_columns(key):
    return ["数据"]


win._get_columns = _fake_get_columns


def _on_leaf_checked(item, column):
    """最小勾选业务：创建空工作表（模拟真实 _on_tree_item_changed 主路径）"""
    if win._loading:
        return
    key = item.data(0, Qt.UserRole)
    if not key:
        return
    checked = item.checkState(0) == Qt.Checked
    if checked and str(key) not in win.sheet_data:
        win.sheet_data[str(key)] = [["" for _ in range(1)]
                                    for _ in range(win._default_rows)]
        win._load_item(str(key))


win.tree_panel.itemCheckChanged.connect(_on_leaf_checked)

# 多命中/手选弹窗在 offscreen 下会阻塞：用桩替换 QInputDialog.getItem
import framework.ui.main_window as mw  # noqa: E402

_dialog_calls = []


def _fake_get_item(parent, title, label, items, current=0, editable=True):
    _dialog_calls.append({"title": title, "items": list(items)})
    return (items[0] if items else "", False)  # 一律模拟“取消”


mw.QInputDialog.getItem = staticmethod(_fake_get_item)

# ── 场景1：当前激活表类型一致 → 直接沿用 ──
key_wall = "回弹法检测(主要来源为仪器数据，可选用)（墙）"
win.sheet_data[key_wall] = [[""] * 8]
win.current_item = key_wall
check("当前表类型一致沿用", win._resolve_fill_target("回弹法检测"), key_wall)

# ── 场景2：当前表类型不一致，已建表唯一包含命中 → 跳转 ──
key_beam = "回弹法检测(主要来源为仪器数据，可选用)（梁）"
win.sheet_data = {key_beam: [[""] * 8]}
win.current_item = "剪力墙构件钢筋间距检测"  # 类型无关的当前表
check("已建表唯一包含命中", win._resolve_fill_target("回弹法检测"), key_beam)

# ── 场景3：识别类型未建表、树内多构件命中 → 弹窗列出全部构件，取消返回 None ──
win.sheet_data = {key_wall: [[""] * 8], key_beam: [[""] * 8]}
win.current_item = "剪力墙构件钢筋间距检测"
_dialog_calls.clear()
got = win._resolve_fill_target("回弹法检测")
check("多构件命中弹窗选择（取消=None）", got, None)
opts = _dialog_calls[0]["items"] if _dialog_calls else []
check("弹窗列出回弹法4个构件工作表", len(opts) == 4 and
      all("回弹法检测" in o for o in opts), True)

# ── 场景4：识别类型与树内无构件项目唯一命中 → 自动勾选建表并跳转 ──
lonely = [(iname, key) for cat, items in DETECTION_DATA.items()
          for iname, comps in items.items() if not comps
          for key in [iname]]
print("无构件检测项目：", [n for n, _ in lonely][:5])
assert lonely, "树中应存在无构件的检测项目"
target_name, target_key = lonely[0]
win.sheet_data.pop(target_key, None)
win.current_item = key_beam
_dialog_calls.clear()
got = win._resolve_fill_target(target_name)
check("无构件项目自动勾选建表跳转", got, target_key)
check("已创建该工作表", target_key in win.sheet_data, True)
check("已切换到该工作表", win.current_item, target_key)

# ── 场景5：完全未知类型 → 弹手选框（已打开表非空），取消返回 None ──
_dialog_calls.clear()
got = win._resolve_fill_target("不存在的检测项目XYZ")
check("未知类型弹手选框（取消=None）", got, None)
check("手选框列出已打开工作表",
      _dialog_calls and set(_dialog_calls[0]["items"]) == set(win.sheet_data),
      True)

# ── 场景6：空类型 → None（不弹窗）──
_dialog_calls.clear()
check("空类型返回None", win._resolve_fill_target(""), None)
check("空类型不弹窗", _dialog_calls, [])

ok_all = all(r[1] for r in results)
print("\n结果：", "ALL PASS" if ok_all else "HAS FAILURES")
sys.exit(0 if ok_all else 1)
