# -*- coding: utf-8 -*-
"""规范条文问答对话框。

界面流程：输入条号或自然语言问题 → 检索（条号精确 / FTS+LIKE）→
结果按规范来源分组展示 → 可选本地 Ollama 生成中文解释（后台线程）。
"""

from __future__ import annotations

import traceback

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

try:
    from utils.norm_qa import (NormQueryEngine, db_status, explain_clauses,
                               import_files)
except ImportError:  # 兼容以 report_generator 为根的导入环境
    from report_generator.utils.norm_qa import (NormQueryEngine, db_status,
                                                explain_clauses, import_files)


class _ExplainWorker(QThread):
    """AI 解释后台线程（Ollama 生成需数秒~数十秒，防界面冻结）。"""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, question, clauses, parent=None):
        super().__init__(parent)
        self._question = question
        self._clauses = clauses

    def run(self):
        try:
            text = explain_clauses(self._question, self._clauses)
            if text:
                self.finished_ok.emit(text)
            else:
                self.failed.emit(
                    "Ollama 服务不可用或未返回内容，请确认本地 Ollama 已启动。")
        except Exception:
            self.failed.emit(traceback.format_exc(limit=3))


class NormQADialog(QDialog):
    """规范条文问答主对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("规范条文问答")
        self.resize(860, 620)
        self._engine = NormQueryEngine()
        self._result_clauses = []   # 最近一次查询命中（供 AI 解释引用）
        self._worker = None
        self._setup_ui()
        self._refresh_status()

    # ── 界面 ──
    def _setup_ui(self):
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(
            "输入条号（如 5.1.2）或自然语言问题（如 回弹值如何修正）")
        self._edit.returnPressed.connect(self._on_query)
        self._btn_query = QPushButton("查询")
        self._btn_query.clicked.connect(self._on_query)
        row.addWidget(self._edit, 1)
        row.addWidget(self._btn_query)
        root.addLayout(row)

        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        root.addWidget(self._status)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["条号 / 标题", "规范", "正文预览"])
        self._tree.setColumnWidth(0, 240)
        self._tree.setColumnWidth(1, 190)
        self._tree.setAlternatingRowColors(True)
        root.addWidget(self._tree, 1)

        self._cand_row = QHBoxLayout()
        self._cand_label = QLabel("")
        self._cand_label.setStyleSheet("color: #888;")
        self._cand_row.addWidget(self._cand_label)
        root.addLayout(self._cand_row)

        ai_row = QHBoxLayout()
        self._btn_explain = QPushButton("AI 解释（本地 Ollama）")
        self._btn_explain.clicked.connect(self._on_explain)
        self._btn_import = QPushButton("导入规范文件...")
        self._btn_import.clicked.connect(self._on_import)
        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.accept)
        ai_row.addWidget(self._btn_explain)
        ai_row.addWidget(self._btn_import)
        ai_row.addStretch(1)
        ai_row.addWidget(self._btn_close)
        root.addLayout(ai_row)

        self._answer = QPlainTextEdit()
        self._answer.setReadOnly(True)
        self._answer.setPlaceholderText("AI 解释结果显示在此处（依据命中的条文原文）")
        self._answer.setMaximumHeight(150)
        root.addWidget(self._answer)

    # ── 查询 ──
    def _on_query(self):
        question = self._edit.text().strip()
        self._answer.clear()
        self._clear_candidates()
        if not question:
            return
        try:
            result = self._engine.query(question)
        except Exception as e:
            QMessageBox.critical(self, "查询失败",
                                 "规范库读取失败：%s\n\n若尚未导入规范，"
                                 "请先点击「导入规范文件...」。" % e)
            return
        self._result_clauses = result.get("clauses") or []
        self._tree.clear()
        qtype = result.get("type")

        if qtype == "empty":
            self._status.setText("请输入条号或问题。")
            return
        if qtype == "candidates":
            self._status.setText(
                "未直接命中条文，以下是与问题相关的片段，点击可重查：")
            self._show_candidates(result.get("candidates") or [])
            return

        groups = {}
        for c in self._result_clauses:
            key = (c.get("code") or "", c.get("code_name") or "")
            groups.setdefault(key, []).append(c)
        for (code, code_name), items in groups.items():
            top = QTreeWidgetItem(["%s %s" % (code, code_name), "",
                                   "共 %d 条" % len(items)])
            top.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(top)
            for c in items:
                preview = (c.get("body") or "").replace("\n", " ")[:80]
                child = QTreeWidgetItem([
                    "%s %s" % (c.get("chapter"), c.get("title") or ""),
                    "%s %s" % (code, c.get("chapter_path") or ""),
                    preview])
                child.setData(0, Qt.UserRole, c)
                top.addChild(child)
            top.setExpanded(True)

        mode = "条号精确命中" if qtype == "exact" else "全文检索"
        self._status.setText(
            "%s：%d 条（来自 %d 部规范）" % (
                mode, len(self._result_clauses), len(groups)))

    def _show_candidates(self, candidates):
        for i in reversed(range(self._cand_row.count())):
            w = self._cand_row.takeAt(i).widget()
            if w:
                w.deleteLater()
        self._cand_label.setText("相关片段：")
        for cand in candidates[:6]:
            btn = QPushButton(cand.get("label") or cand.get("term"))
            btn.setStyleSheet("QPushButton{padding:2px 8px;}")
            term = cand.get("term") or ""

            def _requery(t=term):
                self._edit.setText(t)
                self._on_query()

            btn.clicked.connect(_requery)
            self._cand_row.addWidget(btn)
        if not candidates:
            self._cand_label.setText("未找到相关条文，可尝试换个说法或先导入规范。")

    def _clear_candidates(self):
        self._cand_label.setText("")

    # ── AI 解释 ──
    def _on_explain(self):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "请稍候", "AI 解释生成中。")
            return
        clauses = self._selected_clauses() or self._result_clauses
        if not clauses:
            QMessageBox.information(self, "提示", "请先查询出条文再请求 AI 解释。")
            return
        question = self._edit.text().strip() or "解释以上条文要点"
        self._answer.setPlainText("AI 解释生成中，请稍候……")
        self._btn_explain.setEnabled(False)
        self._worker = _ExplainWorker(question, clauses)
        self._worker.finished_ok.connect(self._on_explain_done)
        self._worker.failed.connect(self._on_explain_failed)
        self._worker.start()

    def _selected_clauses(self):
        item = self._tree.currentItem()
        data = item.data(0, Qt.UserRole) if item else None
        return [data] if isinstance(data, dict) else []

    def _on_explain_done(self, text):
        self._btn_explain.setEnabled(True)
        self._answer.setPlainText(text)

    def _on_explain_failed(self, err):
        self._btn_explain.setEnabled(True)
        self._answer.setPlainText("")

    # ── 导入 ──
    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择规范文件（md/txt/docx）", "",
            "规范文件 (*.md *.markdown *.txt *.docx)")
        if not paths:
            return
        try:
            result = import_files(paths, mode="append",
                                  on_log=lambda m: None)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return
        errors = [f["error"] for f in result["files"] if f["error"]]
        msg = "导入完成：本次解析 %d 条，库内共 %d 条条文。" % (
            result["imported"], result["total"])
        if errors:
            msg += "\n\n部分文件失败：\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "导入结果", msg)
        self._refresh_status()

    def _refresh_status(self):
        try:
            info = db_status()
        except Exception:
            info = {"total": 0, "exists": False}
        if info.get("total"):
            codes = "、".join(
                "%s(%d)" % (c["code"], c["count"])
                for c in (info.get("codes") or [])[:4])
            more = "" if len(info.get("codes") or []) <= 4 else " 等"
            self._status.setText("规范库：共 %d 条条文（%s%s）" % (
                info["total"], codes, more))
        else:
            self._status.setText(
                "规范库为空，请先点击「导入规范文件...」导入 md/txt/docx 规范。")

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        super().closeEvent(event)
