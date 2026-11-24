# -*- coding: utf-8 -*-
"""扫描识别路由：识别管线/回填/识别历史/视觉模型列表。

识别管线 scan_recognition.pipeline 已与 GUI 解耦，直接同步调用；
识别历史复用 scan_recognition.storage.ScanDatabase（与桌面版同一数据库）。
"""

import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from typing import List, Optional

from deps import (ROOT, get_controller, get_state, ok, ApiError, Config,
                  ScanDatabase, scan_llm, ITEM_COLUMNS)
import ingest
import scan_jobs

router = APIRouter(tags=["scan"])


class FillBody(BaseModel):
    sheet_key: str
    records: list  # 对齐行 [[单元格,...], ...]


@router.post("/scan/run")
async def scan_run(files: List[UploadFile] = File(...),
                   detection_item: str = Form("")):
    """同步执行扫描识别管线（图片/PDF 多选）。

    detection_item 留空时由 AI 自动判定检测项目（需要 OCR 或视觉模型可用）。
    返回逐文件识别结果与合并的字段复核警告。
    """
    try:
        if not files:
            raise ApiError("未选择要识别的图片/PDF 文件")
        # 延迟导入：管线模块较重（OCR/LLM 惰性加载在内部完成）
        from scan_recognition.pipeline import ScanRecognitionPipeline

        cfg = Config.load()
        # 指定检测项目时带上该项目的列定义，供结构化与匹配使用
        columns = list(ITEM_COLUMNS.get(detection_item, [])) \
            if detection_item else []
        sub_item = detection_item or None

        tmp_dir = tempfile.mkdtemp(prefix="scan_run_")
        pipeline = ScanRecognitionPipeline(cfg=cfg)
        results = []
        all_warnings = []
        for f in files:
            name = os.path.basename(f.filename or "未命名图片")
            path = os.path.join(tmp_dir, name)
            with open(path, "wb") as out:
                out.write(await f.read())
            try:
                res = pipeline.recognize(path, detection_item or None,
                                         sub_item, columns)
            except Exception as e:  # noqa: BLE001 —— 单文件失败不中断批次
                results.append({"filename": name, "error": str(e),
                                "rows": [], "field_warnings": []})
                continue
            warnings = res.get("field_warnings", [])
            all_warnings.extend(warnings)
            results.append({
                "filename": name,
                "doc_id": res.get("doc_id"),
                "detection_item": res.get("detection_item"),
                "sub_item": res.get("sub_item"),
                "columns": res.get("columns", []),
                "rows": res.get("rows", []),
                "structured": res.get("structured", []),
                "normalized": res.get("normalized", []),
                "field_warnings": warnings,
                "classification": res.get("classification"),
                "repair": res.get("repair"),
                "ocr_stats": res.get("ocr_stats"),
            })
        ok_count = sum(1 for r in results if not r.get("error"))
        pipeline.close()
        return ok({"files": results, "field_warnings": all_warnings},
                  f"识别完成：成功 {ok_count}/{len(results)} 个文件，"
                  f"共 {len(all_warnings)} 处需人工复核")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"扫描识别失败：{e}"}


def _resolve_project_file(raw: str) -> str:
    """把相对路径按项目根解析，并限制在项目目录内。"""
    text = str(raw or "").strip()
    if not text:
        raise ApiError("filepath 不能为空")
    path = text if os.path.isabs(text) else os.path.join(ROOT, text)
    path = os.path.realpath(path)
    root = os.path.realpath(ROOT)
    try:
        inside = os.path.commonpath([path, root]) == root
    except ValueError:
        inside = False
    if not inside:
        raise ApiError("只能读取项目目录内的文件")
    if not os.path.isfile(path):
        raise ApiError("文件不存在：%s" % text, 404)
    return path


class OcrTextBody(BaseModel):
    filepath: str
    max_chars: int = 20000


@router.post("/scan/ocr-text")
def scan_ocr_text(body: OcrTextBody):
    """对单张图片/扫描 PDF 执行 OCR，返回文本供文本模型阅读。

    对话上传图片时前端调用这里，把 OCR 文本和附件路径一起写入输入框；
    这样即使当前是纯文本模型，也能理解原始记录内容，不必依赖视觉模型。
    """
    try:
        path = _resolve_project_file(body.filepath)
        from report_generator.scan_recognition.ocr import ocr_file_detail
        detail = ocr_file_detail(path)
        text = str(detail.get("text") or "")
        limit = max(1000, min(int(body.max_chars or 20000), 40000))
        truncated = len(text) > limit
        return ok({
            "filepath": path,
            "text": text[:limit],
            "truncated": truncated,
            "n_cells": detail.get("n_cells", 0),
            "n_rows": detail.get("n_rows", 0),
            "low_confidence": detail.get("low_confidence", []),
            "suspect_numbers": detail.get("suspect_numbers", []),
        }, "OCR 完成：%d 个文本框，%d 行" % (
            int(detail.get("n_cells") or 0), int(detail.get("n_rows") or 0)))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"OCR 失败：{e}"}


class SubmitBody(BaseModel):
    filepath: str
    detection_item: str = ""


@router.post("/scan/submit")
def scan_submit(body: SubmitBody):
    """提交一个异步识别作业（本机路径，秒回作业 id），用 /scan/job/{id} 轮询。"""
    try:
        path = _resolve_project_file(body.filepath)
        view = scan_jobs.submit(path, body.detection_item or None)
        return ok(view, "识别作业已提交：%s" % view["id"])
    except ApiError:
        raise
    except scan_jobs.ScanJobError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"提交识别作业失败：{e}"}


@router.get("/scan/job/{job_id}")
def scan_job(job_id: str):
    """读取识别作业状态；done 时带 rows / columns / 复核警告，可直接 scan_fill。"""
    try:
        view = scan_jobs.status(job_id)
        if view is None:
            raise ApiError(
                "识别作业不存在或已过期：%s（后端重启会中断进行中的识别，请重新提交）" % job_id,
                404)
        return ok(view, "作业状态：%s" % view["status"])
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取识别作业失败：{e}"}


@router.get("/scan/jobs")
def scan_jobs_list(limit: int = 20):
    """最近的识别作业（不含识别结果，避免响应过大）。"""
    try:
        jobs = scan_jobs.list_jobs(limit)
        return ok({"jobs": jobs, "count": len(jobs)},
                  "共 %d 个识别作业" % len(jobs))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取识别作业失败：{e}"}


@router.post("/scan/fill")
def scan_fill(body: FillBody):
    """把识别结果回填到目标表（等价桌面版 _fill_into_sheet 纯数据逻辑）。

    records 为匹配列后的对齐行 [[单元格,...], ...]，逐行追加到目标表末尾。
    """
    try:
        state = get_state()
        key = body.sheet_key
        if not key:
            raise ApiError("缺少 sheet_key")
        records = [["" if v is None else v for v in row]
                   for row in (body.records or []) if isinstance(row, list)]
        if not records:
            raise ApiError("没有可回填的识别数据行")

        if key not in state.sheet_data:
            # 目标表不存在：按检测项目列定义创建空表并计入勾选项
            controller = get_controller()
            base, _comp = controller.parse_sheet_key(key)
            base = controller.resolve_item_name(base)
            columns = ITEM_COLUMNS.get(base, ITEM_COLUMNS.get(key, []))
            state.sheet_data[key] = [list(r) for r in records]
            state.merges.setdefault(key, [])
            state.merge_formats.setdefault(key, {})
            if key not in state.checked_items:
                state.checked_items.append(key)
            message = (f"已新建工作表“{key}”并回填 {len(records)} 行识别数据")
        else:
            target = state.sheet_data[key]
            width = max((len(r) for r in target), default=0)
            for row in records:
                row = list(row) + [""] * max(0, width - len(row))
                target.append(row[:width] if width else row)
            message = f"已回填 {len(records)} 行识别数据到“{key}”"
        return ok({"sheet_key": key, "rows": state.sheet_data[key],
                   "total_rows": len(state.sheet_data[key])}, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"回填识别数据失败：{e}"}




class CommitBody(BaseModel):
    job_id: str
    sheet_key: str
    append: bool = False
    params: Optional[dict] = None
    auto_assess: bool = True


@router.get("/scan/targets")
def scan_targets(detection_item: str = ""):
    """按扫描识别出的检测项目查询可写入的采集表（含构件与参数要求）。

    只返回候选，不创建、不勾选任何工作表；前端确认后再调用 /scan/commit。
    """
    try:
        plan = ingest.scan_targets(detection_item)
        return ok(plan, "已查询检测项目：%s" % plan.get("detection_item", ""))
    except ingest.IngestError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"查询检测项目失败：{e}"}


@router.post("/scan/commit")
def scan_commit(body: CommitBody):
    """把已完成的扫描作业写入指定采集表，只勾选该表并立即评定。"""
    try:
        result = ingest.commit_scan_job(
            body.job_id, body.sheet_key, append=body.append,
            params=body.params, auto_assess=body.auto_assess)
        message = "已写入 %d 行到“%s”" % (result.get("imported", 0),
                                          result.get("sheet_key", ""))
        if result.get("assessment"):
            message += "，已完成评定"
        return ok(result, message)
    except ingest.IngestError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"写入识别数据失败：{e}"}


@router.get("/scan/history")
def scan_history():
    """识别历史记录（与桌面版同一识别数据库）。"""
    try:
        cfg = Config.load()
        db = ScanDatabase(db_path=cfg.database_path, cfg=cfg)
        try:
            docs = db.list_documents()
        finally:
            db.close()
        data = [{
            "id": d.get("id"),
            "detection_item": d.get("detection_item"),
            "sub_item": d.get("sub_item"),
            "source_path": d.get("source_path"),
            "stored_path": d.get("stored_path"),
            "created_at": d.get("created_at"),
            "status": d.get("status"),
        } for d in docs]
        return ok(data, f"共 {len(data)} 条识别记录")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取识别历史失败：{e}"}


@router.get("/scan/vision_models")
def scan_vision_models():
    """Ollama 可用视觉（多模态）模型列表（复用 scan_recognition.llm）。"""
    try:
        cfg = Config.load()
        llm_cfg = cfg.llm or {}
        base_url = (llm_cfg.get("ollama_base_url") or ""
                    or llm_cfg.get("base_url") or "")
        models = scan_llm.list_ollama_vision_models(base_url)
        message = f"共 {len(models)} 个视觉模型" if models \
            else "未发现可用视觉模型（请确认 Ollama 服务与多模态模型）"
        return ok({"models": models, "base_url": base_url}, message)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"获取视觉模型列表失败：{e}"}
