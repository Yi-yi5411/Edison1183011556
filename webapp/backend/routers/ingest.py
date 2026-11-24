# -*- coding: utf-8 -*-
"""统一采集路由：识别文件属于哪个检测项目，并按格式导入工作表。

- GET  /api/ingest/recognize?filepath=&sheet_name=  → 只读识别（不改工程）
- POST /api/ingest/import {filepath, sheet_key, sheet_name?, append?} → 写入并重算

支持 .xlsx/.xlsm/.csv/.docx（直接解析）与 .doc（先转 docx）；
.pdf/图片只识别为 scan 类型，提示走扫描流水线。
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from deps import ApiError, ok
import ingest

router = APIRouter(tags=["ingest"])


class ImportBody(BaseModel):
    filepath: str
    sheet_key: str
    sheet_name: str = ""
    append: bool = False
    auto_assess: bool = True
    params: Optional[dict] = None


@router.get("/ingest/recognize")
def recognize_file(filepath: str = "", sheet_name: str = ""):
    try:
        return ok(ingest.classify_file(filepath, sheet_name or None),
                  "文件识别完成")
    except ingest.IngestError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"文件识别失败：{e}"}


@router.post("/ingest/import")
def import_file(body: ImportBody):
    try:
        if not str(body.filepath or "").strip():
            raise ApiError("filepath 不能为空")
        if not str(body.sheet_key or "").strip():
            raise ApiError("sheet_key 不能为空")
        result = ingest.import_into_sheet(
            body.filepath, body.sheet_key,
            sheet_name=body.sheet_name or None, append=body.append,
            auto_assess=body.auto_assess, params=body.params)
        message = "已导入 %d 行到 %s" % (result["imported"], body.sheet_key)
        if result.get("assessment") is not None:
            message += "，已完成评定" if result.get("ready") else "，评定待补录"
        return ok(result, message)
    except ingest.IngestError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"导入文件失败：{e}"}
