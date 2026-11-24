# -*- coding: utf-8 -*-
"""离线 DXF 后端：不依赖 AutoCAD，直接把图元写为 R12 DXF 文件。

用途：当未连接 AutoCAD 时作为回退，保存命令会生成 .dxf，可在探索者/任意 CAD 中打开。
图纸单位与在线模式一致，统一为毫米。
"""

import math

from . import config


class DxfBackend:
    """与 CadClient 方法名保持一致的轻量 DXF 生成器。"""

    def __init__(self, path=None):
        self.entities = []   # (kind, data)
        self.layers = {}     # name -> color
        self.path = path
        self._layer = "0"

    # ------------------------------------------------------------------ 图层
    def set_layer(self, name, color=None):
        self._layer = name
        if color is not None:
            self.layers[name] = color
        return name

    # ------------------------------------------------------------------ 图元
    def add_line(self, p1, p2, layer=None):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        self.entities.append(("LINE", {"layer": self._layer, "p1": tuple(p1), "p2": tuple(p2)}))

    def add_circle(self, center, radius, layer=None):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        self.entities.append(("CIRCLE", {"layer": self._layer, "center": tuple(center), "r": float(radius)}))

    def add_rect(self, p1, p2, layer=None):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        x1, y1 = p1
        x2, y2 = p2
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        self.entities.append(("LWPOLYLINE", {"layer": self._layer, "pts": pts, "closed": True}))

    def add_polygon(self, corners, layer=None, closed=True):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        self.entities.append(("LWPOLYLINE", {"layer": self._layer, "pts": [tuple(c) for c in corners], "closed": closed}))

    def add_text(self, text, point, height=None, layer="TEXT"):
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        h = height or config.DEFAULT_TEXT_HEIGHT
        self.entities.append(("TEXT", {"layer": self._layer, "text": str(text), "p": tuple(point), "h": float(h)}))

    def add_dimension(self, p1, p2, offset=None, layer="DIM"):
        """简化标注：绘制标注线并写入距离文字（AutoCAD 在线模式为真尺寸标注）。"""
        if layer:
            self.set_layer(layer, config.LAYERS.get(layer))
        x1, y1 = p1
        x2, y2 = p2
        span = max(abs(x2 - x1), abs(y2 - y1), 1.0)
        off = offset or max(400.0, span * 0.15)
        if abs(y2 - y1) < 1e-6:
            a, b = (x1, y1 + off), (x2, y2 + off)
            tp = ((x1 + x2) / 2.0, y1 + off + off * 0.6)
        elif abs(x2 - x1) < 1e-6:
            a, b = (x1 + off, y1), (x2 + off, y2)
            tp = ((x1 + x2) / 2.0 + off * 0.6, (y1 + y2) / 2.0)
        else:
            a, b = (x1 + off, y1 + off), (x2 + off, y2 + off)
            tp = ((x1 + x2) / 2.0 + off, (y1 + y2) / 2.0 + off * 0.6)
        self.entities.append(("LINE", {"layer": self._layer, "p1": a, "p2": b}))
        self.entities.append(("TEXT", {"layer": "TEXT", "text": "%.0f" % math.hypot(x2 - x1, y2 - y1), "p": tp, "h": 250.0}))

    # ------------------------------------------------------------------ 构件
    def _offset_rect_along(self, p1, p2, width):
        x1, y1 = p1
        x2, y2 = p2
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length * (width / 2.0)
        ny = dx / length * (width / 2.0)
        return [(x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x2 - nx, y2 - ny), (x2 + nx, y2 + ny)]

    def add_beam(self, p1, p2, width, layer="BEAM"):
        self.add_polygon(self._offset_rect_along(p1, p2, width), layer=layer, closed=True)

    def add_wall(self, p1, p2, thickness, layer="WALL"):
        self.add_polygon(self._offset_rect_along(p1, p2, thickness), layer=layer, closed=True)

    def add_column(self, center, width, depth=None, layer="COLUMN"):
        depth = depth if depth is not None else width
        x, y = center
        self.add_rect((x - width / 2.0, y - depth / 2.0), (x + width / 2.0, y + depth / 2.0), layer=layer)

    # ------------------------------------------------------------------ 轴网
    def add_axis_grid(self, origin=(0.0, 0.0), x_spacing=6000.0, y_spacing=6000.0,
                      x_bays=3, y_bays=3, labels=True):
        self.set_layer("AXIS", config.LAYERS.get("AXIS"))
        x0, y0 = origin
        x1 = x0 + x_spacing * x_bays
        y1 = y0 + y_spacing * y_bays
        for i in range(y_bays + 1):
            y = y0 + y_spacing * i
            self.add_line((x0, y), (x1, y))
        for j in range(x_bays + 1):
            x = x0 + x_spacing * j
            self.add_line((x, y0), (x, y1))
        if labels:
            self._add_axis_labels(origin, x_spacing, y_spacing, x_bays, y_bays)

    def _add_axis_labels(self, origin, x_spacing, y_spacing, x_bays, y_bays):
        x0, y0 = origin
        d = config.AXIS_LABEL_DIAMETER
        r = d / 2.0
        y_bottom = y0 - r - 400.0
        for i in range(x_bays + 1):
            x = x0 + x_spacing * i
            self.add_circle((x, y_bottom), r, layer="AXIS")
            self.add_text(str(i + 1), (x - r * 0.30, y_bottom - r * 0.40), height=d * 0.35, layer="TEXT")
        x_left = x0 - r - 400.0
        for j in range(y_bays + 1):
            y = y0 + y_spacing * j
            self.add_circle((x_left, y), r, layer="AXIS")
            self.add_text(chr(ord("A") + j), (x_left - r * 0.40, y - r * 0.40), height=d * 0.35, layer="TEXT")

    # ------------------------------------------------------------------ 输出
    def zoom_extents(self):
        # 离线模式无需缩放
        return None

    def save(self, path):
        return self.write(path)

    def write(self, path=None):
        path = path or self.path or "output.dxf"
        out = []
        A = out.append
        A("0"); A("SECTION"); A("2"); A("HEADER")
        A("9"); A("$ACADVER"); A("1"); A("AC1009")
        A("9"); A("$DWGCODEPAGE"); A("3"); A("ANSI_936")
        A("0"); A("ENDSEC")
        A("0"); A("SECTION"); A("2"); A("TABLES")
        A("0"); A("TABLE"); A("2"); A("LAYER"); A("70"); A(str(len(self.layers) + 1))
        A("0"); A("LAYER"); A("2"); A("0"); A("70"); A("0"); A("62"); A("7"); A("6"); A("CONTINUOUS")
        for name, color in self.layers.items():
            A("0"); A("LAYER"); A("2"); A(name); A("70"); A("0"); A("62"); A(str(color)); A("6"); A("CONTINUOUS")
        A("0"); A("ENDTAB"); A("0"); A("ENDSEC")
        A("0"); A("SECTION"); A("2"); A("ENTITIES")
        for kind, data in self.entities:
            self._emit(out, kind, data)
        A("0"); A("ENDSEC")
        A("0"); A("EOF")
        with open(path, "w", encoding="gbk", errors="replace") as f:
            f.write("\n".join(out) + "\n")
        return path

    @staticmethod
    def _emit(out, kind, data):
        A = out.append
        layer = data["layer"]
        if kind == "LINE":
            x1, y1 = data["p1"]; x2, y2 = data["p2"]
            A("0"); A("LINE"); A("8"); A(layer)
            A("10"); A(_fmt(x1)); A("20"); A(_fmt(y1)); A("30"); A("0")
            A("11"); A(_fmt(x2)); A("21"); A(_fmt(y2)); A("31"); A("0")
        elif kind == "CIRCLE":
            x, y = data["center"]
            A("0"); A("CIRCLE"); A("8"); A(layer)
            A("10"); A(_fmt(x)); A("20"); A(_fmt(y)); A("30"); A("0")
            A("40"); A(_fmt(data["r"]))
        elif kind == "LWPOLYLINE":
            pts = data["pts"]
            A("0"); A("LWPOLYLINE"); A("8"); A(layer)
            A("90"); A(str(len(pts)))
            A("70"); A("1" if data["closed"] else "0")
            for px, py in pts:
                A("10"); A(_fmt(px)); A("20"); A(_fmt(py))
        elif kind == "TEXT":
            x, y = data["p"]
            A("0"); A("TEXT"); A("8"); A(layer)
            A("10"); A(_fmt(x)); A("20"); A(_fmt(y)); A("30"); A("0")
            A("40"); A(_fmt(data["h"]))
            A("1"); A(data["text"])
        else:
            raise ValueError("unknown entity kind: " + kind)


def _fmt(v):
    """去掉多余尾零，避免 DXF 数值过长。"""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.4f" % v).rstrip("0").rstrip(".")
