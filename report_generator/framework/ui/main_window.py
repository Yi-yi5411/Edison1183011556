# -*- coding: utf-8 -*-
"""主体结构检测数据管理录入系统V1.0 - PyQt5 GUI（类 Excel 电子表格）

替代 tkinter 版本的 gui.py，提供完整的 Excel 风格电子表格编辑能力。
核心特性：基于 QTableWidget.setSpan 的单元格合并。
"""

import sys
import re
import json
import os
from datetime import datetime

from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence, QIcon

from framework.resources import get_asset
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QTableWidget, QTableWidgetItem, QToolBar, QAction, QStatusBar, QLabel,
    QHBoxLayout, QVBoxLayout, QSplitter, QMenu, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView, QShortcut, QInputDialog,
    QDialog, QLineEdit,
)

from framework.ui import MergeTableWidget, DEFAULT_ROWS, ROLE_FORMULA
from framework.ui.delegates import FloorLabelDelegate
from framework.ui.panels import NotesPanel, TreePanel, SheetTabsBar
from framework.ui.grouped_header import GroupedHeaderView
from framework.ui.theme import (
    DEFAULT_FONT, FONT_SIZE, apply_theme, get_saved_theme, save_theme,
)
from modules.concrete_strength.handlers import CoreDrillingMixin
from modules.steel_rebar.handlers import SteelRebarMixin
from modules.concrete_members.handlers import MemberThicknessMixin
from modules.cover_thickness.handlers import CoverThicknessMixin
from framework.ui.handlers import (
    MergeOpsMixin, SelectionMixin, FormatMixin, ClipboardMixin,
    UndoRedoMixin, RowOpsMixin, EditToolsMixin, CalcRulesMixin,
)
from framework.engine import CalcEngine
from core.app_controller import AppController

from framework.models import DETECTION_DATA, PROJECT_NAME, CALC_RULES
from core.plugin_manager import get_plugin_manager
from framework.models.operation_notes import (
    DEFAULT_OPERATION_NOTES, build_default_sheet_notes,
)
from framework.engine.formula import FormulaEngine
from utils.excel_exporter import export_workbook
from utils.word_to_excel import convert_word_to_excel
from utils.word_report import generate_report
from utils.report_agent import generate_report_via_agent
from framework.ui.report_dialog import ReportInfoDialog
from utils.report_template_map import default_report_info
# 注：通用对话框（批量填充/插入行/函数选择器等）由各 UI Mixin 按需自行 import；
# 项目专属对话框（如钻芯法参数输入）由 controller.create_setup_dialog 经插件钩子
# 动态创建，参数确认后的工作表构建由 controller.build_sheet 经插件钩子完成，
# 框架层不直接 import 任何对话框类或构建方法，实现 UI 与插件解耦。


class _ReportWorker(QThread):
    """报告生成后台线程（Agent 模式含多轮 LLM 调用，不能阻塞 UI）。

    日志经 progress 信号回主线程；结束/失败分别经 succeeded/failed。
    """

    progress = pyqtSignal(str)
    succeeded = pyqtSignal(str, dict)   # 输出路径, 结果 dict
    failed = pyqtSignal(str)

    def __init__(self, fn, output_path, parent=None):
        super().__init__(parent)
        self._fn = fn            # fn(on_log) -> 结果 dict
        self._output_path = output_path

    def run(self):
        try:
            result = self._fn(self.progress.emit)
            self.succeeded.emit(self._output_path, result)
        except Exception as e:
            self.failed.emit(str(e))


# 右键菜单配置（数据驱动）：描述菜单结构与动作。
# 顶层条目类型：
#   ("action", 显示文本, 方法名, 参数元组)   普通动作
#   ("submenu", 子菜单名, 子条目列表)        子菜单（子条目同上 action 结构）
#   ("separator",)                          分隔线
# 模块贡献项（如批推定计算）由 _context_menu_hooks 动态插入，不在此配置。
CONTEXT_MENU_ACTIONS = [
    ("action", "复制 (Ctrl+C)", "_copy", ()),
    ("action", "剪切 (Ctrl+X)", "_cut", ()),
    ("action", "粘贴 (Ctrl+V)", "_paste", ()),
    ("action", "格式刷复制 (Ctrl+Shift+C)", "_format_painter_copy", ()),
    ("action", "格式刷粘贴 (Ctrl+Shift+V)", "_format_painter_paste", ()),
    ("separator",),
    ("action", "撤销 (Ctrl+Z)", "_undo", ()),
    ("action", "重做 (Ctrl+Y)", "_redo", ()),
    ("separator",),
    ("action", "合并居中", "_merge_cells", ()),
    ("action", "取消合并", "_unmerge_cells", ()),
    ("separator",),
    ("submenu", "对齐方式", [
        ("action", "左对齐", "_align", ("left",)),
        ("action", "居中", "_align", ("center",)),
        ("action", "右对齐", "_align", ("right",)),
    ]),
    ("separator",),
    ("submenu", "字体", [
        ("action", "加粗 (Ctrl+B)", "_toggle_bold", ()),
        ("action", "斜体 (Ctrl+I)", "_toggle_italic", ()),
        ("action", "下划线 (Ctrl+U)", "_toggle_underline", ()),
        ("action", "字号+", "_font_bigger", ()),
        ("action", "字号-", "_font_smaller", ()),
        ("action", "字体颜色", "_set_font_color", ()),
        ("action", "背景颜色", "_set_bg_color", ()),
    ]),
    ("separator",),
    ("submenu", "边框", [
        ("action", "全部边框", "_set_border", ("all",)),
        ("action", "仅外框", "_set_border", ("outer",)),
        ("action", "仅内框", "_set_border", ("inner",)),
        ("action", "上边框", "_set_border", ("top",)),
        ("action", "下边框", "_set_border", ("bottom",)),
        ("action", "左边框", "_set_border", ("left",)),
        ("action", "右边框", "_set_border", ("right",)),
        ("action", "无边框", "_set_border", ("none",)),
    ]),
    ("separator",),
    ("submenu", "数字格式", [
        ("action", "常规", "_set_number_format", ("general",)),
        ("action", "整数", "_set_number_format", ("int",)),
        ("action", "两位小数", "_set_number_format", ("dec2",)),
        ("action", "百分比", "_set_number_format", ("percent",)),
        ("action", "千分位", "_set_number_format", ("thousands",)),
    ]),
    ("separator",),
    ("action", "上方插入行", "_insert_row_above", ()),
    ("action", "下方插入行", "_insert_row_below", ()),
    ("action", "删除行", "_delete_rows", ()),
    ("action", "清除内容", "_clear_cells", ()),
    ("action", "批量填充 (Ctrl+D)", "_run_batch_fill", ()),
    ("separator",),
    ("action", "查找替换 (Ctrl+H)", "_find_replace", ()),
    ("action", "自动求和", "_auto_sum", ()),
    ("separator",),
    ("action", "函数选择器", "_show_function_selector", ()),
    ("action", "快速汇总", "_show_quick_summary", ()),
    ("action", "批量修改", "_batch_modify", ()),
    ("action", "批量插入行 (Ctrl+Shift+N)", "_batch_insert_rows", ()),
    ("action", "批量调整行高", "_batch_row_height", ()),
]

# 尾部菜单（模块贡献项之后）：通用删除 + 视图子菜单
CONTEXT_MENU_TAIL = [
    ("action", "删除当前工作表", "_delete_current_sheet", ()),
    ("separator",),
    ("submenu", "视图", [
        ("action", "冻结窗格", "_freeze_panes", ()),
        ("action", "设置行高", "_set_row_height", ()),
        ("action", "设置列宽", "_set_col_width", ()),
    ]),
]

# 表格快捷键配置（数据驱动）：每项为
#   (快捷键, 方法名, 方法参数元组) 或 (快捷键, 方法名, 方法参数元组, 绑定目标)
# 方法名：应用方法名（如 "_copy"）；或点路径（如 "table.selectAll"/"win.close"）
#         表示从 self 出发逐级解析到对象方法。绑定目标：'table'（默认）或 'win'。
# 注：Ctrl+Z/Y/H/Shift+C/Shift+V 由工具栏 QAction 的快捷键统一提供，此处不重复绑定。
TABLE_SHORTCUTS = [
    # ── 剪贴板 / 查找 ──
    ("Ctrl+C", "_copy", ()),
    ("Ctrl+V", "_paste", ()),
    ("Ctrl+X", "_cut", ()),
    ("Ctrl+A", "table.selectAll", ()),
    ("Delete", "_clear_cells", ()),
    ("Ctrl+F", "_find_replace", ()),
    # ── 导航与选区 ──
    ("Ctrl+Space", "_select_column", ()),
    ("Shift+Space", "_select_row", ()),
    # ── 行操作 ──
    ("Ctrl+N", "_insert_row_above", ()),
    ("Ctrl+Shift+I", "_insert_row_above", ()),
    ("Ctrl+Shift+K", "_insert_row_below", ()),
    ("Ctrl+Shift+D", "_delete_rows", ()),
    ("Ctrl+Shift+N", "_batch_insert_rows", ()),
    ("Ctrl+L", "_set_row_height", ()),
    ("Ctrl+Shift+F", "_find_replace", ()),
    # ── 快速汇总 ──
    ("Alt+=", "_auto_sum", ()),
    ("Alt+Shift+A", "_quick_summary", ("average",)),
    ("Alt+Shift+M", "_quick_summary", ("max",)),
    ("Alt+Shift+X", "_quick_summary", ("min",)),
    # ── 应用级（绑定主窗口）──
    ("Ctrl+Q", "win.close", (), "win"),
    ("Ctrl+S", "_export", (), "win"),
    ("F2", "_edit_current_cell", ()),
]

# 工具栏动作配置（数据驱动）：每项为
#   (显示文本, 方法名, 方法参数元组, 快捷键或 None)；None 项为分组分隔符。
TOOLBAR_ACTIONS = [
    # ── 文件组 ──
    ("导出Excel", "_export", (), "Ctrl+E"),
    ("生成报告", "_generate_report", (), "Ctrl+Shift+R"),
    ("保存项目", "_save_project", (), "Ctrl+Shift+S"),
    ("加载项目", "_load_project", (), "Ctrl+Shift+O"),
    None,
    # ── 撤销/重做组（参考 ONLYOFFICE UndoRedo）──
    ("撤销", "_undo", (), "Ctrl+Z"),
    ("重做", "_redo", (), "Ctrl+Y"),
    ("查找替换", "_find_replace", (), "Ctrl+H"),
    None,
    # ── 合并组 ──
    ("合并居中", "_merge_cells", (), "Ctrl+M"),
    ("取消合并", "_unmerge_cells", (), "Ctrl+Shift+M"),
    None,
    # ── 字体组（高频）──
    ("加粗", "_toggle_bold", (), "Ctrl+B"),
    ("斜体", "_toggle_italic", (), "Ctrl+I"),
    ("下划线", "_toggle_underline", (), "Ctrl+U"),
    None,
    # ── 数据组 ──
    ("批推定计算", "_run_batch_assessment", (), "Ctrl+F9"),
    ("自动求和", "_auto_sum", (), None),
]

# 菜单栏配置（数据驱动）：结构与右键菜单配置一致。
# 菜单项仅展示快捷键，实际快捷键仍由工具栏 QAction / TABLE_SHORTCUTS 提供，
# 避免重复绑定导致的快捷键歧义。
MENUBAR_STRUCTURE = [
    ("submenu", "文件(&F)", [
        ("action", "导出Excel...", "_export", ()),
        ("action", "生成检测报告...", "_generate_report", ()),
        ("action", "保存项目", "_save_project", ()),
        ("action", "加载项目...", "_load_project", ()),
        ("separator",),
        ("action", "导入外部数据（回弹法）...", "_import_rebound_data", ()),
        ("action", "Word 转回弹 Excel...", "_word_to_excel", ()),
        ("separator",),
        ("action", "规范问答...", "_open_norm_qa", ()),
        ("action", "批量审查...", "_open_batch_review", ()),
        ("action", "文档扫描识别...", "_open_scan_recognition", ()),
        ("action", "识别记录查看...", "_open_scan_history", ()),
        ("separator",),
        ("action", "退出", "_quit", ()),
    ]),
    ("submenu", "编辑(&E)", [
        ("action", "撤销 (Ctrl+Z)", "_undo", ()),
        ("action", "重做 (Ctrl+Y)", "_redo", ()),
        ("separator",),
        ("action", "剪切 (Ctrl+X)", "_cut", ()),
        ("action", "复制 (Ctrl+C)", "_copy", ()),
        ("action", "粘贴 (Ctrl+V)", "_paste", ()),
        ("action", "清除内容 (Delete)", "_clear_cells", ()),
        ("separator",),
        ("action", "查找替换 (Ctrl+H)", "_find_replace", ()),
        ("action", "删除当前工作表", "_delete_current_sheet", ()),
    ]),
    ("submenu", "插入(&I)", [
        ("action", "上方插入行 (Ctrl+Shift+I)", "_insert_row_above", ()),
        ("action", "下方插入行 (Ctrl+Shift+K)", "_insert_row_below", ()),
        ("action", "删除行 (Ctrl+Shift+D)", "_delete_rows", ()),
        ("action", "批量插入行 (Ctrl+Shift+N)", "_batch_insert_rows", ()),
        ("separator",),
        ("action", "合并居中 (Ctrl+M)", "_merge_cells", ()),
        ("action", "取消合并 (Ctrl+Shift+M)", "_unmerge_cells", ()),
    ]),
    ("submenu", "格式(&O)", [
        ("submenu", "对齐方式", [
            ("action", "左对齐", "_align", ("left",)),
            ("action", "居中", "_align", ("center",)),
            ("action", "右对齐", "_align", ("right",)),
        ]),
        ("submenu", "字体", [
            ("action", "加粗 (Ctrl+B)", "_toggle_bold", ()),
            ("action", "斜体 (Ctrl+I)", "_toggle_italic", ()),
            ("action", "下划线 (Ctrl+U)", "_toggle_underline", ()),
            ("action", "字号+", "_font_bigger", ()),
            ("action", "字号-", "_font_smaller", ()),
            ("action", "字体颜色", "_set_font_color", ()),
        ]),
        ("action", "背景颜色", "_set_bg_color", ()),
        ("submenu", "边框", [
            ("action", "全部边框", "_set_border", ("all",)),
            ("action", "仅外框", "_set_border", ("outer",)),
            ("action", "仅内框", "_set_border", ("inner",)),
            ("action", "上边框", "_set_border", ("top",)),
            ("action", "下边框", "_set_border", ("bottom",)),
            ("action", "左边框", "_set_border", ("left",)),
            ("action", "右边框", "_set_border", ("right",)),
            ("action", "无边框", "_set_border", ("none",)),
        ]),
        ("submenu", "数字格式", [
            ("action", "常规", "_set_number_format", ("general",)),
            ("action", "整数", "_set_number_format", ("int",)),
            ("action", "两位小数", "_set_number_format", ("dec2",)),
            ("action", "百分比", "_set_number_format", ("percent",)),
            ("action", "千分位", "_set_number_format", ("thousands",)),
        ]),
        ("submenu", "格式刷", [
            ("action", "复制格式 (Ctrl+Shift+C)", "_format_painter_copy", ()),
            ("action", "粘贴格式 (Ctrl+Shift+V)", "_format_painter_paste", ()),
        ]),
        ("separator",),
        ("action", "设置行高", "_set_row_height", ()),
        ("action", "设置列宽", "_set_col_width", ()),
        ("action", "批量调整行高", "_batch_row_height", ()),
    ]),
    ("submenu", "数据/工具(&T)", [
        ("action", "批推定计算（钻芯法）(Ctrl+F9)", "_run_batch_assessment", ()),
        ("action", "删除构件 (Ctrl+Shift+Delete)", "_delete_core_drilling_component", ()),
        ("action", "测点录入（保护层原始记录）", "_open_cover_point_entry", ()),
        ("separator",),
        ("action", "自动求和 (Alt+=)", "_auto_sum", ()),
        ("submenu", "快速汇总", [
            ("action", "平均值", "_quick_summary", ("average",)),
            ("action", "最大值", "_quick_summary", ("max",)),
            ("action", "最小值", "_quick_summary", ("min",)),
        ]),
        ("action", "批量填充 (Ctrl+D)", "_run_batch_fill", ()),
        ("action", "批量修改", "_batch_modify", ()),
    ]),
    ("submenu", "视图(&V)", [
        ("action", "浅色主题（Fluent）", "_theme_light", ()),
        ("action", "深色主题（Fluent）", "_theme_dark", ()),
        ("separator",),
        ("action", "冻结窗格", "_freeze_panes", ()),
        ("separator",),
        ("action", "全选检测项目", "_tree_select_all", ()),
        ("action", "全不选检测项目", "_tree_deselect_all", ()),
        ("separator",),
        ("action", "显示/隐藏操作步骤说明", "_toggle_notes_panel", ()),
    ]),
    ("submenu", "帮助(&H)", [
        ("action", "操作说明", "_show_help", ()),
        ("action", "快捷键说明", "_show_shortcuts", ()),
        ("separator",),
        ("action", "检查更新", "_check_update", ()),
        ("separator",),
        ("action", "关于", "_show_about", ()),
    ]),
]


class ReportGeneratorApp(CoreDrillingMixin, SteelRebarMixin,
                         MemberThicknessMixin, CoverThicknessMixin,
                         MergeOpsMixin, SelectionMixin,
                         FormatMixin, ClipboardMixin, UndoRedoMixin,
                         RowOpsMixin, EditToolsMixin, CalcRulesMixin):
    """主体结构检测数据管理录入系统V1.0主应用（PyQt5）"""

    def __init__(self, structure_type=None):
        # structure_type：限定本界面只展示该结构类型的检测项目
        # （None = 展示全部，与原行为一致；钢结构/木结构/砖混入口
        # 分别传 '钢结构'/'木结构'/'砖混结构' 实现专属录入界面）
        self.structure_type = structure_type
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setFont(DEFAULT_FONT)
        apply_theme(self.app, get_saved_theme())  # Fluent 风格主题（浅/深可切换）

        # ── 应用与主窗口图标（标题栏 + 任务栏显示）──
        # 所有静态资源集中存放在 <项目根>/report_generator/assets/ 下，
        # 通过 framework.resources.get_asset() 统一解析，避免硬编码父级回溯。
        icon_path = get_asset("logo.jpg")
        if icon_path.is_file():
            app_icon = QIcon(str(icon_path))
            # 应用级：所有窗口/对话框默认图标（任务栏、弹窗）
            self.app.setWindowIcon(app_icon)
            # 窗口级：主窗口标题栏图标（双重设置更稳妥）
            self._app_icon = app_icon
        else:
            self._app_icon = None

        self.win = QMainWindow()
        self.win.setWindowTitle("主体结构检测报告数据管理录入系统V1.0")
        if self._app_icon is not None:
            self.win.setWindowIcon(self._app_icon)
        self.win.resize(1400, 900)
        self.win.setMinimumSize(1000, 600)

        # ── 数据 ──
        self.sheet_data = {}    # {"检测项目（构件）": [[单元格值, ...], ...]}
        self._merges = {}       # {"检测项目（构件）": [(row, col, rowSpan, colSpan), ...]}
        self._merge_formats = {}  # {"检测项目": {(row, col): {"align": ..., "bold": ..., "bg": ..., "fg": ...}}}
        self._cell_formats = {}  # {"检测项目": {(row, col): {bold,italic,underline,align,bg,fg,numfmt,border}}}
        self.current_item = None
        self._loading = False
        self._default_rows = DEFAULT_ROWS
        self.project_name = PROJECT_NAME
        self._formula_engine = FormulaEngine(self.sheet_data)
        # 通用自动计算引擎（衍生列：平均值/偏差值/合格点率），回调读写当前表格
        self._calc_engine = CalcEngine(
            self._calc_get_cell, self._calc_set_cell, self._calc_format_cell
        )
        # 应用控制器：承载业务逻辑（工作表键解析/序列化/导出/插件编排）
        self.controller = AppController()
        # 单元格联动钩子（注册式分派）：各检测模块 Mixin 提供，
        # 编辑单元格后按序调用，返回 True 表示命中该模块并已处理。
        self._cell_change_hooks = [self._core_drilling_cell_changed]
        # 工作表加载钩子（注册式分派）：各检测模块 Mixin 提供，
        # 加载工作表完成后按序调用（位置列下拉、模块全表重算等）。
        self._sheet_load_hooks = [self._core_drilling_sheet_loaded]
        # 右键菜单贡献钩子（注册式分派）：各检测模块 Mixin 提供，
        # 返回 [(显示文本, 处理函数), ...]，按序追加到右键菜单。
        self._context_menu_hooks = [self._core_drilling_context_menu]
        self._current_font_size = FONT_SIZE
        self._displayed_merges = []  # 当前表格已应用的合并列表（用于切换时重置）
        # 撤销/重做栈（参考 ONLYOFFICE History.js + UndoRedo.js）
        # 每条记录 = {"sheet": str, "cells": {(r,c): (old_text, new_text)}, "merges": [...]}
        self._undo_stack = []
        self._redo_stack = []
        self._undo_limit = 100
        self._snapshot_before_edit = None  # 编辑前的单元格快照
        # 格式刷状态（参考 ONLYOFFICE 选中格式后应用到目标区域）
        self._format_painter_data = None  # {(r,c): {format dict}} 或 None
        # 钻芯法检测参数（按 sheet_key 保存各自的 samples_per）
        self._cd_params = {}  # {sheet_key: {"samples_per": int, ...}}
        # 报告抬头信息（生成检测报告弹窗预填，随项目文件保存）
        self._report_info = {}
        self._use_agent = None          # Agent 模式选择（None=按配置默认）
        self._report_worker = None      # 报告生成后台线程
        # 各检测模块的操作步骤说明由 NotesPanel 内部管理（notes_panel.notes）

        # ── 构建 UI ──
        self._build_ui()
        self.notes_panel.set_defaults(
            build_default_sheet_notes(DETECTION_DATA, DEFAULT_OPERATION_NOTES)
        )
        self._floor_delegate = FloorLabelDelegate(self.table)
        self._floor_delegate_column = None
        self._populate_tree()

    def run(self):
        """启动 Qt 事件循环"""
        self.win.show()
        sys.exit(self.app.exec_())

    # ═════════════════════════════════════════════════════════════
    #  UI 构建
    # ═════════════════════════════════════════════════════════════
    def _build_ui(self):
        self._build_menubar()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    def _build_menubar(self):
        """构建菜单栏"""
        mb = self.win.menuBar()
        self._build_menu_entries(mb, MENUBAR_STRUCTURE)

    def _build_toolbar(self):
        """构建 Excel 风格工具栏（按 TOOLBAR_ACTIONS 配置数据驱动生成）"""
        tb = self.win.addToolBar("主工具栏")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.toolbar = tb

        for entry in TOOLBAR_ACTIONS:
            if entry is None:
                tb.addSeparator()
                continue
            text, method_name, args, shortcut = entry
            a = QAction(text, self.win)
            slot = getattr(self, method_name)
            if args:
                # 带参数的方法：吞掉 triggered(bool) 的 checked 参数后转发
                a.triggered.connect(
                    lambda _=False, s=slot, ar=tuple(args): s(*ar)
                )
            else:
                a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                a.setShortcutContext(Qt.ApplicationShortcut)
            tb.addAction(a)

    def _build_central(self):
        """构建中心区域：项目名称栏 + 左侧树 + 右侧表格 + 底部标签页"""
        central = QWidget()
        self.win.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 0)
        layout.setSpacing(4)

        # 项目名称编辑栏
        project_bar = QWidget()
        pb_layout = QHBoxLayout(project_bar)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        pb_layout.setSpacing(6)
        name_lbl = QLabel("项目名称:")
        name_lbl.setStyleSheet("font-weight: bold;")
        self.project_name_edit = QLineEdit(self.project_name)
        self.project_name_edit.setClearButtonEnabled(True)
        self.project_name_edit.textChanged.connect(self._on_project_name_changed)
        pb_layout.addWidget(name_lbl)
        pb_layout.addWidget(self.project_name_edit, 1)
        layout.addWidget(project_bar)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧：检测项目树（含搜索和按钮）
        self._build_tree()
        splitter.addWidget(self.tree_panel)

        # 右侧：表格 + 底部标签页
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._build_table()
        right_layout.addWidget(self.table, 1)

        # 底部标签页：已勾选的工作表（关闭/切换的业务逻辑由主窗口处理）
        self.sheet_tabs = SheetTabsBar()
        self.sheet_tabs.closeKeyRequested.connect(self._on_tab_close)
        self.sheet_tabs.switchKeyRequested.connect(self._on_tab_changed)
        right_layout.addWidget(self.sheet_tabs)

        splitter.addWidget(right_panel)

        # 最右侧：操作步骤说明面板（按当前检测模块保存，内部自管理）
        self.notes_panel = NotesPanel()
        self.notes_panel.calcRequested.connect(self._run_current_calc)
        splitter.addWidget(self.notes_panel)
        splitter.setSizes([250, 950, 300])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(2, False)

        layout.addWidget(splitter, 1)

    def _on_project_name_changed(self, text):
        """项目名称编辑后同步到当前项目实例"""
        self.project_name = text.strip()

    def _build_tree(self):
        """挂载左侧检测项目树面板（搜索/全选按钮/树均由 TreePanel 自管理）"""
        self.tree_panel = TreePanel()
        # 勾选/点击的业务逻辑（建表/加载）由主窗口处理
        self.tree_panel.itemCheckChanged.connect(self._on_tree_item_changed)
        self.tree_panel.itemLeafClicked.connect(self._on_tree_clicked)
        self.tree_panel.selectAllRequested.connect(self._tree_select_all)
        self.tree_panel.deselectAllRequested.connect(self._tree_deselect_all)

    def _build_table(self):
        """构建右侧数据表格"""
        self.table = MergeTableWidget()
        # 注入合并表与当前 sheet 引用（供 _remap_merged_cell 使用）
        self.table._merges = self._merges
        self.table._current_sheet = None
        self.table.set_fill_callback(self._on_fill_handle_dragged)
        self.table.setRowCount(self._default_rows)
        self.table.setColumnCount(0)
        self.table.setFont(DEFAULT_FONT)
        self.table.setEditTriggers(
            QTableWidget.DoubleClicked |
            QTableWidget.EditKeyPressed |
            QTableWidget.AnyKeyPressed
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemChanged.connect(self._on_cell_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # 行头设置：允许拖拽改行高 + 点击选行
        vh = self.table.verticalHeader()
        vh.setDefaultSectionSize(24)
        vh.setFont(DEFAULT_FONT)
        vh.setMinimumWidth(40)
        vh.setSectionResizeMode(QHeaderView.Interactive)
        vh.setSectionsClickable(True)
        vh.sectionClicked.connect(self._on_row_header_clicked)

        # 列头设置：两层表头（输入区/计算区）+ 允许拖拽改列宽 + 点击选列
        self.table.setHorizontalHeader(GroupedHeaderView(Qt.Horizontal, self.table))
        hh = self.table.horizontalHeader()
        hh.setFont(DEFAULT_FONT)
        hh.setMinimumSectionSize(60)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionsClickable(True)
        hh.sectionClicked.connect(self._on_col_header_clicked)

        # 初始化空表行头
        self._update_row_headers(self._default_rows)

        # ── 表格快捷键（按 TABLE_SHORTCUTS 配置数据驱动；参考 ONLYOFFICE onKeyDown）──
        # 必须保存 QShortcut 的引用，否则会被 Python 垃圾回收，导致快捷键失效。
        self._table_shortcuts = []
        for entry in TABLE_SHORTCUTS:
            key, method_name, args = entry[0], entry[1], entry[2]
            bind = entry[3] if len(entry) > 3 else "table"
            if bind == "win":
                # 应用级快捷键（Ctrl+Q 退出 / Ctrl+S 导出）：任何焦点位置都生效
                target = self.win
                ctx = Qt.ApplicationShortcut
            else:
                # 表格操作快捷键：绑定到 table，使用 WidgetWithChildrenShortcut，
                # 保证单元格进入编辑模式（编辑器作为 table 的子控件获得焦点）时
                # 快捷键仍然生效；同时避免用户在项目名称等外部输入框按 Ctrl+A/C/V
                # 触发表格操作。
                target = self.table
                ctx = Qt.WidgetWithChildrenShortcut
            # 解析方法：点路径（如 table.selectAll）从 self 出发逐级取属性；
            # 否则为应用自身方法
            if "." in method_name:
                obj = self
                for part in method_name.split("."):
                    obj = getattr(obj, part)
                slot = obj
            else:
                slot = getattr(self, method_name)
            if args:
                sc = QShortcut(
                    QKeySequence(key), target,
                    lambda _=False, s=slot, ar=tuple(args): s(*ar),
                )
            else:
                sc = QShortcut(QKeySequence(key), target, slot)
            sc.setContext(ctx)
            self._table_shortcuts.append(sc)

    def _build_statusbar(self):
        """构建底部状态栏"""
        self.statusbar = QStatusBar()
        self.win.setStatusBar(self.statusbar)
        self.status_label = QLabel("就绪")
        self.statusbar.addWidget(self.status_label, 1)

    # ═══════════════════════════════════════════════════════════
    #  检测项目树
    # ═══════════════════════════════════════════════════════════
    def _populate_tree(self):
        """从 DETECTION_DATA 填充三级树结构（填充本身不触发勾选业务）。

        指定 structure_type 时只填充该结构类型的检测类别（专属录入
        界面）；None 时展示全部类别。
        """
        if self.structure_type:
            tree_data = get_plugin_manager().detection_data_for_structure(
                self.structure_type)
        else:
            tree_data = DETECTION_DATA
        self.tree_panel.populate(tree_data, self._sheet_key)

    def _sheet_key(self, item_name, component):
        """构造工作表键：项目名（构件名）"""
        return self.controller.make_sheet_key(item_name, component)

    def _parse_sheet_key(self, key):
        """解析工作表键，返回 (基础项目名, 构件名或None)"""
        return self.controller.parse_sheet_key(key)

    def _get_position_column(self, cols):
        """返回构件位置相关列的列索引，无则返回 None。"""
        for name in ("构件位置及名称", "构件位置及编号", "构件位置"):
            if name in cols:
                return cols.index(name)
        return None

    def _get_columns(self, sheet_key):
        """获取工作表对应的列定义"""
        return self.controller.get_columns(sheet_key)

    def _on_tree_item_changed(self, item, column):
        """树节点勾选状态变化"""
        if self._loading:
            return
        key = item.data(0, Qt.UserRole)
        if not key:
            return  # 非叶节点
        checked = item.checkState(0) == Qt.Checked
        if checked:
            # 需要参数设置对话框的检测项（如钻芯法），由插件能力判定
            if self.controller.requires_setup_dialog(key) and key not in self.sheet_data:
                # 弹出参数对话框（由插件决定具体对话框类型，框架层不感知）
                dlg = self.controller.create_setup_dialog(key, self.win, sheet_key=key)
                if dlg is not None and dlg.exec_() == QDialog.Accepted:
                    params = dlg.get_params()
                    # 工作表构建方式由插件决定（框架层不感知具体构建方法）
                    self.controller.build_sheet(key, params, self)
                    self._load_item(key)
                else:
                    # 用户取消，撤销勾选（面板内屏蔽信号，不回环触发）
                    self.tree_panel.set_leaf_checked(item, False)
                    return
            else:
                # 勾选：创建数据条目并加载
                if key not in self.sheet_data:
                    cols = self._get_columns(key)
                    self.sheet_data[key] = [
                        ["" for _ in range(len(cols))]
                        for _ in range(self._default_rows)
                    ]
                if key != self.current_item:
                    self._load_item(key)
            self._status(f"已勾选: {key}")
            self._sync_tabs_to_data()
        else:
            # 取消勾选 = 删除该检测项目：彻底清除数据，避免残留数据
            # 写入项目文件后“跑”到其他检测项目中
            self._status(f"已删除: {key}")
            self._remove_sheet_data(key)

    def _on_tree_clicked(self, item, column):
        """点击树节点：切换到已勾选的工作表"""
        if self._loading:
            return
        key = item.data(0, Qt.UserRole)
        if not key:
            return
        if item.checkState(0) == Qt.Checked and key != self.current_item:
            self._load_item(key)

    def _is_leaf_checked(self, key):
        """检查指定键对应的叶节点是否已勾选（委托 TreePanel）"""
        return self.tree_panel.is_leaf_checked(key)

    def _active_sheet_data(self):
        """返回当前树中仍勾选的工作表数据。

        取消勾选后 sheet_data 中可能残留旧数据；导出时必须按树的勾选状态过滤，
        避免未勾选的检测项目/构件仍然被生成 Excel 工作表。
        """
        return {
            key: rows for key, rows in self.sheet_data.items()
            if self._is_leaf_checked(key)
        }

    def _check_tree_by_data(self):
        """根据 sheet_data 勾选树中对应的叶节点（委托 TreePanel）"""
        self.tree_panel.check_by_keys(self.sheet_data.keys())

    def _resolve_fill_target(self, name):
        """按识别出的检测项目类型定位回填目标工作表并跳转。

        定位顺序：
        1. 当前激活表：基础项目名与识别类型一致时直接沿用；
        2. 已创建工作表：精确 → 唯一包含命中跳转；
        3. 检测项目树（含未勾选项）：基础项目名归一化匹配（兼容
           "回弹法检测(主要来源为仪器数据，可选用)" 等树名后缀），
           唯一命中自动勾选建表（钻芯法等会弹出参数对话框）后跳转；
        4. 多个构件命中：弹窗由用户选择后勾选跳转；
        5. 完全未命中：从已打开工作表中手选，或提示先勾选项目。
        定位失败返回 None（由调用方决定是否取消回填）。
        """
        name = str(name or "").strip()
        if not name:
            return None
        target = self.controller.resolve_item_name(name)
        # 1) 当前激活表类型一致时直接沿用（已在对应检测项目中，无需跳转）
        if self.current_item:
            cur_base, _comp = self.controller.parse_sheet_key(
                str(self.current_item))
            cur_base = self.controller.resolve_item_name(str(cur_base or ""))
            if target and target == cur_base:
                return str(self.current_item)
        # 2) 已创建的工作表
        keys = [str(k) for k in self.sheet_data.keys()]
        if name in keys:
            self._load_item(name)
            return name
        hits = [k for k in keys if name in k or k in name]
        if len(hits) == 1:
            self._load_item(hits[0])
            return hits[0]
        # 3) 树内查找（含未勾选的检测项目）
        leaf_hits = []
        for leaf_key in self.tree_panel.leaf_keys():
            key_s = str(leaf_key)
            base, _comp = self.controller.parse_sheet_key(key_s)
            base_norm = self.controller.resolve_item_name(str(base or ""))
            if (name == key_s or name in key_s or key_s in name
                    or (target and target == base_norm)):
                leaf_hits.append(key_s)
        if len(leaf_hits) == 1:
            return self._check_and_load_leaf(leaf_hits[0])
        if leaf_hits:
            # 4) 多个构件命中：用户选择目标工作表后勾选跳转
            chosen, ok = QInputDialog.getItem(
                self.win, "选择检测项目",
                f"识别类型「{name}」对应多个构件工作表，请选择：",
                leaf_hits, 0, False)
            return self._check_and_load_leaf(str(chosen)) if ok else None
        # 5) 完全未命中：从已打开工作表中手选
        if keys:
            chosen, ok = QInputDialog.getItem(
                self.win, "选择回填目标",
                f"识别类型「{name}」未匹配到检测项目，请选择回填目标：",
                keys, 0, False)
            return str(chosen) if ok else None
        QMessageBox.warning(
            self.win, "未找到检测项目",
            f"识别类型「{name}」未匹配到检测项目，\n"
            "请先在左侧检测项目树勾选对应项目后再识别回填。")
        return None

    def _check_and_load_leaf(self, key):
        """勾选树叶节点（触发建表/参数对话框）并跳转；失败返回 None。"""
        if key in self.sheet_data:
            self._load_item(key)
            return key
        leaf = self.tree_panel.find_item(key)
        if leaf is None:
            return None
        self.tree_panel.check_leaf(key)
        if key not in self.sheet_data:
            # 勾选业务未产出工作表（如用户取消了钻芯法参数对话框）
            return None
        return key

    def _restore_checked_items(self):
        """根据保存的 checked_items 列表恢复树节点勾选状态（委托 TreePanel）"""
        self.tree_panel.check_by_keys(self._checked_items or [])

    # ═══════════════════════════════════════════════════════════
    #  树全选/全不选（树状态由 TreePanel 管理，此处仅业务联动）
    # ═══════════════════════════════════════════════════════════
    def _tree_select_all(self):
        """全选所有可见叶节点后同步标签页"""
        self.tree_panel.set_all_checked()
        self._sync_tabs_to_data()

    def _tree_deselect_all(self):
        """全不选所有叶节点并彻底清除全部工作表数据"""
        self.tree_panel.set_all_unchecked()
        for key in list(self.sheet_data):
            self._purge_key(key)
        self.current_item = None
        self._clear_table()
        self._sync_tabs_to_data()

    # ═══════════════════════════════════════════════════════════
    #  底部标签页管理
    # ═══════════════════════════════════════════════════════════
    def _sync_tabs_to_data(self):
        """同步底部标签页与已勾选的 sheet_data（委托 SheetTabsBar）。"""
        self.sheet_tabs.sync(self.sheet_data, self._is_leaf_checked, self.current_item)

    def _on_tab_close(self, key):
        """关闭标签页 = 删除对应检测项目（取消勾选并彻底清除数据）"""
        if not key:
            return
        self._remove_sheet_data(key)

    def _on_tab_changed(self, key):
        """切换标签页 = 切换工作表"""
        if key and key != self.current_item and self._is_leaf_checked(key):
            self._load_item(key)

    def _load_item(self, sheet_key):
        """加载指定工作表数据到表格"""
        if not sheet_key:
            return
        # 先保存当前工作表
        if self.current_item and self.current_item != sheet_key:
            self._save_current_notes()
            self._sync_table_to_data()
            self._trim_sheet_data_tail(self.current_item)

        self._loading = True
        try:
            self.current_item = sheet_key
            self._load_notes_for_current()
            # 同步给 MergeTableWidget，供 _remap_merged_cell 使用
            self.table._current_sheet = sheet_key
            # 重置已有合并
            self._reset_spans()

            # 设置列
            cols = self._get_columns(sheet_key)
            self.table.setColumnCount(len(cols))
            self.table.setHorizontalHeaderLabels(cols)

            # 获取数据
            data = self.sheet_data.get(sheet_key, [])
            row_count = max(len(data), self._default_rows)
            self.table.setRowCount(row_count)

            # 填充数据
            self._ensure_engine()
            for r in range(row_count):
                row_data = data[r] if r < len(data) else []
                for c in range(len(cols)):
                    val = row_data[c] if c < len(row_data) else ""
                    item = QTableWidgetItem()
                    if isinstance(val, str) and val.startswith("="):
                        # 公式：存储公式，显示计算结果
                        item.setData(ROLE_FORMULA, val)
                        result = self._formula_engine.evaluate(val, sheet_key, r, c)
                        item.setText(result)
                    else:
                        item.setText(str(val) if val != "" else "")
                    self.table.setItem(r, c, item)

            # 更新行头
            self._update_row_headers(row_count)

            # 恢复单元格级别的非合并格式（斜体/下划线/数字格式/边框等）
            self._restore_cell_formats()

            # 应用合并 + 恢复合并格式
            self._ensure_rebar_axis_merges(sheet_key)
            self._apply_merges_to_table()

            # 模块级工作表加载钩子（注册式分派：位置列下拉、钻芯法全表重算等）
            for hook in self._sheet_load_hooks:
                hook(sheet_key, cols)

            self._apply_all_calc_rules()

            # 区分输入区 / 计算区：两层表头 + 计算列锁定
            self._configure_header_groups(sheet_key)
            self._apply_column_access(sheet_key)

            # 列宽自适应内容
            self.table.resizeColumnsToContents()
            # 限制最小列宽 60，最大 200
            for c in range(self.table.columnCount()):
                w = self.table.columnWidth(c)
                if w < 60:
                    self.table.setColumnWidth(c, 60)
                elif w > 200:
                    self.table.setColumnWidth(c, 200)
        finally:
            self._loading = False

        self._status(f"当前: {sheet_key}")

    def _save_current_notes(self):
        """把右侧文本框内容保存到当前检测模块（委托 NotesPanel）。"""
        if hasattr(self, "notes_panel"):
            self.notes_panel.save_current()

    def _load_notes_for_current(self):
        """把当前检测模块的操作步骤说明加载到右侧文本框（委托 NotesPanel）。"""
        if hasattr(self, "notes_panel"):
            self.notes_panel.load_for(self.current_item)

    def _get_computed_columns(self, sheet_key=None):
        """返回指定工作表的自动计算列集合（0-based）。"""
        sheet_key = sheet_key or self.current_item
        if not sheet_key:
            return set()
        base, _comp = self._parse_sheet_key(sheet_key)
        base = self.controller.resolve_item_name(base)
        cols = self._get_columns(sheet_key)
        column_count = len(cols)
        computed = set()

        rules = CALC_RULES.get(base, {})
        for target_col in rules:
            if isinstance(target_col, int) and target_col < column_count:
                computed.add(target_col)

        summary_columns = {
            '剪力墙构件钢筋间距检测': {19, 20},
            '现浇板钢筋间距检测': {19, 20},
            '楼板构件厚度检测': {13, 14},
            '剪力墙厚度检测': {12, 13},
            '混凝土梁保护层厚度检测': {25, 26},
            '混凝土柱保护层厚度检测': {25, 26},
            '剪力墙保护层厚度检测': {25, 26},
            '混凝土板保护层厚度检测': {25, 26},
            '钻芯法检测': {7, 9, 10, 11},
            '回弹钻芯修正法检测': {7, 9, 11},
        }
        computed.update(summary_columns.get(base, set()))
        return {c for c in computed if c < column_count}

    def _configure_header_groups(self, sheet_key):
        """设置两层表头的分组信息与列头提示。"""
        hh = self.table.horizontalHeader()
        if not isinstance(hh, GroupedHeaderView):
            return
        hh.clear_groups()
        computed = self._get_computed_columns(sheet_key)
        for c in range(self.table.columnCount()):
            is_computed = c in computed
            hh.set_group(c, "计算区" if is_computed else "输入区")
            header_item = self.table.horizontalHeaderItem(c)
            if header_item is not None:
                header_item.setToolTip(
                    "自动计算列：由系统根据输入数据生成，不可编辑"
                    if is_computed else
                    "输入列：请在此填写检测数据"
                )
        hh.viewport().update()

    def _apply_column_access(self, sheet_key=None):
        """锁定自动计算列，输入列保持可编辑。"""
        sheet_key = sheet_key or self.current_item
        if not sheet_key:
            return
        computed = self._get_computed_columns(sheet_key)
        if not computed:
            return
        for r in range(self.table.rowCount()):
            for c in computed:
                if c >= self.table.columnCount():
                    continue
                item = self.table.item(r, c)
                if item is not None:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def _clear_table(self):
        """清空表格"""
        self._loading = True
        try:
            self._reset_spans()
            self.table.clear()
            self.table.setRowCount(self._default_rows)
            self.table.setColumnCount(0)
            self._update_row_headers(self._default_rows)
        finally:
            self._loading = False
        self._load_notes_for_current()

    def _purge_key(self, key):
        """从内存中彻底移除指定工作表的数据、合并、格式与操作说明。"""
        self.sheet_data.pop(key, None)
        self._merges.pop(key, None)
        self._merge_formats.pop(key, None)
        self._cell_formats.pop(key, None)
        self._cd_params.pop(key, None)
        self.notes_panel.remove(key)

    def _remove_sheet_data(self, key):
        """彻底移除指定工作表的所有数据（sheet_data/merges/格式/cd_params），
        并取消树节点勾选、同步标签页。"""
        self._purge_key(key)
        # 取消树节点勾选（面板内屏蔽信号，不触发建表业务）
        self.tree_panel.uncheck(key)
        if self.current_item == key:
            self.current_item = None
            # 切换到其他已勾选项
            first = next(
                (k for k in self.sheet_data if self._is_leaf_checked(k)),
                None,
            )
            if first:
                self._load_item(first)
            else:
                self._clear_table()
        self._sync_tabs_to_data()

    def _delete_current_sheet(self):
        """删除当前工作表（右键菜单通用入口）。

        钻芯法检测按构件分组删除，建议使用「删除当前构件」逐组移除；
        删除最后一组构件时自动调用此方法移除整个 sheet。
        其余检测项目直接删除当前工作表，勾选树节点可重新创建。
        """
        if not self.current_item:
            QMessageBox.information(self.win, "提示", "没有激活的工作表。")
            return
        key = self.current_item
        reply = QMessageBox.question(
            self.win, "确认删除工作表",
            f"确定删除工作表「{key}」？\n删除后重新勾选可重新创建。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._remove_sheet_data(key)
            self._status(f"已删除工作表: {key}")

    # ═══════════════════════════════════════════════════════════
    #  通用自动计算规则（平均值、偏差值、合格点率）
    #  已提取至 framework/ui/handlers/calc_rules.py（CalcRulesMixin）
    # ═══════════════════════════════════════════════════════════
    def _recalc_module_totals(self):
        """触发各检测模块的汇总重算（由各模块 Mixin 提供并自行判断适用性）。"""
        self._recalc_rebar_spacing_totals()
        self._recalc_member_thickness_totals()
        self._recalc_cover_thickness_totals()

    def _run_current_calc(self):
        """对当前工作表执行一次完整计算，无需切换检测项目。"""
        if not self.current_item:
            self._status("请先勾选检测项目")
            return

        self._save_current_notes()
        self._sync_table_to_data()

        self._loading = True
        try:
            self._apply_all_calc_rules()
            if self._is_core_drilling_sheet():
                self._recalc_core_drilling_all()
            elif self._is_rebound_core_drilling_sheet():
                self._recalc_rebound_core_drilling_all()
            self._recalc_module_totals()
            self._recompute_formulas()
        finally:
            self._loading = False

        self._apply_column_access()
        self._status("计算完成")

    # ═══════════════════════════════════════════════════════════
    #  表格事件处理
    # ═══════════════════════════════════════════════════════════
    def _on_cell_changed(self, item):
        if self._loading:
            return
        row = item.row()
        col = item.column()
        text = item.text()

        saved_alignment = item.textAlignment()

        self._loading = True
        try:
            if text.startswith("="):
                item.setData(ROLE_FORMULA, text)
                self._sync_table_to_data()
                self._ensure_engine()
                result = self._formula_engine.evaluate(
                    text, self.current_item, row, col
                )
                item.setText(result)
            else:
                item.setData(ROLE_FORMULA, None)

            item.setTextAlignment(saved_alignment)

            self._sync_table_to_data()

            # 模块级单元格联动（注册式分派：各模块 Mixin 自行判断适用性；
            # 含位置列楼层校验、钻芯法联动重算等）
            for hook in self._cell_change_hooks:
                if hook(row, col, item):
                    break

            self._apply_calc_rules(row)
            self._recalc_module_totals()
            self._recompute_formulas()
        finally:
            self._loading = False

    def _show_context_menu(self, pos):
        """显示右键菜单（按 CONTEXT_MENU_ACTIONS/TAIL 配置数据驱动构建）"""
        if not self.current_item:
            return
        menu = QMenu(self.win)

        # 主菜单项
        self._build_menu_entries(menu, CONTEXT_MENU_ACTIONS)

        # 模块贡献的右键菜单项（注册式分派：各模块 Mixin 自行判断适用性）
        module_items = [it for hook in self._context_menu_hooks for it in hook()]
        for label, handler in module_items:
            menu.addAction(label, handler)
        if module_items:
            menu.addSeparator()

        # 尾部项（通用删除 + 视图）
        self._build_menu_entries(menu, CONTEXT_MENU_TAIL)

        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _build_menu_entries(self, menu, entries):
        """按配置条目列表构建菜单（递归处理子菜单）。"""
        for entry in entries:
            kind = entry[0]
            if kind == "separator":
                menu.addSeparator()
            elif kind == "action":
                _, label, method_name, args = entry
                slot = getattr(self, method_name)
                if args:
                    # 带参数的方法：吞掉 triggered(bool) 的 checked 参数后转发
                    menu.addAction(
                        label, lambda _=False, s=slot, ar=tuple(args): s(*ar)
                    )
                else:
                    menu.addAction(label, slot)
            elif kind == "submenu":
                _, name, sub_entries = entry
                sub = menu.addMenu(name)
                self._build_menu_entries(sub, sub_entries)

    # ═══════════════════════════════════════════════════════════
    #  Excel 导出
    # ═══════════════════════════════════════════════════════════
    def _export(self):
        """导出为 Excel 文件"""
        self._sync_table_to_data()
        sheet_data = self._active_sheet_data()
        if not sheet_data or not any(v for v in sheet_data.values()):
            QMessageBox.warning(self.win, "无数据", "请先勾选检测项目并添加数据！")
            return

        proj = self.project_name.strip() or PROJECT_NAME
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp, _ = QFileDialog.getSaveFileName(
            self.win, "导出Excel", f"{proj}_{ts}.xlsx",
            "Excel文件 (*.xlsx)",
        )
        if not fp:
            return
        try:
            # 导出编排（生成工作簿 + 追加用户合并）由 utils.excel_exporter 统一处理
            export_columns = self.controller.build_export_columns(sheet_data)
            export_workbook(
                proj, sheet_data, export_columns, fp,
                cell_formats=self._cell_formats,
                merge_formats=self._merge_formats,
                merges=self._merges,
                checked_keys=list(sheet_data.keys()),
            )
            ni = len(sheet_data)
            nr = sum(len(v) for v in sheet_data.values())
            self._status(f"导出成功 -> {fp}")
            self.controller.bus.emit("export.done", fp, ni, nr)
            QMessageBox.information(
                self.win, "导出成功", f"共 {ni} 个工作表，{nr} 行数据"
            )
        except Exception as e:
            QMessageBox.critical(self.win, "导出失败", str(e))

    # ═══════════════════════════════════════════════════════════
    #  检测报告 Word 生成
    # ═══════════════════════════════════════════════════════════
    def _generate_report(self):
        """按 report_template/ 章节模板生成《检测报告》.docx"""
        self._sync_table_to_data()
        active = self._active_sheet_data()
        if not active or not any(
                any(str(v).strip() for v in row) if isinstance(row, list)
                else False
                for rows in active.values() for row in rows):
            QMessageBox.warning(
                self.win, "无数据", "请先勾选检测项目并录入数据！")
            return
        active = {k: v for k, v in active.items() if v}

        proj = self.project_name.strip() or PROJECT_NAME
        # 抬头信息弹窗（预填上次值 + 报告日期默认今天 + Agent 模式开关）
        prefill = default_report_info(proj)
        prefill.update(self._report_info or {})
        dlg = ReportInfoDialog(
            prefill=prefill, checked_items=list(active.keys()), parent=self.win,
            default_use_agent=self._use_agent)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._report_info = dlg.get_values()
        use_agent = dlg.use_agent()
        self._use_agent = use_agent

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp, _ = QFileDialog.getSaveFileName(
            self.win, "生成检测报告", f"{proj}_检测报告_{ts}.docx",
            "Word 文档 (*.docx)",
        )
        if not fp:
            return

        if use_agent:
            # Agent 模式：多轮 LLM 工具调用（分钟级），放后台线程防界面冻结
            try:
                columns_map = self.controller.build_export_columns(active)
            except Exception as e:
                QMessageBox.critical(self.win, "生成失败", str(e))
                return
            self._start_report_worker(fp, proj, active, columns_map)
            return

        try:
            columns_map = self.controller.build_export_columns(active)
            result = generate_report(
                proj, self._report_info, active, columns_map,
                checked_order=list(active.keys()), output_path=fp,
                on_log=self._status,
            )
            self._status(f"报告生成成功 -> {fp}")
            self.controller.bus.emit("report.generated", fp)
            QMessageBox.information(
                self.win, "生成成功", self._report_result_message(fp, result))
        except Exception as e:
            QMessageBox.critical(self.win, "生成失败", str(e))

    # ── Agent 模式后台生成 ──
    def _start_report_worker(self, fp, proj, active, columns_map):
        """启动后台生成线程（防止重复触发）。"""
        if self._report_worker is not None and self._report_worker.isRunning():
            QMessageBox.warning(self.win, "正在生成", "报告正在生成中，请稍候。")
            return

        def _run(on_log):
            return generate_report_via_agent(
                proj, self._report_info, active, columns_map,
                checked_order=list(active.keys()), output_path=fp,
                on_log=on_log)

        self._report_worker = _ReportWorker(_run, fp)
        self._report_worker.progress.connect(self._status)
        self._report_worker.succeeded.connect(self._on_report_done)
        self._report_worker.failed.connect(self._on_report_failed)
        self._status(f"Agent 模式生成中（LLM 编排，需数分钟，请勿关闭）-> {fp}")
        self._report_worker.start()

    def _on_report_done(self, fp, result):
        """生成完成（主线程）：状态栏 + 结果弹窗。"""
        self._status(f"报告生成成功 -> {fp}")
        self.controller.bus.emit("report.generated", fp)
        QMessageBox.information(
            self.win, "生成成功", self._report_result_message(fp, result))

    def _on_report_failed(self, err):
        """生成失败（主线程）：Agent 与直接生成均失败时提示。"""
        self._status("报告生成失败")
        QMessageBox.critical(self.win, "生成失败", err)

    @staticmethod
    def _report_result_message(fp, result):
        """统一组装结果提示（含生成方式/回退原因/跳过项/列匹配提示）。"""
        msg = (f"报告已生成：{fp}\n\n"
               f"共填充 {result['tables']} 张检测结果一览表。")
        if result.get("engine") == "agent":
            msg += (f"\n\n生成方式：Agent 模式"
                    f"（{result.get('model', '')}，{result.get('rounds', 0)} 轮工具调用）。")
        elif result.get("fallback_reason"):
            msg += (f"\n\nAgent 模式不可用，已自动回退普通生成："
                    f"{result['fallback_reason']}")
        if result.get("skipped"):
            msg += "\n\n未生成一览表的项目：\n" + "\n".join(result["skipped"])
        if result.get("warnings"):
            msg += "\n\n列匹配提示（请打开报告核对）：\n" + "\n".join(
                result["warnings"][:20])
        return msg

    # ═══════════════════════════════════════════════════════════
    #  项目保存 / 加载
    # ═══════════════════════════════════════════════════════════
    def _structure_data_dir(self):
        """各结构类型独立的项目数据目录（未指定结构类型时返回空串）。

        目录为 <report_generator>/data/projects/<结构类型>/，各结构
        类型的项目文件相互独立、互不耦合；不存在时自动创建。
        """
        if not self.structure_type:
            return ""
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        d = os.path.join(root, "data", "projects", self.structure_type)
        os.makedirs(d, exist_ok=True)
        return d

    def _filter_loaded_data_to_structure(self):
        """专属录入界面加载项目时，仅保留本结构类型的工作表数据。

        返回被过滤掉的其他结构类型工作表数量，保证各结构类型数据
        独立、不耦合。
        """
        keep, dropped = {}, 0
        for key, rows in self.sheet_data.items():
            base, _comp = self._parse_sheet_key(key)
            try:
                plugin = self.controller.get_plugin_for_item(
                    self.controller.resolve_item_name(base))
                st = plugin.structure_type if plugin is not None else None
            except Exception:
                st = None
            if st == self.structure_type:
                keep[key] = rows
            else:
                dropped += 1
        self.sheet_data = keep
        if self._checked_items:
            self._checked_items = [
                k for k in self._checked_items if k in keep]
        return dropped

    def _save_project(self):
        """保存项目到 JSON 文件（专属录入界面默认存到该结构类型目录）"""
        self._save_current_notes()
        self._sync_table_to_data()
        start_dir = self._structure_data_dir()
        default_fp = (os.path.join(start_dir, f"{self.project_name}.json")
                      if start_dir else f"{self.project_name}.json")
        fp, _ = QFileDialog.getSaveFileName(
            self.win, "保存项目", default_fp,
            "JSON文件 (*.json)",
        )
        if not fp:
            return
        # 只保存当前仍勾选（未删除）的检测项目数据，残留数据不写入文件
        active = self._active_sheet_data()
        state = self.controller.serialize(
            self.project_name, active,
            {k: v for k, v in self._merges.items() if k in active},
            {k: v for k, v in self._merge_formats.items() if k in active},
            {k: v for k, v in self._cell_formats.items() if k in active},
            {k: v for k, v in self._cd_params.items() if k in active},
            self.notes_panel.notes,
            report_info=self._report_info,
        )
        try:
            self.controller.save_project_file(fp, state)
            self._status(f"已保存: {fp}")
            self.controller.bus.emit("project.saved", fp)
        except Exception as e:
            QMessageBox.critical(self.win, "保存失败", str(e))

    def _load_project(self):
        """从 JSON 文件加载项目（专属录入界面默认从该结构类型目录打开，
        并只保留本结构类型的工作表数据）"""
        fp, _ = QFileDialog.getOpenFileName(
            self.win, "加载项目", self._structure_data_dir(),
            "JSON文件 (*.json)"
        )
        if not fp:
            return
        try:
            saved = self.controller.load_project_file(fp)
        except Exception as e:
            QMessageBox.critical(self.win, "加载失败", str(e))
            return

        # 反序列化由控制器统一处理
        (project_name, self.sheet_data, self._merges,
         self._merge_formats, self._cell_formats,
         self._cd_params, operation_notes,
         self._checked_items, report_info) = self.controller.deserialize(saved)
        self._report_info = report_info or {}
        dropped = 0
        if self.structure_type:
            dropped = self._filter_loaded_data_to_structure()
        self.notes_panel.set_notes(operation_notes)
        self.project_name = project_name or PROJECT_NAME
        if hasattr(self, "project_name_edit"):
            self.project_name_edit.setText(self.project_name)
        # 重建公式引擎
        self._formula_engine = FormulaEngine(self.sheet_data)
        # 勾选树中已有数据的项
        if self._checked_items is not None:
            self._restore_checked_items()
        else:
            self._check_tree_by_data()
        # 加载第一个有数据的工作表
        first = next((k for k in self.sheet_data if self.sheet_data[k]), None)
        if first:
            self._load_item(first)
        else:
            self.current_item = None
            self._clear_table()
        if dropped:
            self._status(
                f"已加载: {fp}（已过滤 {dropped} 个其他结构类型的工作表）")
        else:
            self._status(f"已加载: {fp}")
        self.controller.bus.emit("project.loaded", fp)

    # ═══════════════════════════════════════════════════════════
    #  回弹法外部数据导入
    # ═══════════════════════════════════════════════════════════
    def _import_rebound_data(self):
        """从外部 Excel/CSV 导入回弹法检测记录。"""
        if not self.current_item:
            QMessageBox.information(
                self.win, "导入外部数据（回弹法）",
                "请先在左侧勾选并激活一个“回弹法检测”工作表。",
            )
            return
        base, _comp = self._parse_sheet_key(self.current_item)
        base = self.controller.resolve_item_name(base)
        if base != "回弹法检测":
            QMessageBox.information(
                self.win, "导入外部数据（回弹法）",
                "当前不是“回弹法检测”工作表，请先切换到回弹法检测项目。",
            )
            return

        fp, _ = QFileDialog.getOpenFileName(
            self.win, "导入外部数据（回弹法）", "",
            "Excel/CSV文件 (*.xlsx *.xlsm *.csv)",
        )
        if not fp:
            return

        try:
            raw = self._read_tabular_file(fp)
        except Exception as e:
            QMessageBox.critical(self.win, "导入失败", str(e))
            return
        if not raw:
            QMessageBox.warning(
                self.win, "导入外部数据（回弹法）", "外部文件为空。")
            return

        # ── 报告版式优先解析：“混凝土强度试验检测报告（回弹法）”每构件一页 ──
        report_rows = self._parse_rebound_report_rows(raw, os.path.basename(fp))
        if report_rows:
            imported = report_rows
        else:
            cols = self._get_columns(self.current_item)
            # 智能识别表头行：外部文件前几行可能是标题/合并行，取与回弹法字段
            # 匹配数最多的行作为表头
            header_idx, headers = self._detect_header_row(raw, cols)
            rows = raw[header_idx + 1:]

            mapping = {}
            used_sources = set()
            for target_idx, target_name in enumerate(cols):
                source_idx = self._match_header_index(headers, target_name,
                                                      used_sources)
                if source_idx is not None:
                    mapping[target_idx] = source_idx
                    used_sources.add(source_idx)
            if not mapping:
                preview = "、".join(
                    str(h) for h in headers[:12] if str(h).strip()) or "（空表头）"
                QMessageBox.warning(
                    self.win, "导入外部数据（回弹法）",
                    "未能识别到匹配列，请检查外部文件表头是否包含回弹法字段。\n\n"
                    f"当前检测表字段：{('、'.join(cols))}\n"
                    f"外部文件表头：{preview}\n\n"
                    "提示：支持两种外部格式：\n"
                    "1. 平铺表格：表头含“构件名称、构件轴号、设计强度等级、"
                    "平均强度值、标准差、最小测区强度值、强度推定值、龄期”；\n"
                    "2. 报告版式：“混凝土强度试验检测报告（回弹法）”"
                    "每构件一页（自动按页提取）。",
                )
                return

            imported = []
            for source_row in rows:
                row_data = ["" for _ in cols]
                for target_idx, source_idx in mapping.items():
                    if source_idx < len(source_row):
                        val = source_row[source_idx]
                        row_data[target_idx] = "" if val is None else str(val).strip()
                if any(cell for cell in row_data):
                    imported.append(row_data)
        if not imported:
            QMessageBox.information(
                self.win, "导入外部数据（回弹法）",
                "外部文件中没有可导入的数据行。",
            )
            return

        box = QMessageBox(self.win)
        box.setWindowTitle("导入外部数据（回弹法）")
        if report_rows:
            box.setText(
                f"已按报告版式解析 {len(imported)} 个构件的汇总数据。\n"
                "请选择导入方式："
            )
        else:
            box.setText(
                f"已识别 {len(mapping)} 列，共 {len(imported)} 行数据。\n"
                "请选择导入方式："
            )
        append_btn = box.addButton("追加到当前表", QMessageBox.AcceptRole)
        replace_btn = box.addButton("替换当前表", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked not in (append_btn, replace_btn):
            return

        self._sync_table_to_data()
        existing = self._trim_empty_tail_rows(
            self.sheet_data.get(self.current_item, [])
        )
        if clicked is replace_btn:
            new_data = imported
        else:
            new_data = existing + imported
        self.sheet_data[self.current_item] = new_data
        self._load_item(self.current_item)
        self._status(f"已导入 {len(imported)} 行回弹法数据")

    # ── 主题切换（Fluent 浅色/深色）──
    def _theme_light(self):
        self._apply_theme("light")

    def _theme_dark(self):
        self._apply_theme("dark")

    def _apply_theme(self, name):
        """应用主题并持久化，状态栏反馈。"""
        from framework.ui.theme import apply_theme as _apply
        theme = _apply(self.app, name)
        save_theme(theme)
        label = "浅色" if theme == "light" else "深色"
        self._status(f"已切换为{label}主题（Fluent 风格）")

    def _open_norm_qa(self):
        """打开规范条文问答对话框（条号精确/自然语言检索 + AI 解释）。"""
        from framework.ui.norm_qa_dialog import NormQADialog
        dlg = NormQADialog(self.win)
        dlg.exec_()

    def _open_batch_review(self):
        """打开批量审查对话框（报告分块提取审查候选 + 规范依据 + 导出 Word）。"""
        from framework.ui.batch_review_dialog import BatchReviewDialog
        dlg = BatchReviewDialog(self.win,
                                project_name=self.project_name.strip())
        dlg.exec_()

    def _open_scan_recognition(self):
        """打开文档扫描识别对话框（第1~8步流水线）。"""
        from report_generator.scan_recognition.gui import ScanRecognitionDialog
        dlg = ScanRecognitionDialog(self, parent=self.win)
        dlg.exec_()

    def _open_scan_history(self):
        """打开识别记录查看对话框（所有识别过的检测项目默认保留位置）。"""
        from report_generator.scan_recognition.history import ScanHistoryDialog
        dlg = ScanHistoryDialog(parent=self.win)
        dlg.exec_()

    def _word_to_excel(self):
        """将 Word 回弹记录转换为恩施格式 Excel。"""
        fp, _ = QFileDialog.getOpenFileName(
            self.win, "Word 转回弹 Excel", "",
            "Word文件 (*.doc *.docx)",
        )
        if not fp:
            return
        default_out = fp.rsplit(".", 1)[0] + "_恩施格式.xlsx"
        out_fp, _ = QFileDialog.getSaveFileName(
            self.win, "保存为 Excel", default_out,
            "Excel文件 (*.xlsx)",
        )
        if not out_fp:
            return
        try:
            convert_word_to_excel(fp, out_fp)
        except Exception as e:
            QMessageBox.critical(self.win, "转换失败", str(e))
            return
        QMessageBox.information(
            self.win, "转换成功",
            f"已生成：\n{out_fp}\n\n请打开文件核对数据位置与格式。",
        )
        self._status(f"已转换 Word 回弹记录 -> {out_fp}")

    @staticmethod
    def _trim_empty_tail_rows(rows):
        """剪除尾部全空行。"""
        data = [list(r) for r in (rows or [])]
        last = len(data) - 1
        while last >= 0 and not any(str(cell).strip() for cell in data[last]):
            last -= 1
        return data[:last + 1] if last >= 0 else []

    @staticmethod
    def _normalize_header(text):
        """表头归一化：去【项目名】前缀、去空格、去括号单位，便于字段匹配。"""
        text = str(text or "").strip()
        text = re.sub(r"【[^】]*】", "", text)      # 去掉 All 页“【项目名】”前缀
        text = re.sub(r"[（(].*?[)）]", "", text)   # 去掉括号内的单位
        return re.sub(r"\s+", "", text)

    @staticmethod
    def _match_header_index(headers, target_name, used=None):
        """在外部表头中查找目标列：精确 → 包含 → 近似，返回列索引或 None。"""
        normalized_target = ReportGeneratorApp._normalize_header(target_name)
        if not normalized_target:
            return None
        normalized_headers = [ReportGeneratorApp._normalize_header(h)
                              for h in headers]
        # 1) 精确匹配
        for idx, nh in enumerate(normalized_headers):
            if nh and nh == normalized_target and not (used and idx in used):
                return idx
        # 2) 包含匹配（如“构件编号”匹配“构件编号/轴线编号”这类组合表头）
        for idx, nh in enumerate(normalized_headers):
            if not nh or (used and idx in used):
                continue
            if normalized_target in nh or nh in normalized_target:
                return idx
        # 3) 近似匹配（difflib 相似度，容忍错别字/多字少字）
        import difflib
        best_idx, best_ratio = None, 0.0
        for idx, nh in enumerate(normalized_headers):
            if not nh or (used and idx in used):
                continue
            ratio = difflib.SequenceMatcher(
                None, normalized_target, nh).ratio()
            if ratio > best_ratio:
                best_idx, best_ratio = idx, ratio
        if best_idx is not None and best_ratio >= 0.6:
            return best_idx
        return None

    @staticmethod
    def _detect_header_row(raw_rows, cols):
        """在前10行中找出与目标字段匹配数最多的行作为表头行。

        返回 (行索引, 该行)。默认第0行（原行为）。要求至少匹配2个字段，
        避免把普通数据行误判为表头。
        """
        best_idx, best_count = 0, -1
        for i, row in enumerate(raw_rows[:10]):
            headers = [str(cell).strip() for cell in row]
            count = sum(
                1 for name in cols
                if ReportGeneratorApp._match_header_index(headers, name)
                is not None
            )
            if count > best_count:
                best_idx, best_count = i, count
        if best_count >= 2:
            return best_idx, [str(c).strip() for c in raw_rows[best_idx]]
        return 0, [str(c).strip() for c in raw_rows[0]]

    @staticmethod
    def _split_rebound_axis(axis, member_kw):
        """把工程部位值拆成（构件名称, 构件轴号）。

        如 '-1FL 9-10-1/A'：'-1FL' 为构件位置（楼层）→ 构件名称，
        '9-10-1/A' 为轴号。构件名称仅保留位置部分（-1FL），不拼接
        构件类型；无位置前缀时回退为构件类型关键字（梁/柱等）。
        """
        axis = (axis or "").strip()
        m = re.match(r"^([+-]?\d+FL)\s*(.*)$", axis, re.I)
        if m:
            floor, rest = m.group(1), m.group(2).strip()
            return (floor or (member_kw or "")), (rest or axis)
        return (member_kw or ""), axis

    @staticmethod
    def _parse_rebound_report_rows(raw_rows, source_name=""):
        """解析“混凝土强度试验检测报告（回弹法）”版式（每构件一页）。

        逐页提取：构件轴号(工程部位/用途)、龄期(d)、设计强度等级、
        平均强度值/标准差/最小测区强度值(统计评定行)、强度推定值。
        返回与回弹法检测汇总 8 列对齐的行；非报告版式返回 []。
        """
        pages = []
        cur = None
        for row in raw_rows:
            cells = ["" if c is None else str(c).strip() for c in row]
            text = " ".join(c for c in cells if c)
            if "工程部位" in text and "用途" in text:
                if cur:
                    pages.append(cur)
                cur = {"axis": "", "age": "", "grade": "", "est": "",
                       "mean": "", "std": "", "minv": "", "_pending": False}
                idx = next((i for i, c in enumerate(cells)
                            if "工程部位" in c), -1)
                for c in cells[idx + 1:]:
                    if c and c != "/" and c != "-":
                        cur["axis"] = c
                        break
                continue
            if cur is None:
                continue
            if "龄期" in text and not cur["age"]:
                idx = next((i for i, c in enumerate(cells) if "龄期" in c), -1)
                for c in cells[idx + 1:]:
                    m = re.match(r"^(\d+(?:\.\d+)?)", c)
                    if m:
                        cur["age"] = m.group(1)
                        break
            if "设计强度" in text and not cur["grade"]:
                idx = next((i for i, c in enumerate(cells)
                            if "设计强度" in c), -1)
                for c in cells[idx + 1:]:
                    if c and c != "/" and c != "-":
                        cur["grade"] = c
                        break
            if "强度推定值" in text and not cur["est"]:
                idx = next((i for i, c in enumerate(cells)
                            if "强度推定值" in c), -1)
                for c in cells[idx + 1:] + cells[max(idx - 1, 0):idx]:
                    m = re.search(r"(\d+(?:\.\d+)?)", c)
                    if m:
                        cur["est"] = m.group(1)
                        break
            if "构件测区最小值" in text:
                cur["_pending"] = True
                continue
            if cur.get("_pending"):
                nums = []
                for c in cells:
                    m = re.match(r"^(\d+(?:\.\d+)?)$", c)
                    if m:
                        nums.append(m.group(1))
                    if len(nums) == 3:
                        break
                if len(nums) == 3:
                    cur["mean"], cur["std"], cur["minv"] = nums
                cur["_pending"] = False
        if cur:
            pages.append(cur)
        if not pages:
            return []
        # 构件类型关键字：来源文件名中的 梁/柱/墙/板/基础
        name_kw = ""
        for kw in ("梁", "柱", "墙", "板", "基础"):
            if kw in source_name:
                name_kw = kw
                break
        rows = []
        for p in pages:
            member_name, axis_no = ReportGeneratorApp._split_rebound_axis(
                p["axis"], name_kw)
            rows.append([member_name, axis_no, p["grade"], p["mean"],
                         p["std"], p["minv"], p["est"], p["age"]])
        return rows

    @staticmethod
    def _read_tabular_file(filepath):
        """读取 Excel/CSV 全部原始行（表头行由调用方智能识别）。"""
        ext = filepath.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            import csv
            with open(filepath, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                raw = list(reader)
        else:
            from openpyxl import load_workbook
            wb = load_workbook(filepath, data_only=True, read_only=True)
            ws = wb.active
            raw = [list(row) for row in ws.iter_rows(values_only=True)]
            wb.close()
        return raw

    # ═══════════════════════════════════════════════════════════
    #  应用级辅助动作（菜单）
    # ═══════════════════════════════════════════════════════════
    def _quit(self):
        self.win.close()

    def _toggle_notes_panel(self):
        if not hasattr(self, "notes_panel"):
            return
        is_visible = self.notes_panel.isVisible()
        self.notes_panel.setVisible(not is_visible)
        self._status(
            "已隐藏操作步骤说明面板" if is_visible else "已显示操作步骤说明面板"
        )

    def _show_help(self):
        QMessageBox.information(
            self.win, "操作说明",
            "1. 在左侧检测项目树中勾选需要检测的项目或构件。\n"
            "2. 灰色“输入区”列由检测人员填写实测数据。\n"
            "3. “计算区”列由系统自动计算，不可编辑。\n"
            "4. 右侧面板会显示当前检测模块的操作步骤说明。",
        )

    def _show_shortcuts(self):
        QMessageBox.information(
            self.win, "快捷键说明",
            "Ctrl+E：导出Excel\n"
            "Ctrl+Shift+S：保存项目\n"
            "Ctrl+Shift+O：加载项目\n"
            "Ctrl+Z / Ctrl+Y：撤销 / 重做\n"
            "Ctrl+C / Ctrl+X / Ctrl+V：复制 / 剪切 / 粘贴\n"
            "Ctrl+H：查找替换\n"
            "Ctrl+M：合并居中\n"
            "Ctrl+F9：批推定计算（钻芯法）",
        )

    def _show_about(self):
        QMessageBox.about(
            self.win, "关于",
            "主体结构检测报告数据管理录入系统 V1.0",
        )

    # ═══════════════════════════════════════════════════════════
    #  系统更新检查（读取本地版本配置文件，提醒是否有新版本）
    # ═══════════════════════════════════════════════════════════
    def _check_update(self):
        """读取本地 update_config.json，对比版本号并给出系统更新提示。"""
        config = get_asset("update_config.json")
        try:
            with open(str(config), "r", encoding="utf-8") as f:
                info = json.load(f)
        except FileNotFoundError:
            QMessageBox.warning(
                self.win, "系统更新提示",
                "未找到更新配置文件，无法检查更新。",
            )
            return
        except Exception as e:
            QMessageBox.warning(
                self.win, "系统更新提示",
                f"读取更新配置失败：{e}",
            )
            return

        current = str(info.get("current_version", "")).strip()
        latest = str(info.get("latest_version", "")).strip()
        title = info.get("update_title") or "系统更新提示"
        changelog = info.get("changelog") or []

        if not current or not latest:
            QMessageBox.warning(
                self.win, title,
                "更新配置缺少版本信息，无法检查更新。",
            )
            return

        def _parse(v):
            """把 '1.0' / '1.0.2' 转成可比较的整数元组。"""
            parts = []
            for p in re.split(r"[._-]", v):
                if p.isdigit():
                    parts.append(int(p))
            return tuple(parts) or (0,)

        up_to_date = _parse(current) >= _parse(latest)

        if up_to_date:
            QMessageBox.information(
                self.win, title,
                f"当前版本：V{current}\n"
                f"最新版本：V{latest}\n\n"
                f"{info.get('update_content') or '当前已是最新版本，无需更新。'}",
            )
            return

        log_text = "\n".join(f"• {item}" for item in changelog)
        QMessageBox.information(
            self.win, title,
            f"检测到新版本：V{latest}\n"
            f"当前版本：V{current}\n\n"
            f"更新说明：\n{log_text or '（无更新说明）'}\n\n"
            f"请更新系统后再使用。",
        )
