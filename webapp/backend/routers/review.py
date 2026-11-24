# -*- coding: utf-8 -*-
"""批量审查路由：检测报告文件批量审查与审查意见表导出。

复用 utils.norm_qa.batch_review（Ollama 逐块提取候选 + 规范依据匹配），
同步阻塞执行（LLM 调用内部已有 timeout）。
"""

import os
import tempfile

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List

from deps import ok, ApiError, run_batch_review, export_review_docx

router = APIRouter(tags=["review"])

SUPPORTED_SUFFIX = (".docx", ".pdf", ".txt")


class ExportBody(BaseModel):
    candidates: list = []
    project_name: str = ""


@router.post("/review/run")
async def review_run(files: List[UploadFile] = File(...)):
    """批量审查（multipart 文件多选 docx/pdf/txt），同步执行返回候选意见。"""
    try:
        if not files:
            raise ApiError("未选择要审查的文件")
        tmp_dir = tempfile.mkdtemp(prefix="review_run_")
        paths = []
        skipped = []
        for f in files:
            name = os.path.basename(f.filename or "")
            if not name.lower().endswith(SUPPORTED_SUFFIX):
                skipped.append(name)
                continue
            path = os.path.join(tmp_dir, name)
            with open(path, "wb") as out:
                out.write(await f.read())
            paths.append(path)
        if not paths:
            raise ApiError(
                "没有可审查的文件（支持 docx/pdf/txt），跳过：" +
                "、".join(skipped) if skipped else "没有可审查的文件（支持 docx/pdf/txt）")
        result = run_batch_review(paths)
        message = (f"审查完成：{len(result.get('files', []))} 个文件，"
                   f"{result.get('chunks', 0)} 个片段，"
                   f"提取 {len(result.get('candidates', []))} 条候选意见")
        return ok(result, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"批量审查失败：{e}"}


@router.post("/review/export")
def review_export(body: ExportBody):
    """导出审查意见表 docx 下载（复用 export_review_docx）。"""
    try:
        candidates = [c for c in (body.candidates or []) if isinstance(c, dict)]
        if not candidates:
            raise ApiError("没有可导出的审查意见（候选列表为空）")
        out_dir = tempfile.mkdtemp(prefix="review_export_")
        filepath = os.path.join(out_dir, "检测报告审查意见表.docx")
        export_review_docx(candidates, filepath, body.project_name)
        return FileResponse(
            filepath, filename="检测报告审查意见表.docx",
            media_type="application/vnd.openxmlformats-officedocument"
                       ".wordprocessingml.document")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "data": None,
                             "message": f"导出审查意见表失败：{e}"}, status_code=500)
