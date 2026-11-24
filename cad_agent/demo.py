# -*- coding: utf-8 -*-
"""生成示例图纸：轴网 + 柱 + 梁 + 墙 + 文字 + 标注，保存为 DXF（离线）或 DWG（在线）。

    python -m cad_agent.demo [输出路径]
"""
import os
import sys

if __package__ in (None, ""):  # python cad_agent/demo.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from cad_agent.drawing import CadDrawing, run_plan
else:
    from .drawing import CadDrawing, run_plan

PLAN = {"ops": [
    {"op": "grid", "origin": [0, 0], "x_bays": 3, "y_bays": 2,
     "x_spacing": 6000, "y_spacing": 7200},
    {"op": "column", "center": [0, 0], "width": 400},
    {"op": "column", "center": [18000, 0], "width": 400},
    {"op": "beam", "p1": [0, 0], "p2": [18000, 0], "width": 300},
    {"op": "wall", "p1": [0, 7200], "p2": [18000, 7200], "thickness": 240},
    {"op": "text", "text": "一层平面图", "point": [0, 9000], "height": 500},
    {"op": "dimension", "p1": [0, 0], "p2": [18000, 0]},
]}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    drawing = CadDrawing()
    plan = {"ops": list(PLAN["ops"])}
    out = argv[0] if argv else ""
    plan["ops"].append({"op": "save",
                        "path": out or drawing._default_save_path()})
    result = run_plan(drawing, plan)
    print("backend=%s saved=%s" % (result["backend"],
                                   result["results"][-1].get("filepath")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
