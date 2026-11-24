# -*- coding: utf-8 -*-
"""报告记录库 / 原始记录库（SQLite，无 Qt / FastAPI 依赖）。

设计目标：
  - 把原先 JSON 文件保存的报告生成历史、原始记录生成历史迁入数据库；
  - 支持按项目 / 报告编号 / 文件名检索、分页、统计；
  - 原始记录可保存生成时的数据快照，便于追溯；
  - 旧 JSON 文件保留作兼容兜底，首次初始化时幂等导入并备份。

数据库：data/records/records.db（可用 STRUCTURAL_RECORDS_DB 覆盖）
表：report_records / original_records / meta
"""

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DB_DIR = _ROOT / "data" / "records"
_DEFAULT_DB = _DB_DIR / "records.db"
_DB_PATH = Path(os.environ.get("STRUCTURAL_RECORDS_DB") or _DEFAULT_DB)
_LEGACY_REPORT = _ROOT / "report_generator" / "report_history.json"
_LEGACY_ORIGINAL = _ROOT / "data" / "original_record_history.json"
_BACKUP_ROOT = _ROOT / "data" / "backup"

MAX_SNAPSHOT_BYTES = 1024 * 1024  # 单条原始记录快照上限 1MB

_LOCK = threading.RLock()
_READY = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_records (
    id TEXT PRIMARY KEY,
    report_no TEXT DEFAULT '',
    project_name TEXT DEFAULT '',
    filepath TEXT NOT NULL,
    filename TEXT DEFAULT '',
    engine TEXT DEFAULT '',
    template_id TEXT DEFAULT '',
    template_name TEXT DEFAULT '',
    tables_json TEXT DEFAULT '[]',
    skipped_json TEXT DEFAULT '[]',
    warnings_json TEXT DEFAULT '[]',
    model TEXT DEFAULT '',
    fallback_reason TEXT DEFAULT '',
    report_info_json TEXT DEFAULT '{}',
    assessment_results_json TEXT DEFAULT '{}',
    assessed_count INTEGER DEFAULT 0,
    file_size INTEGER DEFAULT 0,
    generated_at TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_report_record_file
    ON report_records(filepath, generated_at);
CREATE INDEX IF NOT EXISTS idx_report_record_time
    ON report_records(generated_at DESC);

CREATE TABLE IF NOT EXISTS original_records (
    id TEXT PRIMARY KEY,
    sheet_key TEXT DEFAULT '',
    base_item TEXT DEFAULT '',
    template_id TEXT DEFAULT '',
    template_name TEXT DEFAULT '',
    project_name TEXT DEFAULT '',
    filepath TEXT NOT NULL,
    filename TEXT DEFAULT '',
    rows_count INTEGER DEFAULT 0,
    warnings_json TEXT DEFAULT '[]',
    snapshot_json TEXT DEFAULT '',
    snapshot_size INTEGER DEFAULT 0,
    generated_at TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_original_record_file
    ON original_records(filepath, generated_at, sheet_key);
CREATE INDEX IF NOT EXISTS idx_original_record_time
    ON original_records(generated_at DESC);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value, default="[]"):
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return default


def _json_loads(text, default):
    try:
        data = json.loads(text or "")
        return data if data is not None else default
    except Exception:  # noqa: BLE001
        return default


def _connect():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _meta_get(conn, key, default=""):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                 (key, str(value)))


def ensure_schema():
    """建表 + 旧 JSON 备份/导入（幂等）。"""
    global _READY
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        with _connect() as conn:
            conn.executescript(_SCHEMA)
        _backup_legacy()
        import_legacy()
        _READY = True


def _backup_legacy():
    """首次迁移前把两个历史 JSON 备份到 data/backup/<时间戳>/。"""
    files = [p for p in (_LEGACY_REPORT, _LEGACY_ORIGINAL) if p.is_file()]
    if not files:
        return
    try:
        with _connect() as conn:
            if _meta_get(conn, "legacy_backup_done"):
                return
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = _BACKUP_ROOT / ("records_%s" % stamp)
            target.mkdir(parents=True, exist_ok=True)
            for path in files:
                shutil.copy2(str(path), str(target / path.name))
            _meta_set(conn, "legacy_backup_done", target.as_posix())
    except Exception:  # noqa: BLE001 - 备份失败不阻断主流程
        pass


def _legacy_id(prefix, filepath, generated_at, extra=""):
    raw = ("%s|%s|%s" % (filepath or "", generated_at or "",
                         extra or "")).encode("utf-8")
    return "%s_%s" % (prefix, hashlib.sha1(raw).hexdigest()[:16])


def import_legacy():
    """把旧 JSON 历史导入数据库；可重复执行，依靠唯一索引去重。"""
    with _LOCK:
        with _connect() as conn:
            for path, kind in ((_LEGACY_REPORT, "report"),
                               (_LEGACY_ORIGINAL, "original")):
                if not path.is_file():
                    continue
                data = _json_loads(path.read_text(encoding="utf-8"), [])
                if not isinstance(data, list):
                    continue
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    if kind == "report":
                        _insert_report(conn, entry, legacy=True)
                    else:
                        _insert_original(conn, entry, legacy=True)


def _insert_report(conn, entry, legacy=False):
    filepath = str(entry.get("filepath") or "").strip()
    if not filepath:
        return ""
    generated_at = str(entry.get("generated_at") or _now())
    if legacy:
        record_id = _legacy_id("legacy_report", filepath, generated_at)
    else:
        record_id = str(entry.get("id") or uuid.uuid4().hex)
    filename = os.path.basename(filepath)
    file_size = 0
    try:
        if os.path.isfile(filepath):
            file_size = os.path.getsize(filepath)
    except Exception:  # noqa: BLE001
        pass
    sql = """INSERT OR IGNORE INTO report_records
        (id, report_no, project_name, filepath, filename, engine,
         template_id, template_name, tables_json, skipped_json,
         warnings_json, model, fallback_reason, report_info_json,
         assessment_results_json, assessed_count, file_size,
         generated_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    cur = conn.execute(sql, (
        record_id,
        str(entry.get("report_no") or ""),
        str(entry.get("project_name") or ""),
        filepath,
        filename,
        str(entry.get("engine") or ""),
        str(entry.get("template_id") or ""),
        str(entry.get("template_name") or ""),
        _json_dumps(entry.get("tables") if entry.get("tables") is not None else 0),
        _json_dumps(entry.get("skipped") or []),
        _json_dumps(entry.get("warnings") or []),
        str(entry.get("model") or ""),
        str(entry.get("fallback_reason") or ""),
        _json_dumps(entry.get("report_info") or {}, "{}"),
        _json_dumps(entry.get("assessment_results") or {}, "{}"),
        int(entry.get("assessed_count") or 0),
        file_size,
        generated_at,
        str(entry.get("created_at") or _now()),
    ))
    if cur.rowcount:
        return record_id
    row = conn.execute(
        "SELECT id FROM report_records WHERE filepath=? AND generated_at=?",
        (filepath, generated_at)).fetchone()
    return row["id"] if row else record_id


def add_report_record(entry):
    """写入一条报告记录，返回记录 ID。"""
    ensure_schema()
    entry = dict(entry or {})
    entry.setdefault("generated_at", _now())
    with _LOCK, _connect() as conn:
        return _insert_report(conn, entry, legacy=False)


def _report_view(row):
    data = dict(row)
    data["tables"] = _json_loads(data.pop("tables_json", ""), 0)
    data["skipped"] = _json_loads(data.pop("skipped_json", ""), [])
    data["warnings"] = _json_loads(data.pop("warnings_json", ""), [])
    data["report_info"] = _json_loads(data.pop("report_info_json", ""), {})
    data["assessment_results"] = _json_loads(
        data.pop("assessment_results_json", ""), {})
    data["exists"] = bool(data.get("filepath")
                          and os.path.isfile(str(data["filepath"])))
    return data


def _original_view(row, with_snapshot=False):
    data = dict(row)
    data["warnings"] = _json_loads(data.pop("warnings_json", ""), [])
    snapshot_raw = data.pop("snapshot_json", "") or ""
    data["has_snapshot"] = bool(snapshot_raw)
    if with_snapshot and snapshot_raw:
        data["snapshot"] = _json_loads(snapshot_raw, {})
    data["exists"] = bool(data.get("filepath")
                          and os.path.isfile(str(data["filepath"])))
    return data


def list_report_records(q="", project="", limit=100, offset=0):
    ensure_schema()
    where, params = [], []
    q = str(q or "").strip()
    if q:
        like = "%" + q + "%"
        where.append("(report_no LIKE ? OR project_name LIKE ? "
                     "OR filepath LIKE ? OR template_name LIKE ?)")
        params.extend([like, like, like, like])
    project = str(project or "").strip()
    if project:
        where.append("project_name LIKE ?")
        params.append("%" + project + "%")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with _LOCK, _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM report_records" + clause, params).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM report_records" + clause
            + " ORDER BY generated_at DESC, created_at DESC LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)]).fetchall()
    return [_report_view(r) for r in rows], int(total)


def get_report_record(record_id):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM report_records WHERE id=?",
                           (str(record_id),)).fetchone()
    return _report_view(row) if row else None


def delete_report_record(record_id):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM report_records WHERE id=?",
                           (str(record_id),)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM report_records WHERE id=?", (str(record_id),))
    return _report_view(row)


def clear_report_records():
    ensure_schema()
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM report_records")
    _empty_legacy(_LEGACY_REPORT)


def _insert_original(conn, entry, legacy=False):
    filepath = str(entry.get("filepath") or "").strip()
    if not filepath:
        return ""
    generated_at = str(entry.get("generated_at") or _now())
    sheet_key = str(entry.get("sheet_key") or "")
    if legacy:
        record_id = _legacy_id("legacy_original", filepath, generated_at,
                               sheet_key)
    else:
        record_id = str(entry.get("id") or uuid.uuid4().hex)
    snapshot = entry.get("snapshot")
    snapshot_json = ""
    snapshot_size = 0
    if snapshot is not None:
        snapshot_json = _json_dumps(snapshot, "{}")
        snapshot_size = len(snapshot_json.encode("utf-8"))
        if snapshot_size > MAX_SNAPSHOT_BYTES:
            snapshot_json = _json_dumps({
                "truncated": True,
                "reason": "快照超过 %d 字节，未保存完整数据" % MAX_SNAPSHOT_BYTES,
            }, "{}")
            snapshot_size = len(snapshot_json.encode("utf-8"))
    sql = """INSERT OR IGNORE INTO original_records
        (id, sheet_key, base_item, template_id, template_name, project_name,
         filepath, filename, rows_count, warnings_json, snapshot_json,
         snapshot_size, generated_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    cur = conn.execute(sql, (
        record_id,
        sheet_key,
        str(entry.get("base_item") or ""),
        str(entry.get("template_id") or ""),
        str(entry.get("template_name") or ""),
        str(entry.get("project_name") or ""),
        filepath,
        os.path.basename(filepath),
        int(entry.get("rows") or entry.get("rows_count") or 0),
        _json_dumps(entry.get("warnings") or []),
        snapshot_json,
        snapshot_size,
        generated_at,
        str(entry.get("created_at") or _now()),
    ))
    if cur.rowcount:
        return record_id
    row = conn.execute(
        "SELECT id FROM original_records WHERE filepath=? AND generated_at=?"
        " AND sheet_key=?",
        (filepath, generated_at, sheet_key)).fetchone()
    return row["id"] if row else record_id


def add_original_record(entry):
    """写入一条原始记录，返回记录 ID。"""
    ensure_schema()
    entry = dict(entry or {})
    entry.setdefault("generated_at", _now())
    with _LOCK, _connect() as conn:
        return _insert_original(conn, entry, legacy=False)


def list_original_records(q="", project="", limit=100, offset=0):
    ensure_schema()
    where, params = [], []
    q = str(q or "").strip()
    if q:
        like = "%" + q + "%"
        where.append("(sheet_key LIKE ? OR project_name LIKE ? "
                     "OR filepath LIKE ? OR template_name LIKE ?)")
        params.extend([like, like, like, like])
    project = str(project or "").strip()
    if project:
        where.append("project_name LIKE ?")
        params.append("%" + project + "%")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with _LOCK, _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM original_records" + clause,
            params).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM original_records" + clause
            + " ORDER BY generated_at DESC, created_at DESC LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)]).fetchall()
    return [_original_view(r) for r in rows], int(total)


def get_original_record(record_id, with_snapshot=False):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM original_records WHERE id=?",
                           (str(record_id),)).fetchone()
    return _original_view(row, with_snapshot=with_snapshot) if row else None


def delete_original_record(record_id):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM original_records WHERE id=?",
                           (str(record_id),)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM original_records WHERE id=?",
                     (str(record_id),))
    return _original_view(row)


def clear_original_records():
    ensure_schema()
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM original_records")
    _empty_legacy(_LEGACY_ORIGINAL)


def _empty_legacy(path):
    """清空旧 JSON 历史，避免重启后被重新导入。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def stats():
    ensure_schema()
    month = datetime.now().strftime("%Y-%m")
    with _LOCK, _connect() as conn:
        report_total = conn.execute(
            "SELECT COUNT(*) FROM report_records").fetchone()[0]
        report_month = conn.execute(
            "SELECT COUNT(*) FROM report_records WHERE generated_at LIKE ?",
            (month + "%",)).fetchone()[0]
        original_total = conn.execute(
            "SELECT COUNT(*) FROM original_records").fetchone()[0]
        original_month = conn.execute(
            "SELECT COUNT(*) FROM original_records WHERE generated_at LIKE ?",
            (month + "%",)).fetchone()[0]
        snapshot_count = conn.execute(
            "SELECT COUNT(*) FROM original_records WHERE snapshot_json <> ''"
        ).fetchone()[0]
        latest = conn.execute(
            "SELECT generated_at FROM ("
            " SELECT generated_at FROM report_records"
            " UNION ALL SELECT generated_at FROM original_records"
            ") ORDER BY generated_at DESC LIMIT 1").fetchone()
    return {
        "report": {"total": report_total, "this_month": report_month},
        "original": {"total": original_total, "this_month": original_month,
                     "with_snapshot": snapshot_count},
        "latest": latest["generated_at"] if latest else "",
        "db_path": str(_DB_PATH),
    }


def count_records(kind):
    ensure_schema()
    table = "report_records" if kind == "report" else "original_records"
    with _LOCK, _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
