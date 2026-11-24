# -*- coding: utf-8 -*-
"""报告生成路由：报告抬头信息与《检测报告》.docx 生成。

P5 后只保留确定性渲染：事实包（report_facts）+ 可选的措辞覆盖
（overview / basis / conclusions）+ word_report.generate_report。
不再有应用内 LLM 代理循环；措辞由 DSH 里的模型写好后再传进来。
"""

import hashlib
import os
import re
import json
import queue
import subprocess
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from utils.equipment_store import (
    EquipmentUnavailable, release_equipment_for_report,
    report_equipment_rows_for, reserve_equipment_for_report,
)

from deps import (get_controller, get_state, ok, ApiError,
                  get_report_gen_dir, get_template_library,
                  get_record_store,
                  REPORT_INFO_FIELDS, ReportTemplateSet,
                  generate_report)
from utils.report_facts import build_facts
from utils.report_render import render_from_facts
from utils.template_match import explain_switch, rank_templates
from utils.report_template_map import resolve_sheet_key
from utils.report_preflight import format_errors, run_preflight

router = APIRouter(tags=["report"])

INFO_KEYS = [f[0] for f in REPORT_INFO_FIELDS]  # 基础抬头字段
# 工程概况等报告补充信息（随项目保存，也参与第一章概况生成）
EXTRA_INFO_KEYS = [
    "construction_unit", "contractor", "design_unit", "supervision_unit", "survey_unit",
    "structure_type", "building_area", "floor_count", "building_height",
    "start_date", "completion_date", "inspection_purpose", "project_overview",
]
INFO_KEYS = list(dict.fromkeys(INFO_KEYS + EXTRA_INFO_KEYS))

# 生成历史（JSON 文件，最多保留 50 条；与 exports 同目录）
HISTORY_FILE = os.path.join(get_report_gen_dir(), "report_history.json")
HISTORY_LIMIT = 50
_PREVIEW_LOCK = threading.RLock()
_PREVIEW_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data", "previews")

# 报告编号规则：前缀-年份-序号（如 JC-2026-001），前缀可为空
RE_REPORT_NO = re.compile(r"^(?P<prefix>[A-Za-z0-9\u4e00-\u9fa5]+)?[-_](?P<year>\d{4})[-_](?P<seq>\d+)$")


def _load_history_json() -> list:
    """旧 JSON 历史（仅作数据库不可用时的兜底）。"""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _save_history(items: list) -> None:
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(items[:HISTORY_LIMIT], f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass  # 历史记录失败不影响主流程


def _append_history_json(entry: dict) -> None:
    items = _load_history_json()
    items.insert(0, entry)
    _save_history(items)


def _append_history(entry: dict):
    """写入记录库；数据库不可用时回退旧 JSON。返回记录 ID 或 None。"""
    try:
        return get_record_store().add_report_record(entry)
    except Exception:  # noqa: BLE001
        _append_history_json(entry)
        return None


def _load_history() -> list:
    try:
        items, _total = get_record_store().list_report_records(limit=500)
        return items
    except Exception:  # noqa: BLE001
        return _load_history_json()


def _history_view(items: list) -> list:
    """历史条目视图：附加文件存在性（前端据此禁用打开按钮）。"""
    out = []
    for it in items:
        view = dict(it)
        view["exists"] = os.path.isfile(str(it.get("filepath") or ""))
        out.append(view)
    return out


class ReportInfoBody(BaseModel):
    report_info: dict


class GenerateBody(BaseModel):
    output_path: Optional[str] = None
    template_id: Optional[str] = None
    # 草稿：只生成已有数据、模板、评定结论都就绪的检测项
    draft: bool = False
    # 可选措辞覆盖：{"overview": str, "basis": [str], "conclusions": [str]}
    narrative: Optional[dict] = None


class RenderBody(BaseModel):
    narrative: Optional[dict] = None
    output_path: Optional[str] = None
    template_id: Optional[str] = None


def _clean_info(info):
    """过滤抬头与工程概况字段，统一为字符串。"""
    return {k: ("" if (info or {}).get(k) is None else str((info or {}).get(k)))
            for k in INFO_KEYS}


@router.post("/report/auto_info")
def report_auto_info():
    """AI/规则自动整理报告信息与二~五章节，不需要人工选择模板。"""
    try:
        state = get_state()
        checked = _effective_report_order(state)
        if not checked:
            return ok({
                "missing": ["当前项目还没有可用检测数据，请先上传文件或在数据采集页录入"],
                "report_info": _clean_info(state.report_info),
                "template": {"id": "", "name": "", "auto": True},
                "basis": [], "equipment": [], "content": [], "results": [],
                "counts": {"checked": 0, "filled": 0, "assessed": 0,
                           "items": 0},
            }, "当前项目还没有检测数据")

        info = _clean_info(state.report_info)
        if not info.get("project_name"):
            info["project_name"] = state.project_name or ""
        if not info.get("report_date"):
            info["report_date"] = datetime.now().strftime("%Y-%m-%d")
        if not info.get("test_date"):
            info["test_date"] = info["report_date"]
        if not info.get("report_no"):
            try:
                info["report_no"] = next_report_no().get("data") or ""
            except Exception:  # noqa: BLE001
                info["report_no"] = ""
        state.report_info = info

        try:
            from report_generator.utils.report_narrative import (
                equipment_for, overview_template, standards_for,
            )
        except ImportError:  # noqa: BLE001
            from utils.report_narrative import (
                equipment_for, overview_template, standards_for,
            )

        overview_draft = overview_template(info, checked)
        existing_overview = str(info.get("project_overview") or "").strip()
        if not existing_overview or "【请填写】" in existing_overview:
            # 旧稿带占位符时用新字段刷新；纯手工概况不覆盖
            info["project_overview"] = overview_draft
        state.report_info = info
        basis = standards_for(checked)
        try:
            equipment = report_equipment_rows_for(checked, limit=20)
        except Exception:  # noqa: BLE001
            equipment = []
        if not equipment:
            equipment = equipment_for(checked)

        controller = get_controller()
        content = []
        results = []
        filled_total = 0
        assessed = 0
        for key in checked:
            base, component = controller.parse_sheet_key(key)
            display_item = re.sub(r"[（(].*?[）)]", "", base).strip() or base
            rows = state.sheet_data.get(key) or []
            filled = sum(1 for row in rows
                         if any(str(v).strip() for v in row))
            filled_total += filled
            columns = controller.get_columns(key)
            content.append({
                "sheet_key": key,
                "item": display_item,
                "component": component or "",
                "rows": filled,
                "columns": columns,
            })
            outcome = (state.assessment_results or {}).get(key) or {}
            if outcome.get("ok"):
                assessed += 1
                conclusion = (outcome.get("conclusion")
                              or outcome.get("conclusion_text")
                              or outcome.get("summary") or "")
                status = "已评定"
            else:
                conclusion = "已录入 %d 行，报告生成时由检测结果表引擎自动汇总。" % filled
                status = "待评定"
            results.append({
                "sheet_key": key,
                "item": display_item,
                "component": component or "",
                "rows": filled,
                "status": status,
                "conclusion": conclusion,
            })

        template_set, warnings = _resolve_report_template(state)
        content_text = "；".join(
            "%s（%s）%d 行" % (x["item"], x["component"] or "构件", x["rows"])
            for x in content)
        return ok({
            "report_info": info,
            "overview_template": overview_draft,
            "template": {
                "id": template_set.template_id,
                "name": template_set.name,
                "auto": True,
            },
            "basis": basis,
            "equipment": equipment,
            "content": content,
            "content_text": "本次检测内容包括：" + content_text + "。",
            "results": results,
            "counts": {
                "checked": len(checked),
                "filled": filled_total,
                "assessed": assessed,
                "items": len(checked),
            },
            "warnings": warnings,
            "missing": [],
        }, "报告信息已自动整理")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"自动整理报告信息失败：{e}"}


@router.get("/report/match_template")
def match_report_template():
    """只读：列出报告模板库并给出当前项目应使用的模板与理由。

    与生成时同一套解析顺序（项目选择 → 模板库默认 → 内置），但不写项目状态。
    """
    try:
        state = get_state()
        controller = get_controller()
        lib = get_template_library()
        template_set, warnings = _resolve_report_template(state)

        # 与报告生成保持同一口径：有数据的已勾选工作表才算参与匹配，
        # 且基础项目名要按 resolve_sheet_key 归一化后再查结果表模板。
        checked = []
        for key in (state.checked_items or []):
            rows = state.sheet_data.get(key) or []
            if not any(str(value).strip() for row in rows for value in row):
                continue
            checked.append(key)
        entries = []
        for key in checked:
            base, component = resolve_sheet_key(key)
            entries.append({"base": base, "component": component or None,
                            "key": key})

        selected = str((state.template_selection or {}).get(
            "report_template_id") or "")
        try:
            default_id = str(lib.default_report_template_id() or "")
        except Exception:  # noqa: BLE001
            default_id = ""

        candidates = []
        unavailable = []
        for row in lib.list_report_templates() or []:
            tid = str(row.get("id") or "")
            candidate = {"id": tid, "name": row.get("name") or "",
                         "builtin": bool(row.get("builtin")),
                         "template_set": None}
            try:
                candidate["template_set"] = lib.get_report_template_set(tid)
            except Exception as e:  # noqa: BLE001
                unavailable.append({"id": tid, "name": candidate["name"],
                                    "error": str(e)[:120]})
            candidates.append(candidate)

        known = {candidate["id"] for candidate in candidates}
        if "builtin_standard" not in known:
            try:
                builtin = ReportTemplateSet.builtin()
            except Exception:  # noqa: BLE001
                builtin = None
            if builtin is not None:
                candidates.append({"id": "builtin_standard",
                                   "name": builtin.name,
                                   "builtin": True,
                                   "template_set": builtin})

        scored = rank_templates([item for item in candidates
                                 if item.get("template_set")],
                                entries, selected, default_id)
        best = scored[0] if scored else None
        recommend_switch, switch_reason = explain_switch(
            scored, template_set.template_id)

        recommended = str(template_set.template_id or "")
        if selected and selected == recommended:
            source = "project"
        elif default_id and default_id == recommended:
            source = "default"
        else:
            source = "builtin"
        return ok({
            "effective": {"id": recommended, "name": template_set.name,
                          "source": source},
            "best_fit": ({"id": best["id"], "name": best["name"],
                          "score": best["score"], "reasons": best["reasons"]}
                         if best else None),
            "recommend_switch": recommend_switch,
            "switch_reason": switch_reason,
            "checked_items": checked,
            "result_entries": len(entries),
            "templates": scored,
            "unavailable_templates": unavailable,
            "recommended": recommended,
            "recommended_name": template_set.name,
            "source": source,
            "missing_chapters": template_set.missing_chapters(),
            "warnings": warnings,
        }, "报告模板推荐已生成（%d 份模板，%d 个检测项）"
                  % (len(scored), len(entries)))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"匹配报告模板失败：{e}"}


def _preview_source(filepath):
    target = os.path.realpath(str(filepath or ""))
    root = os.path.realpath(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    if not target.startswith(root + os.sep):
        raise ApiError("只允许预览本系统生成的文件")
    if not target.lower().endswith(".docx") or not os.path.isfile(target):
        raise ApiError("预览文件不存在或不是 .docx")
    return target


def _docx_to_pdf(source, target):
    """用本机 Word 把 docx 转成 PDF；只在本机部署使用。"""
    with _PREVIEW_LOCK:
        if os.path.isfile(target) and os.path.getmtime(target) >= os.path.getmtime(source):
            return target
        os.makedirs(os.path.dirname(target), exist_ok=True)
        import win32com.client  # 延迟导入，Linux/无 Office 环境会明确报错
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001
            pythoncom = None
        app = None
        doc = None
        try:
            app = win32com.client.Dispatch("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            doc = app.Documents.Open(source, ReadOnly=True)
            doc.ExportAsFixedFormat(target, 17)  # wdExportFormatPDF
        finally:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:  # noqa: BLE001
                    pass
            try:
                if app is not None:
                    app.Quit()
            except Exception:  # noqa: BLE001
                pass
            try:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass
        if not os.path.isfile(target):
            raise ApiError("PDF 预览生成失败")
        return target


@router.get("/report/preview")
def preview_report(filepath: str):
    """在线预览报告/原始记录：docx → PDF，浏览器直接内嵌。"""
    try:
        source = _preview_source(filepath)
        stamp = "%s|%s" % (source, os.path.getmtime(source))
        key = hashlib.sha1(stamp.encode("utf-8")).hexdigest()[:16]
        target = os.path.join(_PREVIEW_DIR, key + ".pdf")
        _docx_to_pdf(source, target)
        return FileResponse(
            target, media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=preview.pdf"})
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ApiError("在线预览失败：%s" % e, 503)


@router.get("/report/download")
def download_report(filepath: str):
    """下载已生成报告/原始记录 docx。"""
    source = _preview_source(filepath)
    return FileResponse(
        source,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(source))


@router.get("/report/info")
def get_report_info():
    """报告信息当前值（随项目保存；工程名称始终与项目名一致）。"""
    try:
        state = get_state()
        info = _clean_info(state.report_info)
        if not info.get("project_name"):
            info["project_name"] = state.project_name or ""
        return ok(info, "报告信息读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取报告信息失败：{e}"}


@router.put("/report/info")
def put_report_info(body: ReportInfoBody):
    """保存报告信息；工程名称与项目名双向保持一致。"""
    try:
        state = get_state()
        info = _clean_info(body.report_info)
        name = str(info.get("project_name") or "").strip()
        if name:
            state.project_name = name
        else:
            info["project_name"] = state.project_name or ""
        state.report_info = info
        return ok(state.report_info, "报告信息已保存")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存报告信息失败：{e}"}


def _resolve_report_template(state, explicit_id=None):
    """解析报告模板：请求体 → 项目选择 → 模板库默认 → 内置。

    返回 (ReportTemplateSet, warnings)。显式选择不存在的模板直接报错；
    项目里保存的模板失效时回退默认并给出警告。
    """
    lib = get_template_library()
    warnings = []
    explicit = str(explicit_id or "").strip()
    state_id = str((state.template_selection or {}).get(
        "report_template_id") or "").strip()
    candidate = explicit or state_id
    template_set = None
    if candidate:
        row = lib.get_report_template(candidate)
        if row:
            ts = lib.get_report_template_set(candidate)
            missing = ts.missing_chapters()
            if missing:
                if explicit:
                    raise ApiError("所选报告模板文件缺失：%s"
                                   % "；".join(missing[:3]))
                warnings.append("项目保存的报告模板文件缺失，已回退默认模板")
            else:
                template_set = ts
        elif explicit:
            raise ApiError("报告模板不存在：%s" % candidate)
        else:
            warnings.append("项目保存的报告模板不存在，已回退默认模板")

    if template_set is None:
        default_id = lib.default_report_template_id()
        template_set = (lib.get_report_template_set(default_id)
                        if default_id else ReportTemplateSet.builtin())
        missing = template_set.missing_chapters()
        if missing:
            builtin = ReportTemplateSet.builtin()
            if not builtin.missing_chapters():
                warnings.append("默认报告模板不可用，已使用内置模板")
                template_set = builtin
            else:
                raise ApiError("报告模板文件缺失：%s"
                               % "；".join(missing[:3]))
    return template_set, warnings


def _default_output_path(given=None):
    """报告输出路径：指定值 → 目录补文件名 → exports/时间戳/检测报告.docx。"""
    if given:
        path = given
    else:
        export_dir = os.path.join(get_report_gen_dir(), "exports",
                                  datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, "检测报告.docx")
    if os.path.isdir(path):
        path = os.path.join(path, "检测报告.docx")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def _state_report_info(state):
    """抬头信息 + 名称/日期缺省值（封面、首页、记录库共用同一份）。"""
    info = _clean_info(state.report_info)
    if not info.get("project_name"):
        info["project_name"] = state.project_name or ""
    if not info.get("report_date"):
        info["report_date"] = datetime.now().strftime("%Y-%m-%d")
    if not info.get("test_date"):
        info["test_date"] = info["report_date"]
    return info


def _has_report_rows(rows):
    """报告口径的有效行：至少一个非空单元格。"""
    return any(str(cell).strip() for row in (rows or []) for cell in (row or []))


def _effective_report_order(state):
    """参与报告的检测项：已勾选且有数据优先，随后补上其它有数据的表。

    这样“没勾选、只上传了数据”的工程也能直接出报告；已勾选但空数据的
    表仍由预检给出缺口，不会被静默忽略。
    """
    sheet_data = state.sheet_data or {}
    order = []
    seen = set()
    for key in (state.checked_items or []):
        if key in sheet_data and key not in seen and _has_report_rows(
                sheet_data.get(key)):
            order.append(key)
            seen.add(key)
    for key in sheet_data:
        if key not in seen and _has_report_rows(sheet_data.get(key)):
            order.append(key)
            seen.add(key)
    return order


def _draft_ready_order(state, order, template_set):
    """草稿模式：挑出数据、模板、评定结论都就绪的项，其余给出原因。"""
    controller = get_controller()
    ready, skipped = [], []
    for key in order:
        base, comp = controller.parse_sheet_key(key)
        reason = ""
        if not _has_report_rows((state.sheet_data or {}).get(key)):
            reason = "没有有效数据"
        elif template_set is None or template_set.result_entry(base, comp) is None:
            reason = "缺少对应的报告结果表模板"
        elif not ((state.assessment_results or {}).get(key) or {}).get("ok"):
            reason = "尚未完成评定"
        if reason:
            skipped.append({"sheet_key": key, "reason": reason})
        else:
            ready.append(key)
    return ready, skipped


def _state_facts(state, template_set):
    """当前工程 → 事实包（只读，不占用设备）。"""
    checked_order = _effective_report_order(state)
    if not checked_order:
        raise ApiError("当前项目没有可用的检测数据")
    columns_map = get_controller().build_export_columns(state.sheet_data)
    facts = build_facts(
        state.project_name, _state_report_info(state), checked_order,
        state.sheet_data, columns_map,
        assessment_results=state.assessment_results,
        equipment=report_equipment_rows_for(checked_order),
        template_set=template_set,
        params_map=getattr(state, "cd_params", None) or {})
    facts["template"] = {"id": template_set.template_id,
                         "name": template_set.name}
    return facts, checked_order, columns_map


def _record_generation(state, report_info, output_path, data):
    """写生成历史（失败不影响主流程），返回记录 ID。"""
    try:
        return _append_history({
            "filepath": output_path,
            "report_no": report_info.get("report_no") or "",
            "engine": data.get("engine", "direct"),
            "tables": data.get("tables", 0),
            "skipped": data.get("skipped", []),
            "warnings": data.get("warnings", []),
            "model": data.get("model"),
            "fallback_reason": data.get("fallback_reason"),
            "template_id": data.get("template_id"),
            "template_name": data.get("template_name"),
            "project_name": state.project_name or "",
            "report_info": report_info,
            "assessment_results": dict(state.assessment_results or {}),
            "assessed_count": data.get("assessed_count", 0),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception:  # noqa: BLE001
        return None


def _run_generate(body: GenerateBody, on_log=None):
    """执行一次报告生成，返回 (data, message)。供同步接口和 SSE 流式接口复用。

    普通模式按“有数据的检测项”生成（不要求先勾选）；草稿模式只生成
    数据、模板、评定都就绪的项，其余放入 skipped_items 供前端提示补录。
    """
    log = on_log or (lambda msg: None)
    state = get_state()
    sheet_data = {k: v for k, v in state.sheet_data.items() if v}
    if not sheet_data or not _effective_report_order(state):
        raise ApiError("当前项目没有任何检测数据，请先上传文件或在数据采集页录入")
    log("已读取项目数据：%s" % (state.project_name or "未命名项目"))
    controller = get_controller()
    columns_map = controller.build_export_columns(state.sheet_data)
    template_set, template_warnings = _resolve_report_template(
        state, body.template_id)
    checked_order = _effective_report_order(state)
    skipped_items = []
    if body.draft:
        checked_order, skipped_items = _draft_ready_order(
            state, checked_order, template_set)
        if not checked_order:
            reasons = "；".join("%s（%s）" % (item["sheet_key"], item["reason"])
                               for item in skipped_items) or "没有可用的检测项"
            raise ApiError("没有可生成草稿的已就绪检测项：" + reasons)
        log("草稿模式：%d 项就绪，%d 项跳过"
            % (len(checked_order), len(skipped_items)))
    log("检测项目：%d 个，数据表：%d 张" % (len(checked_order), len(sheet_data)))
    log("报告模板：%s" % template_set.name)

    output_path = _default_output_path(body.output_path)
    report_info = _state_report_info(state)
    preflight = run_preflight(
        report_info, checked_order, state.sheet_data, template_set,
        state.assessment_results)
    if preflight["errors"]:
        raise ApiError("报告预检未通过：\n" + format_errors(preflight))
    report_key = uuid.uuid4().hex
    try:
        equipment = reserve_equipment_for_report(
            checked_order, report_key=report_key)
    except EquipmentUnavailable as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        raise ApiError("设备库不可用，无法完成仪器占用：%s" % e)
    log("报告仪器：%d 台（在用且当日未满10次）" % len(equipment))
    log("开始组装封面、首页、一~六章…")
    try:
        result = generate_report(
            state.project_name, report_info, sheet_data, columns_map,
            checked_order=checked_order, output_path=output_path,
            template_set=template_set,
            assessment_results=state.assessment_results,
            equipment=equipment, on_log=log,
            narrative=body.narrative)
    except Exception:
        release_equipment_for_report(report_key)
        raise

    warnings = (list(preflight.get("warnings") or [])
                + list(template_warnings)
                + list(result.get("warnings") or []))
    data = {
        "filepath": output_path,
        "engine": result.get("engine", "direct"),
        "tables": result.get("tables", 0),
        "skipped": result.get("skipped", []),
        "skipped_items": skipped_items,
        "draft": bool(body.draft),
        "warnings": warnings,
        "model": result.get("model"),
        "fallback_reason": result.get("fallback_reason"),
        "template_id": result.get("template_id") or template_set.template_id,
        "template_name": result.get("template_name") or template_set.name,
        "assessed_count": sum(
            1 for key in checked_order
            if (state.assessment_results.get(key) or {}).get("ok")),
    }
    if body.narrative:
        data["applied_narrative"] = [
            key for key in ("overview", "basis", "conclusions")
            if (body.narrative or {}).get(key)]
    engine = data["engine"]
    message = (f"检测报告生成完成（共 {data['tables']} 张一览表，"
               f"模板：{data['template_name']}）")
    if body.draft:
        message = "检测报告草稿生成完成（共 %d 张一览表，模板：%s）" % (
            data["tables"], data["template_name"])
        if skipped_items:
            message += "；跳过 %d 项未就绪检测项" % len(skipped_items)
    if data.get("applied_narrative"):
        message += "；已应用措辞覆盖：%s" % "、".join(data["applied_narrative"])

    data["preview_url"] = "/api/report/preview?filepath=" + quote(output_path, safe="")
    data["download_url"] = "/api/report/download?filepath=" + quote(output_path, safe="")
    data["record_id"] = _record_generation(
        state, report_info, output_path, data)
    log("报告已写入：%s" % output_path)
    return data, message


@router.post("/report/generate")
def generate(body: GenerateBody):
    """同步生成《检测报告》.docx（兼容旧调用）。"""
    try:
        data, message = _run_generate(body)
        return ok(data, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"生成检测报告失败：{e}"}


@router.get("/report/facts")
def report_facts_endpoint():
    """只读：报告事实包（report.facts/1）+ 确定性措辞底稿。

    数值、列、行、评定结论、规范清单、设备全部来自当前工程；
    智能体可据此撰写 overview/basis/conclusions，再调 /report/render 写回。
    """
    try:
        state = get_state()
        template_set, warnings = _resolve_report_template(state, None)
        facts, checked_order, _cols = _state_facts(state, template_set)
        facts["warnings"] = list(warnings) + list(facts.get("warnings") or [])
        facts["preflight"] = run_preflight(
            _state_report_info(state), checked_order, state.sheet_data,
            template_set, state.assessment_results)
        return ok(facts, "报告事实包已生成：%d 个项目，%d 张一览表"
                  % (facts["stats"]["items"], facts["stats"]["rendered_tables"]))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"生成报告事实包失败：{e}"}


@router.post("/report/render")
def render_report_endpoint(body: RenderBody):
    """按当前工程事实 + 措辞覆盖渲染报告（确定性，不调用模型）。"""
    try:
        state = get_state()
        template_set, template_warnings = _resolve_report_template(
            state, body.template_id)
        facts, checked_order, _cols = _state_facts(state, template_set)
        if not any(item.get("rows_filled") for item in facts.get("items") or []):
            raise ApiError("当前项目没有已录入数据的检测项目，无法渲染报告")
        output_path = _default_output_path(body.output_path)
        report_info = _state_report_info(state)
        preflight = run_preflight(
            report_info, checked_order, state.sheet_data, template_set,
            state.assessment_results)
        if preflight["errors"]:
            raise ApiError("报告预检未通过：\n" + format_errors(preflight))
        report_key = uuid.uuid4().hex
        try:
            equipment = reserve_equipment_for_report(
                checked_order, report_key=report_key)
        except EquipmentUnavailable as e:
            raise ApiError(str(e))
        except Exception as e:  # noqa: BLE001
            raise ApiError("设备库不可用，无法完成仪器占用：%s" % e)
        facts["equipment"] = equipment
        try:
            result = render_from_facts(
                facts, body.narrative, output_path=output_path,
                template_set=template_set)
        except Exception:
            release_equipment_for_report(report_key)
            raise
        data = {
            "filepath": output_path,
            "engine": "direct",
            "tables": result.get("tables", 0),
            "skipped": result.get("skipped", []),
            "warnings": (list(preflight.get("warnings") or [])
                         + list(template_warnings)
                         + list(result.get("warnings") or [])),
            "template_id": result.get("template_id")
                           or template_set.template_id,
            "template_name": result.get("template_name")
                             or template_set.name,
            "applied_narrative": result.get("applied_narrative", []),
            "assessed_count": facts["stats"]["assessed"],
        }
        data["record_id"] = _record_generation(
            state, report_info, output_path, data)
        message = "报告已渲染：%d 张一览表" % data["tables"]
        if data["applied_narrative"]:
            message += "；已应用措辞覆盖：%s" % "、".join(data["applied_narrative"])
        return ok(data, message)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"渲染检测报告失败：{e}"}


@router.post("/report/generate/stream")
def generate_stream(body: GenerateBody):
    """SSE 流式生成报告：实时输出组装日志，最后返回报告结果。"""
    q = queue.Queue()
    started = time.time()

    def worker():
        try:
            data, message = _run_generate(
                body, on_log=lambda msg: q.put(("log", msg)))
            q.put(("result", {"data": data, "message": message}))
        except ApiError as exc:
            q.put(("error", {"message": exc.message}))
        except Exception as exc:  # noqa: BLE001
            q.put(("error", {"message": "生成检测报告失败：%s" % exc}))
        finally:
            q.put(("done", None))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def event(name, payload):
        return "event: %s\ndata: %s\n\n" % (
            name, json.dumps(payload, ensure_ascii=False))

    def stream():
        yield event("log", {"message": "已连接报告生成服务…", "elapsed": 0})
        while True:
            try:
                kind, payload = q.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if kind == "log":
                yield event("log", {
                    "message": payload,
                    "elapsed": round(time.time() - started, 1),
                })
            elif kind == "result":
                yield event("result", payload)
            elif kind == "error":
                yield event("error", payload)
            elif kind == "done":
                break
        yield event("done", {"elapsed": round(time.time() - started, 1)})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


class RevealBody(BaseModel):
    filepath: str


@router.post("/report/reveal")
def reveal(body: RevealBody):
    """在 Windows 资源管理器中定位已生成的报告文件。"""
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


@router.get("/report/next_no")
def next_report_no():
    """按「前缀-年份-序号」规则推算下一个报告编号。

    读取生成历史中本年份的最大序号 +1；前缀沿用最近一条编号的前缀（默认 JC）。
    """
    try:
        year = datetime.now().year
        best_seq = 0
        prefix = "JC"
        for it in _load_history():
            m = RE_REPORT_NO.match(str(it.get("report_no") or "").strip())
            if not m:
                continue
            if m.group("prefix"):
                prefix = m.group("prefix")
            if int(m.group("year")) == year and int(m.group("seq")) > best_seq:
                best_seq = int(m.group("seq"))
        next_no = f"{prefix}-{year}-{best_seq + 1:03d}"
        return ok(next_no, "下一个报告编号已推算")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"推算报告编号失败：{e}"}


@router.get("/report/history")
def get_report_history():
    """报告生成历史（最近 50 条，倒序，附文件存在性）。"""
    try:
        return ok(_history_view(_load_history()), "生成历史读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取生成历史失败：{e}"}


@router.post("/report/history/clear")
def clear_report_history():
    """清空全部生成历史（不影响已生成的报告文件）。"""
    try:
        try:
            get_record_store().clear_report_records()
        except Exception:  # noqa: BLE001
            _save_history([])
        return ok(True, "生成历史已清空")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"清空生成历史失败：{e}"}
