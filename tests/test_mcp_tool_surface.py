# -*- coding: utf-8 -*-
"""MCP 工具面冒烟（P1）：工具表完整性 + 新增工具可用性。

三部分：
1. 结构校验：命名、描述、schema、必填项、confirm 注入、annotations 一致；
2. 分类校验：写工具必须要求 confirm，读工具不得要求 confirm；新增工具名齐全；
3. 可用性：只读工具对运行中的后端做真实调用；新增的 3 个只读端点
   （match_report_template / recommend_equipment / suggest_detection_items）
   直接调用后端函数验证（旧后端进程未重启时也不会误报）。

运行：python test_mcp_tool_surface.py
后端未运行时第 3 部分自动 SKIP。
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP = os.path.join(ROOT, "webapp")
sys.path.insert(0, WEBAPP)

import mcp_server  # noqa: E402

# 本测试会真实调用写工具做校验，审计必须切到临时目录
_AUDIT_TMP = tempfile.mkdtemp(prefix="audit_")
mcp_server._AUDIT_DIR = _AUDIT_TMP
mcp_server._AUDIT_FILE = os.path.join(_AUDIT_TMP, "mcp_writes.jsonl")

RESULTS = []
ALLOWED_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def check(desc, ok, got=None):
    RESULTS.append((desc, bool(ok)))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def skip(desc, why=""):
    print("SKIP", desc, "->", why)


# ── 1. 结构校验 ───────────────────────────────────────────
def test_structure():
    tools = mcp_server.TOOLS
    check("工具数量 = 109", len(tools) == 109, len(tools))
    names = [t["name"] for t in tools]
    check("工具名唯一", len(names) == len(set(names)),
          [n for n in names if names.count(n) > 1][:5])
    bad = [n for n in names
           if not n or not set(n) <= ALLOWED_NAME_CHARS or len(n) > 64]
    check("工具名合法（小写+下划线）", not bad, bad[:5])

    for name in names:
        tool = mcp_server._TOOL_MAP[name]
        if not str(tool.get("description") or "").strip():
            check("描述非空：%s" % name, False)
            continue
        schema = tool.get("inputSchema") or {}
        if schema.get("type") != "object":
            check("schema 为 object：%s" % name, False, schema.get("type"))
            continue
        if schema.get("additionalProperties") is not False:
            check("schema 关闭额外属性：%s" % name, False)
            continue
        props = set((schema.get("properties") or {}).keys())
        required = set(schema.get("required") or [])
        if not required <= props:
            check("required 都在 properties：%s" % name, False,
                  sorted(required - props))
            continue
        if not callable(tool.get("handler")):
            check("handler 可调用：%s" % name, False)
            continue
        annotations = tool.get("annotations") or {}
        if bool(annotations.get("readOnlyHint")) == bool(tool.get("write")):
            check("annotations 与写标记一致：%s" % name, False, annotations)
    check("全部工具结构与注解一致", True)


# ── 2. 写保护与工具清单 ───────────────────────────────────
NEW_TOOL_GROUPS = {
    "模板库": ["get_report_template", "upload_report_template",
              "set_default_report_template", "delete_report_template",
              "upload_original_template", "set_original_template_defaults",
              "delete_original_template", "list_original_template_defaults"],
    "人员库": ["list_personnel", "get_personnel", "create_personnel",
              "update_personnel", "delete_personnel", "import_personnel"],
    "知识库": ["save_wiki_page", "delete_wiki_page", "import_wiki_files",
              "get_wiki_context"],
    "规范库": ["query_norms", "explain_norms", "import_norms",
             "norm_coverage", "search_norms"],
    "记录库": ["get_records_stats", "get_report_record", "get_original_record",
              "get_original_record_snapshot", "delete_record",
              "find_similar_records", "list_record_sheets",
              "reuse_original_record"],
    "表格结构": ["merge_sheet_cells", "smart_merge_sheet", "insert_sheet_rows",
                "delete_sheet_rows", "fill_down_sheet", "recalc_sheet",
                "get_project_columns"],
    "项目": ["rename_project", "get_project_history", "get_project_items",
            "suggest_detection_items", "current_project", "list_projects",
            "activate_project", "list_project_backups", "restore_project"],
    "设备": ["equipment_status", "delete_equipment", "sync_remote_equipment",
            "recommend_equipment"],
    "配置": ["get_config", "put_config"],
    "报告": ["report_auto_info", "get_report_info", "put_report_info",
            "next_report_no", "match_report_template", "generate_report",
            "report_facts", "render_report"],
    "扫描": ["scan_history", "scan_vision_models", "scan_fill",
            "scan_submit", "scan_job", "scan_jobs"],
    "采集入口": ["recognize_file", "import_file"],
    "检测项契约": ["get_item_contract"],
}


def test_write_gate():
    missing = []
    for group, names in NEW_TOOL_GROUPS.items():
        for name in names:
            if name not in mcp_server._TOOL_MAP:
                missing.append("%s/%s" % (group, name))
    check("P1 新增工具齐全", not missing, missing)

    no_confirm = []
    has_confirm = []
    for name, tool in mcp_server._TOOL_MAP.items():
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        if tool.get("write"):
            if "confirm" not in props or "confirm" not in required:
                no_confirm.append(name)
        elif "confirm" in props or "confirm" in required:
            has_confirm.append(name)
    check("写工具都要求 confirm", not no_confirm, no_confirm)
    check("读工具都没有 confirm", not has_confirm, has_confirm)

    writes = [n for n, t in mcp_server._TOOL_MAP.items() if t.get("write")]
    reads = len(mcp_server._TOOL_MAP) - len(writes)
    print("工具统计：共 %d（写 %d / 读 %d）"
          % (len(mcp_server._TOOL_MAP), len(writes), reads))


# ── 3. 可用性 ─────────────────────────────────────────────
def _backend_up():
    try:
        mcp_server._call_tool("health", {})
        return True
    except Exception as e:  # noqa: BLE001
        print("backend down:", e)
        return False


LIVE_READ_TOOLS = [
    ("list_personnel", {}),
    ("get_records_stats", {}),
    ("get_config", {}),
    ("equipment_status", {}),
    ("scan_history", {}),
    ("next_report_no", {}),
    ("get_project_items", {}),
    ("get_project_history", {}),
]


def test_live_reads():
    if not _backend_up():
        skip("只读工具真实调用", "后端未运行")
        return
    for name, args in LIVE_READ_TOOLS:
        try:
            data = mcp_server._call_tool(name, args)
            check("真实调用 %s" % name, data is not None)
        except Exception as e:  # noqa: BLE001
            check("真实调用 %s" % name, False, str(e)[:120])


def test_structured_content_shape():
    """tools/call 的 structuredContent 必须是对象（MCP 规范）。

    列表类工具（list_report_templates 返回数组）曾直接把数组塞进
    structuredContent，客户端按 record 校验会整体失败。
    """
    if not _backend_up():
        skip("structuredContent 为对象", "后端未运行")
        return
    captured = []
    original = mcp_server._write_message
    mcp_server._write_message = lambda payload: captured.append(payload)
    try:
        for name in ("list_report_templates", "list_original_templates"):
            captured[:] = []
            mcp_server._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": name, "arguments": {}}})
            result = (captured[0].get("result") or {}) if captured else {}
            structured = result.get("structuredContent")
            check("structuredContent 为对象：%s" % name,
                  isinstance(structured, dict),
                  type(structured).__name__)
    finally:
        mcp_server._write_message = original


def test_new_endpoints_direct():
    """新增只读端点直接调后端函数，避免依赖已启动的旧后端进程。"""
    backend = os.path.join(WEBAPP, "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        import fastapi  # noqa: F401,E402
    except ImportError:
        skip("新增只读端点直连验证", "当前解释器没有 fastapi（用系统 Python 3.8 跑可覆盖）")
        return
    try:
        from routers import equipment as equipment_router  # noqa: E402
        from routers import project as project_router  # noqa: E402
        from routers import report as report_router  # noqa: E402
    except Exception as e:  # noqa: BLE001
        check("导入后端路由", False, str(e)[:200])
        return

    try:
        data = report_router.match_report_template()
        check("match_report_template 返回模板推荐",
              isinstance(data, dict) and data.get("ok") is True
              and isinstance((data.get("data") or {}).get("templates"), list),
              list((data.get("data") or {}).keys())[:6])
    except Exception as e:  # noqa: BLE001
        check("match_report_template 返回模板推荐", False, str(e)[:120])

    try:
        data = equipment_router.equipment_recommend(limit=5)
        check("recommend_equipment 返回设备列表",
              isinstance(data, dict) and data.get("ok") is True
              and isinstance((data.get("data") or {}).get("equipment"), list),
              len(((data.get("data") or {}).get("equipment") or [])))
    except Exception as e:  # noqa: BLE001
        check("recommend_equipment 返回设备列表", False, str(e)[:120])

    try:
        data = project_router.suggest_detection_items(text="录回弹法梁的数据")
        body = data.get("data") or {}
        items = [str(x) for x in (body.get("items") or [])]
        check("suggest_detection_items 识别出回弹法",
              data.get("ok") is True and any("回弹法" in x for x in items),
              items)
    except Exception as e:  # noqa: BLE001
        check("suggest_detection_items 识别出回弹法", False, str(e)[:120])


# ── 4. _upload_many ───────────────────────────────────────
def test_upload_many(tmp):
    captured = {}

    class _Resp(object):
        ok = True
        status_code = 200

        def json(self):
            return {"ok": True, "data": {"imported": []}}

    def fake_post(url, files=None, data=None, timeout=None):
        captured["url"] = url
        captured["files"] = list(files or [])
        captured["data"] = data
        return _Resp()

    original = mcp_server.requests.post
    mcp_server.requests.post = fake_post
    try:
        paths = []
        for index, ext in enumerate((".md", ".docx")):
            path = os.path.join(tmp, "kb%d%s" % (index, ext))
            with open(path, "wb") as fh:
                fh.write(b"x")
            paths.append(path)
        mcp_server._upload_many("/wiki/import", paths,
                                data={"category": "规范"})
        check("多文件上传构造两个 part", len(captured.get("files") or []) == 2,
              [f[1][0] for f in captured.get("files") or []])
        check("多文件上传带表单", captured.get("data") == {"category": "规范"},
              captured.get("data"))

        try:
            mcp_server._upload_many("/wiki/import", [])
            check("多文件上传拒绝空列表", False, "未抛错")
        except mcp_server.ToolError as e:
            check("多文件上传拒绝空列表", "不能为空" in str(e), str(e))

        bad = os.path.join(tmp, "kb.pdf")
        open(bad, "wb").close()
        try:
            mcp_server._upload_many("/wiki/import", [bad])
            check("多文件上传拒绝 .pdf", False, "未抛错")
        except mcp_server.ToolError as e:
            check("多文件上传拒绝 .pdf", ".md" in str(e), str(e))
    finally:
        mcp_server.requests.post = original


def test_extra_write_gate(tmp):
    """扩展工具的 confirm 门控与 api.json 序列化。"""
    captured = {}

    def fake_upload_many(path, filepaths, data=None, field="files", allowed=None):
        captured["path"] = path
        captured["data"] = data
        return {"ok": True, "imported": []}

    def fake_request(method, path, params=None, json_body=None):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = json_body
        return {"ok": True}

    original_many = mcp_server._upload_many
    original_request = mcp_server._request
    mcp_server._upload_many = fake_upload_many
    mcp_server._request = fake_request
    try:
        try:
            mcp_server._call_tool("save_wiki_page",
                                  {"title": "测试页", "content": "正文"})
            check("扩展写工具要求 confirm", False, "未抛错")
        except mcp_server.ToolError as e:
            check("扩展写工具要求 confirm", "确认" in str(e), str(e))

        passed = mcp_server._call_tool("create_personnel",
                                       {"name": "张三", "role": "检测",
                                        "confirm": True})
        check("扩展写工具 confirm=true 可执行",
              passed.get("ok") is True and captured.get("method") == "POST"
              and captured.get("body", {}).get("name") == "张三",
              captured.get("body"))

        mcp_server._call_tool("import_wiki_files",
                              {"filepaths": ["a.md"],
                               "category": "规范",
                               "detection_items": ["回弹法检测"],
                               "confirm": True})
        check("import_wiki_files 序列化 detection_items",
              captured.get("data", {}).get("detection_items")
              == '["回弹法检测"]', captured.get("data"))

        key = "钻芯法检测（梁）"
        mcp_server._call_tool("recalc_sheet",
                              {"sheet_key": key, "confirm": True})
        expected = "/sheet/" + mcp_server.quote(key, safe="") + "/calc"
        check("recalc_sheet 走 POST 计算端点",
              captured.get("path") == expected, captured.get("path"))
    finally:
        mcp_server._upload_many = original_many
        mcp_server._request = original_request


def test_create_data_sheet_contract():
    """缺采集参数时，create_data_sheet 要把 manifest 字段说清楚。"""
    original = mcp_server._request

    def fake_request(method, path, params=None, json_body=None):
        return {
            "requires_setup": True,
            "fields": ["building", "diameter"],
            "field_specs": [
                {"key": "building", "label": "楼栋", "type": "string",
                 "required": True, "default": "1#"},
                {"key": "diameter", "label": "芯样直径(mm)", "type": "float",
                 "default": 100},
            ],
        }

    mcp_server._request = fake_request
    try:
        try:
            mcp_server._call_tool("create_data_sheet",
                                  {"sheet_key": "钻芯法检测（梁）",
                                   "confirm": True})
            check("缺参数时提示 params", False, "未抛错")
        except mcp_server.ToolError as e:
            message = str(e)
            check("缺参数时提示 params",
                  "params" in message and "building" in message
                  and "楼栋" in message and "默认 1#" in message,
                  message[:140])
    finally:
        mcp_server._request = original


def main():
    import shutil
    import tempfile
    work = tempfile.mkdtemp(prefix="tool_surface_")
    try:
        test_structure()
        test_write_gate()
        test_live_reads()
        test_structured_content_shape()
        test_new_endpoints_direct()
        test_upload_many(work)
        test_extra_write_gate(work)
        test_create_data_sheet_contract()
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(_AUDIT_TMP, ignore_errors=True)
    fails = [d for d, ok in RESULTS if not ok]
    print("=" * 50)
    print("%d/%d PASS" % (len(RESULTS) - len(fails), len(RESULTS)))
    if fails:
        print("FAILED:", fails[:10])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
