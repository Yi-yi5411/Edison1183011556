# -*- coding: utf-8 -*-
"""框架通用对话框模块。

仅保留与具体检测项目无关的通用对话框：批量填充、批量插入行、
函数选择器、批量修改、批量行高。

项目专属对话框（如钻芯法参数输入、批推定结果展示）已迁移至对应
插件目录 ``modules/<plugin>/dialogs.py``，框架层不再感知任何具体项目。
"""

from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QRadioButton)


class BatchFillDialog(QDialog):
    """批量填充对话框。

    支持三种模式：
    1. 固定值：所有选中单元格填入同一值
    2. 递增序列：起始值 + 步长，按行列顺序递增
    3. 向下填充首值：选中区域每列填入该列第一个单元格的值
    """

    MODE_FIXED = 0
    MODE_INCREMENT = 1
    MODE_DOWN_FILL = 2

    def __init__(self, parent=None, row_count=1, col_count=1):
        super().__init__(parent)
        self._row_count = row_count
        self._col_count = col_count
        self.setWindowTitle("批量填充")
        self.setMinimumWidth(340)
        self._result = None  # ("mode", value, step)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        info_lbl = QLabel(f"选中区域：{self._row_count} 行 × {self._col_count} 列")
        info_lbl.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(info_lbl)

        # ── 填充模式 ──
        self._grp_mode = QGroupBox("填充模式")
        mode_layout = QVBoxLayout(self._grp_mode)

        self._rb_fixed = QRadioButton("固定值")
        self._rb_increment = QRadioButton("递增序列")
        self._rb_down = QRadioButton("向下填充首值")
        self._rb_fixed.setChecked(True)

        mode_layout.addWidget(self._rb_fixed)
        mode_layout.addWidget(self._rb_increment)
        mode_layout.addWidget(self._rb_down)
        layout.addWidget(self._grp_mode)

        # ── 参数区 ──
        form = QFormLayout()
        form.setSpacing(8)

        self._ed_value = QLineEdit()
        self._ed_value.setPlaceholderText("输入要填入的值（支持文本或数字）")
        self._ed_value.setText("0")
        form.addRow("固定值：", self._ed_value)

        self._ed_start = QLineEdit()
        self._ed_start.setPlaceholderText("起始值")
        self._ed_start.setText("1")
        form.addRow("起始值：", self._ed_start)

        self._ed_step = QLineEdit()
        self._ed_step.setPlaceholderText("步长（可为负数）")
        self._ed_step.setText("1")
        form.addRow("步长：", self._ed_step)

        layout.addLayout(form)

        # ── 按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        # ── 联动 ──
        self._rb_fixed.toggled.connect(lambda c: self._set_param_enabled(c, 0))
        self._rb_increment.toggled.connect(lambda c: self._set_param_enabled(c, 1))
        self._rb_down.toggled.connect(lambda c: self._set_param_enabled(c, 2))
        self._set_param_enabled(True, 0)

    def _set_param_enabled(self, enabled, mode_idx):
        """根据选中模式启用/禁用对应参数"""
        self._ed_value.setEnabled(mode_idx == 0)
        self._ed_start.setEnabled(mode_idx == 1)
        self._ed_step.setEnabled(mode_idx == 1)

    def _on_ok(self):
        if self._rb_fixed.isChecked():
            self._result = (self.MODE_FIXED, self._ed_value.text(), None)
        elif self._rb_increment.isChecked():
            self._result = (self.MODE_INCREMENT,
                            self._ed_start.text(),
                            self._ed_step.text())
        else:
            self._result = (self.MODE_DOWN_FILL, None, None)
        self.accept()

    def get_result(self):
        """返回 (mode, value_or_start, step) 或 None"""
        return self._result


class BatchInsertRowsDialog(QDialog):
    """批量插入行对话框"""
    def __init__(self, parent=None, max_rows=100):
        super().__init__(parent)
        self.setWindowTitle("批量插入行")
        self.setMinimumWidth(300)
        self._result = None
        layout = QFormLayout(self)
        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, 100)
        self._spin_count.setValue(5)
        layout.addRow("插入行数:", self._spin_count)
        self._spin_pos = QSpinBox()
        self._spin_pos.setRange(1, max_rows)
        self._spin_pos.setValue(1)
        layout.addRow("起始位置（第几行）:", self._spin_pos)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addRow(btn_layout)

    def _on_ok(self):
        self._result = (self._spin_pos.value() - 1, self._spin_count.value())
        self.accept()

    def get_result(self):
        return self._result


class FunctionSelectorDialog(QDialog):
    """函数选择器对话框"""
    FUNCTIONS = {
        "SUM": "SUM(A1:A10) - 求和",
        "AVERAGE": "AVERAGE(A1:A10) - 平均值",
        "MAX": "MAX(A1:A10) - 最大值",
        "MIN": "MIN(A1:A10) - 最小值",
        "COUNT": "COUNT(A1:A10) - 计数",
        "IF": "IF(条件, 真值, 假值) - 条件判断",
        "ROUND": "ROUND(A1, 2) - 四舍五入",
        "ABS": "ABS(A1) - 绝对值",
        "SQRT": "SQRT(A1) - 平方根",
        "CONCAT": "CONCAT(A1, B1) - 文本连接",
        "LEFT": "LEFT(A1, 3) - 左取字符",
        "RIGHT": "RIGHT(A1, 3) - 右取字符",
        "MID": "MID(A1, 2, 3) - 中间取字符",
        "TRIM": "TRIM(A1) - 去空格",
        "LEN": "LEN(A1) - 字符长度",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("函数选择器")
        self.setMinimumWidth(350)
        self._result = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("选择函数:"))
        self._combo = QComboBox()
        for name, desc in self.FUNCTIONS.items():
            self._combo.addItem(desc, name)
        layout.addWidget(self._combo)
        layout.addWidget(QLabel("参数（可选，修改模板）:"))
        self._edit_args = QLineEdit()
        layout.addWidget(self._edit_args)
        self._combo.currentIndexChanged.connect(self._on_func_changed)
        self._on_func_changed(0)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("插入")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def _on_func_changed(self, idx):
        name = self._combo.itemData(idx)
        if name == "SUM": self._edit_args.setText("A1:A10")
        elif name == "AVERAGE": self._edit_args.setText("A1:A10")
        elif name == "MAX": self._edit_args.setText("A1:A10")
        elif name == "MIN": self._edit_args.setText("A1:A10")
        elif name == "COUNT": self._edit_args.setText("A1:A10")
        elif name == "IF": self._edit_args.setText("A1>0, \"是\", \"否\"")
        elif name == "ROUND": self._edit_args.setText("A1, 2")
        elif name == "ABS": self._edit_args.setText("A1")
        elif name == "SQRT": self._edit_args.setText("A1")
        elif name == "CONCAT": self._edit_args.setText("A1, B1")
        elif name == "LEFT": self._edit_args.setText("A1, 3")
        elif name == "RIGHT": self._edit_args.setText("A1, 3")
        elif name == "MID": self._edit_args.setText("A1, 2, 3")
        elif name == "TRIM": self._edit_args.setText("A1")
        elif name == "LEN": self._edit_args.setText("A1")

    def _on_ok(self):
        name = self._combo.currentData()
        args = self._edit_args.text().strip()
        self._result = f"={name}({args})"
        self.accept()

    def get_result(self):
        return self._result


class BatchModifyDialog(QDialog):
    """批量修改对话框：算术运算或文本替换"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量修改")
        self.setMinimumWidth(320)
        self._result = None
        layout = QVBoxLayout(self)
        self._grp_mode = QGroupBox("修改模式")
        mode_layout = QVBoxLayout(self._grp_mode)
        self._rb_arith = QRadioButton("算术运算（仅对数值有效）")
        self._rb_replace = QRadioButton("文本替换")
        self._rb_arith.setChecked(True)
        mode_layout.addWidget(self._rb_arith)
        mode_layout.addWidget(self._rb_replace)
        layout.addWidget(self._grp_mode)
        form = QFormLayout()
        self._combo_op = QComboBox()
        self._combo_op.addItems(["+", "-", "*", "/"])
        form.addRow("运算符:", self._combo_op)
        self._ed_find = QLineEdit()
        self._ed_find.setPlaceholderText("查找文本")
        form.addRow("查找:", self._ed_find)
        self._ed_value = QLineEdit()
        self._ed_value.setPlaceholderText("数值或替换文本")
        form.addRow("值:", self._ed_value)
        layout.addLayout(form)
        self._rb_arith.toggled.connect(self._on_mode_changed)
        self._on_mode_changed(True)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def _on_mode_changed(self, is_arith):
        self._combo_op.setEnabled(is_arith)
        self._ed_find.setEnabled(not is_arith)
        self._ed_value.setEnabled(True)

    def _on_ok(self):
        if self._rb_arith.isChecked():
            self._result = ("arithmetic", self._combo_op.currentText(), self._ed_value.text())
        else:
            self._result = ("replace", self._ed_find.text(), self._ed_value.text())
        self.accept()

    def get_result(self):
        return self._result


class BatchRowHeightDialog(QDialog):
    """批量调整行高对话框"""
    def __init__(self, parent=None, start_row=1, end_row=10):
        super().__init__(parent)
        self.setWindowTitle("批量调整行高")
        self.setMinimumWidth(280)
        self._height = None
        layout = QFormLayout(self)
        info = QLabel(f"行范围: 第 {start_row} 行 ~ 第 {end_row} 行")
        layout.addRow(info)
        self._spin_height = QSpinBox()
        self._spin_height.setRange(10, 200)
        self._spin_height.setValue(24)
        self._spin_height.setSuffix(" 像素")
        layout.addRow("行高:", self._spin_height)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addRow(btn_layout)

    def _on_ok(self):
        self._height = self._spin_height.value()
        self.accept()

    def get_height(self):
        return self._height
