# -*- coding: utf-8 -*-
"""MCP 扩展工具（P1）：模板库 / 人员库 / 知识库 / 规范庫 / 记录库 /
表格结构 / 项目 / 设备 / 配置 / 报告信息 / 扫描历史 / 检测项建议。

本模块只做后端 API 的薄封装，业务逻辑仍在 report_generator 与 FastAPI 侧；
由 webapp/mcp_server.py 在启动时调用 build_tools(mcp_server) 合并进工具表。

写操作统一由 mcp_server._tool 注入必填 confirm，并由后端二次校验。
"""

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_OBJ = {"type": "object"}
_STRS = {"type": "array", "items": {"type": "string"}}
_ROWS = {
    "type": "array",
    "description": "二维行数据 [[单元格, ...], ...]",
    "items": {"type": "array"},
}
_MERGES = {
    "type": "array",
    "description": "[{row, col, rowspan, colspan}]，行列从 0 开始",
    "items": {"type": "object"},
}


def _need(api, args, key, label=""):
    value = str(args.get(key) or "").strip()
    if not value:
        raise api.ToolError("%s 不能为空" % (label or key))
    return value


def _seg(api, value):
    return api.quote(str(value), safe="")


def _list(value):
    if isinstance(value, str):
        return [value]
    return [x for x in (value or []) if str(x).strip()]


# ── 模板库 ────────────────────────────────────────────────
def _get_report_template(api, args):
    tid = _need(api, args, "template_id", "报告模板 ID")
    return api._request("GET", "/templates/report/" + _seg(api, tid))


def _upload_report_template(api, args):
    return api._upload("/templates/report/upload", args.get("filepath"),
                       allowed=(".zip",))


def _set_default_report_template(api, args):
    tid = _need(api, args, "template_id", "报告模板 ID")
    return api._request("POST", "/templates/report/" + _seg(api, tid) + "/default")


def _delete_report_template(api, args):
    tid = _need(api, args, "template_id", "报告模板 ID")
    return api._request("DELETE", "/templates/report/" + _seg(api, tid))


def _upload_original_template(api, args):
    return api._upload(
        "/templates/original/upload", args.get("filepath"),
        data={
            "name": args.get("name") or "",
            "code": args.get("code") or "",
            "detection_items": api.json.dumps(_list(args.get("detection_items")),
                                             ensure_ascii=False),
            "set_default": "true" if args.get("set_default") else "false",
        },
        allowed=(".docx", ".doc"))


def _set_original_template_defaults(api, args):
    tid = _need(api, args, "template_id", "原始记录模板 ID")
    return api._request("POST", "/templates/original/" + _seg(api, tid) + "/default",
                        json_body={"items": _list(args.get("items"))})


def _delete_original_template(api, args):
    tid = _need(api, args, "template_id", "原始记录模板 ID")
    return api._request("DELETE", "/templates/original/" + _seg(api, tid))


def _list_original_template_defaults(api, args):
    return api._request("GET", "/templates/original/defaults")


# ── 人员库 ────────────────────────────────────────────────
def _personnel_body(args):
    body = {}
    for key in ("name", "role", "cert_no", "phone", "organization",
                "note"):
        if args.get(key) is not None:
            body[key] = str(args.get(key) or "")
    if args.get("active") is not None:
        body["active"] = bool(args.get("active"))
    return body


def _list_personnel(api, args):
    return api._request("GET", "/personnel", params={
        "q": args.get("q") or "",
        "role": args.get("role") or "",
        "active_only": "true" if args.get("active_only") else "false",
        "limit": int(args.get("limit") or 200),
        "offset": int(args.get("offset") or 0),
    })


def _get_personnel(api, args):
    pid = _need(api, args, "person_id", "人员 ID")
    return api._request("GET", "/personnel/" + _seg(api, pid))


def _create_personnel(api, args):
    if not str(args.get("name") or "").strip():
        raise api.ToolError("name 不能为空")
    return api._request("POST", "/personnel", json_body=_personnel_body(args))


def _update_personnel(api, args):
    pid = _need(api, args, "person_id", "人员 ID")
    body = _personnel_body(args)
    if not body:
        raise api.ToolError("至少提供一个要修改的字段")
    return api._request("PUT", "/personnel/" + _seg(api, pid), json_body=body)


def _delete_personnel(api, args):
    pid = _need(api, args, "person_id", "人员 ID")
    return api._request("DELETE", "/personnel/" + _seg(api, pid))


def _import_personnel(api, args):
    return api._upload("/personnel/import", args.get("filepath"))


# ── 知识库 Wiki ───────────────────────────────────────────
def _save_wiki_page(api, args):
    title = str(args.get("title") or "").strip()
    content = str(args.get("content") or "")
    if not title and not args.get("id"):
        raise api.ToolError("title 不能为空")
    if not content and not args.get("id"):
        raise api.ToolError("content 不能为空")
    body = {
        "title": title,
        "category": args.get("category") or "未分类",
        "summary": args.get("summary") or "",
        "content": content,
        "tags": _list(args.get("tags")),
        "detection_items": _list(args.get("detection_items")),
        "source": args.get("source") or "",
    }
    if args.get("id"):
        body["id"] = str(args.get("id"))
    return api._request("POST", "/wiki/pages", json_body=body)


def _delete_wiki_page(api, args):
    pid = _need(api, args, "page_id", "Wiki 页面 ID")
    return api._request("DELETE", "/wiki/pages/" + _seg(api, pid))


def _import_wiki_files(api, args):
    items = _list(args.get("filepaths"))
    if not items:
        raise api.ToolError("filepaths 不能为空")
    return api._upload_many("/wiki/import", items, data={
        "category": args.get("category") or "未分类",
        "detection_items": api.json.dumps(_list(args.get("detection_items")),
                                         ensure_ascii=False),
    })


def _get_wiki_context(api, args):
    question = _need(api, args, "question", "问题")
    return api._request("POST", "/wiki/context", json_body={
        "question": question,
        "top_k": int(args.get("top_k") or 3),
        "detection_items": _list(args.get("detection_items")),
    })


# ── 规范库 ────────────────────────────────────────────────
def _query_norms(api, args):
    question = _need(api, args, "question", "问题")
    return api._request("POST", "/normqa/query",
                        json_body={"question": question})


def _explain_norms(api, args):
    question = _need(api, args, "question", "问题")
    return api._request("POST", "/normqa/explain", json_body={
        "question": question,
        "clauses": args.get("clauses") or [],
    })


def _import_norms(api, args):
    items = _list(args.get("filepaths"))
    if not items:
        raise api.ToolError("filepaths 不能为空")
    mode = str(args.get("mode") or "append").strip().lower()
    if mode not in ("append", "rebuild"):
        raise api.ToolError("mode 只支持 append 或 rebuild")
    return api._upload_many("/normqa/import", items, data={"mode": mode})


# ── 记录库 ────────────────────────────────────────────────
def _get_records_stats(api, args):
    return api._request("GET", "/records/stats")


def _find_similar_records(api, args):
    return api._request("GET", "/records/similar", params={
        "q": args.get("q") or "",
        "kind": args.get("kind") or "both",
        "project": args.get("project") or "",
        "limit": int(args.get("limit") or 10),
    })


def _list_record_sheets(api, args):
    record_id = _need(api, args, "record_id", "原始记录 ID")
    return api._request(
        "GET", "/records/original/" + _seg(api, record_id) + "/sheets")


def _reuse_original_record(api, args):
    record_id = _need(api, args, "record_id", "原始记录 ID")
    return api._request(
        "POST", "/records/original/" + _seg(api, record_id) + "/reuse",
        json_body={"sheet_key": args.get("sheet_key") or "",
                   "append": bool(args.get("append"))})


def _get_report_record(api, args):
    rid = _need(api, args, "record_id", "记录 ID")
    return api._request("GET", "/records/report/" + _seg(api, rid))


def _get_original_record(api, args):
    rid = _need(api, args, "record_id", "记录 ID")
    return api._request("GET", "/records/original/" + _seg(api, rid))


def _get_original_record_snapshot(api, args):
    rid = _need(api, args, "record_id", "记录 ID")
    return api._request("GET", "/records/original/" + _seg(api, rid) + "/snapshot")


def _delete_record(api, args):
    kind = str(args.get("kind") or "").strip().lower()
    if kind not in ("report", "original"):
        raise api.ToolError("kind 只支持 report 或 original")
    rid = _need(api, args, "record_id", "记录 ID")
    return api._request("DELETE", "/records/" + kind + "/" + _seg(api, rid))


# ── 表格结构 ──────────────────────────────────────────────
def _merge_sheet_cells(api, args):
    key = _need(api, args, "sheet_key", "工作表键")
    merges = args.get("merges")
    if not isinstance(merges, list) or not merges:
        raise api.ToolError("merges 必须是非空数组")
    return api._request("POST", "/sheet/" + _seg(api, key) + "/merge",
                        json_body={"merges": merges,
                                   "append": bool(args.get("append"))})


def _smart_merge_sheet(api, args):
    key = _need(api, args, "sheet_key", "工作表键")
    columns = args.get("columns")
    body = {"columns": columns} if isinstance(columns, list) and columns else None
    return api._request("POST", "/sheet/" + _seg(api, key) + "/smart_merge",
                        json_body=body)


def _row_edit(api, args, action):
    key = _need(api, args, "sheet_key", "工作表键")
    index = args.get("index")
    if index is None:
        raise api.ToolError("index 不能为空")
    return api._request("POST", "/sheet/" + _seg(api, key) + "/rows/" + action,
                        json_body={"index": int(index),
                                   "count": max(1, int(args.get("count") or 1))})


def _insert_sheet_rows(api, args):
    return _row_edit(api, args, "insert")


def _delete_sheet_rows(api, args):
    return _row_edit(api, args, "delete")


def _fill_down_sheet(api, args):
    key = _need(api, args, "sheet_key", "工作表键")
    cols = args.get("col_keys")
    if not isinstance(cols, list) or not cols:
        raise api.ToolError("col_keys 必须是非空数组（列序号或列头）")
    return api._request("POST", "/sheet/" + _seg(api, key) + "/fill_down",
                        json_body={"col_keys": cols,
                                   "row_from": int(args.get("row_from") or 0),
                                   "row_to": int(args.get("row_to") or 0)})


def _recalc_sheet(api, args):
    key = _need(api, args, "sheet_key", "工作表键")
    body = {}
    if args.get("rows") is not None:
        body["rows"] = args.get("rows")
    return api._request("POST", "/sheet/" + _seg(api, key) + "/calc",
                        json_body=body)


def _get_project_columns(api, args):
    key = _need(api, args, "sheet_key", "工作表键")
    return api._request("GET", "/project/columns/" + _seg(api, key))


# ── 项目 ──────────────────────────────────────────────────
def _rename_project(api, args):
    name = _need(api, args, "project_name", "项目名")
    return api._request("PUT", "/project/name",
                        json_body={"project_name": name})


def _get_project_history(api, args):
    return api._request("GET", "/project/history")


def _list_projects(api, args):
    return api._request("GET", "/project/list")


def _current_project(api, args):
    return api._request("GET", "/project/current")


def _activate_project(api, args):
    filepath = _need(api, args, "filepath", "工程文件路径")
    return api._request("POST", "/project/activate",
                        json_body={"filepath": filepath})


def _list_project_backups(api, args):
    return api._request("GET", "/project/backups", params={
        "limit": int(args.get("limit") or 50)})


def _restore_project(api, args):
    filepath = _need(api, args, "filepath", "备份文件路径")
    return api._request("POST", "/project/restore",
                        json_body={"filepath": filepath})


def _get_project_items(api, args):
    return api._request("GET", "/project/items")


def _get_item_contract(api, args):
    item = _need(api, args, "item", "检测项目名")
    return api._request("GET", "/project/item_contract", params={"item": item})


def _suggest_detection_items(api, args):
    text = _need(api, args, "text", "需求描述")
    return api._request("GET", "/project/suggest", params={"text": text})


# ── 设备 ──────────────────────────────────────────────────
def _equipment_status(api, args):
    return api._request("GET", "/equipment/status")


def _delete_equipment(api, args):
    ids = _list(args.get("ids"))
    if not ids:
        raise api.ToolError("ids 不能为空")
    return api._request("POST", "/equipment/library/delete",
                        json_body={"ids": ids})


def _sync_remote_equipment(api, args):
    ids = _list(args.get("ids"))
    if not ids and not args.get("all"):
        raise api.ToolError("ids 不能为空（或传 all=true 全量同步）")
    return api._request("POST", "/equipment/sync",
                        json_body={"ids": ids, "all": bool(args.get("all"))})


def _recommend_equipment(api, args):
    return api._request("GET", "/equipment/recommend", params={
        "limit": max(1, min(int(args.get("limit") or 20), 100)),
    })


# ── 配置 ──────────────────────────────────────────────────
def _get_config(api, args):
    return api._request("GET", "/config")


def _put_config(api, args):
    section = _need(api, args, "section", "配置段")
    values = args.get("values")
    if not isinstance(values, dict) or not values:
        raise api.ToolError("values 必须是非空对象")
    return api._request("PUT", "/config",
                        json_body={"section": section, "values": values})


# ── 采集入口 ──────────────────────────────────────────────
def _recognize_file(api, args):
    filepath = _need(api, args, "filepath", "文件路径")
    return api._request("GET", "/ingest/recognize", params={
        "filepath": filepath,
        "sheet_name": args.get("sheet_name") or "",
    })


def _import_file(api, args):
    filepath = _need(api, args, "filepath", "文件路径")
    sheet_key = _need(api, args, "sheet_key", "工作表键")
    return api._request("POST", "/ingest/import", json_body={
        "filepath": filepath,
        "sheet_key": sheet_key,
        "sheet_name": args.get("sheet_name") or "",
        "append": bool(args.get("append")),
    })


# ── 报告信息 ──────────────────────────────────────────────
def _report_auto_info(api, args):
    return api._request("POST", "/report/auto_info")


def _get_report_info(api, args):
    return api._request("GET", "/report/info")


def _put_report_info(api, args):
    info = args.get("report_info")
    if not isinstance(info, dict) or not info:
        raise api.ToolError("report_info 必须是非空对象")
    return api._request("PUT", "/report/info", json_body={"report_info": info})


def _next_report_no(api, args):
    return api._request("GET", "/report/next_no")


def _match_report_template(api, args):
    return api._request("GET", "/report/match_template")


# ── 扫描识别 ──────────────────────────────────────────────
def _scan_submit(api, args):
    filepath = _need(api, args, "filepath", "文件路径")
    return api._request("POST", "/scan/submit", json_body={
        "filepath": filepath,
        "detection_item": args.get("detection_item") or "",
    })


def _scan_job(api, args):
    job_id = _need(api, args, "job_id", "作业 ID")
    return api._request("GET", "/scan/job/" + _seg(api, job_id))


def _scan_jobs(api, args):
    return api._request("GET", "/scan/jobs", params={
        "limit": max(1, min(int(args.get("limit") or 20), 50)),
    })


def _scan_history(api, args):
    return api._request("GET", "/scan/history")


def _scan_vision_models(api, args):
    return api._request("GET", "/scan/vision_models")


def _scan_fill(api, args):
    key = _need(api, args, "sheet_key", "工作表键")
    records = args.get("records")
    if not isinstance(records, list) or not records:
        raise api.ToolError("records 必须是非空二维数组")
    return api._request("POST", "/scan/fill",
                        json_body={"sheet_key": key, "records": records})


def build_tools(api):
    """用 mcp_server 的 _tool/_request/_upload/_upload_many 构造扩展工具。

    handler 内通过 api.json 复用 mcp_server 已导入的 json 模块。
    """

    def tool(name, description, props, required, write, handler,
             danger=False):
        def run(args):
            # 与基础工具一致：写操作必须在参数里显式 confirm
            if write:
                api._require_confirm(args)
            return handler(api, args)
        return api._tool(name, description, props, required, write, run,
                         danger=danger)

    return [
        # ── 模板库 ──
        tool("get_report_template", "读取单个报告模板的章节与文件清单。",
             {"template_id": {**_STR, "description": "报告模板 ID"}},
             ["template_id"], False, _get_report_template),
        tool("upload_report_template",
             "导入报告模板包（.zip，含 manifest 与各章节 docx）。",
             {"filepath": {**_STR, "description": "本机 .zip 完整路径"}},
             ["filepath"], True, _upload_report_template),
        tool("set_default_report_template", "把某个报告模板设为默认模板。",
             {"template_id": {**_STR, "description": "报告模板 ID"}},
             ["template_id"], True, _set_default_report_template),
        tool("delete_report_template", "删除报告模板（内置模板不可删）。",
             {"template_id": {**_STR, "description": "报告模板 ID"}},
             ["template_id"], True, _delete_report_template, danger=True),
        tool("upload_original_template",
             "导入原始记录模板（.docx/.doc，可按检测项绑定默认）。",
             {"filepath": {**_STR, "description": "本机 .docx/.doc 完整路径"},
              "name": {**_STR, "description": "模板名称，缺省取文件名"},
              "code": {**_STR, "description": "检测编号，如 JJ0224005"},
              "detection_items": {**_STRS, "description": "适用的检测项目基础名列表"},
              "set_default": {**_BOOL, "description": "true=设为这些项目的默认模板"}},
             ["filepath"], True, _upload_original_template),
        tool("set_original_template_defaults",
             "把某个原始记录模板设为指定检测项目的默认模板。",
             {"template_id": {**_STR, "description": "原始记录模板 ID"},
              "items": {**_STRS, "description": "检测项目基础名列表"}},
             ["template_id", "items"], True, _set_original_template_defaults),
        tool("delete_original_template", "删除原始记录模板（内置模板不可删）。",
             {"template_id": {**_STR, "description": "原始记录模板 ID"}},
             ["template_id"], True, _delete_original_template, danger=True),
        tool("list_original_template_defaults",
             "读取检测项目到原始记录模板的默认映射。",
             {}, [], False, _list_original_template_defaults),

        # ── 人员库 ──
        tool("list_personnel", "查询人员库（姓名/岗位/证书/电话）。",
             {"q": {**_STR, "description": "姓名或证书关键词"},
              "role": {**_STR, "description": "岗位过滤"},
              "active_only": {**_BOOL, "description": "只看在用人员"},
              "limit": _INT, "offset": _INT},
             [], False, _list_personnel),
        tool("get_personnel", "读取单个人员档案。",
             {"person_id": {**_STR, "description": "人员 ID"}},
             ["person_id"], False, _get_personnel),
        tool("create_personnel", "新增人员档案。",
             {"name": {**_STR, "description": "姓名"},
              "role": {**_STR, "description": "岗位：检测/审核/批准/见证等"},
              "cert_no": {**_STR, "description": "证书编号"},
              "phone": {**_STR, "description": "电话"},
              "organization": {**_STR, "description": "所属单位"},
              "note": {**_STR, "description": "备注"},
              "active": {**_BOOL, "description": "是否在用，默认 true"}},
             ["name"], True, _create_personnel),
        tool("update_personnel", "修改人员档案（只改传入字段）。",
             {"person_id": {**_STR, "description": "人员 ID"},
              "name": _STR, "role": _STR, "cert_no": _STR, "phone": _STR,
              "organization": _STR, "note": _STR, "active": _BOOL},
             ["person_id"], True, _update_personnel),
        tool("delete_personnel", "删除人员档案。",
             {"person_id": {**_STR, "description": "人员 ID"}},
             ["person_id"], True, _delete_personnel, danger=True),
        tool("import_personnel",
             "从 Excel/CSV/Word 表格批量导入人员（表头自动识别）。",
             {"filepath": {**_STR, "description": "本机 .xlsx/.xlsm/.csv/.docx 完整路径"}},
             ["filepath"], True, _import_personnel),

        # ── 知识库 Wiki ──
        tool("save_wiki_page",
             "新建或更新 Wiki 知识页（传 id 为更新）。",
             {"id": {**_STR, "description": "页面 ID；留空为新建"},
              "title": {**_STR, "description": "标题"},
              "category": {**_STR, "description": "分类，默认未分类"},
              "summary": {**_STR, "description": "摘要"},
              "content": {**_STR, "description": "正文（Markdown）"},
              "tags": {**_STRS, "description": "标签"},
              "detection_items": {**_STRS, "description": "关联检测项目基础名"},
              "source": {**_STR, "description": "来源说明"}},
             [], True, _save_wiki_page),
        tool("delete_wiki_page", "删除 Wiki 页面（内置页面不可删）。",
             {"page_id": {**_STR, "description": "Wiki 页面 ID"}},
             ["page_id"], True, _delete_wiki_page, danger=True),
        tool("import_wiki_files",
             "导入知识文件到 Wiki（.md/.markdown/.txt/.docx，可多选）。",
             {"filepaths": {**_STRS, "description": "本机文件路径列表"},
              "category": {**_STR, "description": "分类"},
              "detection_items": {**_STRS, "description": "关联检测项目"}},
             ["filepaths"], True, _import_wiki_files),
        tool("get_wiki_context",
             "检索 Wiki + 规范条文并拼成问答上下文块。",
             {"question": {**_STR, "description": "问题或关键词"},
              "top_k": _INT, "detection_items": _STRS},
             ["question"], False, _get_wiki_context),

        # ── 规范库 ──
        tool("query_norms",
             "规范条文检索（条号精确/自然语言/术语候选）。",
             {"question": {**_STR, "description": "规范问题或条号，如 6.3.1"}},
             ["question"], False, _query_norms),
        tool("explain_norms",
             "基于已检索条文生成规范解释（需要本地模型）。",
             {"question": {**_STR, "description": "问题"},
              "clauses": {"type": "array", "items": _OBJ,
                          "description": "query_norms 返回的条文对象，留空自动检索"}},
             ["question"], False, _explain_norms),
        tool("import_norms",
             "导入规范文件（.md/.markdown/.txt/.docx，可多选）。",
             {"filepaths": {**_STRS, "description": "本机文件路径列表"},
              "mode": {**_STR, "description": "append（增量）或 rebuild（全量重建）"}},
             ["filepaths"], True, _import_norms, danger=True),

        # ── 记录库 ──
        tool("get_records_stats", "读取报告/原始记录库统计。",
             {}, [], False, _get_records_stats),
        tool("find_similar_records",
             "按项目名/检测项/模板/报告编号/结论检索历史报告与原始记录，返回相关度、"
             "命中字段与（有快照时的）历史结论。做新项目前先查有没有可复用的历史。",
             {"q": {**_STR, "description": "关键词：项目名、检测项、模板、报告编号或结论"},
              "kind": {**_STR, "description": "both（默认）/ report / original"},
              "project": {**_STR, "description": "限定项目名的模糊过滤"},
              "limit": _INT},
             [], False, _find_similar_records),
        tool("list_record_sheets",
             "列出某条原始记录快照里可复用的表：列头、行数、当时的结论、以及"
             "与当前列定义的兼容性（缺列/多列/是否要重排）。",
             {"record_id": {**_STR, "description": "原始记录 ID"}},
             ["record_id"], False, _list_record_sheets),
        tool("reuse_original_record",
             "把历史原始记录的某张表复制到当前工程（默认覆盖，append=true 追加）："
             "按当前列名对齐，恢复当时的钻芯参数与评定原始输入，并立即重算。",
             {"record_id": {**_STR, "description": "原始记录 ID"},
              "sheet_key": {**_STR, "description": "可选：快照里的表名，缺省取第一张"},
              "append": {**_BOOL, "description": "true=追加，缺省覆盖"}},
             ["record_id"], True, _reuse_original_record, danger=True),
        tool("get_report_record", "读取单份报告记录详情。",
             {"record_id": {**_STR, "description": "记录 ID"}},
             ["record_id"], False, _get_report_record),
        tool("get_original_record", "读取单份原始记录详情。",
             {"record_id": {**_STR, "description": "记录 ID"}},
             ["record_id"], False, _get_original_record),
        tool("get_original_record_snapshot",
             "读取原始记录生成时的工程快照（可用于复用历史数据）。",
             {"record_id": {**_STR, "description": "记录 ID"}},
             ["record_id"], False, _get_original_record_snapshot),
        tool("delete_record", "删除报告或原始记录条目（不会删除磁盘文件）。",
             {"kind": {**_STR, "description": "report 或 original"},
              "record_id": {**_STR, "description": "记录 ID"}},
             ["kind", "record_id"], True, _delete_record, danger=True),

        # ── 表格结构 ──
        tool("merge_sheet_cells",
             "合并单元格（服务端校验重叠/越界）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "merges": _MERGES,
              "append": {**_BOOL, "description": "true=追加到现有合并"}},
             ["sheet_key", "merges"], True, _merge_sheet_cells),
        tool("smart_merge_sheet",
             "按当前数据自动推算表头/构件合并并应用；columns 给定时只合并这些列（0-based 下标）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "columns": {"type": "array", "items": {"type": "integer"},
                          "description": "只合并的列下标；省略=全部候选分组列"}},
             ["sheet_key"], True, _smart_merge_sheet),
        tool("insert_sheet_rows", "在指定行前插入空行（合并区域随之调整）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "index": _INT, "count": _INT},
             ["sheet_key", "index"], True, _insert_sheet_rows),
        tool("delete_sheet_rows", "删除指定行（合并区域随之调整）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "index": _INT, "count": _INT},
             ["sheet_key", "index"], True, _delete_sheet_rows, danger=True),
        tool("fill_down_sheet",
             "把首行值向下填充到指定列区间（等价 Ctrl+D）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "col_keys": {"type": "array", "description": "列序号或列头列表"},
              "row_from": _INT, "row_to": _INT},
             ["sheet_key", "col_keys"], True, _fill_down_sheet),
        tool("recalc_sheet",
             "重算整张工作表的计算列（自动计算/钻芯法专属重算）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "rows": {**_ROWS, "description": "可选：用这批行替换后再重算"}},
             ["sheet_key"], True, _recalc_sheet),
        tool("get_project_columns", "读取工作表的列头定义。",
             {"sheet_key": {**_STR, "description": "工作表键"}},
             ["sheet_key"], False, _get_project_columns),

        # ── 项目 ──
        tool("rename_project", "修改当前项目名。",
             {"project_name": {**_STR, "description": "新项目名"}},
             ["project_name"], True, _rename_project),
        tool("get_project_history", "读取历史工程列表与保存位置。",
             {}, [], False, _get_project_history),
        tool("current_project",
             "读取当前工程的显式身份：名称、文件路径、勾选项、表数与已评定数。"
             "多工程切换前先确认当前在哪个工程。",
             {}, [], False, _current_project),
        tool("list_projects",
             "列出可切换的历史工程（自动备份/会话工程/历史保存/项目文件），含来源、"
             "修改时间、勾选数与工作表数。",
             {}, [], False, _list_projects),
        tool("activate_project",
             "把指定工程文件切换为当前工程（等价于打开该工程）。",
             {"filepath": {**_STR, "description": "list_projects 返回的 filepath"}},
             ["filepath"], True, _activate_project),
        tool("list_project_backups",
             "列出自动备份与恢复前快照（人工回退用）：文件、大小、修改时间。",
             {"limit": _INT},
             [], False, _list_project_backups),
        tool("restore_project",
             "从备份恢复工程：先把当前工程另存为 restore_<时间戳>.json，再加载备份。",
             {"filepath": {**_STR, "description": "list_project_backups 返回的 filepath"}},
             ["filepath"], True, _restore_project, danger=True),
        tool("get_project_items", "读取左侧检测项目树（结构类型→项目→构件）。",
             {}, [], False, _get_project_items),
        tool("get_item_contract",
             "读取检测项目的完整契约：采集参数（含默认值与校验）、表格列、导入表头别名、"
             "评定规则、报告设备、原始记录模板与对应技能。建表/导入前先看这个。",
             {"item": {**_STR, "description": "检测项目名或工作表键，如 钻芯法检测（梁）"}},
             ["item"], False, _get_item_contract),
        tool("suggest_detection_items",
             "把一句话需求识别成检测项目/构件/工作表键与建议页面（规则匹配，不调模型）。",
             {"text": {**_STR, "description": "用户原话，如“录回弹法梁的数据”"}},
             ["text"], False, _suggest_detection_items),

        # ── 设备 ──
        tool("equipment_status", "读取设备库/远程登录状态。",
             {}, [], False, _equipment_status),
        tool("delete_equipment", "从本地设备库删除设备。",
             {"ids": _STRS},
             ["ids"], True, _delete_equipment, danger=True),
        tool("sync_remote_equipment",
             "把远程设备同步到本地库（需先在后端登录设备系统）。",
             {"ids": _STRS, "all": {**_BOOL, "description": "true=全量同步"}},
             [], True, _sync_remote_equipment),
        tool("recommend_equipment",
             "按已勾选检测项目推荐在用设备：返回扁平设备行（equipment）与逐项目明细"
             "（items：需要什么仪器、候选设备、当天用了几次、为什么推荐/不可用、缺什么）。"
             "不占用当日额度。",
             {"limit": _INT},
             [], False, _recommend_equipment),

        # ── 配置 ──
        tool("get_config", "读取系统配置（密钥自动掩码）。",
             {}, [], False, _get_config),
        tool("put_config", "修改系统配置段（OCR/模型/存储等）。",
             {"section": {**_STR, "description": "配置段：ocr/llm/storage/server/match"},
              "values": {**_OBJ, "description": "该段要更新的键值"}},
             ["section", "values"], True, _put_config),

        # ── 采集入口 ──
        tool("recognize_file",
             "识别一份原始记录文件：类型（表格/知识/扫描）、最可能的检测项目与构件、"
             "列匹配情况与预览。只读，不改工程。支持 .xlsx/.xlsm/.csv/.docx/.doc，"
             ".pdf/图片只识别为扫描件。",
             {"filepath": {**_STR, "description": "本机文件完整路径（与后端同一台机器）"},
              "sheet_name": {**_STR, "description": "可选：Excel 工作表名"}},
             ["filepath"], False, _recognize_file),
        tool("import_file",
             "把文件按表头匹配导入指定工作表（.doc 自动转换），导入后立即重算并勾选。",
             {"filepath": {**_STR, "description": "本机文件完整路径"},
              "sheet_key": {**_STR, "description": "目标工作表键，如 回弹法检测(主要来源为仪器数据，可选用)（梁）"},
              "sheet_name": {**_STR, "description": "可选：Excel 工作表名"},
              "append": {**_BOOL, "description": "true=追加，缺省覆盖"}},
             ["filepath", "sheet_key"], True, _import_file, danger=True),

        # ── 报告信息 ──
        tool("report_auto_info",
             "自动整理报告信息与二~五章内容，并推荐报告模板（会写项目抬头）。",
             {}, [], True, _report_auto_info),
        tool("get_report_info", "读取当前项目报告抬头信息。",
             {}, [], False, _get_report_info),
        tool("put_report_info", "保存报告抬头信息（工程概况、委托方、日期等）。",
             {"report_info": {**_OBJ, "description": "要保存的抬头字段"}},
             ["report_info"], True, _put_report_info),
        tool("next_report_no", "按 前缀-年份-序号 推算下一个报告编号。",
             {}, [], False, _next_report_no),
        tool("match_report_template",
             "给报告模板库打分：返回当前生效模板（effective）、最佳匹配（best_fit）、"
             "每份模板的分数/覆盖检测项/缺失章节与依据，以及是否建议切换（recommend_switch）。",
             {}, [], False, _match_report_template),

        # ── 扫描识别 ──
        tool("scan_submit",
             "提交扫描件/图片的异步 OCR 识别作业（直接传本机路径，秒回 job_id）。"
             "识别较慢，用 scan_job 轮询，done 后用 scan_fill 回填工作表。",
             {"filepath": {**_STR, "description": "本机图片/PDF 完整路径"},
              "detection_item": {**_STR,
                                 "description": "可选：指定检测项目名，留空由 AI 判定"}},
             ["filepath"], True, _scan_submit),
        tool("scan_job",
             "读取 OCR 作业状态；done 时返回 rows/columns/复核警告。",
             {"job_id": {**_STR, "description": "scan_submit 返回的作业 ID"}},
             ["job_id"], False, _scan_job),
        tool("scan_jobs", "列出最近的 OCR 作业（不含识别结果）。",
             {"limit": _INT},
             [], False, _scan_jobs),
        tool("scan_history", "读取扫描识别历史记录。",
             {}, [], False, _scan_history),
        tool("scan_vision_models", "读取本地可用的视觉（多模态）模型列表。",
             {}, [], False, _scan_vision_models),
        tool("scan_fill",
             "把识别结果行回填到工作表（工作表不存在时自动建表并勾选）。",
             {"sheet_key": {**_STR, "description": "工作表键"},
              "records": _ROWS},
             ["sheet_key", "records"], True, _scan_fill),
    ]
