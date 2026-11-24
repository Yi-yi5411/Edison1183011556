# -*- coding: utf-8 -*-
"""扫描识别的异步作业封装（P2b）。

同步 /scan/run 需要浏览器上传文件；作业化后调用方可以直接给本机路径并轮询结果，
避免一次工具调用被 OCR 长时间占满。

作业默认只保存在内存；后端启动时调用 configure(path) 后才落到 data/scan_jobs.json。
这样单元测试不会污染真实作业，服务重启后仍能读取最近的作业状态；重启时仍在
running 的作业会被标记为 interrupted，避免调用方只拿到一个 404。

对外：
    configure(path) -> None
    submit(filepath, detection_item=None, runner=None) -> 作业视图
    status(job_id) -> 作业视图或 None
    list_jobs(limit=20) -> [作业视图]
"""
import json
import os
import threading
import time
import uuid

_MAX_JOBS = 50
_jobs = {}
_order = []
_lock = threading.RLock()
_persist_path = ""


class ScanJobError(Exception):
    """可读的作业提交错误（路由层转 400）。"""


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _compact(result):
    """只保留写回需要的信息，避免把 OCR 中间结构塞进作业记录。"""
    result = result or {}
    return {
        "doc_id": result.get("doc_id"),
        "detection_item": result.get("detection_item"),
        "sub_item": result.get("sub_item"),
        "columns": result.get("columns") or [],
        "rows": result.get("rows") or [],
        "field_warnings": result.get("field_warnings") or [],
        "classification": result.get("classification"),
        "ocr_stats": result.get("ocr_stats"),
        "repair": result.get("repair"),
    }


def _default_runner(filepath, detection_item=None):
    """真正跑 OCR 流水线；重模块延迟到作业线程里导入。"""
    from deps import Config, ITEM_COLUMNS
    from scan_recognition.pipeline import ScanRecognitionPipeline

    cfg = Config.load()
    columns = list(ITEM_COLUMNS.get(detection_item, [])) if detection_item else []
    pipeline = ScanRecognitionPipeline(cfg=cfg)
    try:
        return pipeline.recognize(filepath, detection_item or None,
                                  detection_item or None, columns)
    finally:
        try:
            pipeline.close()
        except Exception:  # noqa: BLE001
            pass


def _view(record, with_result=True):
    view = {key: record.get(key) for key in (
        "id", "status", "filepath", "detection_item", "submitted_at",
        "finished_at", "error", "duration_ms")}
    if with_result and record.get("status") == "done":
        view["result"] = record.get("result")
    return view


def _prune():
    while len(_order) > _MAX_JOBS:
        old = _order.pop(0)
        _jobs.pop(old, None)


def _persist():
    """把当前作业原子写入磁盘；未 configure 时保持纯内存模式。"""
    path = _persist_path
    if not path:
        return
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        payload = {"jobs": [_jobs[i] for i in _order if i in _jobs]}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 —— 持久化失败不能影响识别本身
        pass


def configure(path=""):
    """启用/切换持久化文件，并载入上次作业。

    后端启动时调用；单元测试不调用，因此不会读写真实 data/scan_jobs.json。
    上次进程退出时仍为 running 的作业没有线程继续执行，统一标记为 interrupted。
    """
    global _persist_path
    with _lock:
        _persist_path = os.path.abspath(path) if path else ""
        _jobs.clear()
        _order.clear()
        if not _persist_path or not os.path.isfile(_persist_path):
            return
        try:
            with open(_persist_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:  # noqa: BLE001 —— 损坏的作业文件不应阻塞服务启动
            return
        for record in (payload or {}).get("jobs") or []:
            if not isinstance(record, dict):
                continue
            job_id = str(record.get("id") or "")
            if not job_id:
                continue
            if record.get("status") == "running":
                record.update(
                    status="interrupted",
                    error="后端重启，识别作业已中断，请重新提交",
                    finished_at=_now(),
                    duration_ms=0,
                )
            _jobs[job_id] = record
            _order.append(job_id)
        _prune()
        _persist()


def _run(job_id, path, detection_item, runner):
    started = time.time()
    try:
        result = runner(path, detection_item)
        with _lock:
            record = _jobs.get(job_id)
            if record is not None:
                record.update(status="done", result=_compact(result),
                              finished_at=_now(),
                              duration_ms=int((time.time() - started) * 1000))
                _persist()
    except Exception as e:  # noqa: BLE001 —— 作业失败要落进记录，不能抛给线程
        with _lock:
            record = _jobs.get(job_id)
            if record is not None:
                record.update(status="failed", error=str(e)[:500],
                              finished_at=_now(),
                              duration_ms=int((time.time() - started) * 1000))
                _persist()


def submit(filepath, detection_item=None, runner=None):
    path = os.path.abspath(str(filepath or ""))
    if not os.path.isfile(path):
        raise ScanJobError("文件不存在：%s" % path)
    job_id = "scan-" + uuid.uuid4().hex[:12]
    record = {
        "id": job_id, "status": "running", "filepath": path,
        "detection_item": detection_item or "",
        "submitted_at": _now(), "finished_at": "", "error": "",
        "result": None, "duration_ms": 0,
    }
    with _lock:
        _jobs[job_id] = record
        _order.append(job_id)
        _prune()
        _persist()
    thread = threading.Thread(
        target=_run, name=job_id,
        args=(job_id, path, detection_item, runner or _default_runner),
        daemon=True)
    thread.start()
    return _view(record)


def status(job_id):
    with _lock:
        record = _jobs.get(str(job_id or ""))
        return _view(record) if record is not None else None


def list_jobs(limit=20):
    try:
        limit = max(1, min(int(limit or 20), _MAX_JOBS))
    except (TypeError, ValueError):
        limit = 20
    with _lock:
        ids = list(reversed(_order))[:limit]
        return [_view(_jobs[i], with_result=False) for i in ids if i in _jobs]
