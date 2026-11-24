# -*- coding: utf-8 -*-
r"""PaddleOCR 3.x GPU OCR 服务。

主程序运行在 Python 3.8（PaddleOCR 2.8 CPU）。RTX 5090 属于 sm_120，
需要 PaddlePaddle 3.x + CUDA 12.9，而官方 CUDA 12.9 wheel 不再提供
cp38。因此把 GPU OCR 放进独立的 Python 3.12 进程，通过本机 HTTP
暴露，主程序按需调用；服务不可用时主程序自动回退 CPU。

启动：
    .venv-ocr-gpu\Scripts\python.exe scripts\ocr_gpu_service.py --port 8770

接口：
    GET  /health  -> {ok, ready, gpu, paddle, paddleocr, models}
    POST /ocr     -> {"path": "..."} -> {ok, items: [{text, score, box}]}
"""
import argparse
import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("ocr_gpu")


def _jsonable(value):
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _result_dict(result):
    """把 PaddleOCR 3.x 的 OCRResult / dict 统一成 dict。"""
    if isinstance(result, dict):
        data = result
    else:
        data = getattr(result, "json", None)
        if callable(data):
            data = data()
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            try:
                data = dict(result)
            except Exception:
                data = {}
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        data = data["res"]
    return data if isinstance(data, dict) else {}


def _items_from_result(result):
    items = []
    for page in result or []:
        data = _result_dict(page)
        texts = data.get("rec_texts") or []
        scores = data.get("rec_scores") or []
        polys = data.get("rec_polys")
        if polys is None:
            polys = data.get("dt_polys") or []
        for i, text in enumerate(texts):
            text = str(text or "").strip()
            if not text:
                continue
            score = None
            if i < len(scores):
                try:
                    score = float(scores[i])
                except Exception:
                    score = None
            box = _jsonable(polys[i]) if i < len(polys) else []
            items.append({"text": text, "score": score, "box": box})
    return items


class OcrState:
    def __init__(self):
        self.ocr = None
        self.error = ""
        self.ready = False
        self.gpu = False
        self.device = ""
        self.paddle_version = ""
        self.paddleocr_version = ""
        self.models = {}
        self.lock = threading.Lock()

    def health(self):
        return {
            "ok": self.ready and not self.error,
            "ready": self.ready,
            "gpu": self.gpu,
            "device": self.device,
            "paddle": self.paddle_version,
            "paddleocr": self.paddleocr_version,
            "models": self.models,
            "error": self.error,
        }


STATE = OcrState()


def _add_cuda_dll_dirs():
    """把 nvidia-*-cu12 wheel 的 DLL 目录加入搜索路径。

    Paddle 在 Windows 上不一定能自动找到 pip 安装的 cublas/cudnn/cufft 等
    DLL；显式 add_dll_directory 后，CUDA 12.9 wheel 才能被加载。
    """
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return []
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    added = []
    if not base.is_dir():
        return added
    for child in sorted(base.iterdir()):
        bin_dir = child / "bin"
        if not bin_dir.is_dir():
            continue
        try:
            os.add_dll_directory(str(bin_dir))
            added.append(str(bin_dir))
        except OSError as e:
            LOG.warning("无法加入 DLL 目录 %s: %s", bin_dir, e)
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")
        LOG.info("CUDA DLL 目录: %s", ", ".join(added))
    return added


def load_model(args):
    import paddle
    import paddleocr

    STATE.paddle_version = getattr(paddle, "__version__", "")
    STATE.paddleocr_version = getattr(paddleocr, "__version__", "")
    cuda = bool(paddle.device.is_compiled_with_cuda())
    count = int(paddle.device.cuda.device_count()) if cuda else 0
    want_gpu = args.device != "cpu"
    if want_gpu and not (cuda and count > 0):
        raise RuntimeError(
            "Paddle 不是 CUDA 版或未检测到 GPU：compiled_with_cuda=%s, count=%s"
            % (cuda, count)
        )
    device = "gpu:0" if want_gpu else "cpu"
    from paddleocr import PaddleOCR

    kwargs = dict(
        lang="ch",
        device=device,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        text_detection_model_name=args.det_model or None,
        text_recognition_model_name=args.rec_model or None,
    )
    # None 不作为模型名传入，避免部分 PaddleOCR 版本把它当成路径。
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    LOG.info("初始化 PaddleOCR device=%s det=%s rec=%s", device,
             args.det_model or "default", args.rec_model or "default")
    started = time.time()
    STATE.ocr = PaddleOCR(**kwargs)
    STATE.gpu = want_gpu
    STATE.device = str(getattr(paddle.device, "get_device", lambda: device)())
    STATE.models = {
        "det": args.det_model or "default",
        "rec": args.rec_model or "default",
        "orientation": "PP-LCNet_x1_0_textline_ori" if kwargs.get("use_textline_orientation") else "",
    }
    STATE.ready = True
    LOG.info("PaddleOCR 就绪，用时 %.1fs，device=%s", time.time() - started, STATE.device)


def run_ocr(path):
    if not STATE.ready or STATE.ocr is None:
        raise RuntimeError(STATE.error or "OCR 模型尚未就绪")
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    with STATE.lock:
        result = STATE.ocr.predict(str(p))
        items = _items_from_result(result)
    return items


class Handler(BaseHTTPRequestHandler):
    server_version = "StructuralOcrGpu/1.0"

    def log_message(self, fmt, *args):
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            h = STATE.health()
            self._send(200 if h["ready"] else 503, h)
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/ocr":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(min(length, 1024 * 1024)) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            path = str(payload.get("path") or "")
            if not path:
                raise ValueError("缺少 path")
            items = run_ocr(path)
            self._send(200, {"ok": True, "items": items, "device": STATE.device})
        except FileNotFoundError as e:
            self._send(404, {"ok": False, "error": "文件不存在：" + str(e)})
        except Exception as e:
            LOG.exception("OCR 失败")
            self._send(500, {"ok": False, "error": str(e)[:500]})


def main():
    parser = argparse.ArgumentParser(description="PaddleOCR GPU HTTP service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--device", default="gpu", choices=["gpu", "cpu"])
    parser.add_argument("--det-model", default="PP-OCRv5_mobile_det")
    parser.add_argument("--rec-model", default="PP-OCRv5_mobile_rec")
    parser.add_argument("--cache-dir", default=str(ROOT / "data" / "models" / "paddlex"))
    args = parser.parse_args()

    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", args.cache_dir)
    # 国内网络优先走百度 BOS 官方模型源；可用 PADDLE_PDX_MODEL_SOURCE 覆盖为
    # modelscope / huggingface / aistudio。
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "bos")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    _add_cuda_dll_dirs()
    try:
        load_model(args)
    except Exception as e:
        STATE.error = str(e)[:500]
        LOG.exception("PaddleOCR GPU 初始化失败")
        # 仍启动服务返回 503，方便主程序读取失败原因。
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    LOG.info("监听 http://%s:%s", args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
