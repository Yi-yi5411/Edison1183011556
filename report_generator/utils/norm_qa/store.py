# -*- coding: utf-8 -*-
"""规范条文 SQLite 存储（FTS5 全文索引）。

表结构沿用 Civil_check 约定：
- 主表 clauses：一条记录对应一条规范条文；
- 虚表 clauses_fts：FTS5，仅索引 title 与 body（独立表自存副本，避免
  content= 外部表在部分环境下的损坏问题）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

DB_FILENAME = "norm_codes.db"


def get_db_path(base_dir=None) -> Path:
    """规范库数据目录：report_generator/data/norm_qa/norm_codes.db。"""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parents[2] / "data" / "norm_qa"
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / DB_FILENAME


@dataclass
class ClauseRecord(object):
    """规范条款在 SQLite 中的一条记录。"""

    code: str                       # 规范代号，如 JGJ/T 23-2011
    chapter: str                    # 条号/节号，如 5.1.2
    title: str                      # 条款标题（条号后的文字）
    body: str                       # 条款正文全文
    code_name: Optional[str] = None  # 规范中文名
    category: Optional[str] = None  # 专业/主题分类（可选）
    chapter_path: Optional[str] = None  # 章节路径（如 "5 混凝土强度 / 5.1 一般规定"）
    source_file: Optional[str] = None  # 来源文件名


def _connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_schema(db_path=None) -> Path:
    """初始化规范库表结构，返回数据库文件路径。"""
    db_path = Path(db_path) if db_path else get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clauses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                code_name TEXT,
                chapter TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                category TEXT,
                chapter_path TEXT,
                source_file TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS clauses_fts USING fts5(title, body);
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def build_from_records(db_path, records: Iterable[ClauseRecord]) -> int:
    """单连接内完成清空 → 全量插入 → 重建 FTS，返回入库条数。

    单连接降低多连接写库导致 database disk image is malformed 的风险。
    """
    db_path = Path(db_path) if db_path else get_db_path()
    init_schema(db_path)
    rows = list(records)
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM clauses_fts;")
        cur.execute("DELETE FROM clauses;")
        cur.executemany(
            "INSERT INTO clauses (code, code_name, chapter, title, body,"
            " category, chapter_path, source_file)"
            " VALUES (:code, :code_name, :chapter, :title, :body,"
            " :category, :chapter_path, :source_file);",
            [
                {
                    "code": r.code,
                    "code_name": r.code_name,
                    "chapter": r.chapter,
                    "title": r.title,
                    "body": r.body,
                    "category": r.category,
                    "chapter_path": r.chapter_path,
                    "source_file": r.source_file,
                }
                for r in rows
            ],
        )
        cur.execute("DELETE FROM clauses_fts;")
        cur.execute(
            "INSERT INTO clauses_fts(rowid, title, body)"
            " SELECT id, title, body FROM clauses;"
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def append_records(db_path, records: Iterable[ClauseRecord]) -> int:
    """增量追加条文（同 code+chapter 存在时覆盖），返回最终条数。

    便于按规范文件逐个导入而不清掉已导入的其他规范。
    """
    db_path = Path(db_path) if db_path else get_db_path()
    init_schema(db_path)
    rows = list(records)
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        for r in rows:
            cur.execute(
                "SELECT id FROM clauses WHERE code=? AND chapter=?;",
                (r.code, r.chapter),
            )
            hit = cur.fetchone()
            if hit:
                cur.execute(
                    "UPDATE clauses SET code_name=?, title=?, body=?,"
                    " category=?, chapter_path=?, source_file=? WHERE id=?;",
                    (r.code_name, r.title, r.body, r.category,
                     r.chapter_path, r.source_file, hit[0]),
                )
            else:
                cur.execute(
                    "INSERT INTO clauses (code, code_name, chapter, title,"
                    " body, category, chapter_path, source_file)"
                    " VALUES (?,?,?,?,?,?,?,?);",
                    (r.code, r.code_name, r.chapter, r.title, r.body,
                     r.category, r.chapter_path, r.source_file),
                )
        cur.execute("DELETE FROM clauses_fts;")
        cur.execute(
            "INSERT INTO clauses_fts(rowid, title, body)"
            " SELECT id, title, body FROM clauses;"
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM clauses;")
        total = cur.fetchone()[0]
    finally:
        conn.close()
    return total


def db_status(db_path=None) -> dict:
    """规范库状态：条数与规范清单。"""
    db_path = Path(db_path) if db_path else get_db_path()
    info = {"db_path": str(db_path), "exists": db_path.exists(),
            "total": 0, "codes": []}
    if not db_path.exists():
        return info
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clauses;")
        info["total"] = cur.fetchone()[0]
        cur.execute(
            "SELECT code, code_name, COUNT(*) FROM clauses"
            " GROUP BY code, code_name ORDER BY code;"
        )
        info["codes"] = [
            {"code": r[0], "code_name": r[1] or "", "count": r[2]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
    return info
