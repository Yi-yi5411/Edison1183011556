# -*- coding: utf-8 -*-
"""扫描识别测试工具（独立于主窗口，可在登录界面直接打开）。

用于在首个界面上快速验证「文档扫描识别」流水线（第1~8步）：
- 选择检测子项，或选“AI 自动识别”由大模型判定图片属于哪个检测项目
- 选择 图片/扫描PDF 文件
- 后台线程执行：保存原文件 -> OCR(PaddleOCR) -> [AI判定项目] -> 大模型结构化
  (Ollama/vLLM/Qwen) -> 存库 -> 规范化 -> 匹配到检测列
- 左侧步骤列表 + 右侧详情可依次查看每一步的效果（识别中即可实时查看）；
  底部保留运行日志（不依赖主窗口表格，故不受登录环境影响）
"""
import json
import os
import time

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFileDialog, QComboBox,
    QPlainTextEdit, QPushButton, QLabel, QMessageBox, QFrame,
    QSplitter, QListWidget, QTextBrowser, QListWidgetItem,
)

from report_generator.scan_recognition.config import Config
from report_generator.scan_recognition.pipeline import ScanRecognitionPipeline
from report_generator.scan_recognition.matcher import available_sub_items
from report_generator.scan_recognition.preview import RecognitionTablePreview

AI_AUTO = "AI 自动识别"
AUTO_MODEL_LABEL = "自动探测（配置默认）"


class VisionModelListWorker(QThread):
    """后台拉取 Ollama 可用视觉模型列表（识别模型下拉框数据源）。

    避免 /api/tags + /api/show 能力探测在网络不佳时阻塞界面。
    """
    loaded = pyqtSignal(list)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def run(self):
        models = []
        try:
            from report_generator.scan_recognition.llm import (
                list_vision_models_from_cfg,
            )
            models = list_vision_models_from_cfg(self.cfg) or []
        except Exception:
            models = []
        self.loaded.emit(models)


class _TestWorker(QThread):
    """后台执行识别流水线，避免阻塞界面。"""
    step_changed = pyqtSignal(int, str)
    step_done = pyqtSignal(str, int, str, object)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, pipeline, source_path, sub_item, columns, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.source_path = source_path
        # sub_item/columns 为 None 时由流水线内的 AI 判定步骤自动确定
        self.sub_item = sub_item
        self.columns = list(columns) if columns else None

    def run(self):
        try:
            # 测试环境不绑定主窗口，detection_item 直接用 sub_item 名称
            result = self.pipeline.recognize(
                self.source_path, self.sub_item, self.sub_item,
                self.columns, progress=self._emit,
                step_done=self._emit_step_done,
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))

    def _emit(self, step, label):
        self.step_changed.emit(step, label)

    def _emit_step_done(self, key, step_no, label, snapshot):
        self.step_done.emit(key, step_no, label, snapshot)


class ScanRecognitionTestDialog(QDialog):
    """自包含的扫描识别测试对话框（登录页入口用）。"""

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg or Config.load()
        self.pipeline = ScanRecognitionPipeline(cfg=self.cfg)
        self.selected_file = None
        self._worker = None
        self._last_result = None
        self._step_snaps = {}          # (run_no, key) -> snapshot
        self._run_no = 0               # 识别轮次（切换模型重跑对比用）
        self._run_start = 0.0
        self._results = {}             # run_no -> result
        self._elapsed = {}             # run_no -> 用时(秒)
        self.setWindowTitle("文档扫描识别 - 测试")
        self.resize(860, 620)
        self._items = available_sub_items() or {}
        self._init_ui()
        self._append_log(
            "扫描识别测试工具就绪。选择检测子项（或默认“AI 自动识别”）与图片/PDF后点击“开始识别”。\n"
            "识别链路：保存原文件 → OCR → (AI判定项目) → 大模型结构化 → 存库 → 规范化 → 匹配到检测列。\n"
            f"大模型配置：{self.cfg.llm.get('provider')} @ {self.cfg.llm.get('base_url')} "
            f"(model={self.cfg.llm.get('model')})，可在 report_generator/assets/scan_recognition_config.json 修改。\n"
        )

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        row = QHBoxLayout()
        row.addWidget(QLabel("检测子项："))
        self._item_combo = QComboBox()
        self._item_combo.addItem(AI_AUTO)
        self._item_combo.addItems(list(self._items.keys()))
        self._item_combo.setCurrentIndex(0)          # 默认 AI 自动识别
        self._item_combo.setMinimumWidth(220)
        row.addWidget(self._item_combo, 1)
        root.addLayout(row)

        # 识别模型：Ollama 视觉模型下拉框，切换后重跑即可对比识别效果
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("识别模型："))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(220)
        self._model_combo.setToolTip(
            "视觉模型直接看图转写识别。切换模型后重新识别同一张图，"
            "可在下方步骤列表与日志对比两轮效果；选择会自动记住。")
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._model_combo.blockSignals(True)
        self._model_combo.addItem(AUTO_MODEL_LABEL)
        _cur = (self.cfg.llm.get("vision_model") or "").strip()
        if _cur:
            self._model_combo.addItem(_cur)
            self._model_combo.setCurrentText(_cur)
        self._model_combo.blockSignals(False)
        mrow.addWidget(self._model_combo, 1)
        root.addLayout(mrow)
        # 后台拉取可用视觉模型列表（不阻塞界面打开）
        self._model_worker = VisionModelListWorker(self.cfg, self)
        self._model_worker.loaded.connect(self._on_models_loaded)
        self._model_worker.start()

        file_row = QHBoxLayout()
        self._file_lbl = QLabel("未选择文件")
        self._file_lbl.setStyleSheet("color:#666;")
        btn_pick = QPushButton("选择图片/PDF...")
        btn_pick.clicked.connect(self._pick_file)
        file_row.addWidget(self._file_lbl, 1)
        file_row.addWidget(btn_pick)
        root.addLayout(file_row)

        ops = QHBoxLayout()
        self._btn_run = QPushButton("开始识别")
        self._btn_run.clicked.connect(self._run)
        self._btn_preview = QPushButton("查看/校正表格")
        self._btn_preview.setToolTip("以类 Excel 表格查看识别结果，可校正、导出Excel、保存回数据库")
        self._btn_preview.setEnabled(False)
        self._btn_preview.clicked.connect(self._open_preview)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        for b in (self._btn_run, self._btn_preview, btn_close):
            b.setMinimumHeight(30)
            ops.addWidget(b)
        root.addLayout(ops)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        # ── 分步效果查看：左步骤列表 + 右详情 ──
        split = QSplitter(Qt.Horizontal)
        self._step_list = QListWidget()
        self._step_list.currentRowChanged.connect(self._on_step_selected)
        split.addWidget(self._step_list)
        self._step_view = QTextBrowser()
        self._step_view.setPlaceholderText("点击“开始识别”后，每完成一步即可在此查看该步效果。")
        split.addWidget(self._step_view)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 3)

        root.addWidget(QLabel("运行日志："))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        root.addWidget(self._log, 1)

        self.setStyleSheet("""
            QDialog { background:#f5f6f8; }
            QPlainTextEdit, QTextBrowser, QListWidget {
                background:white; font-family:Consolas; font-size:12px; }
            QPushButton { padding:4px 12px; }
        """)

    # ── 日志 ──
    def _append_log(self, text):
        self._log.appendPlainText(str(text))
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum())

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

    # ── 分步查看 ──
    def _on_step_done(self, key, step_no, label, snapshot):
        """识别线程每完成一步：加入步骤列表并自动选中最新项。"""
        self._step_snaps[(self._run_no, key)] = snapshot
        display = f"第{self._run_no}轮 {step_no} {label}"
        self._step_list.addItem(QListWidgetItem(display))
        self._step_list.setCurrentRow(self._step_list.count() - 1)

    def _on_step_selected(self, row):
        keys = list(self._step_snaps.keys())
        if row < 0 or row >= len(keys):
            return
        run_no, key = keys[row]
        self._step_view.setPlainText(
            self._render_step(key, self._step_snaps[(run_no, key)], run_no))

    def _render_step(self, key, snap, run_no=None):
        if snap is None:
            return "（该步无产物）"
        if key == "store":
            return (f"存储路径：{snap.get('stored_path', '')}\n"
                    f"文件哈希(MD5)：{snap.get('file_hash', '')}")
        if key == "ocr":
            low = snap.get("low_confidence") or []
            suspect = snap.get("suspect_numbers") or []
            head = (f"识别单元格 {snap.get('n_cells', 0)} 个，还原 {snap.get('n_rows', 0)} 行\n"
                    f"低置信度 {len(low)} 个，可疑数字 {len(suspect)} 个\n"
                    + "-" * 46 + "\n")
            return head + (snap.get("text") or "")
        if key == "classify":
            lines = [f"候选检测项目（{len(snap.get('candidates', []))} 个）："]
            lines += [f"  {c}" for c in snap.get("candidates", [])]
            lines.append(f"AI 判定结果：{snap.get('chosen', '')}")
            lines.append(f"置信度：{snap.get('confidence', 0)}")
            lines.append("-" * 46)
            lines.append(f"大模型原始回复：\n{snap.get('raw_reply', '')}")
            return "\n".join(lines)
        if key == "extract":
            mode = snap.get("mode", "")
            head = "目标表头：{}\n".format(snap.get("columns", []))
            if mode.startswith("vision"):
                head += f"识别方式：视觉模型看图转写（{mode.split(':', 1)[-1]}）\n"
                if snap.get("vision_fallback_reason"):
                    head += f"上次回退原因：{snap['vision_fallback_reason']}\n"
            else:
                head += "识别方式：OCR 文本 + 大模型结构化\n"
                if snap.get("vision_fallback_reason"):
                    head += f"视觉识别失败已回退：{snap['vision_fallback_reason']}\n"
            if snap.get("memory_hints"):
                head += (f"识别记忆命中 {snap.get('memory_hits', 0)} 条"
                         "（已注入提示词辅助识别）：\n"
                         + str(snap.get("memory_hints")) + "\n")
            return (head + "-" * 46 + "\n"
                    + "结构化记录（大模型输出）：\n"
                    + json.dumps(snap.get("structured", []), ensure_ascii=False, indent=2))
        if key == "save":
            return f"document_id = {snap.get('doc_id')}"
        if key == "normalize":
            warns = snap.get("field_warnings") or []
            head = f"规范化后记录（{len(snap.get('normalized', []))} 条）："
            if warns:
                head += f"\n字段复核提示 {len(warns)} 条："
                head += "\n" + "\n".join(
                    f"  行{w.get('行')} {w.get('字段')}=「{w.get('值')}」{w.get('问题')}"
                    for w in warns)
            return (head + "\n"
                    + json.dumps(snap.get("normalized", []), ensure_ascii=False, indent=2))
        if key == "repair":
            if not snap.get("enabled"):
                return ("AI 智能体自修复：未启用。\n"
                        f"原因：{snap.get('fallback_reason') or 'agent.enabled=false'}")
            if not snap.get("warnings_before"):
                return "AI 智能体自修复：规范化校验未发现可疑值，无需修复。"
            lines = [
                f"修复模型：{snap.get('model') or '自动探测'}",
                f"修复轮数：{snap.get('rounds', 0)}",
                f"可疑值：{snap.get('warnings_before', 0)} → "
                f"{snap.get('warnings_after', 0)} 条",
                ("已采纳修复结果（择优：可疑值最少）" if snap.get("adopted")
                 else "未采纳（保留原识别结果）"),
            ]
            if snap.get("fallback_reason"):
                lines.append(f"回退原因：{snap['fallback_reason']}")
            log = snap.get("log") or []
            if log:
                lines.append("-" * 46)
                lines += [f"  {x}" for x in log]
            warns = snap.get("field_warnings") or []
            if warns:
                lines.append("-" * 46)
                lines.append(f"最终复核提示 {len(warns)} 条：")
                lines += [f"  行{w.get('行')} {w.get('字段')}"
                          f"=「{w.get('值')}」{w.get('问题')}" for w in warns]
            lines.append("-" * 46)
            lines.append("修复后规范化记录：")
            lines.append(json.dumps(snap.get("normalized", []),
                                    ensure_ascii=False, indent=2))
            return "\n".join(lines)
        if key == "match":
            res = (self._results.get(run_no) if run_no else None) \
                or self._last_result
            cols = res.get("columns", []) if res else []
            lines = [f"对齐行 {len(snap.get('rows', []))} 条，其中匹配 {snap.get('matched_rows', 0)} 条："]
            for i, r in enumerate(snap.get("rows", [])):
                cells = ", ".join(f"{c}={v}" for c, v in zip(cols, r) if v not in ("", None))
                lines.append(f"  行{i+1}: {cells or '（无匹配列）'}")
            return "\n".join(lines)
        return json.dumps(snap, ensure_ascii=False, indent=2)

    # ── 交互 ──
    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片/扫描PDF", "",
            "图片/PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.pdf)",
        )
        if path:
            self.selected_file = path
            self._file_lbl.setText(os.path.basename(path))

    def _run(self):
        sub_item = self._item_combo.currentText()
        if not self.selected_file:
            QMessageBox.warning(self, "提示", "请选择图片/PDF文件。")
            return
        ai_mode = (sub_item == AI_AUTO)
        columns = None
        if not ai_mode:
            columns = self._items.get(sub_item, [])
            if not columns:
                QMessageBox.warning(self, "提示", f"检测子项 {sub_item} 未定义列。")
                return
        self._set_busy(True)
        # 轮次标记：步骤列表保留历史轮次，切换模型重跑后可逐项点击对比
        self._run_no += 1
        self._run_start = time.time()
        self._step_view.clear()
        # AI 模式：sub_item/columns 传 None，由流水线内 ClassifyStep 判定
        self._worker = _TestWorker(self.pipeline, self.selected_file,
                                   None if ai_mode else sub_item,
                                   columns, parent=self)
        self._worker.step_changed.connect(lambda s, l: self._append_log(f"[步骤{s}] {l}"))
        self._worker.step_done.connect(self._on_step_done)
        self._worker.finished_ok.connect(self._on_finish)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()
        self._append_log(
            f"第{self._run_no}轮开始识别：{os.path.basename(self.selected_file)}"
            + ("（AI 自动识别检测项目）" if ai_mode else f"（{sub_item}）")
            + f"，识别模型：{self._model_combo.currentText()}")

    def _on_finish(self, result):
        self._set_busy(False)
        self._last_result = result
        if result.get("rows"):
            self._btn_preview.setEnabled(True)
        rows = result["rows"]
        elapsed = time.time() - self._run_start if self._run_start else 0.0
        self._results[self._run_no] = result
        self._elapsed[self._run_no] = elapsed
        n_warn = len(result.get("field_warnings") or [])
        model = result.get("vision_model") or ""
        self._append_log(
            f"第{self._run_no}轮识别完成：识别模型={model or '自动探测'}，"
            f"匹配 {len(rows)} 条，复核提示 {n_warn} 条，用时 {elapsed:.1f}s，"
            f"document_id={result['doc_id']}。")
        prev_no = self._run_no - 1
        if prev_no in self._results:
            prev = self._results[prev_no]
            self._append_log(
                f"与上一轮对比：匹配 {len(prev.get('rows') or [])}→{len(rows)} 条，"
                f"复核提示 {len(prev.get('field_warnings') or [])}→{n_warn} 条，"
                f"用时 {self._elapsed[prev_no]:.1f}s→{elapsed:.1f}s"
                f"（识别模型：{prev.get('vision_model') or '自动探测'}→"
                f"{model or '自动探测'}）")
        cls = result.get("classification")
        if cls:
            self._append_log(
                f"AI 判定检测项目：{cls.get('sub_item', '')}"
                f"（置信度 {cls.get('confidence', 0)}）")
        stats = result.get("ocr_stats") or {}
        low = stats.get("low_confidence") or []
        suspect = stats.get("suspect_numbers") or []
        if low:
            self._append_log(
                f"低置信度单元格 {len(low)} 个（请人工复核）："
                + ", ".join(f"{d['text']}({d['score']})" for d in low[:10])
                + (" ..." if len(low) > 10 else ""))
        if suspect:
            self._append_log(
                f"可疑数字单元格 {len(suspect)} 个（含O/0、I/1等易混字符）："
                + ", ".join(f"{d['text']}({d['score']})" for d in suspect[:10])
                + (" ..." if len(suspect) > 10 else ""))
        if not low and not suspect:
            self._append_log("OCR 置信度正常，无可疑数字单元格。")
        fw = result.get("field_warnings") or []
        if fw:
            self._append_log(f"字段复核提示 {len(fw)} 条（轴线编号/方向/设计值可疑，请人工复核）：")
            for w in fw[:10]:
                self._append_log(
                    f"  行{w.get('行')} {w.get('字段')}=「{w.get('值')}」{w.get('问题')}")
            if len(fw) > 10:
                self._append_log(f"  ... 其余 {len(fw) - 10} 条见“规范化”步骤详情")
        cols = result["columns"]
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
                    f"{'已采纳' if rp.get('adopted') else '未采纳'}"
                    + (f"，回退原因：{fr}" if fr else "") + "。")
                for x in (rp.get("log") or [])[:6]:
                    self._append_log(f"  [智能体] {x}")
        self._append_log("---- 匹配到检测列（对齐行） ----")
        for i, r in enumerate(rows):
            cells = ", ".join(f"{c}={v}" for c, v in zip(cols, r) if v not in ("", None))
            self._append_log(f"行{i+1}: {cells}")

    def _on_fail(self, msg):
        self._set_busy(False)
        self._append_log(f"识别失败：{msg}")
        QMessageBox.critical(self, "识别失败", msg)

    def _set_busy(self, busy):
        self._btn_run.setEnabled(not busy)
        if busy:
            self._btn_preview.setEnabled(False)

    def _open_preview(self):
        """以类 Excel 表格查看/校正识别结果，可保存校正回数据库。"""
        result = self._last_result
        if not result or not result.get("rows"):
            QMessageBox.information(self, "提示", "请先完成一次识别。")
            return

        def _save_db(rows):
            if not result.get("doc_id"):
                return ""
            self.pipeline.db.replace_records(
                result["doc_id"], result.get("detection_item"),
                result.get("sub_item"), result.get("structured", []),
                result.get("normalized", []), rows)
            msg = (f"校正结果已更新（document_id={result['doc_id']}，"
                   f"{len(rows)} 行）")
            self._append_log(msg)
            return msg

        dlg = RecognitionTablePreview(
            self, result["columns"], [list(r) for r in result["rows"]],
            doc_id=result.get("doc_id"), save_db=_save_db,
            title=f"识别结果查看与校正 - {result.get('sub_item') or ''}")
        dlg.exec_()

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
