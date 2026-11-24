# -*- coding: utf-8 -*-
"""盈建科（YJK）MCP Server（stdio，JSON-RPC 2.0）。

工具：
    yjk_status        探测安装目录 / Python / YJKAPI 是否可用
    yjk_build_frame   JSON 规格 → 建模脚本 → 生成 .ydb（写，需 confirm）
    yjk_read_ydb      读取 .ydb 的楼层/节点/截面摘要（只读）
    yjk_run_script    执行工作目录内的 YJK 脚本（危险，需 confirm + confirm_delete）

主程序不 import YJKAPI；所有调用交给盈建科自带 Python 3.10 子进程。
启动：python -m integrations.yjk.mcp_server [--list-tools]
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from integrations.yjk import bridge  # noqa: E402

SERVER_NAME = "yjk"
SERVER_VERSION = "1.0.0"
TOOLS = []


class ToolError(Exception):
    pass


def _confirm(args):
    if not args.get("confirm"):
        raise ToolError("写操作需要用户确认：请在参数中传 confirm=true。")


def _danger(args):
    if not args.get("confirm_delete"):
        raise ToolError(
            "危险操作需要二次确认：执行 YJK 脚本会改动模型/文件，"
            "确认后请传 confirm_delete=true。")


def _status(args):
    return bridge.status()


def _build(args):
    spec = args.get("spec")
    if not isinstance(spec, dict) or not spec:
        raise ToolError("spec 必须是 JSON 对象（x/y/截面/层高等）")
    result = bridge.build_frame(spec, output_dir=args.get("output_dir") or None,
                                timeout=args.get("timeout") or None)
    data = result.get("data") or {}
    return {
        "ok": bool(result.get("ok")),
        "ydb": data.get("ydb") or "",
        "duration_s": result.get("duration_s"),
        "script": result.get("script"),
        "stdout": (result.get("stdout") or "")[-1000:],
        "stderr": (result.get("stderr") or "")[-1000:],
    }


def _read(args):
    path = str(args.get("path") or "").strip()
    if not path:
        raise ToolError("path 不能为空")
    result = bridge.read_ydb(path, timeout=args.get("timeout") or None)
    return {"ok": bool(result.get("ok")),
            "data": result.get("data"),
            "stderr": (result.get("stderr") or "")[-1000:]}


def _run_script(args):
    path = str(args.get("path") or "").strip()
    if not path or not os.path.isfile(path):
        raise ToolError("脚本不存在：%s" % path)
    work_dir = bridge.paths()["work_dir"]
    real = os.path.realpath(path)
    allowed = (os.path.realpath(_ROOT), os.path.realpath(work_dir))
    if not any(real.startswith(root) for root in allowed):
        raise ToolError("只允许执行项目目录或 [yjk].work_dir 下的脚本：%s" % path)
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        source = handle.read()
    result = bridge.run_script(source, workdir=os.path.dirname(path),
                               timeout=args.get("timeout") or None,
                               name="manual", args=args.get("args") or [])
    return {"ok": bool(result.get("ok")),
            "data": result.get("data"),
            "returncode": result.get("returncode"),
            "duration_s": result.get("duration_s"),
            "stdout": (result.get("stdout") or "")[-2000:],
            "stderr": (result.get("stderr") or "")[-2000:]}


def _tool(name, description, properties, required, write, handler,
          danger=False):
    props = dict(properties)
    required = list(required)
    if write:
        props["confirm"] = {"type": "boolean",
                            "description": "写操作确认；必须为 true"}
        if "confirm" not in required:
            required.append("confirm")
    if danger:
        props["confirm_delete"] = {"type": "boolean",
                                   "description": "危险操作二次确认；必须为 true"}
        if "confirm_delete" not in required:
            required.append("confirm_delete")
    tool = {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": props,
                        "required": required, "additionalProperties": False},
        "annotations": {"title": name, "readOnlyHint": not write,
                        "destructiveHint": bool(danger),
                        "idempotentHint": False, "openWorldHint": False},
        "handler": handler,
        "write": write,
        "danger": bool(danger),
    }
    TOOLS.append(tool)
    return tool


_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}

_tool("yjk_status",
      "探测盈建科环境：Python 解释器、安装目录、YJKAPI 是否可导入、工作目录。",
      {}, [], False, _status)
_tool("yjk_build_frame",
      "按 JSON 规格建立框架模型并生成 .ydb：x/y 轴网坐标、柱梁截面、标准层层数与层高。"
      "规格示例见 integrations/yjk/model.py 的 DEFAULT_SPEC。",
      {"spec": {"type": "object", "description": "建模规格（JSON）"},
       "output_dir": {**_STR, "description": "ydb 输出目录，缺省 [yjk].work_dir/models"},
       "timeout": {**_NUM, "description": "秒，缺省取配置"}},
      ["spec"], True, _build)
_tool("yjk_read_ydb",
      "读取 .ydb 摘要：标准层、楼层、节点数、柱/梁截面。",
      {"path": {**_STR, "description": ".ydb 完整路径"},
       "timeout": {**_NUM, "description": "秒"}},
      ["path"], False, _read)
_tool("yjk_run_script",
      "执行项目目录或 [yjk].work_dir 下的 YJK 脚本（危险）。",
      {"path": {**_STR, "description": "脚本完整路径"},
       "args": {"type": "array", "items": _STR, "description": "脚本参数"},
       "timeout": {**_NUM, "description": "秒"}},
      ["path"], True, _run_script, danger=True)

_TOOL_MAP = {tool["name"]: tool for tool in TOOLS}


def _call_tool(name, arguments):
    tool = _TOOL_MAP.get(name)
    if tool is None:
        raise ToolError("未知工具：%s" % name)
    args = dict(arguments or {})
    if tool["write"]:
        _confirm(args)
    if tool["danger"]:
        _danger(args)
    return tool["handler"](args)


def _response(rid, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def _public_tools():
    return [{k: v for k, v in tool.items() if k not in ("handler", "write", "danger")}
            for tool in TOOLS]


def _handle(message):
    method = message.get("method")
    rid = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        return _response(rid, {
            "protocolVersion": params.get("protocolVersion") or "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "tools/list":
        return _response(rid, {"tools": _public_tools()})
    if method == "tools/call":
        name = params.get("name")
        try:
            result = _call_tool(name, params.get("arguments") or {})
        except ToolError as exc:
            return _response(rid, {"content": [{"type": "text", "text": str(exc)}],
                                   "isError": True})
        except Exception as exc:  # noqa: BLE001
            return _response(rid, {"content": [{"type": "text",
                                                "text": "YJK 执行失败：%s" % exc}],
                                   "isError": True})
        return _response(rid, {"content": [{"type": "text",
                                            "text": json.dumps(result, ensure_ascii=False)}],
                               "isError": False})
    if method in ("ping", "shutdown"):
        return _response(rid, {})
    return _response(rid, error={"code": -32601,
                                 "message": "Method not found: %s" % method})


def _serve():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        sys.stdout.write(json.dumps(_handle(message), ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--list-tools" in argv:
        print(json.dumps({"tools": _public_tools()}, ensure_ascii=False,
                         indent=2))
        return 0
    _serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
