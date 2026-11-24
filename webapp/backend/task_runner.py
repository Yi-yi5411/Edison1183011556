# -*- coding: utf-8 -*-
"""并行任务中心：把检测项评定拆成可观察的并发任务。

设计要点：
- 任务只读取当前工程快照，计算在独立线程中完成；
- 全部完成后由协调线程一次性写回 ProjectState，避免多个评定结果边算边写；
- 任务持久化到 data/tasks.json，进程重启后把中断的任务标记为 interrupted；
- 并发度受 STRUCTURAL_TASK_WORKERS 控制（默认 4），后续可替换为进程池或 ACP worker。
"""
import copy
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from deps import ROOT, assess, get_controller, get_spec, get_state

TASKS_PATH = os.path.join(ROOT, "data", "tasks.json")
MAX_TASKS = 30
MAX_WORKERS = max(1, min(8, int(os.environ.get("STRUCTURAL_TASK_WORKERS", "4") or "4")))


def _now():
    return time.time()


def _iso(value):
    if not value:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(value)))
    except (TypeError, ValueError, OSError):
        return ""


def _result_summary(result):
    result = result if isinstance(result, dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "conclusion": str(result.get("conclusion") or ""),
        "errors": [str(item) for item in (result.get("errors") or [])][:8],
        "warnings": [str(item) for item in (result.get("warnings") or [])][:8],
    }


def _public_task(task):
    view = copy.deepcopy(task)
    for item in view.get("items") or []:
        item["result"] = _result_summary(item.get("result"))
    view["created_at_text"] = _iso(view.get("created_at"))
    view["started_at_text"] = _iso(view.get("started_at"))
    view["finished_at_text"] = _iso(view.get("finished_at"))
    view["progress"] = (
        int(round(100.0 * (view.get("completed") or 0) / view.get("total") or 0))
        if view.get("total") else 0
    )
    return view


class TaskRunner:
    def __init__(self, path=None):
        self.path = path or TASKS_PATH
        self._lock = threading.RLock()
        self._tasks = []
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = []
        tasks = raw if isinstance(raw, list) else []
        changed = False
        for task in tasks:
            if task.get("status") == "running":
                task["status"] = "interrupted"
                task["finished_at"] = task.get("finished_at") or _now()
                task["message"] = "后端重启，任务已中断"
                changed = True
            for item in task.get("items") or []:
                if item.get("status") in ("queued", "running"):
                    item["status"] = "interrupted"
                    item["message"] = item.get("message") or "后端重启，已中断"
                    changed = True
        self._tasks = tasks[:MAX_TASKS]
        if changed:
            self._persist()

    def _persist(self):
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(self._tasks[:MAX_TASKS], fh, ensure_ascii=False, indent=2)
        os.replace(temp, self.path)

    def list(self, limit=12):
        with self._lock:
            return [_public_task(task) for task in self._tasks[:max(1, min(50, int(limit)))]]

    def get(self, task_id):
        with self._lock:
            for task in self._tasks:
                if task.get("id") == task_id:
                    return _public_task(task)
        return None

    def cancel(self, task_id):
        with self._lock:
            for task in self._tasks:
                if task.get("id") != task_id:
                    continue
                if task.get("status") != "running":
                    return _public_task(task)
                task["cancel_requested"] = True
                task["message"] = "正在停止：已开始的检测项会跑完，未开始的不再执行"
                self._persist()
                return _public_task(task)
        return None

    def start_assessment(self, sheet_keys=None, title=""):
        project, snapshots, errors = self._snapshot(sheet_keys)
        with self._lock:
            if any(task.get("status") == "running" for task in self._tasks):
                raise RuntimeError("已有并行任务在运行，请等待完成或先停止")
            task = {
                "id": "task-" + time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
                "kind": "assessment_parallel",
                "title": title or ("并行评定 %d 个检测项" % len(snapshots)),
                "project": project,
                "status": "running",
                "message": "正在并行执行",
                "created_at": _now(),
                "started_at": _now(),
                "finished_at": 0,
                "total": len(snapshots),
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
                "cancel_requested": False,
                "workers": min(MAX_WORKERS, max(1, len(snapshots))),
                "items": [],
            }
            for snapshot in snapshots:
                task["items"].append({
                    "key": snapshot["key"],
                    "base": snapshot["base"],
                    "component": snapshot.get("component") or "",
                    "status": "queued",
                    "message": "",
                    "started_at": 0,
                    "finished_at": 0,
                    "duration_ms": 0,
                    "result": {},
                })
            for key, message in errors:
                task["items"].append({
                    "key": key, "base": "", "component": "", "status": "failed",
                    "message": message, "started_at": 0, "finished_at": _now(),
                    "duration_ms": 0, "result": {},
                })
            task["total"] = len(task["items"])
            task["failed"] = len(errors)
            self._tasks.insert(0, task)
            self._tasks = self._tasks[:MAX_TASKS]
            self._persist()
        if snapshots:
            threading.Thread(
                target=self._coordinate, args=(task["id"], project, snapshots),
                name="task-coordinator", daemon=True,
            ).start()
        else:
            with self._lock:
                self._finish_locked(task, "failed", "没有可执行的检测项")
        return self.get(task["id"])

    def _snapshot(self, sheet_keys):
        state = get_state()
        controller = get_controller()
        project = getattr(state, "project_name", "") or "未命名工程"
        with state._lock:
            keys = [str(key) for key in (sheet_keys or []) if str(key).strip()]
            if not keys:
                keys = [key for key in state.checked_items if key in state.sheet_data]
            snapshots = []
            errors = []
            for key in keys:
                try:
                    base, comp = controller.parse_sheet_key(key)
                    base = controller.resolve_item_name(base) or base
                    spec = get_spec(base)
                    if spec is None:
                        raise RuntimeError("未找到评定规则")
                    rows = [list(row) for row in (state.sheet_data.get(key) or [])]
                    snapshots.append({
                        "key": key,
                        "base": base,
                        "component": comp,
                        "spec": spec,
                        "columns": copy.deepcopy(controller.get_columns(key)),
                        "rows": rows,
                        "options": dict(state.assessment_options.get(key) or {}),
                        "input": copy.deepcopy(state.assessment_inputs.get(key)),
                    })
                except Exception as exc:  # noqa: BLE001 - 单项失败不影响其它项
                    errors.append((key, str(exc)))
        return project, snapshots, errors

    def _coordinate(self, task_id, project, snapshots):
        task = self._find(task_id)
        if not task:
            return
        results = {}
        def run_one(snapshot):
            if task.get("cancel_requested"):
                return snapshot, None, "已取消"
            self._mark_running(task_id, snapshot["key"])
            return snapshot, assess(
                snapshot["key"], snapshot["base"], snapshot["component"],
                snapshot["columns"], snapshot["rows"],
                options=dict(snapshot.get("options") or {}),
                raw_input=snapshot.get("input"),
            ), ""

        workers = min(MAX_WORKERS, max(1, len(snapshots)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="assess") as pool:
            futures = {pool.submit(run_one, snapshot): snapshot for snapshot in snapshots}
            for future in as_completed(futures):
                snapshot = futures[future]
                try:
                    _snapshot, result, cancelled = future.result()
                except Exception as exc:  # noqa: BLE001
                    result, cancelled = None, ""
                    message = str(exc)
                else:
                    message = cancelled
                self._complete_item(task_id, snapshot["key"], result, message)
                if result is not None:
                    results[snapshot["key"]] = (snapshot, result)
        self._write_back(project, results)
        with self._lock:
            task = self._find(task_id)
            if not task:
                return
            if task.get("cancel_requested"):
                status = "cancelled"
                message = "任务已停止（已开始的项保留结果）"
            elif task.get("failed"):
                status = "partial" if task.get("completed") else "failed"
                message = "完成 %d/%d 项，失败 %d 项" % (
                    task.get("completed") or 0, task.get("total") or 0, task.get("failed") or 0)
            else:
                status = "done"
                message = "全部 %d 项完成" % (task.get("total") or 0)
            self._finish_locked(task, status, message)

    def _find(self, task_id):
        for task in self._tasks:
            if task.get("id") == task_id:
                return task
        return None

    def _item(self, task_id, key):
        with self._lock:
            task = self._find(task_id)
            if not task:
                return None
            for item in task.get("items") or []:
                if item.get("key") == key:
                    return item
        return None

    def _mark_running(self, task_id, key):
        with self._lock:
            task = self._find(task_id)
            if not task:
                return
            for item in task.get("items") or []:
                if item.get("key") == key:
                    item["status"] = "running"
                    item["started_at"] = _now()
                    self._persist()
                    return

    def _complete_item(self, task_id, key, result, message=""):
        with self._lock:
            task = self._find(task_id)
            if not task:
                return
            for item in task.get("items") or []:
                if item.get("key") != key:
                    continue
                item["finished_at"] = _now()
                start = float(item.get("started_at") or item["finished_at"])
                item["duration_ms"] = int(max(0, item["finished_at"] - start) * 1000)
                if result is None:
                    if message == "已取消":
                        item["status"] = "cancelled"
                        item["message"] = "未开始，已取消"
                        task["cancelled"] = int(task.get("cancelled") or 0) + 1
                    else:
                        item["status"] = "failed"
                        item["message"] = message or "执行失败"
                        task["failed"] = int(task.get("failed") or 0) + 1
                elif result.get("ok"):
                    item["status"] = "done"
                    item["result"] = result
                    item["message"] = str(result.get("conclusion") or "")
                    task["completed"] = int(task.get("completed") or 0) + 1
                else:
                    item["status"] = "failed"
                    item["result"] = result
                    item["message"] = "；".join(result.get("errors") or []) or "评定未通过"
                    task["failed"] = int(task.get("failed") or 0) + 1
                self._persist()
                break

    def _write_back(self, project, results):
        if not results:
            return
        state = get_state()
        if getattr(state, "project_name", "") != project:
            return
        with state._lock:
            for key, (snapshot, result) in results.items():
                state.assessment_results[key] = result
                state.assessment_options[key] = dict(snapshot.get("options") or {})
                if snapshot.get("input") is not None:
                    state.assessment_inputs[key] = snapshot["input"]
        try:
            state.autosave()
        except Exception:  # noqa: BLE001
            pass

    def _finish_locked(self, task, status, message):
        task["status"] = status
        task["message"] = message
        task["finished_at"] = _now()
        self._persist()


_runner = None
_runner_lock = threading.Lock()


def get_task_runner():
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = TaskRunner()
    return _runner
