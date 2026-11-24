# -*- coding: utf-8 -*-
"""CAD 配置：统一从 config/structural.toml 的 [cad] 段读取（环境变量可覆盖）。

不再写死本机路径；缺省值只是常见安装位置，实际以配置为准。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "webapp") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "webapp"))

try:
    from structural_config import get as _get
except ImportError:  # pragma: no cover - 脱离项目运行时的兜底
    def _get(section, key, default=None):
        return default


def _path(key, default):
    value = str(_get("cad", key, default) or default)
    return value if os.path.isabs(value) else os.path.join(_ROOT, value)


BACKEND = str(_get("cad", "backend", "auto") or "auto").strip().lower()

ACAD_PROGID = str(_get("cad", "acad_progid", "AutoCAD.Application.23"))
ACAD_EXE = _path("acad_exe",
                 r"D:\Program Files\Autodesk\AutoCAD 2020\acad.exe")

TSDP_DIR = _path("tsdp_dir", r"D:\Program Files\TszCAD\TSDP2024")
TSDP_RUNNER = os.path.join(TSDP_DIR, "TSDPRun.exe")

TSDP_WORK_DIR = _path("work_dir", r"D:\TSSDWORK")

# 绘图默认参数（图纸单位统一为毫米）
DEFAULT_TEXT_HEIGHT = float(_get("cad", "text_height", 300) or 300)
AXIS_LABEL_DIAMETER = float(_get("cad", "axis_label_diameter", 800) or 800)

# 图层名 -> AutoCAD ACI 颜色索引
LAYERS = {
    "AXIS": 1,     # 红
    "COLUMN": 3,   # 绿
    "BEAM": 4,     # 青
    "WALL": 2,     # 黄
    "SLAB": 30,    # 橙
    "TEXT": 7,     # 白
    "DIM": 3,      # 绿
}
