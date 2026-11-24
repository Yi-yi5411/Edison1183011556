# -*- coding: utf-8 -*-
"""检测流程总览：把项目、数据采集、评定、设备、报告串成一条可执行流程。"""
import os

from fastapi import APIRouter

from deps import get_state, ok, get_report_gen_dir, get_template_library
from utils.equipment_store import list_equipment

router = APIRouter(tags=["workflow"])


def _has_value(row):
    if isinstance(row, (list, tuple)):
        return any(str(v or "").strip() for v in row)
    if isinstance(row, dict):
        return any(str(v or "").strip() for v in row.values())
    return bool(str(row or "").strip())


@router.get("/workflow/status")
def workflow_status():
    state = get_state()
    checked = list(state.checked_items or [])
    filled = 0
    total_rows = 0
    for key in checked:
        rows = [r for r in (state.sheet_data.get(key) or []) if _has_value(r)]
        total_rows += len(rows)
        if rows:
            filled += 1
    assessed = sum(
        1 for key in checked
        if (state.assessment_results.get(key) or {}).get("ok")
    )
    equipment = list_equipment(selected_only=True, limit=200)
    try:
        lib = get_template_library()
        template_id = ((state.template_selection or {}).get(
            "report_template_id") or "").strip()
        if not template_id:
            template_id = lib.default_report_template_id() or ""
        template = lib.get_report_template(template_id) if template_id else None
        template_name = (template.get("name") if template else "") or "系统默认模板"
    except Exception:
        template_name = "系统默认模板"

    project_name = state.project_name or "未命名项目"
    project_done = bool(project_name and project_name != "未命名项目")
    collect_done = bool(checked) and filled >= len(checked)
    assess_done = bool(checked) and assessed >= len(checked)
    equipment_done = bool(equipment)
    template_done = True
    report_ready = bool(filled)
    done_count = sum([project_done, collect_done, assess_done,
                      equipment_done, template_done, report_ready])

    steps = [
        {"key": "project", "title": "项目信息", "status": "done" if project_done else "pending",
         "detail": project_name, "route": "/project"},
        {"key": "collect", "title": "数据采集", "status": "done" if collect_done else ("progress" if filled else "pending"),
         "detail": f"{filled}/{len(checked)} 项已录入，共 {total_rows} 行", "route": "/project"},
        {"key": "assess", "title": "检测评定", "status": "done" if assess_done else ("progress" if assessed else "pending"),
         "detail": f"{assessed}/{len(checked)} 项已评定", "route": "/project"},
        {"key": "equipment", "title": "报告设备", "status": "done" if equipment_done else "pending",
         "detail": f"{len(equipment)} 台已选入报告", "route": "/equipment"},
        {"key": "template", "title": "报告模板", "status": "done" if template_done else "pending",
         "detail": template_name, "route": "/report"},
        {"key": "report", "title": "生成报告", "status": "ready" if report_ready else "pending",
         "detail": "可直接流式生成并查看日志" if report_ready else "请先录入检测数据", "route": "/report"},
    ]
    next_step = next((s for s in steps if s["status"] in ("pending", "progress")), steps[-1])
    return ok({
        "project_name": project_name,
        "checked_count": len(checked),
        "filled_count": filled,
        "total_rows": total_rows,
        "assessed_count": assessed,
        "equipment_count": len(equipment),
        "template_name": template_name,
        "report_ready": report_ready,
        "done_count": done_count,
        "total_steps": len(steps),
        "steps": steps,
        "next_step": next_step,
        "report_dir": os.path.join(get_report_gen_dir(), "exports"),
    }, "流程状态读取成功")
