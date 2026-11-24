# -*- coding: utf-8 -*-
"""P7 盈建科（YJK）集成冒烟。

不依赖 YJK 安装：验证规格→脚本生成、脚本可编译、环境探测与 MCP 安全门。
运行：python test_yjk_integration.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp"))

import structural_config  # noqa: E402
from integrations.yjk import bridge, model  # noqa: E402
from integrations.yjk import mcp_server as yjk_mcp  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


def test_spec():
    spec = model.normalize_spec({"x": [0, 6000], "y": [0, 7000]})
    check("默认层高与层数", spec["floors"]["height"] == 3900
          and spec["floors"]["number"] == 6, spec["floors"])
    check("坐标转浮点", spec["x"] == [0.0, 6000.0], spec["x"])
    check("默认截面", spec["column_sections"][0]["shape"] == "400,400",
          spec["column_sections"])

    for bad, tag in (
            ({"x": [0]}, "x 少于两点"),
            ({"name": "a/b"}, "name 含路径"),
            ({"column_sections": []}, "柱截面为空")):
        try:
            model.normalize_spec(bad)
            check("%s 报错" % tag, False, "未抛错")
        except ValueError as e:
            check("%s 报错" % tag, True, str(e)[:30])


def test_script():
    spec = model.normalize_spec({"x": [0, 3900, 7800], "y": [0, 6700]})
    source = model.frame_script(spec, output_dir=r"C:\\tmp\\yjk")
    try:
        compile(source, "<yjk_frame>", "exec")
        check("建模脚本可编译", True)
    except SyntaxError as e:
        check("建模脚本可编译", False, str(e))

    required = [
        "from YJKAPI import *",
        "StdFlr = dataFunc.StdFlr_Generate(3900, 5.0, 2.0)",
        'dataFunc.ColSect_Def(6, 1, "400,400")',
        'dataFunc.BeamSect_Def(6, 1, "250,600")',
        "dataFunc.Joint_Generate(StdFlr.ID, xv, yv)",
        "dataFunc.Axis_Generate(",
        "dataFunc.Grid_Generate(",
        "dataFunc.column_arrange(nodelist, defcol0)",
        "dataFunc.beam_arrange(gridlist, defbeam0)",
        "dataFunc.Floors_Assemb(0, StdFlr, 6, 3600)",
        "dataFunc.DbModel_Assign()",
        "Hi_AddToAndReadYjk(dataFunc.GetDbModelData())",
        "my.CreateYDB(out_dir,",
    ]
    missing = [item for item in required if item not in source]
    check("脚本使用真实 YJKAPI 调用", not missing, missing)
    check("轴网坐标按序写入", "xpos = [0.0, 3900.0, 7800.0]" in source,
          "xpos = [" in source)
    check("输出名带 .ydb", '"kj.ydb"' in source)

    read = model.read_ydb_script()
    check("读取脚本含 ReadYdb/ToPyList",
          "ReadYdb(path).ToPyList()" in read and "m_StdFlr" in read)
    try:
        compile(read, "<yjk_read>", "exec")
        check("读取脚本可编译", True)
    except SyntaxError as e:
        check("读取脚本可编译", False, str(e))


def test_status_without_yjk():
    old = os.environ.get("STRUCTURAL_YJK_PYTHON")
    os.environ["STRUCTURAL_YJK_PYTHON"] = os.path.join(ROOT, "no_such_python.exe")
    structural_config.reload()
    try:
        info = bridge.status()
        check("缺解释器时不可用", info["available"] is False, info["available"])
        check("缺解释器时给出原因",
              "解释器" in info.get("reason", ""), info.get("reason", "")[:40])
        check("工作目录为绝对路径", os.path.isabs(info["work_dir"]),
              info["work_dir"])
    finally:
        if old is None:
            os.environ.pop("STRUCTURAL_YJK_PYTHON", None)
        else:
            os.environ["STRUCTURAL_YJK_PYTHON"] = old
        structural_config.reload()


def test_mcp():
    check("YJK MCP 工具数 4", len(yjk_mcp.TOOLS) == 4, len(yjk_mcp.TOOLS))
    names = [tool["name"] for tool in yjk_mcp.TOOLS]
    check("工具齐备", names == ["yjk_status", "yjk_build_frame",
                                 "yjk_read_ydb", "yjk_run_script"], names)
    script_tool = yjk_mcp._TOOL_MAP["yjk_run_script"]
    check("脚本执行为危险工具",
          script_tool["danger"] is True
          and script_tool["annotations"]["destructiveHint"] is True
          and "confirm_delete" in script_tool["inputSchema"]["required"],
          script_tool["annotations"])

    try:
        yjk_mcp._call_tool("yjk_build_frame", {"spec": {"x": [0, 1], "y": [0, 1]}})
        check("建模缺 confirm 被拒", False, "未抛错")
    except yjk_mcp.ToolError as e:
        check("建模缺 confirm 被拒", "confirm" in str(e), str(e)[:30])

    try:
        yjk_mcp._call_tool("yjk_run_script",
                           {"path": os.path.join(ROOT, "no_such.py"),
                            "confirm": True})
        check("脚本缺 confirm_delete 被拒", False, "未抛错")
    except yjk_mcp.ToolError as e:
        check("脚本缺 confirm_delete 被拒",
              "二次确认" in str(e) or "不存在" in str(e), str(e)[:40])

    try:
        yjk_mcp._call_tool("yjk_build_frame",
                           {"spec": {"x": [0, 6000], "y": [0, 6000]},
                            "confirm": True})
        check("无 YJK 环境时建模报错", False, "未抛错")
    except bridge.YjkUnavailable as e:
        check("无 YJK 环境时建模报错", "盈建科 Python" in str(e), str(e)[:40])


def main():
    test_spec()
    test_script()
    test_status_without_yjk()
    test_mcp()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
