# -*- coding: utf-8 -*-
"""配置路由：读取/保存扫描识别配置（scan_recognition.config.Config）。"""

import copy

from fastapi import APIRouter
from pydantic import BaseModel

from deps import ok, ApiError, Config

router = APIRouter(tags=["config"])

_SECRET_KEYS = ("api_key", "password")


def _mask_secrets(data):
    """GET 配置时脱敏，避免把 API Key 暴露给前端页面。"""
    out = copy.deepcopy(data or {})
    for section in out.values():
        if not isinstance(section, dict):
            continue
        for key in list(section.keys()):
            if key in _SECRET_KEYS and section.get(key):
                section[key] = "***"
    return out


class SaveBody(BaseModel):
    section: str
    values: dict


@router.get("/config")
def get_config():
    """当前生效配置（默认值 + 配置文件覆盖 + 环境变量覆盖；密钥脱敏）。"""
    try:
        data = Config.load().data
        return ok(_mask_secrets(data), "配置读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取配置失败：{e}"}


@router.put("/config")
def put_config(body: SaveBody):
    """保存配置节（llm/ocr/report_agent/matcher 等已存在的配置节）。"""
    try:
        cfg = Config.load()
        section = body.section
        if section not in cfg.data:
            raise ApiError(f"未知配置节：{section}（可用："
                           + "、".join(cfg.data.keys()) + "）")
        if not isinstance(body.values, dict):
            raise ApiError("values 必须为对象")
        # 深合并进当前节后整体持久化；密钥字段传 *** 时保留原值
        target = cfg.data[section]
        for k, v in body.values.items():
            if k in _SECRET_KEYS and v == "***":
                continue
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                target[k].update(v)
            else:
                target[k] = v
        cfg.save()
        return ok(_mask_secrets(cfg.data), f"配置节“{section}”已保存")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存配置失败：{e}"}
