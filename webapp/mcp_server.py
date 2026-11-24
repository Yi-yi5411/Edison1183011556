# -*- coding: utf-8 -*-
"""工程检测harness MCP Server（stdio，JSON-RPC 2.0）。

把运行中的 Web 后端（默认 http://127.0.0.1:8765/api）包装成 Harness
可调用的 MCP tools/resources。LLM 只负责编排；计算与结论由后端评定引擎完成。

启动：
    python webapp/mcp_server.py

配置：
    config/structural.toml 的 [server].api_base（环境变量 STRUCTURAL_API_BASE 优先）

写操作（新建/勾选/保存/评定/生成/修改）必须显式传 confirm=true；
读操作不需要。所有数据以 JSON 文本返回，便于 Harness 解析。

stdio 传输：换行分隔 JSON（同时兼容 Content-Length 帧）。
"""
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import quote

import requests

try:  # 配置与代码同目录（webapp/structural_config.py）
    from structural_config import api_base as _configured_api_base
except ImportError:  # pragma: no cover - 兜底
    def _configured_api_base():
        return "http://127.0.0.1:8765/api"

BASE_URL = (os.environ.get("STRUCTURAL_API_BASE")
            or _configured_api_base()).rstrip("/")
TIMEOUT = int(os.environ.get("STRUCTURAL_TIMEOUT", "300"))
SERVER_NAME = "structural-inspection"
SERVER_VERSION = "1.1.0"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPT_DIR = os.path.join(_ROOT, "prompt")

# 写操作审计（人工复核/追责用；不记录到后端，纯本地 JSONL）
_AUDIT_DIR = (os.environ.get("STRUCTURAL_AUDIT_DIR")
              or os.path.join(_ROOT, "data", "audit"))
_AUDIT_FILE = os.path.join(_AUDIT_DIR, "mcp_writes.jsonl")
_AUDIT_MAX_BYTES = 5 * 1024 * 1024
_SECRET_KEYS = ("api_key", "password", "token", "secret", "authorization")


def _redact_args(value, depth=0):
    """写操作参数脱敏：密钥类字段置 ***，长文本截断，数组只留前 50 项。"""
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if any(s in str(key).lower() for s in _SECRET_KEYS):
                redacted[key] = "***"
            else:
                redacted[key] = _redact_args(item, depth + 1)
        return redacted
    if isinstance(value, list):
        return [_redact_args(item, depth + 1) for item in value[:50]]
    if isinstance(value, str) and len(value) > 800:
        return value[:800] + "…"
    return value


def _audit_write(tool, args, ok, error, duration):
    """记录一次写操作（含被安全门拦下的调用）。失败不影响主流程。"""
    if not tool.get("write"):
        return
    try:
        os.makedirs(_AUDIT_DIR, exist_ok=True)
        if (os.path.isfile(_AUDIT_FILE)
                and os.path.getsize(_AUDIT_FILE) > _AUDIT_MAX_BYTES):
            os.replace(_AUDIT_FILE, _AUDIT_FILE + ".1")
        entry = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool.get("name", ""),
            "danger": bool(tool.get("danger")),
            "ok": bool(ok),
            "duration_ms": int(duration * 1000),
            "error": str(error or "")[:300],
            "args": _redact_args(args),
        }
        with open(_AUDIT_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


class ToolError(Exception):
    pass


def _log(message):
    sys.stderr.write("[structural-mcp] %s\n" % message)
    sys.stderr.flush()


def _decode(resp):
    try:
        body = resp.json()
    except ValueError:
        raise ToolError("后端返回非 JSON（HTTP %s）：%s"
                        % (resp.status_code, resp.text[:300]))
    if not resp.ok:
        raise ToolError(body.get("message") or "HTTP %s" % resp.status_code)
    if isinstance(body, dict) and body.get("ok") is False:
        raise ToolError(body.get("message") or "后端返回失败")
    return body.get("data") if isinstance(body, dict) else body


def _request(method, path, params=None, json_body=None):
    url = BASE_URL + path
    try:
        resp = requests.request(method, url, params=params, json=json_body,
                                timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ToolError("无法连接后端 %s：%s（请先启动 webapp/backend）"
                        % (BASE_URL, e))
    return _decode(resp)


# 上传文件扩展名 → MIME；具体工具再用 allowed 收窄白名单。
_UPLOAD_MIME = {
    ".xlsx": "application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document",
    ".doc": "application/msword",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".zip": "application/zip",
}

# 工作表/评定/人员导入：与后端 excel_import.read_rows 一致
_SHEET_FORMATS = (".xlsx", ".xlsm", ".csv", ".docx")
# 知识库/规范库导入：与后端 wiki/normqa 的 SUPPORTED_SUFFIX 一致
_KNOWLEDGE_FORMATS = (".md", ".markdown", ".txt", ".docx")


def _check_upload(filepath, allowed):
    """校验文件存在与扩展名，返回 (绝对路径, MIME)。"""
    filepath = os.path.abspath(str(filepath or ""))
    if not os.path.isfile(filepath):
        raise ToolError("文件不存在：%s" % filepath)
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in allowed:
        raise ToolError("仅支持 %s 文件：%s"
                        % (" / ".join(allowed), os.path.basename(filepath)))
    return filepath, _UPLOAD_MIME.get(ext, "application/octet-stream")


def _upload(path, filepath, data=None, allowed=_SHEET_FORMATS):
    filepath, mime = _check_upload(filepath, allowed)
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                BASE_URL + path,
                files={"file": (os.path.basename(filepath), f, mime)},
                data=data or {},
                timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ToolError("无法连接后端 %s：%s" % (BASE_URL, e))
    return _decode(resp)


def _upload_many(path, filepaths, data=None, field="files",
                 allowed=_KNOWLEDGE_FORMATS):
    """一次上传多个文件（wiki/normqa 的多文件导入端点用）。"""
    if isinstance(filepaths, str):
        filepaths = [filepaths]
    items = [str(p).strip() for p in (filepaths or []) if str(p).strip()]
    if not items:
        raise ToolError("filepath 不能为空")
    files = []
    handles = []
    try:
        for item in items:
            filepath, mime = _check_upload(item, allowed)
            handle = open(filepath, "rb")
            handles.append(handle)
            files.append((field, (os.path.basename(filepath), handle, mime)))
        try:
            resp = requests.post(BASE_URL + path, files=files,
                                 data=data or {}, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise ToolError("无法连接后端 %s：%s" % (BASE_URL, e))
        return _decode(resp)
    finally:
        for handle in handles:
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass


def _require_confirm(arguments):
    if not arguments.get("confirm"):
        raise ToolError("写操作需要用户确认：请在参数中传 confirm=true。")


def _require_danger_confirm(tool, arguments):
    """危险操作二次确认：删除/覆盖类工具必须再传 confirm_delete=true。"""
    if tool.get("danger") and not arguments.get("confirm_delete"):
        raise ToolError(
            "危险操作需要二次确认：%s 会删除或覆盖数据且不可恢复，"
            "确认后请传 confirm_delete=true。" % tool["name"])


def _tool(name, description, properties, required, write, handler,
          danger=False):
    """注册一个工具。

    write=True  → 必须传 confirm=true（普通写操作）
    danger=True → 额外必须传 confirm_delete=true（删除/覆盖，不可恢复）
    """
    props = dict(properties)
    required = list(required)
    if write:
        props["confirm"] = {
            "type": "boolean",
            "description": "写操作确认；必须为 true，调用前请向用户确认",
        }
        if "confirm" not in required:
            required.append("confirm")
    if danger:
        props["confirm_delete"] = {
            "type": "boolean",
            "description": "危险操作二次确认：删除或覆盖后不可恢复，"
                           "确认后必须为 true",
        }
        if "confirm_delete" not in required:
            required.append("confirm_delete")
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
        "annotations": {
            "title": name,
            "readOnlyHint": not write,
            "destructiveHint": bool(danger),
            "idempotentHint": not write,
            "openWorldHint": False,
        },
        "handler": handler,
        "write": write,
        "danger": bool(danger),
    }


# ── 工具实现 ──────────────────────────────────────────────
def _get_audit_log(args):
    """读取写操作审计（最近 N 条），支持按工具/失败过滤。"""
    try:
        limit = max(1, min(int(args.get("limit") or 20), 500))
    except (TypeError, ValueError):
        limit = 20
    tool_filter = str(args.get("tool") or "").strip()
    only_failed = bool(args.get("only_failed"))
    items = []
    if os.path.isfile(_AUDIT_FILE):
        with open(_AUDIT_FILE, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if tool_filter and entry.get("tool") != tool_filter:
                    continue
                if only_failed and entry.get("ok"):
                    continue
                items.append(entry)
    return {"items": items[-limit:][::-1], "count": len(items),
            "shown": min(limit, len(items)), "path": _AUDIT_FILE,
            "exists": os.path.isfile(_AUDIT_FILE)}


def _health(args):
    return _request("GET", "/health")


def _get_project(args):
    return _request("GET", "/project")


def _get_project_structured(args):
    return _request("GET", "/project/structured")


def _list_detection_items(args):
    # 优先用 manifest 摘要：一次调用同时拿到参数、评定规则与技能名
    try:
        summary = _request("GET", "/plugins/summary")
        if isinstance(summary, dict) and summary.get("items"):
            return {"items": summary["items"],
                    "count": summary.get("count"),
                    "manifest": bool(summary.get("manifest")),
                    "source": "summary"}
    except ToolError:
        pass  # 老后端没有 /plugins/summary，退回 /plugins
    plugins = _request("GET", "/plugins")
    items = []
    for plugin in plugins or []:
        for item, comps in (plugin.get("tree") or {}).items():
            items.append({
                "plugin_id": plugin.get("id"),
                "structure_type": plugin.get("structure_type"),
                "item": item,
                "components": comps,
                "sheet_keys": [
                    (item + "（%s）" % c) if c else item for c in comps
                ] if comps else [item],
                "column_count": len(plugin.get("columns") or []),
            })
    return {"items": items, "count": len(items), "manifest": False,
            "source": "plugins"}


def _get_item_schema(args):
    base = str(args.get("item") or "").strip()
    data = _request("GET", "/assessment/specs")
    specs = data.get("specs") if isinstance(data, dict) else data
    for spec in specs or []:
        names = spec.get("base_items") or [spec.get("name")]
        if base and any(base == n or base.startswith(n) or n.startswith(base)
                        for n in names if n):
            return spec
    raise ToolError("未找到检测项目：%s（可先调用 list_detection_items）" % base)


def _create_project(args):
    _require_confirm(args)
    return _request("POST", "/project/new", json_body={
        "project_name": args.get("project_name") or "新建项目"})


def _open_project(args):
    _require_confirm(args)
    return _request("POST", "/project/open", json_body={
        "filepath": args.get("filepath")})


def _save_project(args):
    _require_confirm(args)
    body = {}
    if args.get("filepath"):
        body["filepath"] = args["filepath"]
    return _request("POST", "/project/save", json_body=body)


def _check_item(args):
    _require_confirm(args)
    body = {
        "sheet_key": args.get("sheet_key"),
        "checked": bool(args.get("checked", True)),
    }
    if args.get("params"):
        body["params"] = args["params"]
    return _request("POST", "/project/check_item", json_body=body)


def _create_data_sheet(args):
    """创建/复用一张数据采集表，并可选地写入行数据 + 自动计算。

    只编排现有后端接口，不复制列定义/计算逻辑：
      check_item → put_rows → calc → get_project
    """
    _require_confirm(args)
    key = str(args.get("sheet_key") or "").strip()
    if not key:
        raise ToolError("sheet_key 不能为空")
    params = args.get("params") or {}
    created = _request("POST", "/project/check_item", json_body={
        "sheet_key": key, "checked": True, "params": params})
    if isinstance(created, dict) and created.get("requires_setup"):
        specs = created.get("field_specs") or []
        if specs:
            detail = "；".join(
                "%s（%s，%s%s%s）" % (
                    spec.get("key"), spec.get("label") or spec.get("key"),
                    spec.get("type") or "string",
                    "，必填" if spec.get("required") else "",
                    "，默认 %s" % spec["default"]
                    if spec.get("default") not in (None, "") else "")
                for spec in specs)
        else:
            detail = "、".join(created.get("fields") or [])
        raise ToolError(
            "该检测项目需要先设置参数，带上 params 重新调用 create_data_sheet：%s"
            % detail)
    rows = args.get("rows")
    warnings = []
    if rows is not None:
        if not isinstance(rows, list):
            raise ToolError("rows 必须是二维数组")
        _request("PUT", "/sheet/%s/rows" % quote(key, safe=""),
                 json_body={"rows": rows, "force": False})
        try:
            calc = _request("POST", "/sheet/%s/calc" % quote(key, safe=""),
                            json_body={})
            final_rows = (calc or {}).get("rows") or rows
        except ToolError as e:
            warnings.append("自动计算未完成：%s" % e)
            final_rows = rows
    else:
        project = _request("GET", "/project")
        sheet = (project.get("sheets") or {}).get(key) or {}
        final_rows = sheet.get("rows") or []
    project = _request("GET", "/project")
    sheet = (project.get("sheets") or {}).get(key) or {}
    return {
        "sheet_key": key,
        "created": True,
        "rows": len(final_rows or []),
        "columns": sheet.get("columns") or [],
        "params": sheet.get("params") or params,
        "assessment": (sheet.get("assessment") or {}).get("result"),
        "warnings": warnings,
    }


def _get_sheet(args):
    key = str(args.get("sheet_key") or "").strip()
    project = _request("GET", "/project")
    sheet = (project.get("sheets") or {}).get(key)
    if sheet is None:
        raise ToolError("工作表不存在：%s" % key)
    return {"sheet_key": key, "sheet": sheet}


def _put_rows(args):
    _require_confirm(args)
    key = str(args.get("sheet_key") or "").strip()
    rows = args.get("rows")
    if not isinstance(rows, list):
        raise ToolError("rows 必须是二维数组")
    return _request("PUT", "/sheet/%s/rows" % quote(key, safe=""),
                    json_body={"rows": rows})


def _import_sheet_excel(args):
    _require_confirm(args)
    key = str(args.get("sheet_key") or "").strip()
    if not key:
        raise ToolError("sheet_key 不能为空")
    return _upload("/sheet/%s/import_excel" % quote(key, safe=""),
                   args.get("filepath"),
                   data={"append": "true" if args.get("append") else "false",
                         "sheet_name": args.get("sheet_name") or ""})


def _import_assessment_excel(args):
    _require_confirm(args)
    key = str(args.get("sheet_key") or "").strip()
    if not key:
        raise ToolError("sheet_key 不能为空")
    return _upload("/assessment/%s/import_excel" % quote(key, safe=""),
                   args.get("filepath"),
                   data={"sheet_name": args.get("sheet_name") or ""})


def _get_assessment_specs(args):
    return _request("GET", "/assessment/specs")


def _get_assessment(args):
    key = str(args.get("sheet_key") or "").strip()
    return _request("GET", "/assessment/%s" % quote(key, safe=""))


def _save_assessment_input(args):
    _require_confirm(args)
    key = str(args.get("sheet_key") or "").strip()
    body = {}
    if args.get("input") is not None:
        body["input"] = args["input"]
    if args.get("options") is not None:
        body["options"] = args["options"]
    return _request("PUT", "/assessment/%s/input" % quote(key, safe=""),
                    json_body=body)


def _run_assessment(args):
    _require_confirm(args)
    key = str(args.get("sheet_key") or "").strip()
    body = {}
    if args.get("input") is not None:
        body["input"] = args["input"]
    if args.get("options") is not None:
        body["options"] = args["options"]
    return _request("POST", "/assessment/%s/run" % quote(key, safe=""),
                    json_body=body)


def _run_all_assessments(args):
    _require_confirm(args)
    return _request("POST", "/assessment/run_all", json_body={
        "sheet_keys": args.get("sheet_keys") or []})


def _select_templates(args):
    _require_confirm(args)
    project = _request("GET", "/project")
    selection = dict((project.get("template_selection") or {}))
    if args.get("report_template_id") is not None:
        selection["report_template_id"] = str(args["report_template_id"])
    if args.get("original_template_map") is not None:
        selection["original_template_map"] = args["original_template_map"]
    selection.setdefault("original_template_map", {})
    return _request("PUT", "/project/template_selection",
                    json_body=selection)


def _list_report_templates(args):
    return _request("GET", "/templates/report")


def _list_original_templates(args):
    return _request("GET", "/templates/original")


def _generate_report(args):
    _require_confirm(args)
    body = {}
    if args.get("template_id"):
        body["template_id"] = args["template_id"]
    if args.get("output_path"):
        body["output_path"] = args["output_path"]
    if isinstance(args.get("narrative"), dict):
        body["narrative"] = args["narrative"]
    return _request("POST", "/report/generate", json_body=body)


def _report_facts(args):
    return _request("GET", "/report/facts")


def _render_report(args):
    _require_confirm(args)
    body = {}
    if args.get("template_id"):
        body["template_id"] = args["template_id"]
    if args.get("output_path"):
        body["output_path"] = args["output_path"]
    if isinstance(args.get("narrative"), dict):
        body["narrative"] = args["narrative"]
    return _request("POST", "/report/render", json_body=body)


def _generate_original_record(args):
    _require_confirm(args)
    body = {
        "sheet_keys": args.get("sheet_keys") or [],
        "template_map": args.get("template_map") or {},
    }
    return _request("POST", "/original-record/generate", json_body=body)


def _load_report_document(args):
    path = str(args.get("filepath") or "")
    if not path:
        raise ToolError("filepath 不能为空")
    return _request("GET", "/report/document", params={"filepath": path})


def _save_report_document(args):
    _require_confirm(args)
    return _request("POST", "/report/document/save", json_body={
        "filepath": args.get("filepath"),
        "paragraphs": args.get("paragraphs") or [],
        "cells": args.get("cells") or [],
        "output_path": args.get("output_path"),
        "overwrite": bool(args.get("overwrite", False)),
    })


def _replace_report_text(args):
    _require_confirm(args)
    return _request("POST", "/report/document/replace", json_body={
        "filepath": args.get("filepath"),
        "find": args.get("find"),
        "replace": args.get("replace") or "",
        "overwrite": bool(args.get("overwrite", False)),
    })


def _get_report_history(args):
    return _request("GET", "/report/history")


def _get_original_history(args):
    return _request("GET", "/original-record/history")


def _search_norms(args):
    items = args.get("detection_items") or []
    if isinstance(items, str):
        items = [items]
    return _request("POST", "/normqa/query", json_body={
        "question": args.get("question") or "",
        "detection_items": [str(i) for i in items if str(i).strip()]})


def _norm_status(args):
    return _request("GET", "/normqa/status")


def _norm_coverage(args):
    return _request("GET", "/normqa/coverage")


def _get_workflow_status(args):
    return _request("GET", "/workflow/status")


def _get_library_status(args):
    return _request("GET", "/libraries/status")


def _search_wiki(args):
    return _request("POST", "/wiki/search", json_body={
        "question": args.get("question") or "",
        "top_k": int(args.get("top_k") or 3),
        "detection_items": args.get("detection_items") or [],
    })


def _get_wiki_page(args):
    page_id = str(args.get("page_id") or "").strip()
    if not page_id:
        raise ToolError("page_id 不能为空")
    return _request("GET", "/wiki/pages/%s" % quote(page_id, safe=""))


def _list_wiki_pages(args):
    return _request("GET", "/wiki/pages", params={
        "category": args.get("category") or "",
        "query": args.get("query") or "",
        "limit": int(args.get("limit") or 50),
        "offset": int(args.get("offset") or 0),
    })


def _list_report_records(args):
    return _request("GET", "/records/report", params={
        "q": args.get("q") or "",
        "project": args.get("project") or "",
        "limit": int(args.get("limit") or 50),
        "offset": int(args.get("offset") or 0),
    })


def _list_original_records(args):
    return _request("GET", "/records/original", params={
        "q": args.get("q") or "",
        "project": args.get("project") or "",
        "limit": int(args.get("limit") or 50),
        "offset": int(args.get("offset") or 0),
    })


def _list_equipment(args):
    return _request("GET", "/equipment/library", params={
        "keyword": args.get("keyword") or "",
        "selected_only": "true" if args.get("selected_only") else "false",
    })


def _select_equipment(args):
    _require_confirm(args)
    return _request("POST", "/equipment/library/select", json_body={
        "ids": args.get("ids") or [],
        "selected": bool(args.get("selected", True)),
    })


_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_OBJ = {"type": "object"}
_ROWS = {
    "type": "array",
    "description": "二维行数据 [[单元格,...], ...]",
    "items": {
        "type": "array",
        "items": {"type": ["string", "number", "boolean", "null"]},
    },
}

TOOLS = [
    _tool("health", "检查检测系统后端是否运行。", {}, [], False, _health),
    _tool("get_audit_log",
          "读取写操作审计（最近的在前）：时间、工具、是否危险、耗时、结果、错误、"
          "脱敏参数。可用来回答“刚才改了什么/有没有失败的危险操作”。",
          {"limit": {"type": "integer",
                     "description": "返回条数，默认 20，最大 500"},
           "tool": {**_STR, "description": "只看某个工具，如 delete_record"},
           "only_failed": {**_BOOL, "description": "true=只看失败（含被安全门拦下）"}},
          [], False, _get_audit_log),
    _tool("get_project", "读取当前项目的项目名、勾选项、各工作表数据、抬头与模板选择。",
          {}, [], False, _get_project),
    _tool("get_project_structured", "读取结构化项目数据（列头 + 行 + 按列展开的 records）。",
          {}, [], False, _get_project_structured),
    _tool("list_detection_items",
          "列出检测项目树、构件、工作表键、列数，以及 manifest 摘要"
          "（采集参数、评定规则、技能名、原始记录模板）。",
          {}, [], False, _list_detection_items),
    _tool("get_item_schema", "读取某个检测项目的填写要求、阈值和评定规则。",
          {"item": {**_STR, "description": "检测项目基础名，如“回弹法检测”"}},
          ["item"], False, _get_item_schema),

    _tool("create_project", "新建项目（会清空当前项目内存状态）。",
          {"project_name": {**_STR, "description": "项目名称"}},
          ["project_name"], True, _create_project),
    _tool("open_project", "打开项目 JSON 文件。",
          {"filepath": {**_STR, "description": "项目文件完整路径"}},
          ["filepath"], True, _open_project),
    _tool("save_project", "保存当前项目（缺省保存到当前路径或 exports）。",
          {"filepath": {**_STR, "description": "可选保存路径"}},
          [], True, _save_project),
    _tool("check_item", "勾选/取消检测项目；requires_setup 项目可传 params。",
          {"sheet_key": {**_STR, "description": "工作表键"},
           "checked": {**_BOOL, "description": "True=勾选，False=取消"},
           "params": {**_OBJ, "description": "钻芯法等参数"}},
          ["sheet_key"], True, _check_item),
    _tool("create_data_sheet",
          "创建一张数据采集表并可选写入行数据（自动计算列由后端完成）。"
          "等价于 check_item → put_rows → calc，适合对话中直接生成采集页。"
          "钻芯法/回弹钻芯修正法需传 params。",
          {"sheet_key": {**_STR,
                         "description": "精确工作表键，如 钻芯法检测（梁）"},
           "params": {**_OBJ,
                      "description": "requires_setup 参数：楼栋/构件数/芯样数/"
                                     "起始编号/设计等级/直径等"},
           "rows": _ROWS},
          ["sheet_key"], True, _create_data_sheet),
    _tool("get_sheet", "读取单个工作表的数据/列/合并/评定状态。",
          {"sheet_key": {**_STR, "description": "工作表键"}},
          ["sheet_key"], False, _get_sheet),
    _tool("put_rows", "覆盖保存单个工作表的行数据。",
          {"sheet_key": {**_STR, "description": "工作表键"},
           "rows": _ROWS},
          ["sheet_key", "rows"], True, _put_rows),

    _tool("import_sheet_excel",
          "从本机 Excel/CSV/Word 表格导入工作表行（表头自动匹配列，默认覆盖）。",
          {"sheet_key": {**_STR, "description": "工作表键"},
           "filepath": {**_STR, "description": "本机 .xlsx/.xlsm/.csv/.docx 完整路径"},
           "sheet_name": {**_STR, "description": "可选工作表名；多表工作簿留空自动选最匹配表"},
           "append": {**_BOOL, "description": "true=追加，false/省略=覆盖"}},
          ["sheet_key", "filepath"], True, _import_sheet_excel, danger=True),
    _tool("import_assessment_excel",
          "从本机 Excel/CSV/Word 表格导入回弹法/回弹钻芯修正法原始数据。",
          {"sheet_key": {**_STR, "description": "工作表键"},
           "filepath": {**_STR, "description": "本机 .xlsx/.xlsm/.csv/.docx 完整路径"},
           "sheet_name": {**_STR, "description": "可选工作表名"}},
          ["sheet_key", "filepath"], True, _import_assessment_excel, danger=True),

    _tool("get_assessment_specs", "读取 13 份提示词对应的全部评定规则摘要。",
          {}, [], False, _get_assessment_specs),
    _tool("get_assessment", "读取某个工作表的评定规则、原始数据、选项和最近结果。",
          {"sheet_key": {**_STR, "description": "工作表键"}},
          ["sheet_key"], False, _get_assessment),
    _tool("save_assessment_input", "保存评定原始数据/选项（不执行评定）。",
          {"sheet_key": {**_STR, "description": "工作表键"},
           "input": {**_OBJ, "description": "原始数据，如回弹法的 components"},
           "options": {**_OBJ, "description": "no_drawing/table_no/include_component_stats"}},
          ["sheet_key"], True, _save_assessment_input),
    _tool("run_assessment", "执行单个检测项目评定，返回结论类型/结论表述/统计。",
          {"sheet_key": {**_STR, "description": "工作表键"},
           "input": {**_OBJ, "description": "可选原始数据（回弹法等）"},
           "options": {**_OBJ, "description": "no_drawing/table_no/include_component_stats"}},
          ["sheet_key"], True, _run_assessment),
    _tool("run_all_assessments", "对全部已勾选检测项目批量评定。",
          {"sheet_keys": {"type": "array", "items": _STR}},
          [], True, _run_all_assessments),

    _tool("select_templates", "保存报告模板/原始记录模板选择。",
          {"report_template_id": {**_STR, "description": "报告模板 ID"},
           "original_template_map": {
               "type": "object", "additionalProperties": {"type": "string"},
               "description": "{工作表键: 原始记录模板 ID}"}},
          [], True, _select_templates),
    _tool("list_report_templates", "列出报告模板库。", {}, [], False,
          _list_report_templates),
    _tool("list_original_templates", "列出原始记录模板库和默认映射。", {}, [], False,
          _list_original_templates),

    _tool("generate_report",
          "按当前项目数据和选定模板生成检测报告 .docx（确定性渲染）；"
          "可用 narrative 覆盖工程概况/检测依据/结论句的文字。",
          {"template_id": {**_STR, "description": "可选报告模板 ID"},
           "narrative": {"type": "object",
                              "description": "措辞覆盖：overview 字符串 / basis 字符串数组 / conclusions 带编号的结论句数组",
                              "properties": {
                                  "overview": _STR,
                                  "basis": {"type": "array", "items": _STR},
                                  "conclusions": {"type": "array", "items": _STR},
                              }},
           "output_path": {**_STR, "description": "可选输出路径"}},
          [], True, _generate_report),
    _tool("report_facts",
          "只读：生成报告事实包（report.facts/1）——项目抬头、逐项列/行、评定结论与统计、"
          "规范清单、设备、以及确定性措辞底稿（overview/basis/conclusions）。"
          "写报告前先取事实，改写措辞后再 render_report。",
          {}, [], False, _report_facts),
    _tool("render_report",
          "按当前项目事实 + 措辞覆盖渲染报告 .docx（不调用模型）。"
          "narrative.conclusions 需保留 1.1、2.1、 这样的编号前缀。",
          {"narrative": {"type": "object",
                              "description": "措辞覆盖：overview 字符串 / basis 字符串数组 / conclusions 带编号的结论句数组",
                              "properties": {
                                  "overview": _STR,
                                  "basis": {"type": "array", "items": _STR},
                                  "conclusions": {"type": "array", "items": _STR},
                              }},
           "template_id": {**_STR, "description": "可选报告模板 ID"},
           "output_path": {**_STR, "description": "可选输出路径"}},
          [], True, _render_report),
    _tool("generate_original_record", "按检测项目和原始记录模板生成 .docx。",
          {"sheet_keys": {"type": "array", "items": _STR,
                          "description": "要生成的检测项，空=全部已勾选"},
           "template_map": {"type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "{sheet_key: 原始记录模板 ID}"}},
          [], True, _generate_original_record),
    _tool("get_report_history", "读取报告生成历史。", {}, [], False,
          _get_report_history),
    _tool("get_original_record_history", "读取原始记录生成历史。", {}, [], False,
          _get_original_history),

    _tool("load_report_document", "加载报告 .docx 的段落/表格块，供修改。",
          {"filepath": {**_STR, "description": "报告 .docx 完整路径"}},
          ["filepath"], False, _load_report_document),
    _tool("save_report_document", "保存报告段落/表格修改（默认另存新文件）。",
          {"filepath": {**_STR, "description": "原报告路径"},
           "paragraphs": {"type": "array", "items": _OBJ,
                          "description": "[{index,text}]"},
           "cells": {"type": "array", "items": _OBJ,
                     "description": "[{table,row,col,text}]"},
           "output_path": {**_STR, "description": "可选另存路径"},
           "overwrite": {**_BOOL, "description": "是否覆盖原文件（先备份）"}},
          ["filepath"], True, _save_report_document),
    _tool("replace_report_text", "报告全文查找替换（正文+表格）。",
          {"filepath": {**_STR, "description": "报告 .docx 路径"},
           "find": {**_STR, "description": "查找文本"},
           "replace": {**_STR, "description": "替换文本"},
           "overwrite": {**_BOOL, "description": "是否覆盖原文件"}},
          ["filepath", "find"], True, _replace_report_text),

    _tool("search_norms",
          "在规范库中查询条文；传入 detection_items 时优先只在该项目的依据规范里检索，"
          "命中不到会自动放开范围（filtered_out=true）。",
          {"question": {**_STR, "description": "规范问题或条号，如 5.1.2"},
           "detection_items": {"type": "array", "items": _STR,
                               "description": "检测项目名，如 回弹法检测、钻芯法检测"}},
          ["question"], False, _search_norms),
    _tool("norm_status", "读取规范库状态。", {}, [], False, _norm_status),
    _tool("norm_coverage",
          "读取规范库覆盖度：每本规范多少条、每个检测项目有几条可依、哪些项目还缺规范。",
          {}, [], False, _norm_coverage),

    _tool("get_workflow_status", "读取项目检测流程进度与下一步建议。",
          {}, [], False, _get_workflow_status),
    _tool("get_library_status",
          "读取报告模板/原始记录模板/设备/记录库/Wiki/规范库统一状态。",
          {}, [], False, _get_library_status),
    _tool("search_wiki", "在 LLM Wiki 知识库中检索检测方法、操作步骤与规则。",
          {"question": {**_STR, "description": "问题或关键词"},
           "top_k": {"type": "integer", "description": "返回页数，默认 3"},
           "detection_items": {"type": "array", "items": _STR,
                               "description": "可选检测项目名，用于加权"}},
          ["question"], False, _search_wiki),
    _tool("get_wiki_page", "读取单个 Wiki 页面全文。",
          {"page_id": {**_STR, "description": "Wiki 页面 ID"}},
          ["page_id"], False, _get_wiki_page),
    _tool("list_wiki_pages", "列出/搜索 Wiki 页面（不含全文）。",
          {"category": {**_STR, "description": "分类过滤"},
           "query": {**_STR, "description": "关键词"},
           "limit": {"type": "integer"}, "offset": {"type": "integer"}},
          [], False, _list_wiki_pages),
    _tool("list_report_records", "查询报告记录库（分页/关键词/项目）。",
          {"q": {**_STR, "description": "报告编号/文件名/模板关键词"},
           "project": {**_STR, "description": "项目名过滤"},
           "limit": {"type": "integer"}, "offset": {"type": "integer"}},
          [], False, _list_report_records),
    _tool("list_original_records", "查询原始记录库（分页/关键词/项目）。",
          {"q": {**_STR, "description": "检测项/文件名/模板关键词"},
           "project": {**_STR, "description": "项目名过滤"},
           "limit": {"type": "integer"}, "offset": {"type": "integer"}},
          [], False, _list_original_records),
    _tool("list_equipment", "查询本地设备库。",
          {"keyword": {**_STR, "description": "设备名称/编号/型号关键词"},
           "selected_only": {**_BOOL, "description": "仅报告选用设备"}},
          [], False, _list_equipment),
    _tool("select_equipment", "勾选/取消设备为报告选用。",
          {"ids": {"type": "array", "items": _STR,
                   "description": "设备 ID 列表"},
           "selected": {**_BOOL, "description": "true=选入报告"}},
          ["ids"], True, _select_equipment),
]

# ── P1 扩展工具：模板库 / 人员库 / 知识库 / 规范库 / 记录库 / 表格结构 /
#    项目 / 设备 / 配置 / 报告信息 / 扫描识别（见 mcp_tools_extra.py）──
try:
    from mcp_tools_extra import build_tools as _build_extra_tools

    TOOLS.extend(_build_extra_tools(sys.modules[__name__]))
except Exception as _e:  # noqa: BLE001 - 扩展工具失败不影响基础工具
    _log("扩展工具加载失败：%s" % _e)

_TOOL_MAP = {tool["name"]: tool for tool in TOOLS}


def _public_tools():
    return [{k: v for k, v in tool.items() if k not in ("handler", "write")}
            for tool in TOOLS]


def _call_tool(name, arguments):
    """统一入口：写确认 → 危险二次确认 → 执行 → 审计。

    安全门在这里集中执行，不依赖各 handler 自觉；被拦下的调用同样记审计。
    """
    tool = _TOOL_MAP.get(name)
    if tool is None:
        raise ToolError("未知工具：%s" % name)
    args = dict(arguments or {})
    started = time.time()
    try:
        if tool.get("write"):
            _require_confirm(args)
        _require_danger_confirm(tool, args)
        result = tool["handler"](args)
    except Exception as exc:  # noqa: BLE001 - 审计后原样抛出
        _audit_write(tool, args, False, exc, time.time() - started)
        raise
    _audit_write(tool, args, True, "", time.time() - started)
    return result


# ── MCP resources：13 份提示词 + 规则 JSON ─────────────────
def _resource_list():
    resources = [{
        "uri": "assessment://specs",
        "name": "13 项检测评定规则",
        "description": "机器可读的检测评定规则与结论模板（JSON）",
        "mimeType": "application/json",
    }]
    if os.path.isdir(_PROMPT_DIR):
        for filename in sorted(os.listdir(_PROMPT_DIR)):
            if not filename.lower().endswith(".md"):
                continue
            path = os.path.join(_PROMPT_DIR, filename)
            resources.append({
                "uri": "skill://structural-inspection/%s" % quote(filename),
                "name": filename[:-3],
                "description": "检测评定提示词/规则说明",
                "mimeType": "text/markdown",
            })
    return resources


def _read_resource(uri):
    from urllib.parse import unquote
    if uri == "assessment://specs":
        specs = _request("GET", "/assessment/specs")
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(specs, ensure_ascii=False, indent=2),
            }]
        }
    prefix = "skill://structural-inspection/"
    if uri.startswith(prefix):
        filename = unquote(uri[len(prefix):])
        path = os.path.join(_PROMPT_DIR, os.path.basename(filename))
        if not os.path.isfile(path):
            raise ToolError("资源不存在：%s" % uri)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "text/markdown",
                "text": text,
            }]
        }
    raise ToolError("资源不存在：%s" % uri)


# ── JSON-RPC / stdio ──────────────────────────────────────
def _read_message():
    stream = sys.stdin.buffer
    line = stream.readline()
    if not line:
        return None
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return _read_message()
    if text.lower().startswith("content-length:"):
        try:
            length = int(text.split(":", 1)[1].strip())
        except ValueError:
            return None
        while True:
            header = stream.readline()
            if not header or not header.strip():
                break
        data = stream.read(length)
        return json.loads(data.decode("utf-8"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _log("忽略非 JSON 输入：%s" % text[:120])
        return _read_message()


def _write_message(payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(data + "\n")
    sys.stdout.flush()


def _ok(msg_id, result):
    _write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _error(msg_id, code, message):
    _write_message({"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": code, "message": message}})


def _handle(msg):
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    if method is None:
        return  # response from client
    if msg_id is None:
        # notification: initialized / cancelled / progress...
        return
    try:
        if method == "initialize":
            requested = params.get("protocolVersion") or "2025-06-18"
            _ok(msg_id, {
                "protocolVersion": requested,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME,
                               "version": SERVER_VERSION},
                "instructions": (
                    "工程检测harness 工具（Harness 版）。先 get_workflow_status / "
                    "get_project / list_detection_items；录入数据前先向用户确认；"
                    "评定用 run_assessment；生成/保存/删除等写操作必须传 "
                    "confirm=true。新建采集页并填数优先用 create_data_sheet；"
                    "检测方法/操作步骤问题可先用 search_wiki / "
                    "search_norms 查本地知识库；记录库用 list_report_records / "
                    "list_original_records。"),
            })
        elif method == "ping":
            _ok(msg_id, {})
        elif method == "tools/list":
            _ok(msg_id, {"tools": _public_tools()})
        elif method == "tools/call":
            name = params.get("name") or ""
            arguments = params.get("arguments") or {}
            try:
                result = _call_tool(name, arguments)
                # MCP 规定 structuredContent 必须是对象；列表类结果（如
                # list_report_templates）包一层 items，否则客户端校验失败。
                if not isinstance(result, dict):
                    structured = {"items": result}
                else:
                    structured = result
                _ok(msg_id, {
                    "content": [{"type": "text",
                                 "text": json.dumps(result, ensure_ascii=False,
                                                    indent=2)}],
                    "structuredContent": structured,
                    "isError": False,
                })
            except ToolError as e:
                _ok(msg_id, {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                })
        elif method == "resources/list":
            _ok(msg_id, {"resources": _resource_list()})
        elif method == "resources/read":
            _ok(msg_id, _read_resource(params.get("uri") or ""))
        elif method in ("shutdown", "exit"):
            _ok(msg_id, {})
            raise SystemExit(0)
        else:
            _error(msg_id, -32601, "未知方法：%s" % method)
    except ToolError as e:
        _error(msg_id, -32000, str(e))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        _error(msg_id, -32603, "服务器内部错误：%s" % e)


def main():
    if "--list-tools" in sys.argv:
        print(json.dumps([{"name": t["name"], "description": t["description"]}
                          for t in TOOLS], ensure_ascii=False, indent=2))
        return 0
    if "--check" in sys.argv:
        try:
            print(json.dumps(_health({}), ensure_ascii=False, indent=2))
            return 0
        except ToolError as e:
            print(str(e))
            return 2
    _log("MCP server starting; API=%s; tools=%d" % (BASE_URL, len(TOOLS)))
    while True:
        try:
            msg = _read_message()
        except KeyboardInterrupt:
            break
        except Exception as e:  # noqa: BLE001
            _log("读取消息失败：%s" % e)
            continue
        if msg is None:
            break
        try:
            _handle(msg)
        except SystemExit:
            break
        except Exception as e:  # noqa: BLE001
            _log("处理消息失败：%s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
