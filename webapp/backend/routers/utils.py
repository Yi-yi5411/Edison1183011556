# -*- coding: utf-8 -*-
"""通用工具路由：打开文件位置（Windows 资源管理器定位产物文件）。"""

import os
import subprocess

from fastapi import APIRouter
from pydantic import BaseModel

from deps import ApiError, ok

router = APIRouter(tags=["utils"])


class RevealBody(BaseModel):
    filepath: str


@router.post("/utils/reveal")
def reveal(body: RevealBody):
    """在资源管理器中定位文件（审查意见表/导出 Excel/扫描结果等产物通用）。"""
    try:
        path = os.path.abspath(body.filepath)
        if not os.path.isfile(path):
            raise ApiError(f"文件不存在：{path}")
        subprocess.Popen(["explorer", "/select,", path])
        return ok(path, "已在资源管理器中定位文件")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"打开文件位置失败：{e}"}
