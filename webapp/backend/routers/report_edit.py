# -*- coding: utf-8 -*-
"""报告修改路由：加载 .docx 块、保存段落/单元格修改、查找替换、下载。"""
import os
from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from deps import (ApiError, load_report_document, ok, replace_report_text,
                  save_report_document)
from utils.report_edit import _ensure_docx_path

router = APIRouter(tags=["report-edit"])

DOCX_MEDIA = ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document")


class SaveBody(BaseModel):
    filepath: str
    paragraphs: List[dict] = []
    cells: List[dict] = []
    output_path: Optional[str] = None
    overwrite: bool = False


class ReplaceBody(BaseModel):
    filepath: str
    find: str
    replace: str = ""
    output_path: Optional[str] = None
    overwrite: bool = False


@router.get("/report/document")
def get_report_document(filepath: str = ""):
    """加载报告正文块（段落 + 表格）。"""
    try:
        if not str(filepath or "").strip():
            raise ApiError("缺少报告文件路径")
        return ok(load_report_document(filepath), "报告加载成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"加载报告失败：{e}"}


@router.post("/report/document/save")
def save_report(body: SaveBody):
    """保存段落/表格修改（默认另存新文件）。"""
    try:
        result = save_report_document(
            body.filepath, body.paragraphs, body.cells,
            output_path=body.output_path, overwrite=body.overwrite)
        return ok(result, result.get("message") or "报告已保存")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存报告失败：{e}"}


@router.post("/report/document/replace")
def replace_report(body: ReplaceBody):
    """报告全文查找替换（正文 + 表格）。"""
    try:
        result = replace_report_text(
            body.filepath, body.find, body.replace,
            output_path=body.output_path, overwrite=body.overwrite)
        return ok(result, result.get("message") or "替换完成")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"替换失败：{e}"}


@router.get("/report/document/download")
def download_report_document(filepath: str = ""):
    """下载当前报告 .docx。"""
    try:
        path = _ensure_docx_path(filepath)
        return FileResponse(path, filename=os.path.basename(path),
                            media_type=DOCX_MEDIA)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"下载报告失败：{e}"}
