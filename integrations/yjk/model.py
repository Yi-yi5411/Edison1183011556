# -*- coding: utf-8 -*-
"""盈建科（YJK）模型脚本生成：JSON 规格 → YJKAPI Python 源码。

API 名称与调用顺序取自官方示例
（yjkapi_-python-8.1/案例/二次开发/不依赖YJK案例/案例1_框架结构/kj.py）：

    from YJKAPI import *
    dataFunc = DataFunc()
    StdFlr = dataFunc.StdFlr_Generate(3900)
    defcol = dataFunc.ColSect_Def(6, 1, "400,400")
    defbeam = dataFunc.BeamSect_Def(6, 1, "250,600")
    node = dataFunc.Joint_Generate(StdFlr.ID, x, y)
    grid = dataFunc.Grid_Generate(StdFlr.ID, n1.ID, n2.ID, axis.ID)
    cols = dataFunc.column_arrange(nodelist, defcol)
    beams = dataFunc.beam_arrange(gridlist, defbeam)
    dataFunc.Floors_Assemb(0, StdFlr, 6, 3600)
    dataFunc.DbModel_Assign()
    my = Hi_AddToAndReadYjk(dataFunc.GetDbModelData())
    my.CreateYDB(directory, "kj.ydb")

本模块只生成源码，不导入 YJKAPI（主程序 Python 3.8 无法导入它；
脚本必须由 YJK 自带 Python 3.10 执行）。
"""
import json

DEFAULT_SPEC = {
    "name": "kj",
    "floors": {"height": 3900, "number": 6, "floor_height": 3600,
               "deadload": 5.0, "liveload": 2.0},
    "x": [0, 3900, 7800],
    "y": [0, 6700, 12000],
    "column_sections": [{"mat": 6, "kind": 1, "shape": "400,400"}],
    "beam_sections": [{"mat": 6, "kind": 1, "shape": "250,600"}],
}


def _num_list(values, label):
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError("%s 至少需要两个坐标" % label)
    out = []
    for value in values:
        out.append(float(value))
    return out


def normalize_spec(spec):
    """补默认值并做基本校验，返回可直接生成脚本的规格。"""
    spec = dict(spec or {})
    merged = dict(DEFAULT_SPEC)
    for key in ("name", "floors", "x", "y", "column_sections",
                "beam_sections"):
        # 显式传了就用传入值（哪怕是空列表），由下面的校验报错，
        # 避免“悄悄换成默认值”掩盖调用方的错误。
        if key in spec and spec[key] is not None and spec[key] != "":
            merged[key] = spec[key]
    if isinstance(merged["floors"], int):
        merged["floors"] = dict(DEFAULT_SPEC["floors"],
                                height=merged["floors"])
    merged["x"] = _num_list(merged["x"], "x")
    merged["y"] = _num_list(merged["y"], "y")
    if not merged["column_sections"]:
        raise ValueError("column_sections 不能为空")
    if not merged["beam_sections"]:
        raise ValueError("beam_sections 不能为空")
    name = str(merged["name"] or "kj").strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError("name 只能是文件名，不含路径分隔符")
    merged["name"] = name
    merged["output_dir"] = str(spec.get("output_dir") or "").strip()
    merged["slab"] = spec.get("slab") or None
    merged["beam_loads"] = spec.get("beam_loads") or []
    return merged


def _q(value):
    """嵌入源码的 Python 字面量（字符串走 JSON，等价且安全）。"""
    return json.dumps(value, ensure_ascii=False)


def frame_script(spec, output_dir=None):
    """生成框架结构建模脚本（对应案例1）。返回 Python 源码字符串。"""
    spec = normalize_spec(spec)
    floors = spec["floors"]
    x = spec["x"]
    y = spec["y"]
    cols = spec["column_sections"]
    beams = spec["beam_sections"]
    lines = [
        "# -*- coding: utf-8 -*-",
        "# 由 structural_inspection 生成（盈建科 YJKAPI 8.x）",
        "import json",
        "import os",
        "from YJKAPI import *",
        "",
        "dataFunc = DataFunc()",
        "StdFlr = dataFunc.StdFlr_Generate(%s, %s, %s)" % (
            int(floors.get("height", 3900)),
            float(floors.get("deadload", 5.0)),
            float(floors.get("liveload", 2.0))),
        "",
        "# 截面定义",
    ]
    for index, item in enumerate(cols):
        lines.append('defcol%d = dataFunc.ColSect_Def(%d, %d, %s)' % (
            index, int(item.get("mat", 6)), int(item.get("kind", 1)),
            _q(str(item.get("shape", "400,400")))))
    for index, item in enumerate(beams):
        lines.append('defbeam%d = dataFunc.BeamSect_Def(%d, %d, %s)' % (
            index, int(item.get("mat", 6)), int(item.get("kind", 1)),
            _q(str(item.get("shape", "250,600")))))
    lines.extend([
        "",
        "# 节点与网格",
        "xpos = %s" % _q(x),
        "ypos = %s" % _q(y),
        "nodelist = []",
        "for xv in xpos:",
        "    _row = []",
        "    for yv in ypos:",
        "        _row.append(dataFunc.Joint_Generate(StdFlr.ID, xv, yv))",
        "    nodelist.append(_row)",
        "gridlist = []",
        "for _row in nodelist:",
        "    for i in range(len(_row) - 1):",
        "        axis = dataFunc.Axis_Generate(StdFlr.ID, _row[i].ID, _row[i + 1].ID)",
        "        gridlist.append(dataFunc.Grid_Generate(",
        "            StdFlr.ID, _row[i].ID, _row[i + 1].ID, axis.ID))",
        "for i in range(len(nodelist) - 1):",
        "    for j in range(len(nodelist[i])):",
        "        axis = dataFunc.Axis_Generate(StdFlr.ID, nodelist[i][j].ID,",
        "                                      nodelist[i + 1][j].ID)",
        "        gridlist.append(dataFunc.Grid_Generate(",
        "            StdFlr.ID, nodelist[i][j].ID, nodelist[i + 1][j].ID,",
        "            axis.ID))",
        "",
        "# 布置柱、梁",
        "col_list = dataFunc.column_arrange(nodelist, defcol0)",
        "beam_list = dataFunc.beam_arrange(gridlist, defbeam0)",
    ])
    for index, item in enumerate(spec.get("beam_loads") or []):
        lines.extend([
            'beamload%d = dataFunc.Load_Def(%d, %s)' % (
                index, int(item.get("kind", 12)),
                _q(str(item.get("value", "1.00,9.60")))),
            'dataFunc.load_arrange(beam_list, beamload%d)' % index,
        ])
    slab = spec.get("slab")
    if isinstance(slab, dict):
        centroid = slab.get("centroid") or [0, 0]
        dead_live = slab.get("dead_live") or [9, 9]
        lines.extend([
            "",
            "# 布置板",
            "slabInfo = SlabCreateInfo()",
            "slabInfo.SetCentroid(%s, %s).SetThick(%s).SetStdFlr(StdFlr)" % (
                float(centroid[0]), float(centroid[1]),
                float(slab.get("thick", 300))),
            "slabInfo.SetCc(%s).SetDeadLive(%s, %s)" % (
                float(slab.get("cc", 0) or 0),
                float(dead_live[0]), float(dead_live[1])),
            "dataFunc.slab_arrange(slabInfo)",
        ])
    number = int(floors.get("number", 6))
    floor_height = int(floors.get("floor_height", 3600))
    lines.extend([
        "",
        "# 标准层复制并提交",
        "dataFunc.Floors_Assemb(0, StdFlr, %d, %d)" % (number, floor_height),
        "dataFunc.DbModel_Assign()",
        "my = Hi_AddToAndReadYjk(dataFunc.GetDbModelData())",
        "out_dir = %s or os.getcwd()" % _q(output_dir or spec.get("output_dir") or ""),
        "os.makedirs(out_dir, exist_ok=True)",
        "ok = my.CreateYDB(out_dir, %s)" % _q(spec["name"] + ".ydb"),
        "print(json.dumps({'ok': bool(ok), "
        "'ydb': os.path.join(out_dir, %s), "
        "'joints': len(xpos) * len(ypos), "
        "'floors': %d}, ensure_ascii=False))" % (
            _q(spec["name"] + ".ydb"), number),
    ])
    return "\n".join(lines) + "\n"


READ_YDB_SCRIPT = '''# -*- coding: utf-8 -*-
import json
import os
import sys
from YJKAPI import *

path = sys.argv[1]
dataFunc = DataFunc()
my = Hi_AddToAndReadYjk()
model = my.ReadYdb(path).ToPyList()
dataFunc.SetModel(model)

def attr(obj, name, default=None):
    return getattr(obj, name, default)

summary = {
    "ok": True,
    "path": path,
    "std_floors": [
        {"ID": attr(s, "ID"), "No": attr(s, "No"), "Height": attr(s, "Height")}
        for s in (attr(model, "m_StdFlr") or [])
    ],
    "floors": [
        {"ID": attr(f, "ID"), "LevelB": attr(f, "LevelB"),
         "Height": attr(f, "Height")}
        for f in (attr(model, "m_Floor") or [])
    ],
    "joints": len(attr(model, "m_Joint") or []),
    "column_sections": [
        {"ID": attr(s, "ID"), "ShapeVal": attr(s, "ShapeVal")}
        for s in (attr(model, "m_ColSect") or [])
    ],
    "beam_sections": [
        {"ID": attr(s, "ID"), "ShapeVal": attr(s, "ShapeVal")}
        for s in (attr(model, "m_BeamSect") or [])
    ],
}
print(json.dumps(summary, ensure_ascii=False))
'''


def read_ydb_script():
    return READ_YDB_SCRIPT
