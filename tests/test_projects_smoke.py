# -*- coding: utf-8 -*-
"""工程作用域冒烟（P0）：当前工程身份、历史清单、切换与恢复。

切换会写入工程状态，测试用临时工程文件并 monkeypatch 会话绑定，
最后把用户原来的 autosave 工程load 回来。

运行：python test_projects_smoke.py
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
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

RESULTS = []
AUTOSAVE = os.path.join(ROOT, "data", "projects", "autosave.json")


def check(desc, ok, got=None):
    RESULTS.append((desc, bool(ok)))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def skip(desc, why=""):
    print("SKIP", desc, "->", why)


def test_read_only():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("工程端点", "当前解释器没有 fastapi")
        return
    from routers.project import current_project, list_projects

    data = current_project()
    body = data.get("data") or {}
    check("当前工程返回身份", data.get("ok") is True
          and "project_name" in body and "checked_items" in body,
          [body.get("project_name"), body.get("sheet_count")])
    check("当前工程带文件路径字段", "filepath" in body, body.get("filepath"))

    data = list_projects()
    body = data.get("data") or {}
    items = body.get("items") or []
    check("历史工程清单非空", data.get("ok") is True and bool(items), len(items))
    if items:
        item = items[0]
        check("清单字段齐全",
              {"filepath", "name", "source", "modified"} <= set(item),
              sorted(item)[:6])
        check("清单包含工程文件",
              any(str(i.get("filepath", "")).endswith(".json") for i in items),
              [i.get("name") for i in items[:3]])


def test_activate():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("工程切换", "当前解释器没有 fastapi")
        return
    from deps import get_state
    from routers.project import OpenBody, activate_project, current_project

    if not os.path.isfile(AUTOSAVE):
        skip("工程切换", "缺少 autosave.json")
        return

    tmp = tempfile.mkdtemp(prefix="projects_")
    state = get_state()
    original_name = state.project_name
    try:
        with open(AUTOSAVE, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        payload["project_name"] = "配置冒烟工程-临时"
        temp_project = os.path.join(tmp, "smoke_project.json")
        with open(temp_project, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)

        data = activate_project(OpenBody(filepath=temp_project))
        check("切换工程成功", data.get("ok") is True,
              (data.get("data") or {}).get("project_name"))
        body = current_project().get("data") or {}
        check("当前工程名已切换", body.get("project_name") == "配置冒烟工程-临时",
              body.get("project_name"))

        try:
            activate_project(OpenBody(filepath=os.path.join(tmp, "missing.json")))
            check("切换不存在工程报错", False, "未抛错")
        except Exception as e:  # noqa: BLE001
            check("切换不存在工程报错", "不存在" in str(e), str(e)[:60])
    finally:
        state.load(AUTOSAVE)
        shutil.rmtree(tmp, ignore_errors=True)
    check("测试后已恢复原工程", state.project_name == original_name,
          [original_name, state.project_name])


def test_tool_schema():
    sys.path.insert(0, os.path.join(ROOT, "webapp"))
    import mcp_server  # noqa: E402
    for name, is_write in (("current_project", False), ("list_projects", False),
                           ("activate_project", True)):
        tool = mcp_server._TOOL_MAP.get(name)
        check("工具存在且写标记正确：%s" % name,
              tool is not None and bool(tool.get("write")) == is_write,
              tool and tool.get("write"))



def main():
    test_read_only()
    test_activate()
    test_tool_schema()
    fails = [d for d, ok in RESULTS if not ok]
    print("=" * 50)
    print("%d/%d PASS" % (len(RESULTS) - len(fails), len(RESULTS)))
    if fails:
        print("FAILED:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
