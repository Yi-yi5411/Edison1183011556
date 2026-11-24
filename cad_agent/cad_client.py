# -*- coding: utf-8 -*-
"""AutoCAD 2020 COM 自动化层：连接、图层、图元、轴网与常用构件。

说明：探索者 TSDP2024 是架设在 AutoCAD 2020 上的结构绘图平台，本模块通过
AutoCAD ActiveX/COM（pywin32）直接创建图元，单位统一使用毫米。
"""

import math
import os
import subprocess
import time

from . import config

_com = {}


def _com_modules():
    """延迟导入 pywin32：没有安装时仍可导入本模块并使用离线 DXF 后端。"""
    if "pythoncom" not in _com:
        try:
            import pythoncom
            import win32com.client as win32_client
        except ImportError as exc:  # pragma: no cover - 仅在线模式需要
            raise RuntimeError(
                "在线 CAD 需要 pywin32（pip install pywin32）；"
                "或把 [cad].backend 设为 dxf 使用离线模式") from exc
        _com["pythoncom"] = pythoncom
        _com["win32"] = win32_client
    return _com["pythoncom"], _com["win32"]


def _pt(x, y, z=0.0):
    """构造 AutoCAD COM 所需的 3D 点 Variant。"""
    pythoncom, win32 = _com_modules()
    return win32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8,
        [float(x), float(y), float(z)],
    )


def _doubles(values):
    """构造一维 double 数组 Variant（用于多段线顶点）。"""
    pythoncom, win32 = _com_modules()
    return win32.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8,
        [float(v) for v in values],
    )


class CadClient:
    """封装 AutoCAD 的常用绘图调用。"""

    def __init__(self):
        self.app = None
        self.doc = None
        self.ms = None

    # ------------------------------------------------------------------ 连接
    def is_connected(self):
        return self.app is not None and self.doc is not None

    def connect(self, launch=False, timeout=90.0):
        """连接正在运行的 AutoCAD；launch=True 时若未运行则启动纯 AutoCAD。"""
        _pythoncom, win32 = _com_modules()
        for progid in (config.ACAD_PROGID, "AutoCAD.Application"):
            try:
                self.app = win32.GetActiveObject(progid)
                break
            except Exception:
                self.app = None
        if self.app is None:
            if not launch:
                raise RuntimeError(
                    "AutoCAD 未运行。请先启动探索者 TSDP2024，"
                    "或把 [cad].backend 设为 dxf 使用离线模式。"
                )
            self.app = win32.Dispatch(config.ACAD_PROGID)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.app.Visible = True
                self.doc = self.app.ActiveDocument
                self.ms = self.doc.ModelSpace
                return self.doc.Name
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("连接 AutoCAD 超时，请稍后重试。")

    def ensure(self):
        """确保已连接并返回 ModelSpace。"""
        if self.app is None or self.doc is None:
            self.connect(launch=False)
        return self.ms

    def open_tsdp(self, wait=30.0):
        """通过探索者启动器打开 TSDP2024，并等待 AutoCAD COM 就绪。"""
        if not os.path.isfile(config.TSDP_RUNNER):
            raise RuntimeError("未找到探索者启动器：" + config.TSDP_RUNNER)
        _pythoncom, win32 = _com_modules()
        subprocess.Popen([config.TSDP_RUNNER], cwd=config.TSDP_DIR)
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                self.app = win32.GetActiveObject(config.ACAD_PROGID)
                self.app.Visible = True
                self.doc = self.app.ActiveDocument
                self.ms = self.doc.ModelSpace
                return self.doc.Name
            except Exception:
                time.sleep(0.5)
        raise RuntimeError(
            "探索者已启动，但未在限定时间内连上 AutoCAD。可稍后重试绘图命令。"
        )

    # ------------------------------------------------------------------ 图层
    def set_layer(self, name, color=None):
        """切换当前图层，不存在时自动创建。"""
        self.ensure()
        layers = self.doc.Layers
        target = None
        for i in range(layers.Count):
            layer = layers.Item(i)
            if layer.Name.lower() == name.lower():
                target = layer
                break
        if target is None:
            target = layers.Add(name)
        if color is not None:
            target.Color = color
        self.doc.ActiveLayer = target
        return target

    # ------------------------------------------------------------------ 图元
    def add_line(self, p1, p2, layer=None):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        return self.ms.AddLine(_pt(p1[0], p1[1]), _pt(p2[0], p2[1]))

    def add_circle(self, center, radius, layer=None):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        return self.ms.AddCircle(_pt(center[0], center[1]), float(radius))

    def add_rect(self, p1, p2, layer=None):
        """以 p1、p2 为对角点绘制闭合矩形多段线。"""
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        x1, y1 = p1
        x2, y2 = p2
        pl = self.ms.AddLightWeightPolyline(
            _doubles([x1, y1, x2, y1, x2, y2, x1, y2])
        )
        pl.Closed = True
        return pl

    def add_polygon(self, corners, layer=None, closed=True):
        """按顶点列表绘制多段线。"""
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        flat = []
        for c in corners:
            flat.extend([c[0], c[1]])
        pl = self.ms.AddLightWeightPolyline(_doubles(flat))
        pl.Closed = closed
        return pl

    def add_text(self, text, point, height=None, layer="TEXT"):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        h = height or config.DEFAULT_TEXT_HEIGHT
        return self.ms.AddText(str(text), _pt(point[0], point[1]), float(h))

    def add_dimension(self, p1, p2, offset=None, layer="DIM"):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        x1, y1 = p1
        x2, y2 = p2
        if offset is None:
            span = max(abs(x2 - x1), abs(y2 - y1), 1.0)
            offset = max(400.0, span * 0.15)
        if abs(y2 - y1) < 1e-6:
            loc = ((x1 + x2) / 2.0, y1 + offset)
        elif abs(x2 - x1) < 1e-6:
            loc = (x1 + offset, (y1 + y2) / 2.0)
        else:
            loc = ((x1 + x2) / 2.0 + offset, (y1 + y2) / 2.0 + offset)
        return self.ms.AddDimAligned(
            _pt(x1, y1), _pt(x2, y2), _pt(loc[0], loc[1])
        )

    # ------------------------------------------------------------------ 构件
    def _offset_rect_along(self, p1, p2, width):
        """沿线段方向生成一个宽度为 width 的矩形四个角点。"""
        x1, y1 = p1
        x2, y2 = p2
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length * (width / 2.0)
        ny = dx / length * (width / 2.0)
        return [
            (x1 + nx, y1 + ny),
            (x1 - nx, y1 - ny),
            (x2 - nx, y2 - ny),
            (x2 + nx, y2 + ny),
        ]

    def add_beam(self, p1, p2, width, layer="BEAM"):
        return self.add_polygon(self._offset_rect_along(p1, p2, width), layer=layer)

    def add_wall(self, p1, p2, thickness, layer="WALL"):
        return self.add_polygon(self._offset_rect_along(p1, p2, thickness), layer=layer)

    def add_column(self, center, width, depth=None, layer="COLUMN"):
        depth = depth if depth is not None else width
        x, y = center
        return self.add_rect(
            (x - width / 2.0, y - depth / 2.0),
            (x + width / 2.0, y + depth / 2.0),
            layer=layer,
        )

    # ------------------------------------------------------------------ 轴网
    def add_axis_grid(self, origin=(0.0, 0.0), x_spacing=6000.0, y_spacing=6000.0,
                      x_bays=3, y_bays=3, labels=True):
        """绘制 X/Y 轴网：x_bays、y_bays 为开间数，网格线数 = 开间数 + 1。"""
        self.set_layer("AXIS", config.LAYERS.get("AXIS"))
        x0, y0 = origin
        x1 = x0 + x_spacing * x_bays
        y1 = y0 + y_spacing * y_bays
        for i in range(y_bays + 1):  # 横向线，编号为 1..x_bays+1
            y = y0 + y_spacing * i
            self.add_line((x0, y), (x1, y))
        for j in range(x_bays + 1):  # 竖向线，编号为 A..x_bays+1
            x = x0 + x_spacing * j
            self.add_line((x, y0), (x, y1))
        if labels:
            self._add_axis_labels(origin, x_spacing, y_spacing, x_bays, y_bays)
        return {"x_bays": x_bays, "y_bays": y_bays, "x1": x1, "y1": y1}

    def _add_axis_labels(self, origin, x_spacing, y_spacing, x_bays, y_bays):
        x0, y0 = origin
        d = config.AXIS_LABEL_DIAMETER
        r = d / 2.0
        # 底部编号（1,2,3...）
        y_bottom = y0 - r - 400.0
        for i in range(x_bays + 1):
            x = x0 + x_spacing * i
            self.add_circle((x, y_bottom), r, layer="AXIS")
            self.add_text(str(i + 1), (x - r * 0.30, y_bottom - r * 0.40),
                          height=d * 0.35, layer="TEXT")
        # 左侧编号（A,B,C...）
        x_left = x0 - r - 400.0
        for j in range(y_bays + 1):
            y = y0 + y_spacing * j
            self.add_circle((x_left, y), r, layer="AXIS")
            self.add_text(chr(ord("A") + j), (x_left - r * 0.40, y - r * 0.40),
                          height=d * 0.35, layer="TEXT")

    # ------------------------------------------------------------------ 通用
    def zoom_extents(self):
        self.ensure()
        self.app.ZoomExtents()

    def save(self, path):
        self.ensure()
        if path:
            return self.doc.SaveAs(path)
        return self.doc.Save()
