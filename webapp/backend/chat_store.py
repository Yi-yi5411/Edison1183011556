# -*- coding: utf-8 -*-
"""对话持久化与项目长期记忆（本机文件存储）。

- 会话记录：data/chat_transcripts/<sessionId>.json
  保存用户/助手消息、工具轨迹、执行计划与摘要；页面刷新或换浏览器后可恢复。
- 项目记忆：data/chat_memory/<project-hash>.json
  保存最近任务的摘要与交付物路径；新会话首轮注入，保证“继续上文”不丢上下文。

不依赖数据库，单用户本机使用；所有写入均为原子替换。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TRANSCRIPT_DIR = os.path.join(_ROOT, "data", "chat_transcripts")
_MEMORY_DIR = os.path.join(_ROOT, "data", "chat_memory")
_LOCK = threading.RLock()

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_REPORT_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/)?[^\s\"'<>]*report_generator[\\/]exports[\\/][^\s\"'<>]+?\.docx",
    re.IGNORECASE,
)
_PREVIEW_RE = re.compile(r"/api/report/(?:preview|download)\?filepath=[^\s\"'<>)]+")


def _now() -> float:
    return time.time()


def _atomic_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + "." + uuid.uuid4().hex + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path: str, fallback: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data
    except (OSError, ValueError):
        return fallback


def _safe_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not _SESSION_RE.match(value):
        return ""
    return value


# ── 会话记录 ────────────────────────────────────────────────────

def transcript_path(session_id: str) -> str:
    sid = _safe_id(session_id)
    return os.path.join(_TRANSCRIPT_DIR, sid + ".json") if sid else ""


def empty_transcript(session_id: str, project: str = "") -> Dict[str, Any]:
    return {
        "version": 1,
        "sessionId": session_id,
        "project": project,
        "title": "",
        "messages": [],
        "tools": [],
        "plan": [],
        "summary": "",
        "promptCount": 0,
        "updatedAt": 0,
    }


def load_transcript(session_id: str) -> Dict[str, Any]:
    sid = _safe_id(session_id)
    if not sid:
        return empty_transcript("")
    with _LOCK:
        data = _read_json(transcript_path(sid), None)
    if not isinstance(data, dict):
        return empty_transcript(sid)
    base = empty_transcript(sid)
    base.update(data)
    if not isinstance(base.get("messages"), list):
        base["messages"] = []
    if not isinstance(base.get("tools"), list):
        base["tools"] = []
    if not isinstance(base.get("plan"), list):
        base["plan"] = []
    return base


def save_transcript(session_id: str, data: Dict[str, Any]) -> None:
    sid = _safe_id(session_id)
    if not sid:
        return
    with _LOCK:
        payload = dict(data or {})
        payload["sessionId"] = sid
        payload["updatedAt"] = _now()
        _atomic_json(transcript_path(sid), payload)


def transcript_exists(session_id: str) -> bool:
    path = transcript_path(session_id)
    return bool(path and os.path.isfile(path))


def append_message(session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    sid = _safe_id(session_id)
    if not sid:
        return message
    with _LOCK:
        data = load_transcript(sid)
        data.setdefault("messages", []).append(dict(message))
        if message.get("role") == "user":
            data["promptCount"] = int(data.get("promptCount") or 0) + 1
        save_transcript(sid, data)
    return dict(message)


def update_message(session_id: str, message_id: str, **fields: Any) -> None:
    sid = _safe_id(session_id)
    if not sid:
        return
    with _LOCK:
        data = load_transcript(sid)
        for item in data.get("messages") or []:
            if item.get("id") == message_id:
                item.update(fields)
                break
        else:
            return
        save_transcript(sid, data)


def set_plan(session_id: str, plan: List[Dict[str, Any]]) -> None:
    sid = _safe_id(session_id)
    if not sid:
        return
    with _LOCK:
        data = load_transcript(sid)
        data["plan"] = list(plan or [])
        save_transcript(sid, data)


def set_tools(session_id: str, tools: List[Dict[str, Any]]) -> None:
    sid = _safe_id(session_id)
    if not sid:
        return
    with _LOCK:
        data = load_transcript(sid)
        data["tools"] = list(tools or [])
        save_transcript(sid, data)


def update_tool(session_id: str, tool: Dict[str, Any]) -> None:
    sid = _safe_id(session_id)
    if not sid:
        return
    with _LOCK:
        data = load_transcript(sid)
        items = data.setdefault("tools", [])
        target = None
        for item in items:
            if item.get("id") == tool.get("id"):
                target = item
                break
        if target is None:
            items.append(dict(tool))
        else:
            target.update(tool)
        save_transcript(sid, data)


# ── 项目长期记忆 ────────────────────────────────────────────────

def _project_key(project: str) -> str:
    value = str(project or "未命名工程").strip() or "未命名工程"
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def memory_path(project: str) -> str:
    return os.path.join(_MEMORY_DIR, _project_key(project) + ".json")


def empty_memory(project: str) -> Dict[str, Any]:
    return {
        "version": 1,
        "project": str(project or "未命名工程"),
        "facts": [],
        "summaries": [],
        "updatedAt": 0,
    }


def load_memory(project: str) -> Dict[str, Any]:
    with _LOCK:
        data = _read_json(memory_path(project), None)
    if not isinstance(data, dict):
        return empty_memory(project)
    base = empty_memory(project)
    base.update(data)
    if not isinstance(base.get("facts"), list):
        base["facts"] = []
    if not isinstance(base.get("summaries"), list):
        base["summaries"] = []
    return base


def save_memory(project: str, data: Dict[str, Any]) -> None:
    with _LOCK:
        payload = dict(data or {})
        payload["project"] = str(project or "未命名工程")
        payload["updatedAt"] = _now()
        _atomic_json(memory_path(project), payload)


def extract_report_paths(text: str) -> List[str]:
    source = str(text or "")
    found: List[str] = []
    for match in _REPORT_RE.finditer(source):
        value = match.group(0).strip()
        if value and value not in found:
            found.append(value)
    for match in _PREVIEW_RE.finditer(source):
        value = match.group(0).strip()
        if value and value not in found:
            found.append(value)
    return found[:6]


def _short(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:limit]


def record_turn_memory(
    project: str,
    session_id: str,
    title: str,
    user_text: str,
    assistant_text: str,
) -> Dict[str, Any]:
    """把一次完成的回合写入长期记忆；同一会话只保留最新摘要。"""
    project = str(project or "未命名工程").strip() or "未命名工程"
    assistant_text = str(assistant_text or "")
    user_text = str(user_text or "")
    memory = load_memory(project)
    now = _now()
    summary_text = _short(assistant_text, 420)
    if user_text or summary_text:
        item = {
            "sessionId": session_id,
            "title": _short(title, 60) or _short(user_text, 60),
            "user": _short(user_text, 160),
            "summary": summary_text,
            "createdAt": now,
        }
        summaries = [x for x in memory.get("summaries") or []
                     if x.get("sessionId") != session_id]
        summaries.insert(0, item)
        memory["summaries"] = summaries[:12]

    facts = list(memory.get("facts") or [])
    for path in extract_report_paths(assistant_text):
        text = "报告：" + path
        if not any(f.get("text") == text for f in facts):
            facts.insert(0, {
                "id": uuid.uuid4().hex[:12],
                "kind": "report",
                "text": text,
                "sessionId": session_id,
                "createdAt": now,
            })
    turn_text = "任务：%s → %s" % (_short(user_text, 80), _short(summary_text, 180))
    if user_text and not any(f.get("text") == turn_text for f in facts):
        facts.insert(0, {
            "id": uuid.uuid4().hex[:12],
            "kind": "turn",
            "text": turn_text,
            "sessionId": session_id,
            "createdAt": now,
        })
    memory["facts"] = facts[:30]
    save_memory(project, memory)

    # 同步到会话记录，页面会话列表可直接展示
    with _LOCK:
        transcript = load_transcript(session_id)
        transcript["project"] = project
        transcript["title"] = transcript.get("title") or _short(title, 40)
        transcript["summary"] = summary_text
        save_transcript(session_id, transcript)
    return memory


def _snapshot() -> Dict[str, Any]:
    try:
        from deps import get_state
        state = get_state()
    except Exception:  # noqa: BLE001
        return {}
    checked = [str(k) for k in (getattr(state, "checked_items", []) or [])]
    filled = 0
    total_rows = 0
    for key in checked:
        rows = [r for r in (state.sheet_data.get(key) or [])
                if any(str(v or "").strip() for v in (r if isinstance(r, (list, tuple)) else [r]))]
        total_rows += len(rows)
        if rows:
            filled += 1
    assessed = sum(1 for key in checked
                   if (state.assessment_results.get(key) or {}).get("ok"))
    return {
        "project": str(getattr(state, "project_name", "") or ""),
        "checked": len(checked),
        "filled": filled,
        "assessed": assessed,
        "rows": total_rows,
    }


def latest_reports(limit: int = 3) -> List[str]:
    folder = os.path.join(_ROOT, "report_generator", "exports")
    found: List[tuple[float, str]] = []
    try:
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if os.path.isdir(path):
                for inner in os.listdir(path):
                    if inner.lower().endswith(".docx"):
                        full = os.path.join(path, inner)
                        found.append((os.path.getmtime(full), full))
            elif name.lower().endswith(".docx"):
                found.append((os.path.getmtime(path), path))
    except OSError:
        return []
    found.sort(reverse=True)
    return [path for _mtime, path in found[:limit]]


def memory_payload(project: str) -> Dict[str, Any]:
    memory = load_memory(project)
    snapshot = _snapshot()
    facts = sorted(memory.get("facts") or [], key=lambda x: x.get("createdAt") or 0, reverse=True)
    summaries = sorted(memory.get("summaries") or [], key=lambda x: x.get("createdAt") or 0, reverse=True)
    reports = [f.get("text", "")[3:] for f in facts if f.get("kind") == "report"]
    if not reports:
        reports = latest_reports(3)
    return {
        "project": project,
        "snapshot": snapshot,
        "facts": facts[:20],
        "summaries": summaries[:8],
        "reports": reports[:3],
        "updatedAt": memory.get("updatedAt") or 0,
        "count": len(facts),
    }


def context_block(project: str, max_chars: int = 2800) -> str:
    """新会话首轮注入的长期记忆块；已恢复会话不重复注入。"""
    payload = memory_payload(project)
    snapshot = payload.get("snapshot") or {}
    lines = ["【工程长期记忆 · 系统自动注入，不是用户发言】"]
    if snapshot:
        lines.append(
            "工程：%s；已勾选 %s 项，已录入 %s 项，已评定 %s 项，共 %s 行数据。"
            % (project, snapshot.get("checked", 0), snapshot.get("filled", 0),
               snapshot.get("assessed", 0), snapshot.get("rows", 0)))
    else:
        lines.append("工程：%s" % project)
    reports = payload.get("reports") or []
    if reports:
        lines.append("最近报告：" + reports[0])
    summaries = payload.get("summaries") or []
    if summaries:
        lines.append("最近工作：")
        for item in summaries[:5]:
            text = "；".join(x for x in (item.get("user"), item.get("summary")) if x)
            lines.append("- " + _short(text, 260))
    facts = [f.get("text") for f in (payload.get("facts") or [])[:8] if f.get("text")]
    if facts:
        lines.append("关键记忆：")
        for text in facts:
            lines.append("- " + _short(text, 240))
    lines.append(
        "请把这些内容当作已确认的背景；用户说“继续上文/刚才的报告”时直接接续，"
        "不要重复询问工程、已录入数据或上次报告路径。需要最新数据时仍以工具查询结果为准。")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars - 30] + "\n……（长期记忆已截断）"
    return text


# ── 对话任务（异步执行记录） ───────────────────────────────────────

_CHAT_JOBS_PATH = os.path.join(_ROOT, "data", "chat_jobs.json")
_MAX_JOBS = 80
_ACTIVE_JOB_STATUS = ("queued", "running")


def _job_items() -> List[Dict[str, Any]]:
    data = _read_json(_CHAT_JOBS_PATH, [])
    return [dict(x) for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _save_jobs(items: List[Dict[str, Any]]) -> None:
    _atomic_json(_CHAT_JOBS_PATH, list(items)[:_MAX_JOBS])


def _recover_jobs(items: List[Dict[str, Any]]) -> bool:
    """后端重启后，把上一个进程遗留的 queued/running 标记为中断。"""
    changed = False
    now = _now()
    current = os.getpid()
    for item in items:
        if str(item.get("status") or "") not in _ACTIVE_JOB_STATUS:
            continue
        try:
            pid = int(item.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid == current:
            continue
        item["status"] = "interrupted"
        item["message"] = "后端重启，对话任务已中断"
        item["finished_at"] = now
        item["updated_at"] = now
        changed = True
    return changed


def create_job(session_id: str, project: str, text: str, title: str = "") -> Dict[str, Any]:
    now = _now()
    job = {
        "id": "chat-" + time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "kind": "chat",
        "session_id": str(session_id or ""),
        "project": str(project or "未命名工程"),
        "title": _short(title or text, 60),
        "prompt": _short(text, 2000),
        "status": "queued",
        "message": "排队中",
        "assistant": "",
        "queue": 0,
        "pid": os.getpid(),
        "created_at": now,
        "started_at": 0,
        "finished_at": 0,
        "updated_at": now,
    }
    with _LOCK:
        items = _job_items()
        _recover_jobs(items)
        items.insert(0, job)
        _save_jobs(items)
    return dict(job)


def update_job(job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    target = str(job_id or "")
    if not target:
        return None
    with _LOCK:
        items = _job_items()
        _recover_jobs(items)
        found = None
        for item in items:
            if item.get("id") == target:
                item.update(fields)
                item["updated_at"] = _now()
                found = dict(item)
                break
        if found is not None:
            _save_jobs(items)
        return found


def get_job(job_id: str) -> Dict[str, Any]:
    target = str(job_id or "")
    if not target:
        return {}
    with _LOCK:
        items = _job_items()
        _recover_jobs(items)
        for item in items:
            if item.get("id") == target:
                return dict(item)
    return {}


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        size = max(1, min(100, int(limit)))
    except (TypeError, ValueError):
        size = 20
    with _LOCK:
        items = _job_items()
        if _recover_jobs(items):
            _save_jobs(items)
    items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
    return items[:size]
