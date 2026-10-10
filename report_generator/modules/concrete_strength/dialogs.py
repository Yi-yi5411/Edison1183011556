# -*- coding: utf-8 -*-
"""混凝土抗压强度检测（钻芯法）专属对话框。

从 framework/ui/dialogs.py 迁移至此——这些对话框仅服务钻芯法检测，
属于 concrete_strength 插件自有资产，不应驻留在框架层。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFrame, QDialogButtonBox, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)

from framework.engine.core_drilling import COEFF_TABLE, lookup_coeff, batch_assess, parse_design_value
from framework.ui.delegates import FloorLabelDelegate


# ═══════════════════════════════════════════════════════════════
#  钻芯法检测参数输入对话框
# ═══════════════════════════════════════════════════════════════
class CoreDrillingInputDialog(QDialog):
    """钻芯法检测初始参数输入对话框。

        收集楼栋名称、检测方法、检测批次、构件数量、芯样数量/构件、
        芯样编号起始、设计强度等级、芯样直径等参数，用于自动生成表格结构。
    """

    def __init__(self, parent=None, sheet_key=""):
        super().__init__(parent)
        self.setWindowTitle(f"钻芯法检测参数设置 - {sheet_key}")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 10)

        self.ed_building = QLineEdit("1#")
        self.ed_building.setPlaceholderText("如: 1#楼")
        layout.addRow("楼栋名称:", self.ed_building)

        self.cmb_method = QComboBox()
        self.cmb_method.addItem("批推定（批评定）", "batch")
        self.cmb_method.addItem("单构件检测", "single")
        self.cmb_method.currentIndexChanged.connect(self._on_method_changed)
        layout.addRow("检测方法:", self.cmb_method)

        self.sp_batches = QSpinBox()
        self.sp_batches.setRange(1, 100)
        self.sp_batches.setValue(1)
        self.sp_batches.setSuffix(" 批")
        layout.addRow("检测批次:", self.sp_batches)

        self.sp_components = QSpinBox()
        self.sp_components.setRange(1, 500)
        self.sp_components.setValue(13)
        self.sp_components.setSuffix(" 个")
        layout.addRow("构件数量:", self.sp_components)

        self.sp_samples = QSpinBox()
        self.sp_samples.setRange(1, 10)
        self.sp_samples.setValue(2)
        self.sp_samples.setSuffix(" 个/构件")
        layout.addRow("芯样数量/构件:", self.sp_samples)

        self.sp_sample_start = QSpinBox()
        self.sp_sample_start.setRange(1, 9999)
        self.sp_sample_start.setValue(1)
        layout.addRow("芯样编号起始:", self.sp_sample_start)

        self.cmb_grade = QComboBox()
        self.cmb_grade.addItems(["C25", "C30", "C35", "C40", "C45", "C50", "C55", "C60"])
        self.cmb_grade.setCurrentText("C40")
        layout.addRow("设计强度等级:", self.cmb_grade)

        self.sp_diameter = QDoubleSpinBox()
        self.sp_diameter.setRange(20.0, 150.0)
        self.sp_diameter.setValue(75.0)
        self.sp_diameter.setSuffix(" mm")
        self.sp_diameter.setDecimals(1)
        layout.addRow("芯样直径:", self.sp_diameter)

        # 按钮
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btn_box.button(QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _on_method_changed(self, _index):
        """检测方法为单构件时，检测批次不参与计算，予以禁用。"""
        self.sp_batches.setEnabled(self.cmb_method.currentData() != "single")

    def get_params(self):
        """返回对话框参数字典"""
        return {
            "building": self.ed_building.text().strip(),
            "method": self.cmb_method.currentData(),
            "batches": self.sp_batches.value(),
            "components": self.sp_components.value(),
            "samples_per_component": self.sp_samples.value(),
            "sample_start": self.sp_sample_start.value(),
            "grade": self.cmb_grade.currentText(),
            "diameter": self.sp_diameter.value(),
        }


class CoreDrillingComponentInputDialog(QDialog):
    """钻芯法构件信息批量录入对话框。

    将每个构件的“构件位置及名称 / 轴线编号”集中到一个表格中录入，
    名称列仍提供与表格内一致的楼层标签下拉候选（可自由输入），
    避免在合并单元格中逐个寻找锚点行。
    """

    def __init__(self, components, floor_labels=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量录入构件信息 - 钻芯法")
        self.setMinimumSize(560, 440)
        self._components = list(components or [])
        self._setup_ui(floor_labels)

    def _setup_ui(self, floor_labels):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(8)

        tip = QLabel("批量填写各构件的构件位置及名称与轴线编号，确定后写回钻芯法工作表。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.table = QTableWidget(len(self._components), 3)
        self.table.setHorizontalHeaderLabels(["构件编号", "构件位置及名称", "轴线编号"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        for row, comp in enumerate(self._components):
            no_item = QTableWidgetItem(str(comp.get("no", "")))
            no_item.setFlags(no_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, no_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(comp.get("name", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(str(comp.get("axis", ""))))

        if floor_labels:
            delegate = FloorLabelDelegate(self.table)
            delegate.set_items(floor_labels)
            self.table.setItemDelegateForColumn(1, delegate)
        layout.addWidget(self.table)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_components(self):
        """返回录入结果：[{"no", "name", "axis"}, ...]"""
        result = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            axis_item = self.table.item(row, 2)
            result.append({
                "no": self.table.item(row, 0).text() if self.table.item(row, 0) else "",
                "name": name_item.text().strip() if name_item else "",
                "axis": axis_item.text().strip() if axis_item else "",
            })
        return result


class BatchAssessmentResultDialog(QDialog):
    """钻芯法批量推定计算结果展示对话框（只读）。

    展示 batch_assess() 返回的全部中间值与最终结论，
    支持一键复制结论措辞。
    """

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self._result = result
        mode_label = "批量检测" if result.get("mode") == "batch" else "单构件检测"
        self.setWindowTitle(f"批推定计算结果 - {mode_label}")
        self.setMinimumWidth(520)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(8)

        r = self._result

        # ── 错误提示 ──
        if r.get("error"):
            err_lbl = QLabel(f"错误：{r['error']}")
            err_lbl.setStyleSheet("color: #c0392b; font-weight: bold; font-size: 12pt;")
            err_lbl.setWordWrap(True)
            layout.addWidget(err_lbl)
            self._add_close_btn(layout)
            return

        # ── 基本参数 ──
        mode_lbl = "批量检测 (batch)" if r["mode"] == "batch" else "单构件检测 (single)"
        info_lines = [
            f"检测模式：{mode_lbl}",
            f"有效样本数 n：{r['n']}",
        ]
        if r.get("m_fcu") is not None:
            info_lines.append(f"算术平均值 m_fcu：{r['m_fcu']:.2f} MPa")
        if r.get("S_fcu") is not None:
            info_lines.append(f"样本标准差 S_fcu：{r['S_fcu']:.2f} MPa")
        if r.get("k1") is not None:
            info_lines.append(f"推定系数 K1：{r['k1']:.5f}")
        if r.get("k2") is not None:
            info_lines.append(f"推定系数 K2：{r['k2']:.5f}")
        if r.get("confidence") is not None:
            info_lines.append(f"置信度：{r['confidence']:.2f}")

        info_lbl = QLabel("\n".join(info_lines))
        info_lbl.setStyleSheet("font-size: 10pt; line-height: 160%;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        # ── 推定区间（仅 batch）──
        if r["mode"] == "batch" and r.get("f_cu_e1") is not None:
            layout.addWidget(self._sep())
            interval_lines = [
                f"推定上限值 f_cu,e1：{r['f_cu_e1']:.1f} MPa",
                f"推定下限值 f_cu,e2：{r['f_cu_e2']:.1f} MPa",
                f"区间差值 Δ：{r['delta']:.1f} MPa",
                f"允许最大差值 Δmax：{r['delta_max']:.1f} MPa",
            ]
            interval_lbl = QLabel("\n".join(interval_lines))
            interval_lbl.setStyleSheet("font-size: 10pt; line-height: 160%;")
            interval_lbl.setWordWrap(True)
            layout.addWidget(interval_lbl)

            # 有效性标识
            if r["valid"]:
                valid_lbl = QLabel("推定区间有效，结果可信。")
                valid_lbl.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 11pt;")
            else:
                valid_lbl = QLabel("警告：推定区间过宽！")
                valid_lbl.setStyleSheet("color: #c0392b; font-weight: bold; font-size: 11pt;")
            layout.addWidget(valid_lbl)

        # ── 芯样数量不足警告（批量检测数量不足时仍计算，仅提示）──
        if r.get("insufficient"):
            ins_lbl = QLabel(f"警告：{r.get('insufficient_msg', '芯样数量少于规范最小样本量。')}")
            ins_lbl.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 10pt;")
            ins_lbl.setWordWrap(True)
            layout.addWidget(ins_lbl)

        # ── 最终推定值 ──
        layout.addWidget(self._sep())
        if r.get("f_cu_e") is not None:
            if r["mode"] == "batch" and not r.get("valid", True):
                val_lbl = QLabel(f"最终强度推定值 f_cu,e：{r['f_cu_e']:.1f} MPa （推定区间过宽，仅供参考）")
                val_lbl.setStyleSheet("color: #c0392b; font-weight: bold; font-size: 12pt;")
            elif r.get("insufficient"):
                val_lbl = QLabel(f"最终强度推定值 f_cu,e：{r['f_cu_e']:.1f} MPa （芯样数量不足，仅供参考）")
                val_lbl.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 12pt;")
            else:
                val_lbl = QLabel(f"最终强度推定值 f_cu,e：{r['f_cu_e']:.1f} MPa")
                val_lbl.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 12pt;")
            layout.addWidget(val_lbl)

        # ── 警告（single 模式的离散性/补钻警告）──
        if r.get("warning") and r["mode"] == "single":
            warn_lbl = QLabel(f"备注：{r['warning']}")
            warn_lbl.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 10pt;")
            warn_lbl.setWordWrap(True)
            layout.addWidget(warn_lbl)

        # ── 结论措辞 ──
        layout.addWidget(self._sep())
        concl_title = QLabel("结论：")
        concl_title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(concl_title)
        self._conclusion_edit = QTextEdit(r.get("conclusion", ""))
        self._conclusion_edit.setReadOnly(True)
        self._conclusion_edit.setMaximumHeight(60)
        self._conclusion_edit.setStyleSheet("font-size: 10pt;")
        layout.addWidget(self._conclusion_edit)

        # ── 按钮 ──
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("复制结论")
        copy_btn.clicked.connect(self._copy_conclusion)
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _add_close_btn(self, layout):
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _copy_conclusion(self):
        cb = QApplication.clipboard()
        cb.setText(self._result.get("conclusion", ""))
        self._conclusion_edit.setFocus()


# ═════════════════════════════════════════════════════════════
#  回弹钻芯修正法检测初始参数输入对话框
# ═════════════════════════════════════════════════════════════
class ReboundCoreDrillingInputDialog(QDialog):
    """回弹钻芯修正法检测初始参数输入对话框。

    收集楼栋、批次数量、每批构件编号数量、每构件钻芯测区数量、
    芯样直径和设计强度等级，用于自动生成回弹钻芯修正法表格结构。
    """

    def __init__(self, parent=None, sheet_key=""):
        super().__init__(parent)
        self.setWindowTitle(f"回弹钻芯修正法检测参数设置 - {sheet_key}")
        self.setMinimumWidth(440)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 10)

        self.ed_building = QLineEdit("1#")
        self.ed_building.setPlaceholderText("如: 1#楼")
        layout.addRow("楼栋名称:", self.ed_building)

        self.sp_batches = QSpinBox()
        self.sp_batches.setRange(1, 100)
        self.sp_batches.setValue(1)
        self.sp_batches.setSuffix(" 批")
        layout.addRow("批次数量:", self.sp_batches)

        self.sp_components = QSpinBox()
        self.sp_components.setRange(1, 500)
        self.sp_components.setValue(5)
        self.sp_components.setSuffix(" 个/批")
        layout.addRow("构件编号数量:", self.sp_components)

        self.sp_zones = QSpinBox()
        self.sp_zones.setRange(1, 20)
        self.sp_zones.setValue(3)
        self.sp_zones.setSuffix(" 个/构件")
        layout.addRow("钻芯测区数量:", self.sp_zones)

        self.cmb_grade = QComboBox()
        self.cmb_grade.addItems(["C25", "C30", "C35", "C40", "C45", "C50", "C55", "C60"])
        self.cmb_grade.setCurrentText("C40")
        layout.addRow("设计强度等级:", self.cmb_grade)

        self.sp_diameter = QDoubleSpinBox()
        self.sp_diameter.setRange(20.0, 150.0)
        self.sp_diameter.setValue(100.0)
        self.sp_diameter.setSuffix(" mm")
        self.sp_diameter.setDecimals(1)
        layout.addRow("芯样直径:", self.sp_diameter)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btn_box.button(QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_params(self):
        """返回对话框参数字典"""
        return {
            "building": self.ed_building.text().strip(),
            "batches": self.sp_batches.value(),
            "components_per_batch": self.sp_components.value(),
            "zones_per_component": self.sp_zones.value(),
            "grade": self.cmb_grade.currentText(),
            "diameter": self.sp_diameter.value(),
        }
