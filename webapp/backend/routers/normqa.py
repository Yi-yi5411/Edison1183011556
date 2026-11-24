# -*- coding: utf-8 -*-
"""规范问答路由：规范库状态/导入/检索/AI 解释。

复用 utils.norm_qa（SQLite FTS5 检索 + 本地 Ollama 解释）。
"""

import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from typing import List

from deps import ok, ApiError, NormQueryEngine, db_status, import_files, \
    explain_clauses

router = APIRouter(tags=["normqa"])

SUPPORTED_SUFFIX = (".md", ".markdown", ".txt", ".docx")


class QueryBody(BaseModel):
    question: str
    detection_items: List[str] = []


class ExplainBody(BaseModel):
    question: str
    clauses: list = []


@router.get("/normqa/status")
def normqa_status():
    """规范库状态：条数与规范清单（复用 norm_qa.store.db_status）。"""
    try:
        info = db_status()
        return ok({"total": info["total"], "codes": info["codes"],
                   "db_path": info["db_path"], "exists": info["exists"]},
                  "规范库状态读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取规范库状态失败：{e}"}


@router.post("/normqa/import")
async def normqa_import(files: List[UploadFile] = File(...),
                        mode: str = Form("append")):
    """导入规范文件（multipart 多选，mode=append|rebuild）。"""
    try:
        if mode not in ("append", "rebuild"):
            raise ApiError("mode 只支持 append（增量）或 rebuild（全量重建）")
        if not files:
            raise ApiError("未选择要导入的规范文件")
        tmp_dir = tempfile.mkdtemp(prefix="norm_import_")
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
        if skipped:
            raise ApiError(
                "不支持的文件格式：" + "、".join(skipped)
                + "（支持 md/markdown/txt/docx）")
        result = import_files(paths, mode=mode)
        message = f"导入完成：新增 {result['imported']} 条条文，库内共 {result['total']} 条"
        if result["imported"] == 0:
            message = "未解析出任何条文（请检查文件标题格式）"
        return ok(result, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"导入规范文件失败：{e}"}


@router.post("/normqa/query")
def normqa_query(body: QueryBody):
    """规范条文检索（条号精确/自然语言/术语候选，复用 NormQueryEngine）。"""
    try:
        result = NormQueryEngine().query(body.question, body.detection_items)
        types = {"exact": "条号精确命中", "search": "关键词检索命中",
                 "candidates": "未命中，以下是术语候选", "empty": "未检索到相关条文"}
        message = types.get(result.get("type"), "检索完成")
        if result.get("filtered_out"):
            message += "（该项目依据规范内未命中，已放开范围检索）"
        return ok(result, message)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"规范检索失败：{e}"}


@router.get("/normqa/coverage")
def normqa_coverage():
    """规范库覆盖度：每本规范多少条、每个检测项目有几条可依、哪些项目还缺。"""
    try:
        from utils.norm_qa.catalog import coverage
        return ok(coverage(), "规范库覆盖度读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取规范库覆盖度失败：{e}"}


@router.post("/normqa/explain")
def normqa_explain(body: ExplainBody):
    """基于命中的条文原文生成中文解释（本地 Ollama，同步阻塞）。"""
    try:
        if not body.clauses:
            raise ApiError("请先检索并命中条文后再请求解释")
        answer = explain_clauses(body.question, body.clauses)
        if not answer:
            raise ApiError(
                "未能生成解释：Ollama 服务不可用或未配置可用模型", 502)
        return ok({"answer": answer}, "解释生成成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"生成解释失败：{e}"}
