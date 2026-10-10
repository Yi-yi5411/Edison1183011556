# -*- coding: utf-8 -*-
"""批量审查对话框。

流程：选择检测报告/记录文件（docx/pdf/txt）→ 后台分块提取审查候选
（本地 Ollama，进度实时刷新）→ 候选表格人工确认（勾选/编辑/删除）
→ 导出审查意见 Word 表（只导出勾选行）。
"""

from __future__ import annotations

import traceback

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

try:
    from utils.norm_qa.batch_review import (CATEGORIES, export_review_docx,
                                            run_batch_review)
    from utils.norm_qa.store import db_status
except ImportError:  # 兼容以 report_generator 为根的导入环境
    from report_generator.utils.norm_qa.batch_review import (
        CATEGORIES, export_review_docx, run_batch_review)
    from report_generator.utils.norm_qa.store import db_status


class _ReviewWorker(QThread):
    """批量审查后台线程（分块 LLM 提取，分钟级，防界面冻结）。"""

    progress = pyqtSignal(int, int)      # 已完成块数, 总块数
    log_line = pyqtSignal(str)
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, files, model="", parent=None):
        super().__init__(parent)
        self._files = files
        self._model = model

    def run(self):
        try:
            result = run_batch_review(
                self._files, model=self._model,
                on_log=self.log_line.emit,
                on_progress=lambda done, total: self.progress.emit(done, total))
            self.succeeded.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc(limit=4))


class BatchReviewDialog(QDialog):
    """检测报告批量审查主对话框。"""

    COLS = ["确认", "位置", "原文片段", "问题类型", "问题描述", "审查建议", "规范依据"]

    def __init__(self, parent=None, project_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("批量审查（检测报告审查意见辅助）")
        self.resize(1000, 640)
        self._files = []
        self._worker = None
        self._project_name = project_name
        self._setup_ui()
        self._refresh_status()

    # ── 界面 ──
    def _setup_ui(self):
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        self._btn_pick = QPushButton("选择报告文件...")
        self._btn_pick.clicked.connect(self._on_pick)
        self._btn_review = QPushButton("开始审查")
        self._btn_review.clicked.connect(self._on_review)
        self._files_label = QLabel("未选择文件（docx/pdf/txt，可多选）")
        self._files_label.setStyleSheet("color: gray;")
        row.addWidget(self._btn_pick)
        row.addWidget(self._files_label, 1)
        row.addWidget(self._btn_review)
        root.addLayout(row)

        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        root.addWidget(self._status)

        self._table = QTableWidget(0, len(self.COLS))
        self._table.setHorizontalHeaderLabels(self.COLS)
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 44)
        self._table.setColumnWidth(1, 150)
        self._table.setColumnWidth(2, 200)
        self._table.setColumnWidth(3, 90)
        self._table.setColumnWidth(6, 220)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._btn_all = QPushButton("全选")
        self._btn_all.clicked.connect(lambda: self._set_all_selected(True))
        self._btn_none = QPushButton("全不选")
        self._btn_none.clicked.connect(lambda: self._set_all_selected(False))
        self._btn_del = QPushButton("删除选中行")
        self._btn_del.clicked.connect(self._on_delete_rows)
        self._btn_export = QPushButton("导出审查意见 Word...")
        self._btn_export.clicked.connect(self._on_export)
        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_all)
        btn_row.addWidget(self._btn_none)
        btn_row.addWidget(self._btn_del)
        btn_row.addStretch(1)
        btn_row.addWidget(self._btn_export)
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

    def _refresh_status(self):
        """启动提示：规范库状态决定规范依据匹配效果。"""
        try:
            info = db_status()
            total = info.get("total") or 0
        except Exception:
            total = 0
        if total:
            self._status.setText(
                "规范库共 %d 条条文，审查候选将自动匹配规范依据。" % total)
        else:
            self._status.setText(
                "提示：规范库为空，将无法自动匹配规范依据（可先在「规范问答」中导入规范）。")

    # ── 文件选择 / 审查 ──
    def _on_pick(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择检测报告/记录文件", "",
            "报告文件 (*.docx *.pdf *.txt)")
        if not paths:
            return
        self._files = paths
        names = "、".join(p.split("\\")[-1].split("/")[-1] for p in paths[:3])
        more = "" if len(paths) <= 3 else " 等%d个" % len(paths)
        self._files_label.setText(names + more)

    def _on_review(self):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "正在审查", "批量审查进行中，请稍候。")
            return
        if not self._files:
            QMessageBox.information(self, "提示", "请先选择要审查的报告文件。")
            return
        try:
            db_status()  # 规范库可读性预检（不可达时异常提示）
        except Exception:
            pass
        self._table.setRowCount(0)
        self._btn_review.setEnabled(False)
        self._btn_pick.setEnabled(False)
        self._status.setText("审查中……")
        self._worker = _ReviewWorker(self._files)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._append_status)
        self._worker.succeeded.connect(self._on_review_done)
        self._worker.failed.connect(self._on_review_failed)
        self._worker.start()

    def _on_progress(self, done, total):
        self._status.setText("审查中……片段 %d/%d（结果将逐块累加）" % (done, total))

    def _append_status(self, msg):
        self._status.setText(msg)

    def _on_review_done(self, result):
        self._btn_review.setEnabled(True)
        self._btn_pick.setEnabled(True)
        candidates = result.get("candidates") or []
        self._fill_table(candidates)
        self._status.setText(
            "审查完成：%d 个片段，%d 条候选意见（可在表格中勾选、编辑、删除）。"
            % (result.get("chunks") or 0, len(candidates)))

    def _on_review_failed(self, err):
        self._btn_review.setEnabled(True)
        self._btn_pick.setEnabled(True)
        self._status.setText("审查失败。")
        QMessageBox.critical(self, "审查失败", err)

    # ── 表格 ──
    def _fill_table(self, candidates):
        self._table.setRowCount(0)
        for c in candidates:
            self._append_row(c)

    def _append_row(self, cand):
        row = self._table.rowCount()
        self._table.insertRow(row)
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if cand.get("selected", True)
                          else Qt.Unchecked)
        self._table.setItem(row, 0, chk)
        for col, key in enumerate(
                ("location", "excerpt", "category", "description",
                 "suggestion", "basis"), start=1):
            item = QTableWidgetItem(str(cand.get(key) or ""))
            if col == 4:
                item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._table.setItem(row, col, item)

    def _set_all_selected(self, state: bool):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked if state else Qt.Unchecked)

    def _on_delete_rows(self):
        rows = sorted({i.row() for i in self._table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self._table.removeRow(r)

    def _collect_selected(self):
        out = []
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, 0)
            if not chk or chk.checkState() != Qt.Checked:
                continue
            out.append({
                "location": self._table.item(row, 1).text() if
                self._table.item(row, 1) else "",
                "excerpt": self._table.item(row, 2).text() if
                self._table.item(row, 2) else "",
                "category": self._table.item(row, 3).text() if
                self._table.item(row, 3) else "",
                "description": self._table.item(row, 4).text() if
                self._table.item(row, 4) else "",
                "suggestion": self._table.item(row, 5).text() if
                self._table.item(row, 5) else "",
                "basis": self._table.item(row, 6).text() if
                self._table.item(row, 6) else "",
            })
        return out

    # ── 导出 ──
    def _on_export(self):
        selected = self._collect_selected()
        if not selected:
            QMessageBox.information(self, "提示", "没有勾选任何审查意见。")
            return
        default = "审查意见表_%s.docx" % (self._project_name or "检测结果")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出审查意见", default, "Word 文档 (*.docx)")
        if not path:
            return
        try:
            out = export_review_docx(selected, path,
                                     project_name=self._project_name)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(
            self, "导出成功", "已导出 %d 条审查意见：\n%s" % (len(selected), out))

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        super().closeEvent(event)
