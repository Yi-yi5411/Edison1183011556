# -*- coding: utf-8 -*-
"""钢筋保护层厚度检测 - 测点录入对话框。

原始记录（HBJG/JJ 0226014）规则：每根主筋在两个端部和跨中各检测 2 次
（共 6 个读数），平均值作为系统"实测值"；同一位置两次读数差 >1mm 时
该组检测数据无效（实时标红提示）。

流程：逐构件录入测点 → 添加到构件列表（可连续录入多个构件）→ 确定后
由主窗口生成原始记录并跳转回填对应保护层工作表。
"""
from datetime import date

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QPushButton, QDialogButtonBox,
    QMessageBox, QAbstractItemView, QFrame,
)

# 测点表格列：6 个读数 + 自动平均值
READING_HEADERS = ['端部①-1', '端部①-2', '跨中-1', '跨中-2',
                   '端部②-1', '端部②-2', '平均值']
READING_COL_COUNT = 6
INVALID_BG = QColor(255, 130, 130)   # 无效组（两次读数差>1mm）标红


class CoverPointEntryDialog(QDialog):
    """保护层厚度测点录入对话框（批量多构件）。"""

    def __init__(self, project_keys, parent=None, defaults=None):
        super().__init__(parent)
        self.setWindowTitle("测点录入（保护层原始记录）")
        self.resize(860, 560)
        self._components = []      # 已添加构件 [{...}, ...]
        self._updating = False     # itemChanged 重入保护
        defaults = dict(defaults or {})
        self._project_keys = list(project_keys)
        self._defaults = defaults
        self._setup_ui()

    # ── UI ──
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(14, 14, 14, 10)

        # 顶部：构件信息表单（两列布局压缩高度）
        info_row = QHBoxLayout()
        form_left = QFormLayout()
        form_left.setSpacing(6)
        form_right = QFormLayout()
        form_right.setSpacing(6)

        self.cmb_project = QComboBox()
        for key in self._project_keys:
            self.cmb_project.addItem(key)
        form_left.addRow("检测项目:", self.cmb_project)

        self.ed_building = QLineEdit(str(self._defaults.get('楼栋', '')))
        self.ed_building.setPlaceholderText("如: 1#楼")
        form_left.addRow("楼栋:", self.ed_building)

        self.ed_component = QLineEdit()
        self.ed_component.setPlaceholderText("如: 1#楼2层框架梁")
        form_left.addRow("构件名称:", self.ed_component)

        self.ed_position = QLineEdit()
        self.ed_position.setPlaceholderText("如: 2层FL-3")
        form_right.addRow("构件位置及名称:", self.ed_position)

        self.ed_axis = QLineEdit()
        self.ed_axis.setPlaceholderText("如: 1/A")
        form_right.addRow("构件轴线编号:", self.ed_axis)

        self.sp_design = QDoubleSpinBox()
        self.sp_design.setRange(1.0, 300.0)
        self.sp_design.setDecimals(1)
        self.sp_design.setSuffix(" mm")
        self.sp_design.setValue(15.0)
        form_right.addRow("保护层厚度设计值:", self.sp_design)

        self.sp_rebars = QSpinBox()
        self.sp_rebars.setRange(1, 10)
        self.sp_rebars.setValue(1)
        self.sp_rebars.setSuffix(" 根")
        self.sp_rebars.valueChanged.connect(self._on_count_changed)
        form_right.addRow("主筋根数(测点数):", self.sp_rebars)

        info_row.addLayout(form_left, 1)
        info_row.addLayout(form_right, 1)
        root.addLayout(info_row)

        # 原始记录抬头信息（生成 Word 时填充模板信息区）
        head_row = QHBoxLayout()
        head_row.addWidget(QLabel("记录抬头："))
        self.ed_serial = QLineEdit(
            str(self._defaults.get('检测编号', '')))
        self.ed_serial.setPlaceholderText("检测编号，如 JJ0226014")
        self.ed_project_name = QLineEdit(
            str(self._defaults.get('工程名称', '')))
        self.ed_project_name.setPlaceholderText("工程名称")
        self.ed_test_date = QLineEdit(
            str(self._defaults.get('检测日期', date.today().strftime('%Y年%m月%d日'))))
        self.ed_test_date.setPlaceholderText("检测日期")
        head_row.addWidget(QLabel("检测编号:"), 0)
        head_row.addWidget(self.ed_serial, 1)
        head_row.addWidget(QLabel("工程名称:"), 0)
        head_row.addWidget(self.ed_project_name, 2)
        head_row.addWidget(QLabel("检测日期:"), 0)
        head_row.addWidget(self.ed_test_date, 1)
        root.addLayout(head_row)

        # 中部：左侧已录入构件列表 + 右侧测点表格
        mid_row = QHBoxLayout()
        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("已录入构件："))
        self.lst_components = QListWidget()
        self.lst_components.setSelectionMode(QAbstractItemView.SingleSelection)
        left_box.addWidget(self.lst_components, 1)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("添加构件")
        self.btn_add.clicked.connect(self._add_component)
        self.btn_remove = QPushButton("删除选中")
        self.btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        left_box.addLayout(btn_row)
        mid_row.addLayout(left_box, 1)

        table_box = QVBoxLayout()
        table_box.addWidget(QLabel(
            "测点读数(mm)：每根主筋在两个端部和跨中各测 2 次，"
            "平均值自动计算；两次读数差>1mm 标红提示（该组无效）。"))
        self.table = QTableWidget(1, READING_COL_COUNT + 1)
        self.table.setHorizontalHeaderLabels(READING_HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_item_changed)
        table_box.addWidget(self.table, 1)
        mid_row.addLayout(table_box, 3)
        root.addLayout(mid_row, 1)

        # 状态提示
        self.lbl_status = QLabel(" ")
        self.lbl_status.setStyleSheet("color:#b00;")
        root.addWidget(self.lbl_status)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        # 底部按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("生成记录并回填")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        self._on_count_changed(self.sp_rebars.value())

    # ── 表格行为 ──
    def _on_count_changed(self, n):
        """主筋根数变化：调整行数（保留已输入内容）。"""
        self._updating = True
        try:
            self.table.setRowCount(n)
            for r in range(n):
                item = self.table.item(r, READING_COL_COUNT)
                if item is None:
                    item = QTableWidgetItem()
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.table.setItem(r, READING_COL_COUNT, item)
                self._refresh_row(r)
        finally:
            self._updating = False

    def _row_readings(self, r):
        """返回第 r 行的 6 个读数文本。"""
        out = []
        for c in range(READING_COL_COUNT):
            item = self.table.item(r, c)
            out.append(item.text().strip() if item else '')
        return out

    def _refresh_row(self, r):
        """重算第 r 行平均值与无效组标红。"""
        readings = self._row_readings(r)
        valid = True
        for a, b in ((0, 1), (2, 3), (4, 5)):
            pair_invalid = False
            try:
                if readings[a] and readings[b] \
                        and abs(float(readings[a]) - float(readings[b])) > 1.0:
                    pair_invalid = True
                    valid = False
            except ValueError:
                pass
            for c in (a, b):
                item = self.table.item(r, c)
                if item is not None:
                    item.setBackground(INVALID_BG if pair_invalid
                                       else self.table.palette().base())
        # 平均值
        vals = []
        try:
            vals = [float(v) for v in readings]
        except ValueError:
            vals = []
        avg_item = self.table.item(r, READING_COL_COUNT)
        if avg_item is not None:
            avg_item.setText('%.1f' % (sum(vals) / len(vals)) if vals else '')
        return valid

    def _on_item_changed(self, _item):
        if self._updating:
            return
        self._updating = True
        try:
            row = self.table.currentRow()
            if 0 <= row < self.table.rowCount():
                self._refresh_row(row)
            self._update_status()
        finally:
            self._updating = False

    def _invalid_group_count(self):
        """统计当前表格中无效检测组（两次读数差>1mm）数量。"""
        count = 0
        for r in range(self.table.rowCount()):
            readings = self._row_readings(r)
            for a, b in ((0, 1), (2, 3), (4, 5)):
                try:
                    if readings[a] and readings[b] \
                            and abs(float(readings[a]) - float(readings[b])) > 1.0:
                        count += 1
                except ValueError:
                    pass
        return count

    def _update_status(self):
        n = self._invalid_group_count()
        self.lbl_status.setText(
            '当前表格存在 %d 组检测数据无效（两次读数差>1mm）。' % n if n else ' ')

    # ── 构件列表 ──
    def _add_component(self):
        """校验并添加当前构件到列表（不清空抬头，清空测点表便于连续录入）。"""
        project = self.cmb_project.currentText()
        building = self.ed_building.text().strip()
        component_name = self.ed_component.text().strip()
        position = self.ed_position.text().strip()
        axis = self.ed_axis.text().strip()
        design = self.sp_design.value()
        if not building:
            QMessageBox.warning(self, "提示", "请填写楼栋。")
            return
        if not position and not axis:
            QMessageBox.warning(self, "提示", "请至少填写构件位置及名称或构件轴线编号。")
            return
        n = self.table.rowCount()
        readings = []
        for r in range(n):
            row = self._row_readings(r)
            try:
                readings.append([float(v) for v in row])
            except ValueError:
                QMessageBox.warning(
                    self, "提示", "第 %d 根主筋存在空白或非数值读数，请补全。" % (r + 1))
                return
        invalid = self._invalid_group_count()
        if invalid:
            ret = QMessageBox.question(
                self, "确认",
                "存在 %d 组两次读数差>1mm 的检测数据（按记录规则该组无效）。\n"
                "仍要添加该构件吗？" % invalid,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        averages = ['%.1f' % (sum(row) / len(row)) for row in readings]
        self._components.append({
            'project': project,
            'building': building,
            'component_name': component_name or building,
            'position': position,
            'axis': axis,
            'design': design,
            'n_rebars': len(readings),
            'readings': readings,
            'averages': averages,
        })
        label = '%s｜%s｜%s（%d根主筋）' % (
            project.replace('保护层厚度检测', ''),
            building, position or axis, len(readings))
        self.lst_components.addItem(QListWidgetItem(label))
        self.lbl_status.setText(' ')
        # 清空测点表，准备录入下一构件
        self._updating = True
        try:
            self.table.clearContents()
            self._on_count_changed(self.sp_rebars.value())
        finally:
            self._updating = False

    def _remove_selected(self):
        row = self.lst_components.currentRow()
        if row < 0:
            return
        self.lst_components.takeItem(row)
        del self._components[row]

    # ── 确认 / 数据输出 ──
    def _on_accept(self):
        if not self._components:
            QMessageBox.warning(self, "提示", "请先录入并添加至少一个构件的测点数据。")
            return
        self.accept()

    def get_records(self):
        """返回已添加构件列表（word_record 与回填逻辑使用）。"""
        return [dict(comp) for comp in self._components]

    def get_header(self):
        """返回原始记录抬头信息字段。"""
        return {
            '检测编号': self.ed_serial.text().strip(),
            '工程名称': self.ed_project_name.text().strip(),
            '检测日期': self.ed_test_date.text().strip(),
        }
