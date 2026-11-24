# -*- coding: utf-8 -*-
"""人员库：本地 SQLite 存储，用于报告人员信息复用。"""
import os
import sqlite3
import threading
import uuid
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DB_DIR = os.path.join(_ROOT, "data", "personnel")
_DB_PATH = os.environ.get("STRUCTURAL_PERSONNEL_DB") or os.path.join(_DB_DIR, "personnel.db")
_LOCK = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS personnel (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    cert_no TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    organization TEXT DEFAULT '',
    note TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_personnel_name ON personnel(name);
CREATE INDEX IF NOT EXISTS idx_personnel_role ON personnel(role);
"""


def _connect():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row(row):
    return {
        "id": row["id"],
        "name": row["name"] or "",
        "role": row["role"] or "",
        "cert_no": row["cert_no"] or "",
        "phone": row["phone"] or "",
        "organization": row["organization"] or "",
        "note": row["note"] or "",
        "active": bool(row["active"]),
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def normalize(data):
    data = data if isinstance(data, dict) else {}
    return {
        "name": str(data.get("name") or "").strip(),
        "role": str(data.get("role") or "").strip(),
        "cert_no": str(data.get("cert_no") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "organization": str(data.get("organization") or "").strip(),
        "note": str(data.get("note") or "").strip(),
        "active": 1 if data.get("active", True) else 0,
    }


def list_personnel(query="", role="", active_only=False, limit=200, offset=0):
    sql = "SELECT * FROM personnel WHERE 1=1"
    params = []
    query = str(query or "").strip()
    if query:
        like = "%" + query + "%"
        sql += " AND (name LIKE ? OR cert_no LIKE ? OR phone LIKE ? OR organization LIKE ? OR note LIKE ?)"
        params.extend([like] * 5)
    role = str(role or "").strip()
    if role:
        sql += " AND role = ?"
        params.append(role)
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY active DESC, role ASC, name ASC"
    limit = max(1, min(int(limit or 200), 1000))
    offset = max(0, int(offset or 0))
    with _LOCK, _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM (" + sql + ")", params).fetchone()[0]
        rows = conn.execute(sql + " LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
    return {"items": [_row(r) for r in rows], "total": int(total)}


def count_personnel(active_only=False):
    with _LOCK, _connect() as conn:
        if active_only:
            return int(conn.execute("SELECT COUNT(*) FROM personnel WHERE active=1").fetchone()[0])
        return int(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0])


def role_counts():
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT role, COUNT(*) AS n FROM personnel WHERE active=1 AND role <> '' GROUP BY role"
        ).fetchall()
    return {r["role"]: int(r["n"]) for r in rows}


def get_personnel(person_id):
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM personnel WHERE id=?", (person_id,)).fetchone()
    return _row(row) if row else None


def create_personnel(data):
    item = normalize(data)
    if not item["name"]:
        raise ValueError("姓名不能为空")
    person_id = uuid.uuid4().hex
    now = _now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """INSERT INTO personnel
               (id, name, role, cert_no, phone, organization, note, active, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (person_id, item["name"], item["role"], item["cert_no"], item["phone"],
             item["organization"], item["note"], item["active"], now, now))
    return get_personnel(person_id)


def update_personnel(person_id, data):
    item = normalize(data)
    if not item["name"]:
        raise ValueError("姓名不能为空")
    if not get_personnel(person_id):
        return None
    with _LOCK, _connect() as conn:
        conn.execute(
            """UPDATE personnel SET name=?, role=?, cert_no=?, phone=?,
               organization=?, note=?, active=?, updated_at=? WHERE id=?""",
            (item["name"], item["role"], item["cert_no"], item["phone"],
             item["organization"], item["note"], item["active"], _now(), person_id))
    return get_personnel(person_id)


def delete_personnel(person_id):
    with _LOCK, _connect() as conn:
        cur = conn.execute("DELETE FROM personnel WHERE id=?", (person_id,))
    return cur.rowcount > 0


def _find_existing(name, cert_no="", phone=""):
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT * FROM personnel WHERE name=?", (name,)).fetchall()
    for row in rows:
        if cert_no and (row["cert_no"] or "").strip() == cert_no:
            return row["id"]
        if phone and (row["phone"] or "").strip() == phone:
            return row["id"]
    return None


def import_personnel(items):
    """批量导入人员；同名且证书/电话相同则更新，否则新增。"""
    created = 0
    updated = 0
    skipped = 0
    for item in items or []:
        item = normalize(item)
        if not item["name"]:
            skipped += 1
            continue
        existing = _find_existing(item["name"], item["cert_no"], item["phone"])
        if existing:
            update_personnel(existing, item)
            updated += 1
        else:
            create_personnel(item)
            created += 1
    return {"created": created, "updated": updated, "skipped": skipped,
            "total": created + updated}


def status():
    return {
        "total": count_personnel(),
        "active": count_personnel(active_only=True),
        "roles": role_counts(),
        "db_path": _DB_PATH,
    }
