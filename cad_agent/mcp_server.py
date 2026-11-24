# -*- coding: utf-8 -*-
"""AutoCAD / 探索者 MCP Server（stdio，JSON-RPC 2.0）。

只暴露结构化绘图工具，不做自然语言理解——语义由 DSH 负责，这里执行并返回摘要。
写操作（会改动图纸/文件）必须传 confirm=true。

启动：
    python -m cad_agent.mcp_server            # 供 DSH 以 MCP stdio 挂载
    python -m cad_agent.mcp_server --list-tools

配置：config/structural.toml 的 [cad] 段（backend=auto|com|dxf）。
"""
import json
import os
import sys

if __package__ in (None, ""):  # python cad_agent/mcp_server.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from cad_agent import config
    from cad_agent.drawing import CadDrawing
else:
    from . import config
    from .drawing import CadDrawing

SERVER_NAME = "autocad"
SERVER_VERSION = "1.0.0"
TOOLS = []
_DRAWING = [None]


class ToolError(Exception):
    pass


def _drawing():
    if _DRAWING[0] is None:
        _DRAWING[0] = CadDrawing()
    return _DRAWING[0]


def _need(args, key, label=""):
    value = args.get(key)
    if value is None or value == "":
        raise ToolError("%s 不能为空" % (label or key))
    return value


def _confirm(args):
    if not args.get("confirm"):
        raise ToolError("写操作需要用户确认：请在参数中传 confirm=true。")


# ── 工具实现 ──────────────────────────────────────────────
def _status(args):
    return _drawing().status()


def _open(args):
    return _drawing().open_tsdp(wait=float(args.get("wait") or 30))


def _grid(args):
    return _drawing().grid(
        origin=args.get("origin") or [0, 0],
        x_spacing=args.get("x_spacing", 6000),
        y_spacing=args.get("y_spacing", 6000),
        x_bays=args.get("x_bays", 3),
        y_bays=args.get("y_bays", 3),
        labels=args.get("labels", True))


def _column(args):
    return _drawing().column(
        _need(args, "center", "柱中心 [x, y]"),
        _need(args, "width", "柱宽"),
        args.get("depth"))


def _beam(args):
    return _drawing().beam(_need(args, "p1", "起点 [x, y]"),
                           _need(args, "p2", "终点 [x, y]"),
                           _need(args, "width", "梁宽"))


def _wall(args):
    return _drawing().wall(_need(args, "p1", "起点 [x, y]"),
                           _need(args, "p2", "终点 [x, y]"),
                           _need(args, "thickness", "墙厚"))


def _rect(args):
    return _drawing().rect(_need(args, "p1", "对角点1 [x, y]"),
                           _need(args, "p2", "对角点2 [x, y]"))


def _circle(args):
    return _drawing().circle(_need(args, "center", "圆心 [x, y]"),
                             _need(args, "radius", "半径"))


def _text(args):
    return _drawing().text(_need(args, "text", "文字"),
                           _need(args, "point", "插入点 [x, y]"),
                           args.get("height"))


def _dimension(args):
    return _drawing().dimension(_need(args, "p1", "起点 [x, y]"),
                                _need(args, "p2", "终点 [x, y]"),
                                args.get("offset"))


def _save(args):
    return _drawing().save(args.get("path") or None)


def _zoom(args):
    return _drawing().zoom()


def _tool(name, description, properties, required, write, handler):
    props = dict(properties)
    required = list(required)
    if write:
        props["confirm"] = {"type": "boolean",
                            "description": "写操作确认；必须为 true"}
        if "confirm" not in required:
            required.append("confirm")
    tool = {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": props,
                        "required": required, "additionalProperties": False},
        "annotations": {"title": name, "readOnlyHint": not write,
                        "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
        "handler": handler,
        "write": write,
    }
    TOOLS.append(tool)
    return tool


_PT = {"type": "array", "items": {"type": "number"},
       "minItems": 2, "maxItems": 2,
       "description": "[x, y]，单位毫米"}

_tool("cad_status",
      "读取 CAD 后端状态：在线（AutoCAD COM）或离线（DXF）、文档名、工作目录、单位。",
      {}, [], False, _status)
_tool("cad_open",
      "启动探索者 TSDP2024 并连接 AutoCAD（仅在线模式）。",
      {"wait": {"type": "number", "description": "等待秒数，默认 30"}},
      [], True, _open)
_tool("cad_grid",
      "绘制轴网并标注轴号（1..n / A..n）。",
      {"origin": _PT, "x_spacing": {"type": "number"},
       "y_spacing": {"type": "number"},
       "x_bays": {"type": "integer"}, "y_bays": {"type": "integer"},
       "labels": {"type": "boolean"}},
      [], True, _grid)
_tool("cad_column",
      "绘制柱（COLUMN 层），center 为柱中心，depth 缺省等于 width。",
      {"center": _PT, "width": {"type": "number"},
       "depth": {"type": "number"}},
      ["center", "width"], True, _column)
_tool("cad_beam",
      "绘制梁（BEAM 层）：p1→p2 的矩形带，width 为梁宽。",
      {"p1": _PT, "p2": _PT, "width": {"type": "number"}},
      ["p1", "p2", "width"], True, _beam)
_tool("cad_wall",
      "绘制墙（WALL 层）：p1→p2 的矩形带，thickness 为墙厚。",
      {"p1": _PT, "p2": _PT, "thickness": {"type": "number"}},
      ["p1", "p2", "thickness"], True, _wall)
_tool("cad_rect", "绘制矩形（对角点 p1、p2）。",
      {"p1": _PT, "p2": _PT}, ["p1", "p2"], True, _rect)
_tool("cad_circle", "绘制圆。",
      {"center": _PT, "radius": {"type": "number"}},
      ["center", "radius"], True, _circle)
_tool("cad_text", "写单行文字（TEXT 层），height 缺省 300。",
      {"text": {"type": "string"}, "point": _PT,
       "height": {"type": "number"}},
      ["text", "point"], True, _text)
_tool("cad_dimension", "添加对齐标注。",
      {"p1": _PT, "p2": _PT, "offset": {"type": "number"}},
      ["p1", "p2"], True, _dimension)
_tool("cad_save",
      "保存图纸：在线保存 DWG，离线写 DXF（返回 filepath 与大小）。"
      "path 缺省时写到 [cad].work_dir 下的 cad_<时间戳>.<dwg|dxf>。",
      {"path": {"type": "string", "description": "目标文件完整路径"}},
      [], True, _save)
_tool("cad_zoom", "缩放到图形范围（在线模式）。", {}, [], False, _zoom)

_TOOL_MAP = {tool["name"]: tool for tool in TOOLS}


def _call_tool(name, arguments):
    tool = _TOOL_MAP.get(name)
    if tool is None:
        raise ToolError("未知工具：%s" % name)
    args = dict(arguments or {})
    if tool["write"]:
        _confirm(args)
    return tool["handler"](args)


def _response(rid, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


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
        return _response(rid, {"tools": [
            {k: v for k, v in tool.items() if k not in ("handler", "write")}
            for tool in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        try:
            result = _call_tool(name, params.get("arguments") or {})
        except ToolError as exc:
            return _response(rid, {"content": [{"type": "text",
                                                "text": str(exc)}],
                                   "isError": True})
        except Exception as exc:  # noqa: BLE001
            return _response(rid, {"content": [{"type": "text",
                                                "text": "CAD 执行失败：%s" % exc}],
                                   "isError": True})
        return _response(rid, {"content": [{"type": "text",
                                            "text": json.dumps(
                                                result, ensure_ascii=False)}],
                               "isError": False})
    if method in ("ping",):
        return _response(rid, {})
    if method == "shutdown":
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
        if not isinstance(message, dict):
            continue
        if "id" not in message:  # 通知不需要响应
            continue
        reply = _handle(message)
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--list-tools" in argv:
        print(json.dumps({"tools": [
            {k: v for k, v in tool.items() if k not in ("handler", "write")}
            for tool in TOOLS]}, ensure_ascii=False, indent=2))
        return 0
    _serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
