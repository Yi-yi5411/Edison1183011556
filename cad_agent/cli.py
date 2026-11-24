# -*- coding: utf-8 -*-
"""CAD 命令行（结构化，不做自然语言理解）。

    python -m cad_agent.cli status
    python -m cad_agent.cli open
    python -m cad_agent.cli draw --spec plan.json --out D:\\out\\plan.dxf
    python -m cad_agent.cli draw --spec - --out out.dxf      # stdin

plan.json 形如：
    {"ops": [
      {"op": "grid", "x_bays": 3, "y_bays": 2, "x_spacing": 6000, "y_spacing": 7200},
      {"op": "column", "center": [0, 0], "width": 400},
      {"op": "save", "path": "D:/out/plan.dxf"}
    ]}

语义理解交给 DSH；这里只执行结构化计划，便于脚本化与回归测试。
"""
import argparse
import json
import os
import sys

if __package__ in (None, ""):  # python cad_agent/cli.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from cad_agent.drawing import CadDrawing, run_plan
else:
    from .drawing import CadDrawing, run_plan


def _load_spec(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _emit(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cad_agent", description="AutoCAD/探索者 绘图 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="查看 CAD 后端状态")
    open_parser = sub.add_parser("open", help="启动探索者并连接 AutoCAD")
    open_parser.add_argument("--wait", type=float, default=30.0)
    draw = sub.add_parser("draw", help="执行图纸计划（JSON）")
    draw.add_argument("--spec", required=True, help="计划文件路径，- 表示 stdin")
    draw.add_argument("--out", default="", help="保存路径（覆盖计划里的 save.path）")
    draw.add_argument("--backend", default="",
                      choices=["", "auto", "com", "dxf"])
    args = parser.parse_args(argv)

    drawing = CadDrawing(backend=args.backend or None)
    if args.command == "status":
        _emit(drawing.status())
        return 0
    if args.command == "open":
        _emit(drawing.open_tsdp(wait=args.wait))
        return 0

    plan = _load_spec(args.spec)
    if args.out and not any(
            str(op.get("op", "")).lower() == "save"
            for op in plan.get("ops") or [] if isinstance(op, dict)):
        plan.setdefault("ops", []).append({"op": "save", "path": args.out})
    result = run_plan(drawing, plan)
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
