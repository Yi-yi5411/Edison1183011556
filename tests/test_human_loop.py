# -*- coding: utf-8 -*-
"""P6 人机协同冒烟：写操作分级、危险操作二次确认、审计、工程回退。

覆盖：
1. 工具元数据：readOnly / destructive / confirm_delete 必填
2. 安全门：缺 confirm → 拒绝；危险工具缺 confirm_delete → 拒绝
3. 审计：写操作落 JSONL，密钥脱敏，被拦下的调用也记
4. 工程备份与恢复：列出备份、恢复前自动另存当前工程
5. 工具总数

运行：python test_human_loop.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp"))
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

import mcp_server  # noqa: E402

# 审计目录必须在任何 _call_tool 之前切到临时目录，避免测试污染真实审计
_AUDIT_TMP = tempfile.mkdtemp(prefix="audit_")
mcp_server._AUDIT_DIR = _AUDIT_TMP
mcp_server._AUDIT_FILE = os.path.join(_AUDIT_TMP, "mcp_writes.jsonl")

RESULTS = []

DANGER_TOOLS = ("delete_record", "delete_equipment", "delete_personnel",
                "delete_report_template", "delete_original_template",
                "delete_wiki_page", "delete_sheet_rows", "reuse_original_record",
                "import_file", "import_sheet_excel", "import_assessment_excel",
                "import_norms", "restore_project")
WRITE_TOOLS = ("put_rows", "create_project", "save_project", "run_assessment",
               "generate_report", "render_report", "put_config")
READ_TOOLS = ("get_project", "list_projects", "report_facts", "list_equipment")


def check(desc, ok, got=None):
    RESULTS.append((desc, bool(ok)))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def skip(desc, why=""):
    print("SKIP", desc, "->", why)


# ── 1. 元数据 ────────────────────────────────────────────
def test_metadata():
    missing = [n for n in DANGER_TOOLS if n not in mcp_server._TOOL_MAP]
    check("危险工具都存在", not missing, missing)
    for name in DANGER_TOOLS:
        tool = mcp_server._TOOL_MAP.get(name)
        if tool is None:
            continue
        schema = tool["inputSchema"]
        required = schema.get("required") or []
        check("%s：标记危险" % name,
              tool.get("danger") is True
              and tool["annotations"]["destructiveHint"] is True
              and "confirm_delete" in required
              and "confirm_delete" in (schema.get("properties") or {}),
              [tool.get("danger"), "confirm_delete" in required])

    for name in WRITE_TOOLS:
        tool = mcp_server._TOOL_MAP.get(name)
        if tool is None:
            check("%s 存在" % name, False, None)
            continue
        check("%s：普通写不标危险" % name,
              tool.get("write") is True and tool.get("danger") is False
              and tool["annotations"]["destructiveHint"] is False
              and "confirm_delete" not in (tool["inputSchema"].get("properties") or {}),
              tool["annotations"]["destructiveHint"])

    for name in READ_TOOLS:
        tool = mcp_server._TOOL_MAP.get(name)
        if tool is None:
            check("%s 存在" % name, False, None)
            continue
        check("%s：只读标注" % name,
              tool.get("write") is False
              and tool["annotations"]["readOnlyHint"] is True,
              tool["annotations"])


# ── 2. 安全门 ────────────────────────────────────────────
def test_gate():
    try:
        mcp_server._call_tool("delete_record",
                              {"kind": "report", "record_id": "x"})
        check("危险工具缺 confirm 被拒", False, "未抛错")
    except mcp_server.ToolError as e:
        check("危险工具缺 confirm 被拒", "confirm" in str(e), str(e)[:40])

    try:
        mcp_server._call_tool("delete_record",
                              {"kind": "report", "record_id": "x",
                               "confirm": True})
        check("危险工具缺 confirm_delete 被拒", False, "未抛错")
    except mcp_server.ToolError as e:
        check("危险工具缺 confirm_delete 被拒", "二次确认" in str(e), str(e)[:50])

    try:
        mcp_server._call_tool("put_rows", {"sheet_key": "x", "rows": []})
        check("普通写缺 confirm 被拒", False, "未抛错")
    except mcp_server.ToolError as e:
        check("普通写缺 confirm 被拒", "confirm" in str(e), str(e)[:40])

    try:
        mcp_server._call_tool("get_project", {})
        check("只读工具可直接调用", True)
    except Exception as e:  # noqa: BLE001
        check("只读工具可直接调用", False, str(e)[:60])


# ── 3. 审计 ──────────────────────────────────────────────
def test_audit():
    tmp = tempfile.mkdtemp(prefix="audit_")
    old_dir, old_file = mcp_server._AUDIT_DIR, mcp_server._AUDIT_FILE
    old_request = mcp_server._request
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        return {"ok": True, "data": {}}

    mcp_server._AUDIT_DIR = tmp
    mcp_server._AUDIT_FILE = os.path.join(tmp, "mcp_writes.jsonl")
    mcp_server._request = fake_request
    try:
        result = mcp_server._call_tool("put_rows", {
            "sheet_key": "剪力墙厚度检测", "rows": [["1"]],
            "confirm": True, "api_key": "sk-secret"})
        check("普通写放行", result == {"ok": True, "data": {}}, result)
        check("请求已发出", len(calls) == 1 and calls[0][0] == "PUT"
              and calls[0][1].endswith("/rows") and "sheet/" in calls[0][1],
              calls)

        try:
            mcp_server._call_tool("delete_record",
                                  {"kind": "report", "record_id": "x",
                                   "confirm": True})
        except mcp_server.ToolError:
            pass

        check("审计文件存在", os.path.isfile(mcp_server._AUDIT_FILE))
        with open(mcp_server._AUDIT_FILE, "r", encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
        check("写操作有审计", len(entries) == 2, len(entries))
        ok_entry = next((e for e in entries if e["ok"]), {})
        bad_entry = next((e for e in entries if not e["ok"]), {})
        check("审计记录工具与耗时",
              ok_entry.get("tool") == "put_rows"
              and ok_entry.get("danger") is False
              and isinstance(ok_entry.get("duration_ms"), int),
              ok_entry.get("tool"))
        check("审计脱敏 api_key", ok_entry.get("args", {}).get("api_key") == "***",
              ok_entry.get("args", {}).get("api_key"))
        check("被拦下的调用也审计",
              bad_entry.get("tool") == "delete_record"
              and bad_entry.get("danger") is True
              and "二次确认" in bad_entry.get("error", ""),
              bad_entry.get("error", "")[:30])
        check("只读调用不写审计", len([e for e in entries
                                     if e["tool"] == "get_project"]) == 0)

        log = mcp_server._call_tool("get_audit_log", {"limit": 10})
        check("审计读取工具可用", log.get("count") == 2
              and log["items"][0].get("tool") == "delete_record",
              [log.get("count"),
               log["items"][0].get("tool") if log.get("items") else None])
        failed = mcp_server._call_tool("get_audit_log", {"only_failed": True})
        check("审计可按失败过滤", failed.get("count") == 1
              and failed["items"][0].get("ok") is False,
              failed.get("count"))
        by_tool = mcp_server._call_tool("get_audit_log", {"tool": "put_rows"})
        check("审计可按工具过滤", by_tool.get("count") == 1
              and by_tool["items"][0].get("tool") == "put_rows",
              by_tool.get("count"))
    finally:
        mcp_server._AUDIT_DIR, mcp_server._AUDIT_FILE = old_dir, old_file
        mcp_server._request = old_request
        shutil.rmtree(tmp, ignore_errors=True)


# ── 4. 备份与恢复 ────────────────────────────────────────
def test_backup_restore():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("工程备份/恢复", "当前解释器没有 fastapi")
        return
    from deps import get_state
    import routers.project as project_router

    tmp = tempfile.mkdtemp(prefix="backups_")
    old_dir = project_router.BACKUP_DIR
    project_router.BACKUP_DIR = os.path.join(tmp, "backups")
    state = get_state()
    original_name = state.project_name
    original_path = state.filepath
    try:
        os.makedirs(project_router.BACKUP_DIR, exist_ok=True)
        backup = os.path.join(project_router.BACKUP_DIR, "auto_20261112.json")
        state.save(backup)

        data = project_router.project_backups()
        body = data.get("data") or {}
        check("列出备份", data.get("ok") is True
              and any(item["filepath"] == backup for item in body.get("items") or []),
              [item["name"] for item in body.get("items") or []])

        # 改个名再恢复，确认恢复的是备份内容
        state.project_name = "被改坏的工程"
        result = project_router.restore_project(
            project_router.OpenBody(filepath=backup))
        payload = result.get("data") or {}
        check("恢复成功", result.get("ok") is True
              and payload.get("project_name") == original_name,
              [original_name, payload.get("project_name")])
        check("恢复前有安全备份",
              bool(payload.get("safety_backup"))
              and os.path.isfile(payload["safety_backup"]),
              payload.get("safety_backup"))

        try:
            project_router.restore_project(
                project_router.OpenBody(filepath=os.path.join(tmp, "nope.json")))
            check("恢复不存在的备份报错", False, "未抛错")
        except Exception as e:  # noqa: BLE001
            check("恢复不存在的备份报错", "不存在" in str(e), str(e)[:40])
    finally:
        project_router.BACKUP_DIR = old_dir
        state.project_name = original_name
        state.filepath = original_path
        shutil.rmtree(tmp, ignore_errors=True)


def test_tool_count():
    check("工具总数 109", len(mcp_server._TOOL_MAP) == 109,
          len(mcp_server._TOOL_MAP))
    danger = [n for n, t in mcp_server._TOOL_MAP.items() if t.get("danger")]
    check("危险工具数量合理", len(danger) == len(DANGER_TOOLS),
          sorted(danger))


def main():
    try:
        test_metadata()
        test_gate()
        test_audit()
        test_backup_restore()
        test_tool_count()
    finally:
        shutil.rmtree(_AUDIT_TMP, ignore_errors=True)
    fails = [d for d, ok in RESULTS if not ok]
    print("=" * 50)
    print("%d/%d PASS" % (len(RESULTS) - len(fails), len(RESULTS)))
    if fails:
        print("FAILED:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
