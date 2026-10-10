# -*- coding: utf-8 -*-
"""UI 面板组件：从主窗口提取的独立 QWidget 面板。

NotesPanel：操作步骤说明面板，按检测模块（sheet_key）保存/加载说明文本，
自行管理内部文本编辑器与加载状态，主窗口仅做调度。
TreePanel：检测项目树面板（搜索 + 全选/全不选 + 三级树），
仅负责树的展示与状态操作，勾选/点击通过信号抛给主窗口处理业务逻辑。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QTabWidget,
)

from framework.ui.theme import FONT_FAMILY, FONT_SIZE


class NotesPanel(QWidget):
    """操作步骤说明面板。

    内部维护 {sheet_key: 说明文本} 字典：切换工作表时先保存当前文本，
    再加载目标工作表的说明；文本变化时自动保存到当前 key。
    """

    calcRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notes = {}          # {sheet_key: 说明文本}
        self._defaults = {}       # {sheet_key: 默认说明文本}
        self._current_key = None  # 当前对应的检测模块键
        self._loading = False     # 程序化写入文本时抑制自动保存

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        title = QLabel("操作步骤说明")
        title.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(title)

        self._edit = QTextEdit()
        self._edit.setPlaceholderText("在此填写当前检测模块的操作步骤说明...")
        self._edit.setMinimumWidth(220)
        self._edit.setMaximumWidth(460)
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit, 1)

        self.calc_button = QPushButton("点击计算")
        self.calc_button.clicked.connect(self.calcRequested.emit)
        layout.addWidget(self.calc_button)

    # ── 对外接口 ──
    @property
    def notes(self):
        """{sheet_key: 说明文本} 字典（供序列化/反序列化）。"""
        return self._notes

    def set_notes(self, notes):
        """整体替换说明字典（从项目文件加载时）。"""
        self._notes = dict(notes or {})

    def set_defaults(self, defaults):
        """设置默认说明字典；用户未编辑时，加载时回退到默认文案。"""
        self._defaults = dict(defaults or {})

    def save_current(self):
        """把当前文本框内容保存到当前检测模块。"""
        if self._current_key is None:
            return
        text = self._edit.toPlainText()
        if text.strip():
            self._notes[self._current_key] = text
        else:
            self._notes.pop(self._current_key, None)

    def load_for(self, key):
        """加载指定检测模块的说明文本（key 为 None 时清空）。"""
        self._loading = True
        try:
            self._current_key = key
            text = ""
            if key:
                text = self._notes.get(key)
                if text is None:
                    text = self._defaults.get(key, "")
            self._edit.setPlainText(text)
        finally:
            self._loading = False

    def remove(self, key):
        """删除指定检测模块的说明（工作表被删除时）。"""
        self._notes.pop(key, None)

    # ── 内部 ──
    def _on_text_changed(self):
        if self._loading:
            return
        self.save_current()


class TreePanel(QWidget):
    """检测项目树面板：搜索框 + 全选/全不选按钮 + 三级检测项目树。

    仅负责树的展示与状态操作（填充/过滤/勾选/查询）；
    勾选变化与节点点击通过信号抛给主窗口处理业务逻辑
    （创建工作表、弹出参数对话框、加载表格等）。
    """

    # 转发树的交互信号（批量状态操作时面板内部已屏蔽，不会误触发）
    itemCheckChanged = pyqtSignal(object, int)   # 叶节点勾选状态变化
    itemLeafClicked = pyqtSignal(object, int)    # 点击树节点
    selectAllRequested = pyqtSignal()            # 点击「全选」按钮
    deselectAllRequested = pyqtSignal()          # 点击「全不选」按钮

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # ── 搜索框 ──
        search_layout = QHBoxLayout()
        search_layout.setSpacing(2)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索检测项目...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self.filter)
        search_layout.addWidget(self._search)
        layout.addLayout(search_layout)

        # ── 全选/全不选按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(2)
        btn_select_all = QPushButton("全选")
        btn_select_all.setMaximumWidth(60)
        btn_select_all.clicked.connect(self.selectAllRequested.emit)
        btn_deselect_all = QPushButton("全不选")
        btn_deselect_all.setMaximumWidth(80)
        btn_deselect_all.clicked.connect(self.deselectAllRequested.emit)
        btn_layout.addWidget(btn_select_all)
        btn_layout.addWidget(btn_deselect_all)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ── 树控件 ──
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(200)
        self._tree.setMaximumWidth(450)
        self._tree.itemChanged.connect(self.itemCheckChanged.emit)
        self._tree.itemClicked.connect(self.itemLeafClicked.emit)
        layout.addWidget(self._tree)

    # ── 填充 ──
    def populate(self, detection_data, make_sheet_key):
        """按检测项目数据填充三级树（信号屏蔽，不触发勾选业务）。

        :param detection_data: {类别: {项目名: [构件, ...]}} 三级结构
        :param make_sheet_key: 回调 (项目名, 构件名) → 工作表键
        """
        self._tree.blockSignals(True)
        try:
            self._tree.clear()
            for category, items in detection_data.items():
                cat_node = QTreeWidgetItem([category])
                cat_node.setFont(0, QFont(FONT_FAMILY, FONT_SIZE, QFont.Bold))
                self._tree.addTopLevelItem(cat_node)
                for item_name, components in items.items():
                    item_node = QTreeWidgetItem([item_name])
                    cat_node.addChild(item_node)
                    if components:
                        # 有构件子节点：构件为可勾选叶节点
                        for comp in components:
                            comp_node = QTreeWidgetItem([comp])
                            comp_node.setData(0, Qt.UserRole,
                                               make_sheet_key(item_name, comp))
                            comp_node.setCheckState(0, Qt.Unchecked)
                            item_node.addChild(comp_node)
                    else:
                        # 无构件：项目本身为可勾选叶节点
                        item_node.setData(0, Qt.UserRole, item_name)
                        item_node.setCheckState(0, Qt.Unchecked)
            self._tree.expandAll()
        finally:
            self._tree.blockSignals(False)

    # ── 搜索过滤 ──
    def filter(self, text):
        """根据搜索文本过滤树节点（类别/项目/构件三级匹配）"""
        text = text.strip().lower()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat = root.child(i)
            cat_match = text in cat.text(0).lower() if text else True
            any_child_visible = False
            for j in range(cat.childCount()):
                item = cat.child(j)
                item_match = text in item.text(0).lower() if text else True
                any_comp_visible = False
                if item.childCount() > 0:
                    for k in range(item.childCount()):
                        comp = item.child(k)
                        comp_match = text in comp.text(0).lower() if text else True
                        comp.setHidden(not comp_match)
                        if comp_match:
                            any_comp_visible = True
                    item.setHidden(not (item_match or any_comp_visible))
                    if item_match or any_comp_visible:
                        any_child_visible = True
                else:
                    item.setHidden(not item_match)
                    if item_match:
                        any_child_visible = True
            cat.setHidden(not (cat_match or any_child_visible))
            if cat_match or any_child_visible:
                self._tree.expandItem(cat)

    # ── 批量勾选状态（信号屏蔽，不触发勾选业务）──
    def set_all_checked(self):
        """勾选所有可见叶节点"""
        self._with_signals_blocked(
            lambda leaf: leaf.setCheckState(0, Qt.Checked),
            visible_only=True,
        )

    def set_all_unchecked(self):
        """取消所有叶节点勾选"""
        self._with_signals_blocked(
            lambda leaf: leaf.setCheckState(0, Qt.Unchecked)
        )

    def check_by_keys(self, keys):
        """勾选 key 在集合中的叶节点，其余取消勾选（加载项目时恢复状态）"""
        checked = set(keys)
        self._tree.blockSignals(True)
        try:
            for leaf in self._iter_leaves():
                key = leaf.data(0, Qt.UserRole)
                leaf.setCheckState(
                    0, Qt.Checked if key in checked else Qt.Unchecked)
        finally:
            self._tree.blockSignals(False)

    def uncheck(self, key):
        """按 key 取消对应叶节点勾选（关闭标签页时）"""
        self._tree.blockSignals(True)
        try:
            leaf = self.find_item(key)
            if leaf is not None:
                leaf.setCheckState(0, Qt.Unchecked)
        finally:
            self._tree.blockSignals(False)

    def check_leaf(self, key):
        """按 key 勾选叶节点（不屏蔽信号，触发正常勾选业务：建表/参数对话框/加载）"""
        leaf = self.find_item(key)
        if leaf is not None:
            leaf.setCheckState(0, Qt.Checked)

    def leaf_keys(self):
        """返回所有叶节点的工作表键（含未勾选项），用于按类型查找检测项目"""
        return [leaf.data(0, Qt.UserRole) for leaf in self._iter_leaves()
                if leaf.data(0, Qt.UserRole) is not None]

    # ── 查询 ──
    def is_leaf_checked(self, key):
        """检查指定键对应的叶节点是否已勾选"""
        for leaf in self._iter_leaves():
            if leaf.data(0, Qt.UserRole) == key:
                return leaf.checkState(0) == Qt.Checked
        return False

    def find_item(self, key):
        """按 key 查找叶节点对应的 QTreeWidgetItem，找不到返回 None。"""
        for leaf in self._iter_leaves():
            if leaf.data(0, Qt.UserRole) == key:
                return leaf
        return None

    def set_leaf_checked(self, item, checked=True):
        """屏蔽信号地设置指定叶节点勾选状态（用户取消参数对话框时回退用）"""
        self._tree.blockSignals(True)
        try:
            item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._tree.blockSignals(False)

    # ── 内部 ──
    def _iter_leaves(self):
        """遍历所有带工作表键的叶节点（含构件叶与无构件的项目叶）"""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat = root.child(i)
            for j in range(cat.childCount()):
                item = cat.child(j)
                if item.childCount() > 0:
                    for k in range(item.childCount()):
                        comp = item.child(k)
                        if comp.data(0, Qt.UserRole):
                            yield comp
                else:
                    if item.data(0, Qt.UserRole):
                        yield item

    def _with_signals_blocked(self, apply, visible_only=False):
        """屏蔽信号地对每个叶节点应用操作"""
        self._tree.blockSignals(True)
        try:
            for leaf in self._iter_leaves():
                if visible_only and leaf.isHidden():
                    continue
                apply(leaf)
        finally:
            self._tree.blockSignals(False)


class SheetTabsBar(QTabWidget):
    """底部工作表标签栏（已勾选工作表的切换/关闭入口）。

    仅负责标签的展示与状态同步（sync）；关闭与切换转换为 sheet_key
    信号抛给主窗口处理业务逻辑（取消树勾选、加载工作表等）。
    """

    closeKeyRequested = pyqtSignal(str)   # 点击标签关闭按钮（携带 sheet_key）
    switchKeyRequested = pyqtSignal(str)  # 切换标签（携带 sheet_key）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMaximumHeight(30)
        self.tabCloseRequested.connect(self._on_close_requested)
        self.currentChanged.connect(self._on_current_changed)

    # ── 状态同步 ──
    def sync(self, sheet_keys, is_active, current_key):
        """同步标签页：移除失效标签、添加新标签、高亮当前工作表。

        :param sheet_keys: 工作表键的可迭代对象（顺序即标签顺序）
        :param is_active: callable(key) -> bool，标签是否应显示（已勾选）
        :param current_key: 当前工作表键（高亮对应标签）
        """
        self.blockSignals(True)
        try:
            # 移除已不在 sheet_data 中的标签
            for i in range(self.count() - 1, -1, -1):
                key = self.tabText(i)
                if key not in sheet_keys or not is_active(key):
                    self.removeTab(i)

            # 添加新的标签
            existing = {self.tabText(i) for i in range(self.count())}
            for key in sheet_keys:
                if is_active(key) and key not in existing:
                    # 简化标签名：过长的截断
                    label = key if len(key) <= 15 else key[:12] + "..."
                    self.addTab(QWidget(), label)
                    self.setTabToolTip(self.count() - 1, key)

            # 高亮当前工作表
            if current_key:
                for i in range(self.count()):
                    if self.tabText(i) == current_key:
                        self.setCurrentIndex(i)
                        break
        finally:
            self.blockSignals(False)

    # ── 内部 ──
    def _on_close_requested(self, index):
        key = self.tabText(index)
        if key:
            self.closeKeyRequested.emit(key)

    def _on_current_changed(self, index):
        # sync() 期间信号被屏蔽，此处在用户点击切换时才触发
        if 0 <= index < self.count():
            key = self.tabText(index)
            if key:
                self.switchKeyRequested.emit(key)
