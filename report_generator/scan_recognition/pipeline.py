# -*- coding: utf-8 -*-
"""扫描识别流水线（第1~8步编排）。

对外统一入口：``ScanRecognitionPipeline.recognize`` 一次完成
「保存原文件 -> OCR 识别 -> [AI 判定检测项目] -> 大模型结构化 -> 存库 ->
规范化 -> 匹配列」，把匹配好的“对齐行”与元信息返回，由界面层负责第7步
写入当前检测表，第8步上传调用 ``pipeline.upload``。

每个步骤封装为独立的 ``Step`` 类，步骤完成后通过 ``step_done`` 回调把该步
产物（snapshot）实时推给界面，实现“依次查看每个步骤的效果”。
"""
import hashlib
import os
import shutil
from pathlib import Path

from report_generator.scan_recognition.config import Config
from report_generator.scan_recognition import ocr as ocr_mod
from report_generator.scan_recognition.llm import build_llm_extractor
from report_generator.scan_recognition.normalizer import Normalizer
from report_generator.scan_recognition import matcher as matcher_mod
from report_generator.scan_recognition.storage import ScanDatabase
from report_generator.scan_recognition.agent.memory import MemoryStore
from report_generator.scan_recognition.uploader import ServerUploader


class Step:
    """流水线步骤基类：每一步读/写共享上下文 ``ctx`` 并产出可查看快照。

    子类需设置 ``key``（唯一标识）、``step_no``（对外进度编号，兼容 1~7）、
    ``label``（进度文案），并实现 ``execute(ctx)`` 与 ``snapshot(ctx)``。
    """

    key = ""
    step_no = 0
    label = ""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def execute(self, ctx):
        raise NotImplementedError

    def snapshot(self, ctx):
        """返回该步产物的可 JSON 序列化快照（供界面分步查看）。"""
        return None


class StoreSourceStep(Step):
    key = "store"
    step_no = 1
    label = "保存原文件到存储目录"

    def execute(self, ctx):
        stored_path = self.pipeline.store_source_file(ctx["source_path"])
        ctx["stored_path"] = stored_path
        ctx["file_hash"] = self.pipeline._file_hash(ctx["source_path"])

    def snapshot(self, ctx):
        return {
            "stored_path": ctx.get("stored_path"),
            "file_hash": ctx.get("file_hash"),
        }


class OcrStep(Step):
    key = "ocr"
    step_no = 2
    label = "OCR 识别图片/扫描PDF"

    def execute(self, ctx):
        try:
            detail = ocr_mod.ocr_file_detail(ctx["source_path"], cfg=self.pipeline.cfg)
            ctx["ocr_detail"] = detail
            ctx["ocr_text"] = detail["text"]
        except Exception as e:
            # OCR 不可用不中断：结构化阶段优先视觉模型看图转写，
            # OCR 文本仅作回退输入（此处为空）；原因记录进快照供界面提示
            ctx["ocr_detail"] = {"text": "", "n_cells": 0, "n_rows": 0,
                                 "low_confidence": [], "suspect_numbers": [],
                                 "skip_reason": str(e)}
            ctx["ocr_text"] = ""

    def snapshot(self, ctx):
        d = ctx.get("ocr_detail") or {}
        return {
            "text": d.get("text", ""),
            "n_cells": d.get("n_cells", 0),
            "n_rows": d.get("n_rows", 0),
            "low_confidence": d.get("low_confidence", []),
            "suspect_numbers": d.get("suspect_numbers", []),
            "skip_reason": d.get("skip_reason", ""),
        }


class ClassifyStep(Step):
    """AI 自动判定检测项目（sub_item/columns 为空时插入）。

    根据 OCR 表格文本从候选检测项目中判定所属项目，再取该项目的列
    定义填入 ctx，后续 ExtractStep/MatchStep 即可沿用。
    """
    key = "classify"
    step_no = 3
    label = "AI 自动判断检测项目"

    def execute(self, ctx):
        from report_generator.scan_recognition.errors import RecognitionError
        candidates_map = matcher_mod.available_sub_items()
        candidates = list(candidates_map.keys())
        if not candidates:
            raise RecognitionError(
                "未获取到候选检测项目（插件未加载？），无法 AI 判定。")
        extractor = self.pipeline._get_extractor()
        ocr_text = ctx.get("ocr_text", "")
        if ocr_text.strip():
            chosen, confidence = extractor.classify_project(ocr_text, candidates)
            classify_mode = "text"
        else:
            # OCR 文本不可用（exe 未带 PaddleOCR 等）：视觉模型看图判定
            vm = None
            try:
                vm = extractor.resolve_vision_model()
            except Exception:
                vm = None
            image_path = (ctx.get("stored_path")
                          or ctx.get("source_path") or "")
            if not (vm and image_path and os.path.exists(image_path)):
                skip = (ctx.get("ocr_detail") or {}).get("skip_reason", "")
                raise RecognitionError(
                    "OCR 不可用且无视觉模型，无法 AI 判定检测项目，"
                    "请配置可用的视觉模型或启用 OCR 后重试。"
                    + (f"\nOCR 原因：{skip}" if skip else ""))
            chosen, confidence = extractor.classify_project_vision(
                image_path, candidates)
            classify_mode = "vision"
        ctx["detection_item"] = chosen
        ctx["sub_item"] = chosen
        ctx["columns"] = list(candidates_map.get(chosen, []))
        ctx["classification"] = {
            "sub_item": chosen,
            "confidence": confidence,
            "candidates": candidates,
            "mode": classify_mode,
            "raw_reply": getattr(extractor, "_last_classify_raw", ""),
        }

    def snapshot(self, ctx):
        c = ctx.get("classification") or {}
        return {
            "candidates": c.get("candidates", []),
            "chosen": c.get("sub_item", ""),
            "confidence": c.get("confidence", 0.0),
            "mode": c.get("mode", "text"),
            "raw_reply": c.get("raw_reply", ""),
        }


class ExtractStep(Step):
    key = "extract"
    step_no = 3
    label = "大模型结构化识别"

    def execute(self, ctx):
        if ctx.get("structured_override") is not None:
            ctx["structured"] = ctx["structured_override"]
            return
        extractor = self.pipeline._get_extractor()
        # 手写记录表：优先用视觉模型直接看图转写（绕过 OCR），
        # 无视觉模型或视觉识别失败时回退 OCR 文本路径
        vm = None
        try:
            vm = extractor.resolve_vision_model()
        except Exception:
            vm = None
        image_path = (ctx.get("stored_path")
                      or ctx.get("source_path") or "")
        if vm and image_path and os.path.exists(image_path):
            try:
                # 识别记忆召回（短期+长期）注入视觉转写提示词，越用越准
                hints = self.pipeline._memory_hints(ctx)
                ctx["structured"] = extractor.extract_vision(
                    image_path, ctx.get("columns", []), hints=hints)
                ctx["vision_model"] = vm
                return
            except Exception as e:
                ctx["vision_fallback_reason"] = str(e)
        if not ctx.get("ocr_text", "").strip():
            # 视觉失败且没有 OCR 文本可回退：给出组合原因，避免空文本空转
            from report_generator.scan_recognition.errors import RecognitionError
            skip = (ctx.get("ocr_detail") or {}).get("skip_reason", "")
            raise RecognitionError(
                "OCR 与视觉模型均不可用，无法结构化识别。"
                + (f"\nOCR 原因：{skip}" if skip else "")
                + (f"\n视觉原因：{ctx.get('vision_fallback_reason', '')}"
                   if ctx.get("vision_fallback_reason") else ""))
        ctx["structured"] = extractor.extract(ctx.get("ocr_text", ""),
                                              ctx.get("columns", []))

    def snapshot(self, ctx):
        return {
            "columns": list(ctx.get("columns", [])),
            "structured": ctx.get("structured", []),
            "mode": ("vision:" + ctx["vision_model"]) if ctx.get("vision_model")
                    else "text",
            "vision_fallback_reason": ctx.get("vision_fallback_reason", ""),
            "memory_hits": ctx.get("memory_hits", 0),
            "memory_hints": ctx.get("memory_hints", ""),
        }


class SaveStep(Step):
    key = "save"
    step_no = 4
    label = "电子数据存储到数据库"

    def execute(self, ctx):
        ctx["doc_id"] = self.pipeline.db.add_document(
            source_path=str(ctx["source_path"]),
            stored_path=ctx.get("stored_path", ""),
            file_hash=ctx.get("file_hash", ""),
            ocr_text=ctx.get("ocr_text", ""),
            structured=ctx.get("structured", []),
            detection_item=ctx.get("detection_item"),
            sub_item=ctx.get("sub_item"),
        )

    def snapshot(self, ctx):
        return {"doc_id": ctx.get("doc_id")}


class NormalizeStep(Step):
    key = "normalize"
    step_no = 5
    label = "结构化/规范化处理"

    def execute(self, ctx):
        normalizer = Normalizer(self.pipeline.cfg)
        ctx["normalized"] = normalizer.normalize_records(ctx.get("structured", []))
        # 字段治理复核：轴线编号/方向/设计值可疑值标记（供人工复核，不改写）
        warnings = normalizer.validate_records(ctx["normalized"])
        # 量程治理留痕：手写斜杠"/"误识为小数字，已按未测自动清空
        warnings[:0] = [
            {"行": w["行"], "字段": w["字段"], "值": w["值"],
             "问题": "小于合理量程，已按未测（/）自动清空，请确认"}
            for w in normalizer.take_auto_cleared()
        ]
        ctx["field_warnings"] = warnings

    def snapshot(self, ctx):
        return {"normalized": ctx.get("normalized", []),
                "field_warnings": ctx.get("field_warnings", [])}


class RepairStep(Step):
    """AI 智能体自修复复核（LangGraph 状态图，位于规范化之后、匹配之前）。

    字段治理发现可疑值时，智能体带原图与可疑清单重问视觉模型重新转写，
    再经规范化校验，最多 ``agent.max_repair_rounds`` 轮、按“可疑值最少”
    择优采纳；未改善或任何异常均保留原结果（识别不中断）。
    """
    key = "repair"
    step_no = 5
    label = "AI 智能体自修复复核"

    def execute(self, ctx):
        n_warn = len(ctx.get("field_warnings") or [])
        info = {"enabled": False, "rounds": 0, "adopted": False,
                "warnings_before": n_warn, "warnings_after": n_warn,
                "model": "", "fallback_reason": "", "log": []}
        agent_cfg = self.pipeline.cfg.agent or {}
        if not agent_cfg.get("enabled", True):
            info["fallback_reason"] = "未启用（agent.enabled=false）"
            ctx["repair_info"] = info
            return
        if not n_warn:
            # 校验无可疑值：无需修复
            ctx["repair_info"] = info
            return
        info["enabled"] = True
        try:
            # 惰性导入：langgraph 未安装/旧 Python 环境时走降级
            from report_generator.scan_recognition.agent.graph import \
                run_repair_agent
            try:
                vm = self.pipeline._get_extractor().resolve_vision_model() or ""
            except Exception:
                vm = ""
            res = run_repair_agent(
                ctx.get("stored_path") or ctx.get("source_path"),
                ctx.get("columns", []), ctx.get("structured", []),
                ctx.get("field_warnings", []), self.pipeline.cfg,
                max_rounds=int(agent_cfg.get("max_repair_rounds", 2)),
                model=vm or None,
                memory_hints=ctx.get("memory_hints", ""))
            info.update({"rounds": res.get("rounds", 0),
                         "model": res.get("model", ""),
                         "fallback_reason": res.get("fallback_reason", ""),
                         "log": res.get("log", [])})
            if (not res.get("fallback_reason")
                    and res.get("normalized") is not None
                    and len(res.get("warnings") or []) < n_warn):
                # 修复结果更优：更新上下文，后续 MatchStep 入库即最终值
                ctx["structured"] = res["records"]
                ctx["normalized"] = res["normalized"]
                ctx["field_warnings"] = res["warnings"]
                ctx["repair_log"] = res.get("log", [])
                info["adopted"] = True
                info["warnings_after"] = len(res["warnings"])
            else:
                info["warnings_after"] = len(res.get("warnings") or []) \
                    if not res.get("fallback_reason") else n_warn
        except Exception as e:  # noqa: BLE001 —— 智能体任何异常都降级
            info["fallback_reason"] = f"{type(e).__name__}: {e}"
        ctx["repair_info"] = info

    def snapshot(self, ctx):
        snap = dict(ctx.get("repair_info") or {})
        snap["normalized"] = ctx.get("normalized", [])
        snap["field_warnings"] = ctx.get("field_warnings", [])
        return snap


class MatchStep(Step):
    key = "match"
    step_no = 6
    label = "匹配到检测项目列"

    def execute(self, ctx):
        rows, matched_rows = matcher_mod.match_rows(
            ctx.get("normalized", []), ctx.get("columns", []), self.pipeline.cfg)
        ctx["rows"] = rows
        ctx["matched_rows"] = matched_rows
        self.pipeline.db.add_records(
            ctx.get("doc_id"), ctx.get("detection_item"),
            ctx.get("sub_item"), ctx.get("structured", []),
            ctx.get("normalized", []), matched_rows)

    def snapshot(self, ctx):
        return {
            "rows": ctx.get("rows", []),
            "matched_rows": ctx.get("matched_rows", []),
        }


class ScanRecognitionPipeline:
    """端到端扫描识别流水线。"""

    def __init__(self, cfg: Config = None, db: ScanDatabase = None):
        self.cfg = cfg or Config.load()
        self.db = db or ScanDatabase(db_path=self.cfg.database_path, cfg=self.cfg)
        self.memory = MemoryStore(self.db, self.cfg)
        self._extractor = None

    def _get_extractor(self):
        if self._extractor is None:
            self._extractor = build_llm_extractor(self.cfg)
        return self._extractor

    def set_vision_model(self, model_name):
        """运行时切换视觉识别模型（界面下拉框选择后即时生效）。

        model_name 为空 = 恢复"自动探测"。已创建的抽取器同步更新，
        无需重建；配置写入由调用方（界面层）负责持久化。
        """
        self.cfg.llm["vision_model"] = model_name or ""
        ex = self._extractor
        if ex is not None and hasattr(ex, "vision_model"):
            ex.vision_model = model_name or ""
            ex._vision_cache = None

    def _memory_hints(self, ctx):
        """召回识别记忆（短期会话+长期校正经验）拼为提示词文本。

        命中结果同时写入 ctx 供快照/结果展示；任何异常静默降级，
        记忆不可用不能影响识别主流程。
        """
        try:
            text, n = self.memory.compose_hints(
                ctx.get("detection_item") or ctx.get("sub_item") or "",
                ctx.get("file_hash") or "")
            ctx["memory_hints"] = text
            ctx["memory_hits"] = n
            return text
        except Exception:
            return ""

    # ── 第2步：把原文件复制/移动到存储目录 ──
    def store_source_file(self, source_path):
        src = Path(source_path)
        target = self.cfg.document_dir / src.name
        if src.resolve() != target.resolve():
            shutil.copy2(str(src), str(target))
        return str(target)

    @staticmethod
    def _file_hash(path):
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _build_steps(self, ctx):
        """根据上下文决定执行哪些步骤。

        - sub_item 为空/None/"AI 自动识别" 或 columns 为空 → 插入 ClassifyStep。
        - structured_override 非 None → 跳过 OcrStep（ExtractStep 内部短路）。
        """
        ai_mode = (not ctx.get("sub_item")
                   or str(ctx.get("sub_item", "")).strip() in ("", "AI 自动识别")
                   or not ctx.get("columns"))
        steps = [StoreSourceStep(self)]
        if ctx.get("structured_override") is None:
            steps.append(OcrStep(self))
        if ai_mode and ctx.get("structured_override") is None:
            steps.append(ClassifyStep(self))
        steps.append(ExtractStep(self))
        steps.append(SaveStep(self))
        steps.append(NormalizeStep(self))
        steps.append(RepairStep(self))
        steps.append(MatchStep(self))
        return steps

    # ── 主入口：跑通 1-7 步，返回完整结果 ──
    def recognize(self, source_path, detection_item, sub_item, columns,
                  structured_override=None, progress=None, step_done=None):
        """执行识别流水线。

        structured_override: 可选，跳过 OCR/LLM，用给定结构化记录列表。
                            用于界面“先识别、再回填”与离线测试。
        step_done: 可选回调 ``f(key, step_no, label, snapshot)``，每步完成
                  后实时把产物推给界面，实现“依次查看每个步骤的效果”。
        """
        ctx = {
            "source_path": source_path,
            "detection_item": detection_item,
            "sub_item": sub_item,
            "columns": list(columns) if columns else [],
            "structured_override": structured_override,
        }
        steps = self._build_steps(ctx)
        step_results = {}
        for step in steps:
            if progress:
                progress(step.step_no, step.label)
            step.execute(ctx)
            snap = step.snapshot(ctx)
            step_results[step.key] = snap
            if step_done:
                step_done(step.key, step.step_no, step.label, snap)
        # 短期记忆：记录本图最终复核留痕（同图再次识别时注入提示词）
        try:
            self.memory.remember_session(
                ctx.get("file_hash") or "",
                ctx.get("field_warnings") or [],
                summary=f"识别{len(ctx.get('normalized') or [])}条，"
                        f"复核{len(ctx.get('field_warnings') or [])}处")
        except Exception:
            pass
        if progress:
            progress(7, "识别完成，等待回填表格/模板")
        ocr_detail = ctx.get("ocr_detail") or {}
        result = {
            "doc_id": ctx.get("doc_id"),
            "source_path": str(source_path),
            "stored_path": ctx.get("stored_path", ""),
            "detection_item": ctx.get("detection_item"),
            "sub_item": ctx.get("sub_item"),
            "columns": list(ctx.get("columns", [])),
            "structured": ctx.get("structured", []),
            "normalized": ctx.get("normalized", []),
            "field_warnings": ctx.get("field_warnings", []),
            "rows": ctx.get("rows", []),
            "matched_rows": ctx.get("matched_rows", []),
            "ocr_stats": {
                "n_cells": ocr_detail.get("n_cells", 0),
                "n_rows": ocr_detail.get("n_rows", 0),
                "low_confidence": ocr_detail.get("low_confidence", []),
                "suspect_numbers": ocr_detail.get("suspect_numbers", []),
            },
            "step_results": step_results,
            "vision_model": ctx.get("vision_model", ""),
            "memory_hints": ctx.get("memory_hints", ""),
            "memory_hits": ctx.get("memory_hits", 0),
        }
        if ctx.get("classification"):
            result["classification"] = ctx["classification"]
        result["repair"] = ctx.get("repair_info") or {}
        result["repair_log"] = ctx.get("repair_log", [])
        return result

    # ── 第8步：上传到服务器 ──
    def upload(self, result, uploader: ServerUploader = None):
        uploader = uploader or ServerUploader(self.cfg)
        resp = uploader.upload(
            result["detection_item"], result["sub_item"],
            result["rows"], result.get("matched_rows"),
        )
        return resp

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass
