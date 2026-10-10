# -*- coding: utf-8 -*-
"""第4步：电子版数据存储到数据库（SQLite）。

存储对象：
- 识别文档(scan_documents)：原文件路径、存储路径、OCR全文、大模型结构化JSON、检测项等。
- 电子记录(scan_records)：每条结构化记录（含规范化后的数据）。

使用 SQLite，与项目认证数据库(auth_db)风格一致，零外部依赖。
"""
import json
import sqlite3
import threading
from datetime import datetime

from report_generator.scan_recognition.config import Config


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ScanDatabase:
    """扫描识别的电子数据 SQLite 存储。线程安全（加锁）。"""

    def __init__(self, db_path=None, cfg: Config = None):
        cfg = cfg or Config.load()
        self.path = str(db_path or cfg.database_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock, self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT,
                    stored_path TEXT,
                    file_hash TEXT,
                    ocr_text TEXT,
                    structured_json TEXT,
                    detection_item TEXT,
                    sub_item TEXT,
                    status TEXT DEFAULT 'recognized',
                    created_at TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER,
                    row_index INTEGER,
                    detection_item TEXT,
                    sub_item TEXT,
                    structured_json TEXT,
                    normalized_json TEXT,
                    matched_columns TEXT,
                    uploaded INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """)
            # 长期记忆：人工校正差异 / 治理留痕学习出的校正经验，
            # 识别时按检测项目召回注入提示词（越用越准）
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT DEFAULT 'correction',
                    detection_item TEXT,
                    field TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    count INTEGER DEFAULT 1,
                    note TEXT,
                    last_seen TEXT
                )
            """)

    # ── 文档 ──
    def add_document(self, source_path, stored_path, file_hash, ocr_text,
                     structured, detection_item, sub_item, status="recognized"):
        with self._lock, self._conn:
            cur = self._conn.execute(
                """INSERT INTO scan_documents
                   (source_path, stored_path, file_hash, ocr_text, structured_json,
                    detection_item, sub_item, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (source_path, stored_path, file_hash, ocr_text,
                 json.dumps(structured, ensure_ascii=False) if structured else None,
                 detection_item, sub_item, status, _now()),
            )
            return cur.lastrowid

    def get_document(self, doc_id):
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM scan_documents WHERE id=?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def last_document_id(self):
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT MAX(id) AS m FROM scan_documents").fetchone()
        return row["m"] if row else None

    def list_documents(self, detection_item=None):
        """按检测项目列出识别历史文档（新→旧）。"""
        with self._lock, self._conn:
            sql = "SELECT * FROM scan_documents WHERE 1=1"
            args = []
            if detection_item:
                sql += " AND detection_item=?"
                args.append(detection_item)
            rows = self._conn.execute(sql + " ORDER BY id DESC", args).fetchall()
        return [dict(r) for r in rows]

    def delete_document(self, doc_id):
        """删除识别文档及其全部记录。"""
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM scan_records WHERE document_id=?", (doc_id,))
            self._conn.execute(
                "DELETE FROM scan_documents WHERE id=?", (doc_id,))

    # ── 记录 ──
    def add_records(self, doc_id, detection_item, sub_item, records, normalized,
                    matched_columns, row_base=0):
        with self._lock, self._conn:
            for i, rec in enumerate(records):
                self._conn.execute(
                    """INSERT INTO scan_records
                       (document_id, row_index, detection_item, sub_item,
                        structured_json, normalized_json, matched_columns, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (doc_id, row_base + i, detection_item, sub_item,
                     json.dumps(rec, ensure_ascii=False),
                     json.dumps(normalized[i], ensure_ascii=False) if normalized else None,
                     json.dumps(matched_columns, ensure_ascii=False),
                     _now()),
                )
        return len(records)

    def list_records(self, sub_item=None, document_id=None):
        with self._lock, self._conn:
            sql = "SELECT * FROM scan_records WHERE 1=1"
            args = []
            if sub_item:
                sql += " AND sub_item=?"
                args.append(sub_item)
            if document_id:
                sql += " AND document_id=?"
                args.append(document_id)
            rows = self._conn.execute(sql + " ORDER BY id", args).fetchall()
        return [dict(r) for r in rows]

    def replace_records(self, doc_id, detection_item, sub_item, records,
                        normalized, matched_rows):
        """人工校正后整体替换某文档的识别记录（先删后插）。

        以校正后的对齐行（matched_rows）为准逐行落库，保证库中记录与
        用户确认的数据完全一致；structured/normalized 按行号对应补充。
        """
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM scan_records WHERE document_id=?", (doc_id,))
            for i, _row in enumerate(matched_rows):
                self._conn.execute(
                    """INSERT INTO scan_records
                       (document_id, row_index, detection_item, sub_item,
                        structured_json, normalized_json, matched_columns, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (doc_id, i, detection_item, sub_item,
                     json.dumps(records[i], ensure_ascii=False)
                     if i < len(records) else None,
                     json.dumps(normalized[i], ensure_ascii=False)
                     if i < len(normalized) else None,
                     json.dumps(matched_rows, ensure_ascii=False),
                     _now()),
                )
        return len(matched_rows)

    # ── 长期记忆 ──
    def remember_correction(self, detection_item, field, old_value, new_value,
                            kind="correction", note=""):
        """记录一条校正经验；同一 (字段, 原值, 校正值) 已存在则次数 +1。"""
        with self._lock, self._conn:
            row = self._conn.execute(
                """SELECT id, count FROM scan_memory
                   WHERE kind=? AND IFNULL(detection_item,'')=?
                     AND IFNULL(field,'')=? AND IFNULL(old_value,'')=?
                     AND IFNULL(new_value,'')=?""",
                (kind, detection_item or "", field or "", old_value or "",
                 new_value or ""),
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE scan_memory SET count=count+1, last_seen=? "
                    "WHERE id=?", (_now(), row["id"]))
                return row["id"]
            cur = self._conn.execute(
                """INSERT INTO scan_memory
                   (kind, detection_item, field, old_value, new_value,
                    count, note, last_seen) VALUES (?,?,?,?,?,1,?,?)""",
                (kind, detection_item or "", field or "", old_value or "",
                 new_value or "", note or "", _now()))
            return cur.lastrowid

    def list_memory(self, detection_item=None, limit=200):
        """按出现次数降序列出记忆（可按检测项目过滤）。"""
        with self._lock, self._conn:
            sql = "SELECT * FROM scan_memory WHERE 1=1"
            args = []
            if detection_item:
                sql += " AND IFNULL(detection_item,'')=?"
                args.append(detection_item)
            rows = self._conn.execute(
                sql + " ORDER BY count DESC, id DESC LIMIT ?", (
                    args + [int(limit)])).fetchall()
        return [dict(r) for r in rows]

    def memory_count(self):
        with self._lock, self._conn:
            return self._conn.execute(
                "SELECT COUNT(*) AS n FROM scan_memory").fetchone()["n"]

    def clear_memory(self):
        """清空全部长期记忆。"""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM scan_memory")

    # ── 上传日志 ──
    def mark_uploaded(self, rec_ids, server_response=""):
        with self._lock, self._conn:
            for rid in rec_ids:
                self._conn.execute(
                    "UPDATE scan_records SET uploaded=1 WHERE id=?",
                    (rid,),
                )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS upload_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_record_ids TEXT,
                    response TEXT,
                    created_at TEXT
                )"""
            )
            self._conn.execute(
                "INSERT INTO upload_log (scan_record_ids, response, created_at) VALUES (?,?,?)",
                (json.dumps(rec_ids), str(server_response)[:2000], _now()),
            )

    def close(self):
        with self._lock:
            self._conn.close()