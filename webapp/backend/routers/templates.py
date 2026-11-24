# -*- coding: utf-8 -*-
"""模板库路由：报告模板包导入/导出/默认，原始记录模板导入/下载/预览/默认。"""
import json
import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List

from deps import (ApiError, get_controller, get_template_library, ok)
from utils.template_library import TemplateError

router = APIRouter(tags=["templates"])

DOCX_MEDIA = ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document")
DOC_MEDIA = "application/msword"


def _fail(e, prefix):
    """把模板库异常转成中文 API 错误。"""
    if isinstance(e, ApiError):
        raise e
    if isinstance(e, TemplateError):
        raise ApiError(str(e))
    raise ApiError("%s：%s" % (prefix, e))


def _file_suffix(filename):
    return os.path.splitext(str(filename or ""))[1].lower()


# ═══════════════════════════════════════════════════════════
#  报告模板
# ═══════════════════════════════════════════════════════════
@router.get("/templates/report")
def list_report_templates():
    try:
        lib = get_template_library()
        return ok(lib.list_report_templates(), "报告模板列表读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取报告模板失败：{e}"}


@router.post("/templates/report/upload")
async def upload_report_template(file: UploadFile = File(...)):
    tmp_dir = tempfile.mkdtemp(prefix="report_tpl_")
    try:
        name = os.path.basename(file.filename or "template.zip")
        if not name.lower().endswith(".zip"):
            raise ApiError("报告模板包必须是 .zip 文件")
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as out:
            out.write(await file.read())
        lib = get_template_library()
        view, warnings = lib.import_report_package(path)
        return ok({"template": view, "warnings": warnings},
                  "报告模板包导入成功：%s" % view.get("name"))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(e, "导入报告模板失败")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/templates/report/{template_id}")
def get_report_template(template_id: str):
    try:
        lib = get_template_library()
        view = lib.get_report_template(template_id)
        if not view:
            raise ApiError(f"报告模板不存在：{template_id}")
        return ok(view, "报告模板详情读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取报告模板失败：{e}"}


@router.post("/templates/report/{template_id}/default")
def set_default_report_template(template_id: str):
    try:
        lib = get_template_library()
        return ok(lib.set_default_report_template(template_id), "已设为默认报告模板")
    except Exception as e:  # noqa: BLE001
        _fail(e, "设置默认报告模板失败")


@router.delete("/templates/report/{template_id}")
def delete_report_template(template_id: str):
    try:
        lib = get_template_library()
        lib.delete_report_template(template_id)
        return ok(True, "报告模板已删除")
    except Exception as e:  # noqa: BLE001
        _fail(e, "删除报告模板失败")


@router.get("/templates/report/{template_id}/export")
def export_report_template(template_id: str):
    try:
        lib = get_template_library()
        view = lib.get_report_template(template_id)
        if not view:
            raise ApiError(f"报告模板不存在：{template_id}")
        path = lib.export_report_template(template_id)
        return FileResponse(
            path, filename="%s.zip" % (view.get("name") or "报告模板"),
            media_type="application/zip")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(e, "导出报告模板包失败")


# ═══════════════════════════════════════════════════════════
#  原始记录模板
# ═══════════════════════════════════════════════════════════
@router.get("/templates/original")
def list_original_templates():
    try:
        lib = get_template_library()
        return ok({
            "templates": lib.list_original_templates(),
            "defaults": lib.defaults_map(),
        }, "原始记录模板列表读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取原始记录模板失败：{e}"}


@router.get("/templates/original/defaults")
def list_original_defaults():
    try:
        lib = get_template_library()
        return ok(lib.defaults_map(), "原始记录默认模板读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取默认模板失败：{e}"}


@router.post("/templates/original/upload")
async def upload_original_template(
        file: UploadFile = File(...),
        name: str = Form(""),
        code: str = Form(""),
        detection_items: str = Form("[]"),
        set_default: str = Form("false")):
    tmp_dir = tempfile.mkdtemp(prefix="original_tpl_")
    try:
        filename = os.path.basename(file.filename or "template.docx")
        suffix = _file_suffix(filename)
        if suffix not in (".docx", ".doc"):
            raise ApiError("原始记录模板只支持 .docx / .doc 文件")
        path = os.path.join(tmp_dir, "template" + suffix)
        with open(path, "wb") as out:
            out.write(await file.read())
        if suffix == ".docx":
            try:
                from docx import Document
                Document(path)
            except Exception as e:  # noqa: BLE001
                raise ApiError("上传文件不是有效的 .docx：%s" % e)
        items = []
        try:
            parsed = json.loads(detection_items) if detection_items else []
            if isinstance(parsed, list):
                items = [str(x) for x in parsed if str(x).strip()]
        except Exception:
            items = [x.strip() for x in str(detection_items).split(",") if x.strip()]
        lib = get_template_library()
        view = lib.import_original_template(
            path, name or os.path.splitext(filename)[0], code, items,
            set_default=str(set_default).lower() in ("1", "true", "yes"))
        return ok(view, "原始记录模板导入成功：%s" % view.get("name"))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(e, "导入原始记录模板失败")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class OriginalDefaultsBody(BaseModel):
    items: List[str] = []


@router.post("/templates/original/{template_id}/default")
def set_original_defaults(template_id: str, body: OriginalDefaultsBody):
    try:
        lib = get_template_library()
        return ok(lib.set_original_defaults(template_id, body.items),
                  "原始记录默认模板已保存")
    except Exception as e:  # noqa: BLE001
        _fail(e, "设置原始记录默认模板失败")


@router.delete("/templates/original/{template_id}")
def delete_original_template(template_id: str):
    try:
        lib = get_template_library()
        lib.delete_original_template(template_id)
        return ok(True, "原始记录模板已删除")
    except Exception as e:  # noqa: BLE001
        _fail(e, "删除原始记录模板失败")


@router.get("/templates/original/{template_id}/preview")
def preview_original_template(template_id: str):
    try:
        lib = get_template_library()
        return ok(lib.preview_original_template(template_id), "模板预览读取成功")
    except Exception as e:  # noqa: BLE001
        _fail(e, "读取模板预览失败")


@router.get("/templates/original/{template_id}/download")
def download_original_template(template_id: str):
    try:
        lib = get_template_library()
        view = lib.get_original_template(template_id)
        if not view:
            raise ApiError(f"原始记录模板不存在：{template_id}")
        name = view.get("name") or "原始记录模板"
        engine = view.get("engine") or "native_docx"
        if engine == "native_docx":
            controller = get_controller()
            columns = []
            items = view.get("detection_items") or []
            if items:
                columns = controller.get_columns(items[0])
            if not columns:
                columns = ["检测项目", "检测数据"]
            path, _warnings = lib.blank_original_template(
                template_id, columns=columns, info={})
            return FileResponse(path, filename="%s_空白.docx" % name,
                                media_type=DOCX_MEDIA)
        path = lib.get_original_file_path(template_id)
        suffix = os.path.splitext(path)[1].lower()
        if suffix == ".doc":
            return FileResponse(path, filename="%s.doc" % name,
                                media_type=DOC_MEDIA)
        return FileResponse(path, filename="%s.docx" % name,
                            media_type=DOCX_MEDIA)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(e, "下载原始记录模板失败")


@router.get("/templates/original/{template_id}/reference")
def download_reference_doc(template_id: str):
    try:
        lib = get_template_library()
        path = lib.reference_doc_path(template_id)
        return FileResponse(path, filename=os.path.basename(path),
                            media_type=DOC_MEDIA)
    except Exception as e:  # noqa: BLE001
        _fail(e, "下载官方参考模板失败")
