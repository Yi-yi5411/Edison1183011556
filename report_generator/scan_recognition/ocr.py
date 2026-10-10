# -*- coding: utf-8 -*-
"""第1步：图片 / 扫描 PDF 识别（OCR）。

职责：
- 把输入文件（图片 或 扫描 PDF）转成文字。
- PDF 先经 PyMuPDF(fitz) 渲染成高分辨率图片，再逐页 OCR。
- 默认使用 PaddleOCR（本地，离线，中文效果好）。

外部依赖为可选：未安装 paddleocr / fitz 时不会导致应用崩溃，
会抛出 ``DependencyMissingError`` 并带上安装提示。provider 设为
``mock`` 时走内置模拟器，可在无依赖环境下跑通整条流水线。
"""
import os
import tempfile
from pathlib import Path

from report_generator.scan_recognition.errors import DependencyMissingError
from report_generator.scan_recognition.config import Config

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
_PDF_EXTS = {".pdf"}


def is_supported(file_path):
    return Path(file_path).suffix.lower() in (_IMAGE_EXTS | _PDF_EXTS)


def pdf_pages_to_images(pdf_path, dpi=300, out_dir=None, page_cap=None):
    """把 PDF 渲染成多张 PNG 图片（供 OCR）。返回图片路径列表。"""
    try:
        import fitz  # PyMuPDF
    except Exception:
        raise DependencyMissingError(
            "解析扫描 PDF 需要 PyMuPDF(fitz) 库。",
            "pip install PyMuPDF",
        )
    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="scan_pdf_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    paths = []
    stop = len(doc) if page_cap is None else min(page_cap, len(doc))
    for i in range(stop):
        pix = doc[i].get_pixmap(matrix=mat)
        out = out_dir / f"page_{i + 1:03d}.png"
        pix.save(str(out))
        paths.append(str(out))
    doc.close()
    return paths


class OcrBackend:
    """OCR 后端统一接口。

    ``recognize_items(path) -> [{text, score, box}]`` 返回带坐标与
    置信度的文本框明细；``recognize(path) -> str`` 返回表格结构文本
    （每行单元格以制表符分隔，保持行列对应关系）。
    """

    def recognize(self, path):
        raise NotImplementedError

    def recognize_items(self, path):
        raise NotImplementedError


def _median(values, default=0.0):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return default
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def _build_table_lines(items):
    """把带坐标的 OCR 文本框还原成表格结构文本（行列表）。

    步骤：
    1) 行聚类——按文本框纵向中心聚类（容差 = 0.6 × 行高中位数）；
    2) 行内按横向位置排序，横向间隙 > 0.8 × 行高中位数 时视为换列；
       间隙小视为同一单元格（以空格连接）。
    每行各单元格以制表符（\\t）连接。这样数字矩阵（测区×测点等）
    的行结构得以保留，空缺列虽不占位，但行列顺序与原文一致，
    大模型可按表头逐格对应转写。
    """
    boxes = []
    for it in items:
        text = (it.get("text") or "").strip()
        box = it.get("box") or []
        if not text or len(box) < 4:
            continue
        xs = [float(p[0]) for p in box[:4]]
        ys = [float(p[1]) for p in box[:4]]
        boxes.append({
            "text": text,
            "x0": min(xs), "x1": max(xs),
            "yc": (min(ys) + max(ys)) / 2.0,
            "h": max(ys) - min(ys) or 1.0,
        })
    if not boxes:
        return []

    # 1) 行聚类（按纵向中心，容差与行高中位数挂钩）
    boxes.sort(key=lambda b: b["yc"])
    med_h = _median([b["h"] for b in boxes]) or 20.0
    rows = []
    for b in boxes:
        if rows and abs(b["yc"] - rows[-1]["yc"]) <= 0.6 * med_h:
            row = rows[-1]
            n = len(row["items"])
            row["yc"] = (row["yc"] * n + b["yc"]) / (n + 1)
            row["items"].append(b)
        else:
            rows.append({"yc": b["yc"], "items": [b]})
    for r in rows:
        r["items"].sort(key=lambda b: b["x0"])

    # 2) 行内按横向间隙换列
    gap_thr = 0.8 * med_h
    lines = []
    for r in rows:
        cells, cur = [], ""
        prev_x1 = None
        for b in r["items"]:
            if prev_x1 is not None and b["x0"] - prev_x1 > gap_thr:
                cells.append(cur)
                cur = b["text"]
            else:
                cur = f"{cur} {b['text']}".strip() if cur else b["text"]
            prev_x1 = b["x1"]
        if cur:
            cells.append(cur)
        lines.append("\t".join(cells))
    return lines


class PaddleOcrBackend(OcrBackend):
    """基于 PaddleOCR 的本地 OCR 后端。懒加载以避免影响启动。"""

    def __init__(self, model="ch_PP-OCRv4", use_gpu=True, lang="ch"):
        self.model = model
        self.use_gpu = use_gpu
        self.lang = lang
        self._ocr = None

    def _ensure(self):
        if self._ocr is not None:
            return self._ocr
        try:
            from paddleocr import PaddleOCR, __version__ as _ver
        except Exception:
            raise DependencyMissingError(
                "PaddleOCR 未安装或初始化失败。",
                "pip install paddleocr paddlepaddle",
            )
        major = (str(_ver or "")).split(".")[0]
        try:
            import paddle  # noqa: F401
        except Exception:
            raise DependencyMissingError("未能导入 paddlepaddle。", "pip install paddlepaddle")
        if major == "3":
            # PaddleOCR 3.x：use_gpu/show_log 已废弃，用 device；方向分类改名 use_textline_orientation。
            kwargs = dict(
                lang=self.lang,
                use_textline_orientation=True,
                device="gpu" if self.use_gpu else "cpu",
                text_detection_model_name=None,
                text_recognition_model_name=None,
            )
        else:
            # PaddleOCR 2.x：经典参数（PP-OCRv4 时代的稳定接口）。
            kwargs = dict(
                lang=self.lang,
                use_angle_cls=True,
                use_gpu=self.use_gpu,
                show_log=False,
            )
        try:
            self._ocr = PaddleOCR(**kwargs)
        except Exception as e:
            if not self.use_gpu:
                raise DependencyMissingError(
                    "PaddleOCR 初始化失败：" + str(e)[:200],
                    "pip install paddleocr paddlepaddle")
            # GPU 初始化失败（无独显/CUDA 环境缺失）：回退 CPU 重试
            kwargs2 = dict(kwargs)
            if major == "3":
                kwargs2["device"] = "cpu"
            else:
                kwargs2["use_gpu"] = False
            try:
                self._ocr = PaddleOCR(**kwargs2)
                self.use_gpu = False
            except Exception as e2:
                raise DependencyMissingError(
                    "PaddleOCR 初始化失败：" + str(e2)[:200],
                    "pip install paddleocr paddlepaddle")
        return self._ocr

    def recognize_items(self, path):
        """识别并返回带坐标与置信度的文本框列表（供表格结构还原）。"""
        ocr = self._ensure()
        result = ocr.ocr(str(path), cls=True)
        items = []
        # result: 兼容旧版 list[list[box, (text, score)]] 与新版 result[0]
        pages = result if isinstance(result, list) else [result]
        for page in pages:
            if not page:
                continue
            for entry in page:
                try:
                    box, info = entry[0], entry[1]
                except Exception:
                    continue
                text = (info[0] or "").strip()
                if text:
                    try:
                        score = float(info[1])
                    except Exception:
                        score = None
                    items.append({"text": text, "score": score, "box": box})
        return items

    def recognize(self, path):
        # 坐标还原表格结构：每行单元格以制表符分隔，保留行列对应关系，
        # 数字矩阵（测区×测点）不再退化为一串散落文本。
        return "\n".join(_build_table_lines(self.recognize_items(path)))


class MockOcrBackend(OcrBackend):
    """离线模拟 OCR：返回一段表格结构文本（制表符分列）。

    仅供在未安装 paddleocr 的环境里跑通「文件 -> 结构化 -> 匹配 -> 写表」链路，
    也用于单元验证。真实识别请切换到 paddle。
    """

    _MOCK_TABLE = (
        "楼栋\t批次\t构件编号\t芯样直径(mm)\t测试荷载(kN)\t设计等级\n"
        "2号楼\t1\t1\t100\t320\tC30"
    )

    def recognize(self, path):
        name = Path(path).stem
        return f"[mock-ocr] 已识别文件 {name}。\n{self._MOCK_TABLE}"

    def recognize_items(self, path):
        """把模拟表格文本伪造为带坐标的文本框（列宽/行高按格数均匀分布）。"""
        name = Path(path).stem
        items = []
        y = 0.0
        for line in self.recognize(path).splitlines():
            if line.startswith("[mock-ocr]"):
                y += 30.0
                continue
            x = 0.0
            for cell in line.split("\t"):
                w = max(30.0, 12.0 * len(cell))
                items.append({
                    "text": cell,
                    "score": 0.99,
                    "box": [[x, y], [x + w, y], [x + w, y + 20.0], [x, y + 20.0]],
                })
                x += w + 60.0  # 列间隙 60px，确保换列判定成立
            y += 30.0
        return items


_SUSPECT_CHARS = set("OoIl|，。")


def _is_numeric_like(text):
    """单元格是否为数字型内容（数字与常用分隔符占比高）。"""
    t = (text or "").strip()
    if not t:
        return False
    digitish = sum(1 for ch in t if ch.isdigit() or ch in "+-. ")
    return digitish / len(t) >= 0.6


def ocr_file_detail(path, backend=None, cfg: Config = None, logger=None,
                    low_conf_threshold=None):
    """对单个文件执行 OCR，返回明细结果。

    返回 dict：
    - text: 表格结构文本（行内制表符分列）
    - n_cells / n_rows: 识别到的文本框数 / 还原出的行数
    - low_confidence: 置信度低于阈值的单元格 [{text, score}]
    - suspect_numbers: 形似数字但含易混淆字符(O/o/I/l/|/中文标点)的单元格
    """
    cfg = cfg or Config.load()
    backend = backend or build_ocr_backend(cfg)
    if low_conf_threshold is None:
        low_conf_threshold = float(cfg.ocr.get("low_conf_threshold", 0.85))
    ext = Path(path).suffix.lower()
    all_items = []
    if ext in _PDF_EXTS:
        imgs = pdf_pages_to_images(path, dpi=cfg.ocr.get("pdf_dpi", 300))
        for img in imgs:
            all_items.extend(backend.recognize_items(img))
    else:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        all_items.extend(backend.recognize_items(path))

    lines = _build_table_lines(all_items)
    low, suspect = [], []
    for it in all_items:
        text, score = it["text"], it.get("score")
        score_r = round(score, 3) if score is not None else None
        if score is not None and score < low_conf_threshold:
            low.append({"text": text, "score": score_r})
        if _is_numeric_like(text) and any(ch in _SUSPECT_CHARS for ch in text):
            suspect.append({"text": text, "score": score_r})
    return {
        "text": "\n".join(t for t in lines if t),
        "n_cells": len(all_items),
        "n_rows": len(lines),
        "low_confidence": low,
        "suspect_numbers": suspect,
    }


def build_ocr_backend(cfg: Config):
    provider = (cfg.ocr.get("provider") or "paddle").lower()
    if provider == "mock":
        return MockOcrBackend()
    if provider == "paddle":
        return PaddleOcrBackend(
            model=cfg.ocr.get("model", "ch_PP-OCRv4"),
            use_gpu=cfg.ocr.get("use_gpu", True),
            lang=cfg.ocr.get("lang", "ch"),
        )
    raise ValueError(f"未知 OCR provider: {provider}")


def ocr_file(path, backend=None, cfg: Config = None, logger=None):
    """对单个输入文件执行 OCR，返回表格结构文本（行内制表符分列）。"""
    return ocr_file_detail(path, backend=backend, cfg=cfg, logger=logger)["text"]