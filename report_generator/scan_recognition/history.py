# -*- coding: utf-8 -*-
"""识别记录查看（默认保留位置）。

所有扫描识别过的检测项目文档都存放在识别数据库中，本对话框提供
固定入口随时查看：
- 按检测项目筛选、刷新；
- 查看某次识别的检测数据（类 Excel 表格），可再次校正、导出 Excel、
  保存校正回数据库；
- 删除误识别的记录。
"""
import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QListWidget, QListWidgetItem, QPlainTextEdit, QMessageBox,
    QSplitter, QFrame,
)

from report_generator.scan_recognition.config import Config
from report_generator.scan_recognition.storage import ScanDatabase
from report_generator.scan_recognition.preview import RecognitionTablePreview


class ScanHistoryDialog(QDialog):
    """识别记录查看对话框：列出所有识别过的检测项目文档。"""

    def __init__(self, parent=None, cfg: Config = None):
        super().__init__(parent)
        self.cfg = cfg or Config.load()
        self.db = ScanDatabase(db_path=self.cfg.database_path, cfg=self.cfg)
        self._docs = []
        self.setWindowTitle("识别记录查看")
        self.resize(860, 540)
        self._init_ui()
        self._reload_filters()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("检测项目："))
        self._filter_combo = QComboBox()
        self._filter_combo.setMinimumWidth(240)
        self._filter_combo.currentIndexChanged.connect(self._refresh)
        filter_row.addWidget(self._filter_combo, 1)
        btn_reload = QPushButton("刷新")
        btn_reload.clicked.connect(self._reload_filters)
        filter_row.addWidget(btn_reload)
        root.addLayout(filter_row)

        split = QSplitter(Qt.Horizontal)
        self._doc_list = QListWidget()
        self._doc_list.currentRowChanged.connect(self._on_doc_selected)
        split.addWidget(self._doc_list)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setPlaceholderText("选择左侧识别记录查看详情。")
        split.addWidget(self._detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        ops = QHBoxLayout()
        btn_view = QPushButton("查看校正表格")
        btn_view.setToolTip("以类 Excel 表格查看该次识别数据，可校正、导出Excel、保存回数据库")
        btn_view.clicked.connect(self._view_doc)
        btn_del = QPushButton("删除该记录")
        btn_del.clicked.connect(self._delete_doc)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        for b in (btn_view, btn_del):
            b.setMinimumHeight(30)
            ops.addWidget(b)
        ops.addStretch(1)
        ops.addWidget(btn_close)
        root.addLayout(ops)

        self.setStyleSheet("""
            QDialog { background:#f5f6f8; }
            QListWidget, QPlainTextEdit { background:white; font-size:12px; }
            QPushButton { padding:4px 12px; }
        """)

    # ── 数据 ──
    def _reload_filters(self):
        """重建检测项目筛选项（不含空项目的识别文档）。"""
        current = self._filter_combo.currentText() if self._filter_combo.count() else None
        docs = self.db.list_documents()
        items = sorted({d.get("detection_item") or "（未分类）" for d in docs})
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem("全部检测项目")
        self._filter_combo.addItems(items)
        if current:
            idx = self._filter_combo.findText(current)
            if idx >= 0:
                self._filter_combo.setCurrentIndex(idx)
        self._filter_combo.blockSignals(False)
        self._refresh()

    def _refresh(self):
        filt = self._filter_combo.currentText()
        detection_item = None if (not filt or filt == "全部检测项目") else filt
        self._docs = self.db.list_documents(detection_item)
        self._doc_list.clear()
        for d in self._docs:
            title = f"#{d['id']}  {d.get('detection_item') or '（未分类）'}"
            line2 = (f"　{str(d.get('created_at') or '')}  "
                     f"{os.path.basename(str(d.get('source_path') or ''))}")
            item = QListWidgetItem(title + "\n" + line2)
            self._doc_list.addItem(item)
        self._detail.setPlainText(
            f"共 {len(self._docs)} 条识别记录。"
            if self._docs else "暂无识别记录。请先在“原始记录识别”中完成识别。")

    def _current_doc(self):
        row = self._doc_list.currentRow()
        if 0 <= row < len(self._docs):
            return self._docs[row]
        return None

    def _doc_rows(self, doc_id):
        """从记录重建对齐行（校正后的行以 matched_columns 保存）。"""
        records = self.db.list_records(document_id=doc_id)
        if not records:
            return [], []
        try:
            rows = json.loads(records[-1].get("matched_columns") or "[]")
        except Exception:
            rows = []
        return rows, records

    # ── 动作 ──
    def _on_doc_selected(self, row):
        doc = self._current_doc()
        if not doc:
            return
        rows, _ = self._doc_rows(doc["id"])
        lines = [
            f"记录编号：#{doc['id']}",
            f"检测项目：{doc.get('detection_item') or '（未分类）'}"
            f" / {doc.get('sub_item') or ''}",
            f"识别时间：{doc.get('created_at') or ''}",
            f"来源文件：{doc.get('source_path') or ''}",
            f"数据行数：{len(rows)}",
            "-" * 40,
            "OCR 文本（前600字）：",
            (doc.get("ocr_text") or "")[:600],
        ]
        self._detail.setPlainText("\n".join(lines))

    def _view_doc(self):
        doc = self._current_doc()
        if not doc:
            QMessageBox.information(self, "提示", "请先选择一条识别记录。")
            return
        rows, records = self._doc_rows(doc["id"])
        if not rows:
            QMessageBox.information(self, "提示", "该记录没有可查看的数据行。")
            return
        # 列头优先取该检测项目注册的真实列，其次按行数推断
        sub = doc.get("sub_item") or doc.get("detection_item")
        from report_generator.scan_recognition.matcher import available_sub_items
        columns = available_sub_items().get(sub) or self._guess_columns(rows)
        det = doc.get("detection_item") or doc.get("sub_item") or ""

        def _save_db(corrected):
            self.db.replace_records(
                doc["id"], doc.get("detection_item"),
                doc.get("sub_item"),
                self._structured_of(records), [], corrected)
            return f"校正结果已更新（document_id={doc['id']}，{len(corrected)} 行）"

        dlg = RecognitionTablePreview(
            self, columns, [list(r) for r in rows],
            doc_id=doc["id"], save_db=_save_db,
            title=f"识别记录 #{doc['id']} - {det}")
        dlg.exec_()

    @staticmethod
    def _structured_of(records):
        out = []
        for r in records:
            try:
                out.append(json.loads(r.get("structured_json") or "null"))
            except Exception:
                out.append(None)
        return out

    @staticmethod
    def _guess_columns(rows):
        n = max((len(r) for r in rows), default=0)
        return [f"列{i+1}" for i in range(n)]

    def _delete_doc(self):
        doc = self._current_doc()
        if not doc:
            QMessageBox.information(self, "提示", "请先选择一条识别记录。")
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除识别记录")
        box.setText(f"确定删除记录 #{doc['id']}（{doc.get('detection_item')}）"
                    f"及其全部数据行吗？")
        yes = box.addButton("删除", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is not yes:
            return
        self.db.delete_document(doc["id"])
        self._reload_filters()

    def closeEvent(self, event):
        try:
            self.db.close()
        except Exception:
            pass
        super().closeEvent(event)
