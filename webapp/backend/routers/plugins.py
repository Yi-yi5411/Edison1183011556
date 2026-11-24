# -*- coding: utf-8 -*-
"""检测项目（插件）路由：插件发现与列定义查询。"""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from deps import get_plugin_manager, ok, plugin_payload

try:  # manifest 可选：老部署没有 structural_items 时退回 /plugins
    from structural_items import describe_item as _describe_item
except ImportError:  # noqa: BLE001
    _describe_item = None

router = APIRouter(tags=["plugins"])


@router.get("/plugins")
def list_plugins():
    """列出全部检测项目插件及其列定义/计算规则（复用 PluginManager）。"""
    try:
        pm = get_plugin_manager()
        data = [plugin_payload(p, source=pm.source_of(p.plugin_id))
                for p in pm.all_plugins()]
        return ok(data, "检测项目加载成功")
    except Exception as e:  # noqa: BLE001 —— 统一兜底返回中文消息
        return {"ok": False, "data": None, "message": f"加载检测项目失败：{e}"}


class ExternalSourceBody(BaseModel):
    roots: list = []


@router.get("/plugins/external")
def external_plugins():
    """外部插件根目录与加载状态。"""
    try:
        pm = get_plugin_manager()
        return ok(pm.external_status(), "外部插件状态读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取外部插件失败：{e}"}


@router.post("/plugins/external/reload")
def reload_external_plugins():
    """重新发现内置 + 外部插件（不重启后端）。"""
    try:
        pm = get_plugin_manager()
        pm.reload()
        return ok(pm.external_status(), "插件已重新加载")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"重新加载插件失败：{e}"}


@router.put("/plugins/external/sources")
def save_external_sources(body: ExternalSourceBody):
    """保存外部插件根目录并立即重新加载。"""
    try:
        from core.external_plugin_loader import save_sources
        roots = []
        for root in body.roots or []:
            path = os.path.abspath(os.path.expanduser(str(root).strip()))
            if not path:
                continue
            os.makedirs(path, exist_ok=True)
            roots.append(path)
        save_sources(roots)
        pm = get_plugin_manager()
        pm.reload()
        return ok(pm.external_status(), "外部插件目录已保存并重新加载")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存外部插件目录失败：{e}"}


@router.get("/plugins/summary")
def plugins_summary():
    """检测项目树 + manifest 摘要：采集参数、评定规则、技能名、原始记录模板。

    给智能体「一次调用看懂全部项目」用；没有 manifest 时字段留空，不影响树结构。
    """
    try:
        pm = get_plugin_manager()
        items = []
        for plugin in pm.all_plugins():
            for item_name, comps in (plugin.tree_entries() or {}).items():
                contract = {}
                if _describe_item is not None:
                    try:
                        contract = _describe_item(item_name) or {}
                    except Exception:  # noqa: BLE001
                        contract = {}
                collect = contract.get("collect") or {}
                assessment = contract.get("assessment") or {}
                skill = contract.get("skill") or {}
                params = collect.get("params") or []
                components = list(comps or [])
                sheet_keys = ([(item_name + "（%s）" % c) if c else item_name
                               for c in components] or [item_name])
                items.append({
                    "structure_type": plugin.structure_type,
                    "plugin_name": plugin.display_name,
                    "plugin_id": plugin.plugin_id,
                    "item": item_name,
                    "components": components,
                    "sheet_keys": sheet_keys,
                    "column_count": len(contract.get("columns") or []),
                    "param_count": len(params),
                    "param_keys": [p.get("key") for p in params],
                    "param_fields": params,
                    "requires_setup": bool(params),
                    "assessment_spec": assessment.get("spec") or "",
                    "skill": ("structural-" + str(skill.get("slug")))
                             if skill.get("slug") else "",
                    "original_template": (contract.get("original_record")
                                          or {}).get("template") or "",
                    "equipment": list(contract.get("equipment") or []),
                })
        return ok({"items": items, "count": len(items),
                   "manifest": bool(_describe_item)},
                  "检测项目摘要加载成功：%d 个检测项目" % len(items))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"加载检测项目摘要失败：{e}"}
