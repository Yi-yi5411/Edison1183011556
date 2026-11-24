# -*- coding: utf-8 -*-
"""CAD 绘图层：在线（AutoCAD COM）与离线（DXF）统一接口。

- 在线：图元直接画进正在运行的 AutoCAD（探索者 TSDP2024 平台）Open；
- 离线：写 R12 DXF，可被探索者/AutoCAD 打开，用于无 CAD 环境的验证与出图。

所有方法返回可直接 JSON 序列化的摘要；不在这里做自然语言理解——
语义理解交给 DSH，本模块只接受结构化参数。
"""
import os

from . import config


def _as_point(value, name="point"):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ValueError("%s 需要 [x, y] 两个数值" % name)
    return (float(value[0]), float(value[1]))


class CadDrawing:
    """按配置选择后端，并暴露稳定的绘图方法。"""

    def __init__(self, backend=None, path=None):
        wanted = str(backend or config.BACKEND or "auto").strip().lower()
        if wanted not in ("auto", "com", "dxf"):
            wanted = "auto"
        self.fallback_reason = ""
        self.client = None
        self.dxf = None
        if wanted in ("auto", "com"):
            try:
                from .cad_client import CadClient
                client = CadClient()
                client.connect(launch=False)
                self.client = client
            except Exception as exc:  # noqa: BLE001
                if wanted == "com":
                    raise
                self.fallback_reason = str(exc)
        if self.client is None:
            from .dxf_backend import DxfBackend
            self.dxf = DxfBackend(path)
        self.backend = "com" if self.client else "dxf"

    # ------------------------------------------------------------------ 状态
    def status(self):
        info = {
            "backend": self.backend,
            "fallback_reason": self.fallback_reason,
            "cad_backend_config": config.BACKEND,
            "acad_progid": config.ACAD_PROGID,
            "acad_exe": config.ACAD_EXE,
            "tsdp_dir": config.TSDP_DIR,
            "work_dir": config.TSDP_WORK_DIR,
            "units": "mm",
        }
        if self.client is not None:
            info["connected"] = self.client.is_connected()
            try:
                info["document"] = self.client.doc.Name
            except Exception:  # noqa: BLE001
                info["document"] = ""
        else:
            info["connected"] = False
            info["entities"] = len(self.dxf.entities)
            info["layers"] = sorted(self.dxf.layers)
        return info

    def _target(self):
        return self.client if self.client is not None else self.dxf

    def _result(self, **extra):
        payload = {"backend": self.backend, "ok": True}
        payload.update(extra)
        return payload

    # ------------------------------------------------------------------ 图元
    def line(self, p1, p2, layer=None):
        p1, p2 = _as_point(p1, "p1"), _as_point(p2, "p2")
        self._target().add_line(p1, p2, layer=layer)
        return self._result(op="line", p1=p1, p2=p2, layer=layer or "0")

    def circle(self, center, radius, layer=None):
        center = _as_point(center, "center")
        radius = float(radius)
        if radius <= 0:
            raise ValueError("radius 必须为正数")
        self._target().add_circle(center, radius, layer=layer)
        return self._result(op="circle", center=center, radius=radius,
                            layer=layer or "0")

    def rect(self, p1, p2, layer=None):
        p1, p2 = _as_point(p1, "p1"), _as_point(p2, "p2")
        self._target().add_rect(p1, p2, layer=layer)
        return self._result(op="rect", p1=p1, p2=p2, layer=layer or "0")

    def text(self, text, point, height=None, layer="TEXT"):
        point = _as_point(point, "point")
        height = float(height or config.DEFAULT_TEXT_HEIGHT)
        content = str(text)
        self._target().add_text(content, point, height=height, layer=layer)
        return self._result(op="text", text=content, point=point,
                            height=height, layer=layer)

    def dimension(self, p1, p2, offset=None, layer="DIM"):
        p1, p2 = _as_point(p1, "p1"), _as_point(p2, "p2")
        self._target().add_dimension(p1, p2, offset=offset, layer=layer)
        return self._result(op="dimension", p1=p1, p2=p2, layer=layer)

    # ------------------------------------------------------------------ 构件
    def column(self, center, width, depth=None, layer="COLUMN"):
        center = _as_point(center, "center")
        width = float(width)
        depth = float(depth if depth is not None else width)
        if width <= 0 or depth <= 0:
            raise ValueError("width / depth 必须为正数")
        self._target().add_column(center, width, depth, layer=layer)
        return self._result(op="column", center=center, width=width,
                            depth=depth, layer=layer)

    def beam(self, p1, p2, width, layer="BEAM"):
        p1, p2 = _as_point(p1, "p1"), _as_point(p2, "p2")
        width = float(width)
        if width <= 0:
            raise ValueError("width 必须为正数")
        self._target().add_beam(p1, p2, width, layer=layer)
        return self._result(op="beam", p1=p1, p2=p2, width=width, layer=layer)

    def wall(self, p1, p2, thickness, layer="WALL"):
        p1, p2 = _as_point(p1, "p1"), _as_point(p2, "p2")
        thickness = float(thickness)
        if thickness <= 0:
            raise ValueError("thickness 必须为正数")
        self._target().add_wall(p1, p2, thickness, layer=layer)
        return self._result(op="wall", p1=p1, p2=p2, thickness=thickness,
                            layer=layer)

    # ------------------------------------------------------------------ 轴网
    def grid(self, origin=None, x_spacing=6000, y_spacing=6000,
             x_bays=3, y_bays=3, labels=True):
        origin = _as_point(origin or (0, 0), "origin")
        x_spacing, y_spacing = float(x_spacing), float(y_spacing)
        x_bays, y_bays = int(x_bays), int(y_bays)
        if x_bays < 0 or y_bays < 0:
            raise ValueError("x_bays / y_bays 不能为负")
        if x_spacing <= 0 or y_spacing <= 0:
            raise ValueError("x_spacing / y_spacing 必须为正数")
        self._target().add_axis_grid(
            origin=origin, x_spacing=x_spacing, y_spacing=y_spacing,
            x_bays=x_bays, y_bays=y_bays, labels=bool(labels))
        return self._result(
            op="grid", origin=origin, x_bays=x_bays, y_bays=y_bays,
            x_spacing=x_spacing, y_spacing=y_spacing,
            width=x_spacing * x_bays, height=y_spacing * y_bays)

    # ------------------------------------------------------------------ 通用
    def zoom(self):
        self._target().zoom_extents()
        return self._result(op="zoom")

    def save(self, path=None):
        target = path or self._default_save_path()
        target = os.path.abspath(target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        written = self._target().save(target)
        return self._result(op="save", filepath=str(written or target),
                            size=os.path.getsize(written or target)
                            if os.path.isfile(written or target) else 0)

    def _default_save_path(self):
        if self.client is not None:
            base = config.TSDP_WORK_DIR
            name = "cad_agent.dwg"
        else:
            base = os.path.join(config.TSDP_WORK_DIR
                                if os.path.isdir(config.TSDP_WORK_DIR)
                                else os.getcwd())
            name = "cad_agent.dxf"
        if not os.path.isdir(base):
            base = os.getcwd()
        stamp = __import__("time").strftime("%Y%m%d_%H%M%S")
        return os.path.join(base, "cad_%s.%s" % (stamp, name.split(".")[-1]))

    def open_tsdp(self, wait=30.0):  # noqa: D401
        if self.client is None:
            raise RuntimeError("离线模式无法打开探索者；请把 [cad].backend 设为 auto/com")
        return {"backend": "com",
                "document": self.client.open_tsdp(wait=wait)}

# ── 图纸计划（JSON spec）──────────────────────────────────
_OP_METHODS = {
    "grid": "grid", "column": "column", "beam": "beam", "wall": "wall",
    "rect": "rect", "circle": "circle", "text": "text",
    "dimension": "dimension", "dim": "dimension",
    "line": "line", "zoom": "zoom", "save": "save",
}


def run_plan(drawing, plan):
    """执行一份图纸计划：{"ops": [{...}, ...]}，返回逐步结果。

    每个 op 形如 {"op": "grid", "x_bays": 3, ...}；未知 op 直接报错，
    保证计划可审计（不做自然语言猜测）。
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("ops"), list):
        raise ValueError("图纸计划需要 {\"ops\": [...]}")
    results = []
    for index, item in enumerate(plan["ops"]):
        if not isinstance(item, dict):
            raise ValueError("第 %d 个 op 不是对象" % (index + 1))
        op = str(item.get("op") or "").strip().lower()
        method = _OP_METHODS.get(op)
        if method is None:
            raise ValueError("不支持的 op：%r（可用：%s）"
                             % (op, "、".join(sorted(_OP_METHODS))))
        kwargs = {k: v for k, v in item.items() if k != "op"}
        result = getattr(drawing, method)(**kwargs)
        result["index"] = index + 1
        results.append(result)
    return {"backend": drawing.backend, "count": len(results),
            "results": results}
