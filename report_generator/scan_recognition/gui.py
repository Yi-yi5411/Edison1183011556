# -*- coding: utf-8 -*-
"""第1~8步 集成的界面：文档扫描识别对话框。

- 选择图片/扫描PDF文件，AI 判定原始记录类型后自动定位并跳转对应检测项目工作表回填（第7步）。
- 支持“仅识别存库 / 识别并回填检测项目 / 上传服务器”。
- 大模型结构化与OCR在后台线程执行，避免阻塞界面。
"""
import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFileDialog, QPlainTextEdit,
    QPushButton, QLabel, QMessageBox, QFrame, QComboBox,
)

from report_generator.scan_recognition.config import Config
from report_generator.scan_recognition.pipeline import ScanRecognitionPipeline
from report_generator.scan_recognition.uploader import ServerUploader
from report_generator.scan_recognition.test_tool import (
    AUTO_MODEL_LABEL,
    VisionModelListWorker,
)


class _RecWorker(QThread):
    """后台执行识别流水线的线程。"""
    step_changed = pyqtSignal(int, str)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, pipeline, source_path, detection_item, sub_item, columns,
                 use_ocr, structured_override=None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.source_path = source_path
        self.detection_item = detection_item
        self.sub_item = sub_item
        self.columns = columns
        self.use_ocr = use_ocr
        self.structured_override = structured_override

    def run(self):
        try:
            if not self.use_ocr:
                self.structured_override = self.structured_override or []
                self.finished_ok.emit(self._fake_result())
                return
            result = self.pipeline.recognize(
                self.source_path, self.detection_item, self.sub_item,
                self.columns, progress=self._emit_step,
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))

    def _emit_step(self, step, label):
        self.step_changed.emit(step, label)

    def _fake_result(self):
        return {
            "doc_id": None, "source_path": self.source_path,
            "stored_path": self.source_path, "detection_item": self.detection_item,
            "sub_item": self.sub_item, "columns": list(self.columns),
            "structured": self.structured_override, "normalized": self.structured_override,
            "rows": [], "matched_rows": [],
        }


class ScanRecognitionDialog(QDialog):
    """文档扫描识别对话框（集成第1~8步）。"""

    def __init__(self, app, cfg: Config = None, parent=None):
        super().__init__(parent or app.win)
        self.app = app
        self.cfg = cfg or Config.load()
        self.pipeline = ScanRecognitionPipeline(cfg=self.cfg)
        self.selected_files = []
        self._last_result = None
        self._worker = None
        self._fill_on_done = False
        self.setWindowTitle("文档扫描识别")
        self.resize(620, 460)
        self._init_ui()
        self._append_log(
            "文档扫描识别流水线就绪。请选择图片/扫描PDF文件后执行识别，"
            "AI 会自动判定原始记录类型，并跳转进入对应检测项目工作表回填。\n"
            "提示：可在左下配置文件 report_generator/assets/scan_recognition_config.json"
            " 中配置 通义千问Key、服务器地址。\n"
        )

    # ── UI ──
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        info = QLabel(
            "回填方式：识别后按原始记录类型自动定位并跳转对应检测项目工作表"
        )
        info.setObjectName("targetInfo")
        root.addWidget(info)
        self._target_label = info

        # 文件选择区
        file_row = QHBoxLayout()
        file_label = QLabel("文件：")
        self._file_lbl = QLabel("未选择")
        self._file_lbl.setStyleSheet("color:#666;")
        btn_pick = QPushButton("选择图片/PDF...")
        btn_pick.clicked.connect(self._pick_files)
        file_row.addWidget(file_label)
        file_row.addWidget(self._file_lbl, 1)
        file_row.addWidget(btn_pick)
        root.addLayout(file_row)

        # 识别模型：Ollama 视觉模型下拉框，切换后重跑即可对比识别效果
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("识别模型："))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(220)
        self._model_combo.setToolTip(
            "视觉模型直接看图转写识别。切换模型后重新识别同一张图，"
            "可在日志对比两轮效果；选择会自动记住。")
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._model_combo.blockSignals(True)
        self._model_combo.addItem(AUTO_MODEL_LABEL)
        _cur = (self.cfg.llm.get("vision_model") or "").strip()
        if _cur:
            self._model_combo.addItem(_cur)
            self._model_combo.setCurrentText(_cur)
        self._model_combo.blockSignals(False)
        model_row.addWidget(self._model_combo, 1)
        root.addLayout(model_row)
        # 后台拉取可用视觉模型列表（不阻塞界面打开）
        self._model_worker = VisionModelListWorker(self.cfg, self)
        self._model_worker.loaded.connect(self._on_models_loaded)
        self._model_worker.start()

        # 操作按钮
        ops = QHBoxLayout()
        self.btn_ocr = QPushButton("识别并回填检测项目")
        self.btn_ocr.setToolTip(
            "第1-7步：OCR/视觉识别 -> AI 判定检测项目类型 -> 大模型结构化 -> "
            "存库 -> 按类型定位并跳转对应检测项目工作表回填")
        self.btn_ocr.clicked.connect(self._run_ocr_fill)

        self.btn_store_only = QPushButton("仅识别存库")
        self.btn_store_only.setToolTip("第1-5步：只识别并存库，不回填表格")
        self.btn_store_only.clicked.connect(self._run_store_only)

        self.btn_upload = QPushButton("上传服务器")
        self.btn_upload.setToolTip("第8步：把最近一次识别数据上传（默认dry_run）")
        self.btn_upload.clicked.connect(self._run_upload)

        self.btn_memory = QPushButton("识别记忆")
        self.btn_memory.setToolTip(
            "查看/管理长期识别记忆（人工校正经验与治理留痕，越用越准）")
        self.btn_memory.clicked.connect(self._show_memory)

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)

        for b in (self.btn_ocr, self.btn_store_only, self.btn_upload,
                  self.btn_memory, self.btn_close):
            b.setMinimumHeight(30)
            ops.addWidget(b)
        root.addLayout(ops)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        log_label = QLabel("识别日志：")
        root.addWidget(log_label)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        root.addWidget(self._log, 1)

        self.setStyleSheet("""
            QDialog { background:#f5f6f8; }
            QLabel#targetInfo { font-weight:bold; color:#1565C0; }
            QPlainTextEdit { background:white; font-family:Consolas; font-size:12px; }
            QPushButton { padding:4px 10px; }
        """)

    # ── 日志与进度 ──
    def _append_log(self, text):
        self._log.appendPlainText(str(text))

    def _set_busy(self, busy):
        for b in (self.btn_ocr, self.btn_store_only, self.btn_upload):
            b.setEnabled(not busy)

    # ── 识别模型 ──
    def _on_models_loaded(self, models):
        """可用视觉模型列表到达：重建下拉框并保留当前选择。"""
        cur = self._model_combo.currentText()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(AUTO_MODEL_LABEL)
        self._model_combo.addItems(models)
        if cur and cur != AUTO_MODEL_LABEL:
            if self._model_combo.findText(cur) < 0:
                self._model_combo.addItem(cur)
            self._model_combo.setCurrentText(cur)
        else:
            self._model_combo.setCurrentIndex(0)
        self._model_combo.blockSignals(False)
        if models:
            self._append_log("可用识别（视觉）模型：" + "、".join(models))
        else:
            self._append_log(
                "未获取到 Ollama 视觉模型列表（服务不可达？），"
                "仍可沿用配置默认模型识别。")

    def _on_model_changed(self, text):
        """下拉框切换识别模型：流水线即时生效并写回配置文件记住。"""
        model = "" if text == AUTO_MODEL_LABEL else str(text)
        try:
            self.pipeline.set_vision_model(model)
            self.cfg.save()
        except Exception as e:
            self._append_log(f"识别模型切换保存失败：{e}")
            return
        self._append_log(f"识别模型已切换：{text}（即时生效，已记住选择）")

    # ── 动作 ──
    def _pick_files(self):
        fps, _ = QFileDialog.getOpenFileNames(
            self, "选择图片/扫描PDF", "",
            "图片/PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.pdf)",
        )
        if fps:
            self.selected_files = fps
            names = "、".join(os.path.basename(p) for p in fps[:3])
            self._file_lbl.setText(f"{names}{' 等' if len(fps) > 3 else ''}（{len(fps)}个）")

    def _target_context(self):
        """返回 (detection_item, sub_item, columns) 或 None（无激活表时）。

        仅用于 SCAN_MOCK 离线联调借用当前表上下文；正常识别不依赖
        预先激活的工作表，类型由流水线 AI 判定。
        """
        key = self.app.current_item
        if not key:
            return None
        base, comp = self.app._parse_sheet_key(key)
        det = self.app.controller.resolve_item_name(base) if hasattr(self.app.controller, "resolve_item_name") else base
        cols = self.app._get_columns(key)
        return det, key, cols

    def _start_worker(self, use_ocr, fill_on_done):
        if not self.selected_files:
            QMessageBox.warning(self, "提示", "请先选择图片/PDF文件。")
            return
        # 识别优先：检测项目类型由流水线 AI 判定步骤（第3步）根据原始
        # 记录内容自动确定，回填时再按类型定位并跳转对应检测项目工作表
        det = sub = cols = None

        # 离线/无依赖联调用：仅在显式设置 SCAN_MOCK=1 才用模拟识别跑通链路
        # （优先借用当前激活表的上下文，让模拟数据免走 AI 判定）
        override = None
        if os.environ.get("SCAN_MOCK") == "1":
            ctx = self._target_context()
            if ctx:
                det, sub, cols = ctx
                from report_generator.scan_recognition.llm import MockLLMExtractor
                override = MockLLMExtractor().extract("", cols)

        self._fill_on_done = fill_on_done
        self._set_busy(True)
        source = self.selected_files[0]
        self._worker = _RecWorker(
            self.pipeline, source, det, sub, cols, use_ocr, structured_override=override,
            parent=self,
        )
        self._worker.step_changed.connect(
            lambda step, label: self._append_log(f"[步骤{step}] {label}")
        )
        self._worker.finished_ok.connect(self._on_finish)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()
        self._append_log(f"开始识别：{os.path.basename(source)}")

    def _run_ocr_fill(self):
        self._start_worker(use_ocr=True, fill_on_done=True)

    def _run_store_only(self):
        self._start_worker(use_ocr=True, fill_on_done=False)

    def _on_finish(self, result):
        self._set_busy(False)
        self._last_result = result
        model = result.get("vision_model") or ""
        self._append_log(f"识别完成：识别模型={model or '自动探测'}，"
                         f"检测项={result['sub_item']}，"
                         f"共 {len(result['rows'])} 条记录匹配。")
        if result.get("memory_hints"):
            self._append_log(
                f"识别记忆命中 {result.get('memory_hits', 0)} 条，"
                "已注入提示词辅助本次识别。")
        if result["doc_id"]:
            self._append_log(f"已存库 document_id={result['doc_id']}。")
            # 仅存库模式到此结束
            if not self._fill_on_done:
                return
        fw = result.get("field_warnings") or []
        if fw:
            self._append_log(f"字段复核提示 {len(fw)} 条（轴线编号/方向/设计值可疑，请人工复核）：")
            for w in fw[:10]:
                self._append_log(
                    f"  行{w.get('行')} {w.get('字段')}=「{w.get('值')}」{w.get('问题')}")
        rp = result.get("repair") or {}
        if rp:
            if not rp.get("enabled"):
                self._append_log("智能体自修复：未启用，跳过。")
            elif not rp.get("warnings_before"):
                self._append_log("智能体自修复：无可疑值，无需修复。")
            else:
                fr = rp.get("fallback_reason") or ""
                self._append_log(
                    f"智能体自修复：模型={rp.get('model') or '自动探测'}，"
                    f"轮数 {rp.get('rounds', 0)}，"
                    f"可疑值 {rp.get('warnings_before', 0)}"
                    f"→{rp.get('warnings_after', 0)} 条，"
                    f"{'已采纳修复结果' if rp.get('adopted') else '保留原识别结果'}"
                    + (f"，回退原因：{fr}" if fr else "") + "。")
        if not result["rows"]:
            self._append_log("未匹配到可回填数据。")
            return
        self._preview_and_fill(result)

    def _save_corrected(self, result, rows):
        """把人工校正后的对齐行替换写入数据库。"""
        if not result.get("doc_id"):
            return ""
        self.pipeline.db.replace_records(
            result["doc_id"], result.get("detection_item"),
            result.get("sub_item"), result.get("structured", []),
            result.get("normalized", []), rows)
        return f"校正结果已更新（document_id={result['doc_id']}，{len(rows)} 行）"

    def _preview_and_fill(self, result):
        """先以类 Excel 表格预览识别结果，人工校正后再回填当前检测表。"""
        from report_generator.scan_recognition.preview import RecognitionTablePreview
        dlg = RecognitionTablePreview(
            self, result["columns"], [list(r) for r in result["rows"]],
            doc_id=result.get("doc_id"),
            save_db=lambda rows: self._save_corrected(result, rows),
            title=f"识别结果查看与校正 - {result.get('sub_item') or ''}")
        if dlg.exec_() != RecognitionTablePreview.Accepted:
            self._append_log("已取消回填（可重新识别校正）。")
            return
        original = result["rows"]
        corrected = dlg.get_rows()
        changed = sum(1 for a, b in zip(original, corrected)
                      if [str(x) for x in a] != [str(x) for x in b])
        result["rows"] = corrected
        if changed:
            self._learn_memory(result, original, corrected)
            self._append_log(f"人工校正 {changed} 行后回填（数据库同步更新）。")
        self._fill_into_sheet(result)

    def _fill_into_sheet(self, result):
        """第7步：按识别出的检测项目类型定位工作表并回填。

        定位由主窗口 _resolve_fill_target 完成：当前激活表（类型一致）
        → 已建工作表 → 检测项目树（未勾选的自动勾选建表，钻芯法会弹出
        参数对话框）→ 用户手选；定位失败取消回填，避免数据落入无关表格。
        """
        key = self.app._resolve_fill_target(
            result.get("sub_item") or result.get("detection_item"))
        if key is None:
            self._append_log("未定位到对应检测项目工作表，已取消回填。")
            return
        imported = [list(r) for r in result["rows"]]
        self.app._sync_table_to_data()
        existing = self.app._trim_empty_tail_rows(
            self.app.sheet_data.get(key, [])
        )
        box = QMessageBox(self)
        box.setWindowTitle("回填检测表")
        box.setText(f"已识别 {len(imported)} 行匹配数据，目标工作表：{key}。请选择：")
        append_btn = box.addButton("追加到目标表", QMessageBox.AcceptRole)
        replace_btn = box.addButton("替换目标表", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked not in (append_btn, replace_btn):
            return
        new_data = imported if clicked is replace_btn else existing + imported
        switched = key != self.app.current_item
        self.app.sheet_data[key] = new_data
        self.app._load_item(key)
        self.app._status(f"已从扫描识别回填 {len(imported)} 行数据到 {key}")
        if switched:
            self._append_log(f"已自动切换到检测项目工作表：{key}。")
        self._append_log(f"已回填 {len(imported)} 行到工作表 {key}。")

    def _learn_memory(self, result, original, corrected):
        """人工校正差异沉淀为长期识别记忆（失败不影响回填）。"""
        try:
            n1 = self.pipeline.memory.learn_from_correction(
                result.get("sub_item") or "", result.get("columns", []),
                original, corrected)
            n2 = self.pipeline.memory.learn_patterns(
                result.get("sub_item") or "",
                result.get("field_warnings") or [])
            if n1 or n2:
                self._append_log(
                    f"识别记忆已学习：校正经验 {n1} 条、治理留痕 {n2} 条。")
        except Exception as e:
            self._append_log(f"识别记忆学习失败（不影响回填）：{e}")

    def _show_memory(self):
        """识别记忆管理：查看长期记忆（校正经验/治理留痕），可清空。"""
        try:
            items = self.pipeline.db.list_memory(limit=200)
        except Exception as e:
            QMessageBox.warning(self, "识别记忆", f"读取失败：{e}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("识别记忆（长期）")
        dlg.resize(660, 420)
        v = QVBoxLayout(dlg)
        info = QLabel(
            f"共 {len(items)} 条。来源：人工校正差异与量程治理留痕，"
            "识别时自动召回注入提示词（越用越准）。")
        info.setWordWrap(True)
        v.addWidget(info)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        if not items:
            view.setPlainText("暂无记忆。校正识别结果后会自动学习。")
        else:
            lines = []
            for m in items:
                old_v = str(m.get("old_value") or "")
                new_v = str(m.get("new_value") or "")
                tag = "治理留痕" if (m.get("kind") or "") == "pattern" \
                    else "人工校正"
                new_desc = f"实为「{new_v}」" if new_v else "未测（/）/空白"
                lines.append(
                    f"[{tag}] {m.get('detection_item') or ''}｜"
                    f"{m.get('field') or ''}：识别「{old_v}」→{new_desc}"
                    f"（{m.get('count') or 1}次，{m.get('last_seen') or ''}）")
            view.setPlainText("\n".join(lines))
        v.addWidget(view, 1)
        row = QHBoxLayout()
        btn_clear = QPushButton("清空全部记忆")
        btn_close = QPushButton("关闭")
        row.addWidget(btn_clear)
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)

        def _clear():
            if QMessageBox.question(
                    dlg, "确认", "确定清空全部识别记忆？该操作不可恢复。",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                self.pipeline.db.clear_memory()
            except Exception as e:
                QMessageBox.warning(dlg, "识别记忆", f"清空失败：{e}")
                return
            view.setPlainText("已清空全部识别记忆。")
            info.setText("共 0 条。")
            self._append_log("已清空全部识别记忆。")

        btn_clear.clicked.connect(_clear)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec_()

    def _run_upload(self):
        if self._last_result is None:
            QMessageBox.warning(self, "提示", "请先执行一次识别，再上传其结果。")
            return
        try:
            resp = self.pipeline.upload(self._last_result)
        except Exception as e:
            QMessageBox.critical(self, "上传失败", str(e))
            return
        extra = ""
        if resp.get("dry_run"):
            extra = "（dry_run 模式，未发送真实请求）"
        self._append_log(f"上传完成{extra}：{resp}")
        QMessageBox.information(self, "上传结果", f"分辨率：{resp.get('message') or '完成'}{extra}")

    def _on_fail(self, msg):
        self._set_busy(False)
        self._append_log(f"识别失败：{msg}")
        QMessageBox.critical(self, "识别失败", msg)

    def closeEvent(self, event):
        try:
            if self._worker and self._worker.isRunning():
                self._worker.wait(2000)
        except Exception:
            pass
        try:
            self.pipeline.close()
        except Exception:
            pass
        super().closeEvent(event)