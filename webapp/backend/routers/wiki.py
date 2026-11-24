# -*- coding: utf-8 -*-
"""LLM Wiki 知识库路由：浏览/检索/编辑/导入，以及 Harness 引用上下文。"""
import json
import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from typing import List, Optional

from deps import ApiError, get_wiki_store, ok

router = APIRouter(tags=["wiki"])

SUPPORTED_SUFFIX = (".md", ".markdown", ".txt", ".docx")


class PageBody(BaseModel):
    id: Optional[str] = None
    title: str = ""
    category: str = "未分类"
    summary: str = ""
    content: str = ""
    tags: List[str] = []
    detection_items: List[str] = []
    source: str = ""


class SearchBody(BaseModel):
    question: str = ""
    top_k: int = 3
    detection_items: List[str] = []


class ContextBody(BaseModel):
    question: str = ""
    top_k: int = 3
    detection_items: List[str] = []


def _fail(prefix, e):
    if isinstance(e, ApiError):
        raise e
    raise ApiError("%s：%s" % (prefix, e))


@router.get("/wiki/status")
def wiki_status():
    try:
        return ok(get_wiki_store().status(), "知识库状态读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取知识库状态失败：{e}"}


@router.get("/wiki/categories")
def wiki_categories():
    try:
        return ok(get_wiki_store().list_categories(), "知识库分类读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取知识库分类失败：{e}"}


@router.get("/wiki/pages")
def wiki_pages(category: str = "", query: str = "",
               limit: int = 100, offset: int = 0):
    try:
        items, total = get_wiki_store().list_pages(
            category=category, query=query, limit=limit, offset=offset)
        return ok({"items": items, "total": total}, "知识库页面列表读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取知识库页面失败：{e}"}


@router.get("/wiki/pages/{page_id}")
def wiki_page(page_id: str):
    try:
        page = get_wiki_store().get_page(page_id)
        if not page:
            raise ApiError(f"知识库页面不存在：{page_id}", 404)
        return ok(page, "知识库页面读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取知识库页面失败：{e}"}


@router.post("/wiki/pages")
def wiki_save_page(body: PageBody):
    try:
        page = get_wiki_store().save_page(
            page_id=body.id, title=body.title, category=body.category,
            summary=body.summary, content=body.content, tags=body.tags,
            detection_items=body.detection_items, source=body.source)
        return ok(page, "知识库页面已保存")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail("保存知识库页面失败", e)


@router.delete("/wiki/pages/{page_id}")
def wiki_delete_page(page_id: str):
    try:
        if not get_wiki_store().delete_page(page_id):
            raise ApiError(f"知识库页面不存在：{page_id}", 404)
        return ok(True, "知识库页面已删除")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail("删除知识库页面失败", e)


@router.post("/wiki/search")
def wiki_search(body: SearchBody):
    try:
        return ok(get_wiki_store().search(
            body.question, top_k=body.top_k,
            detection_items=body.detection_items), "知识库检索完成")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"知识库检索失败：{e}"}


@router.post("/wiki/context")
def wiki_context(body: ContextBody):
    try:
        return ok(get_wiki_store().build_context(
            body.question, top_k=body.top_k,
            detection_items=body.detection_items), "知识库引用上下文生成成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"生成知识库上下文失败：{e}"}


def _parse_items(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:  # noqa: BLE001
        pass
    return [x.strip() for x in str(raw).split(",") if x.strip()]


@router.post("/wiki/import")
async def wiki_import(files: List[UploadFile] = File(...),
                      category: str = Form("未分类"),
                      detection_items: str = Form("[]")):
    tmp_dir = tempfile.mkdtemp(prefix="wiki_import_")
    try:
        if not files:
            raise ApiError("未选择要导入的知识文件")
        items = _parse_items(detection_items)
        imported, skipped, errors = [], [], []
        for upload in files:
            name = os.path.basename(upload.filename or "")
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in SUPPORTED_SUFFIX:
                skipped.append(name)
                continue
            path = os.path.join(tmp_dir, name)
            with open(path, "wb") as out:
                out.write(await upload.read())
            try:
                page = get_wiki_store().import_file(
                    path, category=category, detection_items=items)
                imported.append({"id": page.get("id"),
                                 "title": page.get("title"),
                                 "category": page.get("category")})
            except Exception as e:  # noqa: BLE001
                errors.append("%s：%s" % (name, e))
        if not imported and not skipped and not errors:
            raise ApiError("没有可导入的文件")
        return ok({
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total": len(imported),
        }, "知识库导入完成：%d 个页面" % len(imported))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        _fail("导入知识库文件失败", e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
