# -*- coding: utf-8 -*-
"""规范条文检索引擎。

检索漏斗（沿用 Civil_check 策略）：
1. 条号精确命中：查询文本中含 x.y / x.y.z 条号 → chapter 精确匹配；
   节号（如 4.2）→ LIKE '4.2.%' 返回该节下全部子条。
2. 自然语言：FTS5 MATCH 优先（英文/数字分词有效），空结果降级
   LIKE 多关键词评分检索（中文整句 FTS5 分词不中，实际走此路）。
3. 术语候选：无结果时从查询滑窗片段在库内计频，返回候选供点击重查。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .store import get_db_path

RE_CLAUSE_NUM = re.compile(r"\d{1,2}\.\d{1,2}(?:\.\d{1,2})?")

# 常见虚词/泛词：不参与关键词检索
STOPWORDS = {
    "请问", "咨询", "什么", "怎么", "如何", "要求", "规定", "规范", "标准",
    "检测", "检查", "进行", "需要", "应该", "必须", "以及", "关于", "哪里",
    "多少", "值是", "方法", "内容", "说明", "解释", "意思", "含义",
    "的", "吗", "呢", "是", "了", "和", "与", "或", "对", "在", "中",
    "应", "需", "有", "其", "及", "并", "按", "时", "当", "为",
}

MAX_LIKE_HITS = 40       # LIKE 评分检索返回上限
MAX_CANDIDATES = 6       # 术语候选上限


class NormQueryEngine(object):
    """规范条文检索器（只读 SQLite，不依赖网络与 LLM）。"""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else get_db_path()

    # ── 查询路由 ──
    def query(self, question: str) -> Dict:
        """统一查询入口。返回：
        {"type": "exact"|"search"|"candidates"|"empty",
         "clauses": [..], "candidates": [..], "query": 原查询}
        """
        q = (question or "").strip()
        if not q:
            return {"type": "empty", "clauses": [], "candidates": [], "query": q}

        nums = RE_CLAUSE_NUM.findall(q)
        if nums:
            clauses = self.exact_lookup(nums)
            if clauses:
                return {"type": "exact", "clauses": clauses,
                        "candidates": [], "query": q}

        clauses = self.search(q)
        if clauses:
            return {"type": "search", "clauses": clauses,
                    "candidates": [], "query": q}

        return {"type": "candidates", "clauses": [],
                "candidates": self.suggest_candidates(q), "query": q}

    # ── 条号精确 ──
    def exact_lookup(self, nums: List[str]) -> List[Dict]:
        """按条号精确查询；二级节号返回其下全部子条（按节号升序）。"""
        results: List[Dict] = []
        seen_ids = set()
        for num in nums:
            for row in self._sql_exact(num):
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    results.append(row)
        return results

    def _sql_exact(self, num: str) -> List[Dict]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM clauses WHERE chapter = ?"
                " ORDER BY code LIMIT 50;", (num,))
            rows = [self._row_to_dict(c) for c in cur.fetchall()]
            if not rows:
                cur.execute(
                    "SELECT * FROM clauses WHERE chapter LIKE ?"
                    " ORDER BY code, chapter LIMIT 100;", (num + ".%",))
                rows = [self._row_to_dict(c) for c in cur.fetchall()]
            return rows
        finally:
            conn.close()

    # ── 自然语言检索 ──
    def search(self, question: str) -> List[Dict]:
        keywords = self.extract_keywords(question)
        if not keywords:
            return []
        clauses = self.fts_search(keywords)
        if clauses:
            return clauses
        return self.like_search(keywords)

    def fts_search(self, keywords: List[str]) -> List[Dict]:
        """FTS5 MATCH：关键词 OR 连接（对英文/数字条目有效）。"""
        terms = ' OR '.join('"%s"' % k.replace('"', "") for k in keywords[:8])
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT c.* FROM clauses_fts f JOIN clauses c ON c.id = f.rowid"
                " WHERE clauses_fts MATCH ? LIMIT ?;", (terms, MAX_LIKE_HITS))
            rows = [self._row_to_dict(c) for c in cur.fetchall()]
        except sqlite3.OperationalError:
            rows = []
        finally:
            conn.close()
        return self._rescore(rows, keywords)

    def like_search(self, keywords: List[str]) -> List[Dict]:
        """LIKE 降级：逐条按命中关键词数评分（标题命中加权）。"""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM clauses;")
            rows = [self._row_to_dict(c) for c in cur.fetchall()]
        finally:
            conn.close()
        return self._rescore(rows, keywords)

    def _rescore(self, rows: List[Dict], keywords: List[str]) -> List[Dict]:
        scored = []
        for row in rows:
            title = row.get("title") or ""
            body = row.get("body") or ""
            hits = 0
            for kw in keywords:
                if kw in title:
                    hits += 2
                elif kw in body:
                    hits += 1
            if hits > 0:
                row["score"] = hits
                scored.append(row)
        scored.sort(key=lambda r: (-r["score"], r.get("code") or "",
                                   _chapter_key(r.get("chapter") or "")))
        return scored[:MAX_LIKE_HITS]

    # ── 术语候选 ──
    def suggest_candidates(self, question: str) -> List[Dict]:
        """从查询 2~4 字滑窗片段中挑库内高频出现的片段作为候选。"""
        text = self._clean(question)
        if len(text) < 2:
            return []
        grams = set()
        for n in (2, 3, 4):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                if self._is_term_like(gram):
                    grams.add(gram)
        if not grams:
            return []
        conn = self._connect()
        try:
            cur = conn.cursor()
            counted = []
            for gram in grams:
                pat = "%" + gram + "%"
                cur.execute(
                    "SELECT COUNT(*) FROM clauses WHERE title LIKE ?"
                    " OR body LIKE ?;", (pat, pat))
                n = cur.fetchone()[0]
                if n > 0:
                    counted.append((gram, n))
        finally:
            conn.close()
        counted.sort(key=lambda x: (-x[1], -len(x[0])))
        return [
            {"term": gram, "count": n, "label": "%s（库内出现 %s 处）" % (gram, n)}
            for gram, n in counted[:MAX_CANDIDATES]
        ]

    # ── 工具 ──
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return dict(row)

    @staticmethod
    def _clean(text: str) -> str:
        out = []
        for ch in text:
            if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
                out.append(ch)
        return "".join(out)

    @staticmethod
    def _is_term_like(gram: str) -> bool:
        """候选片段过滤：剔除全虚词/全数字片段。"""
        clean = gram
        if all(ch.isdigit() or not ("\u4e00" <= ch <= "\u9fff") for ch in clean):
            return False
        for stop in STOPWORDS:
            clean = clean.replace(stop, "")
        return len(clean) >= 2

    @staticmethod
    def extract_keywords(question: str) -> List[str]:
        """从自然语言查询提取检索关键词（去停用词 + 保留整串 + 2字滑窗）。"""
        text = NormQueryEngine._clean(question)
        if not text:
            return []
        kws: List[str] = []
        # 1. 整串（截断防超长）
        whole = text[:24]
        if len(whole) >= 2:
            kws.append(whole)
        # 2. 去停用词后的连续片段
        cleaned = text
        for stop in sorted(STOPWORDS, key=len, reverse=True):
            cleaned = cleaned.replace(stop, " ")
        segs = [s for s in cleaned.split() if len(s) >= 2]
        kws.extend(segs[:8])
        # 3. 整串相邻 2 字滑窗（兜底）
        for i in range(len(text) - 1):
            g = text[i:i + 2]
            if NormQueryEngine._is_term_like(g) and g not in kws:
                kws.append(g)
            if len(kws) >= 24:
                break
        return list(dict.fromkeys(kws))


def _chapter_key(chapter: str) -> Tuple:
    """条号排序键：按数字段逐段比较，非数字段附后。"""
    parts = chapter.split(".")
    key = []
    for p in parts:
        if p.isdigit():
            key.append((0, int(p), ""))
        else:
            key.append((1, 0, p))
    return tuple(key)
