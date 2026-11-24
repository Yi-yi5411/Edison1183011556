# -*- coding: utf-8 -*-
"""P7 CAD 集成冒烟（AutoCAD / 探索者）。

不依赖 AutoCAD：强制 [cad].backend=dxf，验证绘图层、DXF 输出与 MCP 工具面。
运行：python test_cad_agent.py
"""
import os
import shutil
import sys
import tempfile

os.environ["STRUCTURAL_CAD_BACKEND"] = "dxf"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cad_agent import config  # noqa: E402
from cad_agent.drawing import CadDrawing, run_plan  # noqa: E402
from cad_agent import mcp_server as cad_mcp  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


def test_config():
    check("后端配置来自 structural.toml / 环境变量", config.BACKEND == "dxf",
          config.BACKEND)
    check("图纸单位毫米（默认字高 300）", config.DEFAULT_TEXT_HEIGHT == 300,
          config.DEFAULT_TEXT_HEIGHT)
    check("图层表包含 AXIS/COLUMN/BEAM/WALL",
          {"AXIS", "COLUMN", "BEAM", "WALL"} <= set(config.LAYERS),
          sorted(config.LAYERS))


def test_drawing():
    drawing = CadDrawing()
    check("离线后端为 dxf", drawing.backend == "dxf", drawing.backend)
    status = drawing.status()
    check("状态含单位与配置路径",
          status.get("units") == "mm" and bool(status.get("cad_backend_config")),
          status.get("units"))

    result = drawing.grid(origin=(0, 0), x_bays=3, y_bays=2,
                          x_spacing=6000, y_spacing=7200)
    check("轴网尺寸", result["width"] == 18000 and result["height"] == 14400,
          [result["width"], result["height"]])
    kinds = [kind for kind, _data in drawing.dxf.entities]
    check("轴网线条数 = (y_bays+1)+(x_bays+1)", kinds.count("LINE") == 7,
          kinds.count("LINE"))
    check("轴号圆圈 = 4+3", kinds.count("CIRCLE") == 7, kinds.count("CIRCLE"))
    check("轴号文字 = 7", kinds.count("TEXT") == 7, kinds.count("TEXT"))

    drawing.column((0, 0), 400)
    drawing.beam((0, 0), (6000, 0), 300)
    drawing.wall((0, 0), (6000, 0), 240)
    drawing.text("一层平面图", (0, 9000), 500)
    drawing.dimension((0, 0), (6000, 0))
    kinds = [kind for kind, _data in drawing.dxf.entities]
    check("构件为闭合多段线", kinds.count("LWPOLYLINE") == 3,
          kinds.count("LWPOLYLINE"))
    check("标注产生线与文字", kinds.count("LINE") == 8, kinds.count("LINE"))

    try:
        drawing.column((0, 0), 0)
        check("柱宽为 0 报错", False, "未抛错")
    except ValueError as e:
        check("柱宽为 0 报错", "width" in str(e) or "正" in str(e), str(e)[:40])
    try:
        drawing.grid(x_bays=-1)
        check("轴网负数报错", False, "未抛错")
    except ValueError as e:
        check("轴网负数报错", "不能为负" in str(e), str(e)[:30])


def test_save_and_plan():
    tmp = tempfile.mkdtemp(prefix="cad_")
    try:
        out = os.path.join(tmp, "plan.dxf")
        drawing = CadDrawing()
        plan = {"ops": [
            {"op": "grid", "x_bays": 2, "y_bays": 2},
            {"op": "column", "center": [0, 0], "width": 500},
            {"op": "text", "text": "测试", "point": [0, 0]},
            {"op": "save", "path": out},
        ]}
        result = run_plan(drawing, plan)
        check("计划逐步执行", result["count"] == 4
              and result["results"][-1]["op"] == "save", result["count"])
        check("DXF 已写出", os.path.isfile(out) and os.path.getsize(out) > 200,
              os.path.getsize(out) if os.path.isfile(out) else None)
        with open(out, "r", encoding="gbk", errors="replace") as handle:
            text = handle.read()
        check("DXF 结构完整",
              "ENTITIES" in text and "EOF" in text and "LWPOLYLINE" in text)
        check("DXF 含轴网图层", "AXIS" in text and "COLUMN" in text)

        try:
            run_plan(drawing, {"ops": [{"op": "unknown"}]})
            check("未知 op 报错", False, "未抛错")
        except ValueError as e:
            check("未知 op 报错", "不支持的 op" in str(e), str(e)[:40])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_mcp():
    check("CAD MCP 工具数 12", len(cad_mcp.TOOLS) == 12, len(cad_mcp.TOOLS))
    names = [tool["name"] for tool in cad_mcp.TOOLS]
    check("关键工具齐备",
          {"cad_status", "cad_grid", "cad_column", "cad_beam", "cad_wall",
           "cad_save", "cad_open"} <= set(names), names)
    public = cad_mcp._public_tools() if hasattr(cad_mcp, "_public_tools") else [
        {k: v for k, v in t.items() if k not in ("handler", "write")}
        for t in cad_mcp.TOOLS]
    check("工具面不含 handler", all("handler" not in t for t in public))

    status = cad_mcp._call_tool("cad_status", {})
    check("cad_status 可用", status.get("backend") == "dxf", status.get("backend"))

    try:
        cad_mcp._call_tool("cad_save", {"path": "x.dxf"})
        check("cad_save 缺 confirm 被拒", False, "未抛错")
    except cad_mcp.ToolError as e:
        check("cad_save 缺 confirm 被拒", "confirm" in str(e), str(e)[:40])

    try:
        cad_mcp._call_tool("cad_column", {"center": [0, 0], "width": 400,
                                          "confirm": True})
        check("写工具带 confirm 可执行", True)
    except Exception as e:  # noqa: BLE001
        check("写工具带 confirm 可执行", False, str(e)[:40])


def test_lazy_com():
    from cad_agent import cad_client
    check("导入 cad_client 不强制加载 pywin32", "pythoncom" not in cad_client._com,
          sorted(cad_client._com))


def main():
    test_config()
    test_drawing()
    test_save_and_plan()
    test_mcp()
    test_lazy_com()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
