# -*- coding: utf-8 -*-
"""识别结果预览/校正表格（类 Excel 视图）。

把识别得到的“对齐行”用可编辑表格展示（类似 Excel/Word 里的表格），
供人工查看与校正：
- 单元格直接编辑；支持插入/删除行；
- 一键导出 Excel 文件（.xlsx）；
- 可选“保存校正到数据库”（replace_records 整体替换该文档记录）；
- “确认”返回校正后的行数据，由调用方回填到检测项目表格。
"""
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QFileDialog, QFrame,
)

# 项目内置 openpyxl（report_generator/libs），无需额外安装
_LIBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libs")
if _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)


class RecognitionTablePreview(QDialog):
    """识别结果可编辑表格预览对话框。"""

    def __init__(self, parent, columns, rows, doc_id=None, save_db=None,
                 title="识别结果查看与校正"):
        super().__init__(parent)
        self.columns = list(columns)
        self.doc_id = doc_id
        self.save_db = save_db          # callable(rows)->str，校正后存库
        self.setWindowTitle(title)
        self.resize(920, 560)
        self._init_ui(rows)
        self._rows_before = [list(r) for r in rows]

    def _init_ui(self, rows):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        tip = QLabel(
            "请核对识别结果：可直接点击单元格修改；改完可“导出Excel”留档，"
            "“保存校正到数据库”更新识别记录，“确认”后回填到检测项目表格。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555;")
        root.addWidget(tip)

        n_rows = max(len(rows), 1)
        self.table = QTableWidget(n_rows, len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        for i, row in enumerate(rows):
            for j in range(len(self.columns)):
                val = str(row[j]) if j < len(row) and row[j] is not None else ""
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, item)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        ops = QHBoxLayout()
        btn_ins = QPushButton("插入行")
        btn_ins.clicked.connect(self._insert_row)
        btn_del = QPushButton("删除选中行")
        btn_del.clicked.connect(self._delete_rows)
        btn_xls = QPushButton("导出Excel")
        btn_xls.clicked.connect(self._export_excel)
        self.btn_savedb = QPushButton("保存校正到数据库")
        if not (self.doc_id and self.save_db):
            self.btn_savedb.hide()
        self.btn_savedb.clicked.connect(self._save_to_db)
        ops.addWidget(btn_ins)
        ops.addWidget(btn_del)
        ops.addWidget(btn_xls)
        ops.addWidget(self.btn_savedb)
        ops.addStretch(1)

        btn_ok = QPushButton("确认")
        btn_ok.setMinimumHeight(30)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        ops.addWidget(btn_ok)
        ops.addWidget(btn_cancel)
        root.addLayout(ops)

        self.setStyleSheet("""
            QDialog { background:#f5f6f8; }
            QTableWidget { background:white; gridline-color:#C8C8C8;
                           font-size:12px; }
            QTableWidget::item:selected { background:#BBDEFB; color:black; }
            QHeaderView::section { background:#ECEFF1; padding:4px;
                                   border:1px solid #C8C8C8; font-weight:bold; }
            QPushButton { padding:4px 12px; }
        """)

    # ── 编辑操作 ──
    def _insert_row(self):
        sel = self.table.currentRow()
        at = sel + 1 if sel >= 0 else self.table.rowCount()
        self.table.insertRow(at)
        for j in range(len(self.columns)):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(at, j, item)
        self.table.setCurrentCell(at, 0)

    def _delete_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()},
                      reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的行。")
            return
        for r in rows:
            self.table.removeRow(r)

    # ── 数据 ──
    def get_rows(self):
        """返回校正后的行数据（与列头对齐）。"""
        out = []
        for i in range(self.table.rowCount()):
            out.append([(self.table.item(i, j).text()
                         if self.table.item(i, j) else "")
                        for j in range(len(self.columns))])
        return out

    # ── 导出/存库 ──
    def _export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出识别校正表", "识别校正表.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "识别校正表"
            ws.append(self.columns)
            for row in self.get_rows():
                ws.append(row)
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            wb.save(path)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "导出成功", f"已保存：{path}")

    def _save_to_db(self):
        if not (self.doc_id and self.save_db):
            return
        try:
            msg = self.save_db(self.get_rows())
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        QMessageBox.information(self, "保存成功",
                                msg or f"校正结果已更新（document_id={self.doc_id}）")
