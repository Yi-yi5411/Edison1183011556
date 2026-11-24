# -*- coding: utf-8 -*-
"""MCP 上传格式冒烟：文件类型白名单、MIME 选择、错误提示、工具描述。

只覆盖 MCP 层（webapp/mcp_server._upload）——Word/CSV 的解析与导入结果
由 tests/test_ingest_smoke.py 与 tests/test_excel_import_smoke.py 覆盖，
这里不重复造表格。

运行：python tests/test_mcp_upload.py
"""
import os
import shutil
import sys
import tempfile

import _harness

ROOT = _harness.bootstrap(os.path.join(_harness.ROOT, "webapp"))
_harness.utf8_stdio()

from _harness import Results  # noqa: E402

_R = Results()
check = _R.check

import mcp_server  # noqa: E402

CAPTURED = []


class _FakeResponse(object):
    ok = True
    status_code = 200

    def json(self):
        return {"ok": True, "data": {}, "message": "ok"}


def _fake_post(url, files=None, data=None, timeout=None):
    name, handle, mime = files["file"]
    CAPTURED.append({"url": url, "name": name, "mime": mime})
    return _FakeResponse()


def test_upload_formats(tmp):
    original = mcp_server.requests.post
    mcp_server.requests.post = _fake_post
    try:
        for ext, mime in (
                (".xlsx", "spreadsheetml.sheet"),
                (".xlsm", "macroEnabled"),
                (".csv", "text/csv"),
                (".docx", "wordprocessingml.document")):
            path = os.path.join(tmp, "upload" + ext)
            with open(path, "wb") as fh:
                fh.write(b"x")
            CAPTURED[:] = []
            try:
                mcp_server._upload("/sheet/x/import_excel", path, data={})
                captured = CAPTURED[-1] if CAPTURED else {}
                check("接受 %s" % ext, bool(captured), captured)
                check("%s MIME 正确" % ext,
                      mime in str(captured.get("mime", "")), captured.get("mime"))
            except Exception as e:  # noqa: BLE001
                check("接受 %s" % ext, False, str(e))

        rejected = os.path.join(tmp, "upload.pdf")
        with open(rejected, "wb") as fh:
            fh.write(b"x")
        try:
            mcp_server._upload("/sheet/x/import_excel", rejected)
            check("拒绝 .pdf", False, "未抛错")
        except mcp_server.ToolError as e:
            check("拒绝 .pdf", ".xlsx" in str(e), str(e))

        try:
            mcp_server._upload("/sheet/x/import_excel",
                               os.path.join(tmp, "missing.docx"))
            check("拒绝不存在的文件", False, "未抛错")
        except mcp_server.ToolError as e:
            check("拒绝不存在的文件", "不存在" in str(e), str(e))

        schema = mcp_server._TOOL_MAP["import_sheet_excel"]["inputSchema"]
        desc = schema["properties"]["filepath"]["description"]
        check("工具描述含 .docx 与 .csv",
              ".docx" in desc and ".csv" in desc, desc)
    finally:
        mcp_server.requests.post = original


def main():
    tmp = tempfile.mkdtemp(prefix="mcp_upload_")
    try:
        test_upload_formats(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _R.finish("MCP 上传格式")


if __name__ == "__main__":
    sys.exit(main())
