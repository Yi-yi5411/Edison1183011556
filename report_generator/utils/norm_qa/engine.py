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

from .catalog import codes_for_items, expand_keywords, match_db_codes
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
    def query(self, question: str, detection_items=None) -> Dict:
        """统一查询入口。

        detection_items 传入时，优先只在该项目的依据规范里检索；检索不到会
        自动去掉过滤再搜一次，并用 filtered_out 标记，避免「问到了却查不到」。

        返回：
        {"type": "exact"|"search"|"candidates"|"empty",
         "clauses": [..], "candidates": [..], "query": 原查询,
         "detection_items": [..], "codes": [该项目依据规范],
         "filter_codes": [实际生效的库内代号], "filter_applied": bool,
         "filtered_out": bool}
        """
        q = (question or "").strip()
        items = [str(i) for i in (detection_items or []) if str(i).strip()]
        codes = codes_for_items(items) if items else []
        base = {"query": q, "detection_items": items, "codes": codes,
                "filter_codes": [], "filter_applied": False,
                "filtered_out": False}
        if not q:
            return dict(base, type="empty", clauses=[], candidates=[])

        nums = RE_CLAUSE_NUM.findall(q)
        if nums:
            clauses = self.exact_lookup(nums)
            if clauses:
                return dict(base, type="exact", clauses=clauses, candidates=[])

        filter_codes = match_db_codes(codes, self.db_path) if codes else []
        clauses = self.search(q, detection_items=items)
        filtered_out = False
        if not clauses and filter_codes:
            clauses = self.search(q)
            filtered_out = bool(clauses)
        if clauses:
            return dict(base, type="search", clauses=clauses, candidates=[],
                        filter_codes=filter_codes,
                        filter_applied=bool(filter_codes),
                        filtered_out=filtered_out)
        return dict(base, type="candidates", clauses=[],
                    candidates=self.suggest_candidates(q),
                    filter_codes=filter_codes)

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
    def search(self, question: str, detection_items=None) -> List[Dict]:
        """关键词扩展 → FTS(bm25 排序) → LIKE 兜底，可按检测项目的规范过滤。"""
        keywords = self.extract_keywords(question)
        if not keywords:
            return []
        expanded = expand_keywords(keywords)
        db_codes = None
        if detection_items:
            wanted = codes_for_items(detection_items)
            if wanted:
                db_codes = match_db_codes(wanted, self.db_path) or None
        clauses = self.fts_search(expanded, db_codes=db_codes, primary=keywords)
        if clauses:
            return clauses
        return self.like_search(expanded, db_codes=db_codes, primary=keywords)

    @staticmethod
    def _code_where(db_codes):
        """生成代号过滤片段与参数；无过滤时返回空串。"""
        if not db_codes:
            return "", []
        return (" AND c.code IN (%s)" % ",".join("?" * len(db_codes)),
                list(db_codes))

    def fts_search(self, keywords: List[str], db_codes=None,
                   primary=None) -> List[Dict]:
        """FTS5 MATCH：关键词 OR 连接，按 bm25 相关度排序后统一重排。"""
        terms = ' OR '.join('"%s"' % k.replace('"', "")
                            for k in keywords[:12])
        where, params = self._code_where(db_codes)
        sql = ("SELECT c.*, bm25(clauses_fts) AS _rank"
               " FROM clauses_fts f JOIN clauses c ON c.id = f.rowid"
               " WHERE clauses_fts MATCH ?" + where +
               " ORDER BY _rank LIMIT ?;")
        rows: List[Dict] = []
        conn = self._connect()
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql, [terms] + params + [MAX_LIKE_HITS])
                rows = [self._row_to_dict(c) for c in cur.fetchall()]
            except sqlite3.OperationalError:
                # 老 SQLite 无 bm25：退回不带相关度排序的查询
                fallback = ("SELECT c.* FROM clauses_fts f JOIN clauses c"
                            " ON c.id = f.rowid WHERE clauses_fts MATCH ?"
                            + where + " LIMIT ?;")
                try:
                    cur.execute(fallback, [terms] + params + [MAX_LIKE_HITS])
                    rows = [self._row_to_dict(c) for c in cur.fetchall()]
                except sqlite3.OperationalError:
                    rows = []
        finally:
            conn.close()
        return self._rescore(rows, primary or keywords, keywords)

    def like_search(self, keywords: List[str], db_codes=None,
                    primary=None) -> List[Dict]:
        """LIKE 降级：逐条按命中关键词数评分（标题命中加权）。"""
        where, params = self._code_where(db_codes)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT c.* FROM clauses c WHERE 1=1" + where + ";",
                        params)
            rows = [self._row_to_dict(c) for c in cur.fetchall()]
        finally:
            conn.close()
        return self._rescore(rows, primary or keywords, keywords)

    def _rescore(self, rows: List[Dict], primary: List[str],
                 secondary=None) -> List[Dict]:
        """统一打分：用户原词权重高、扩展词低、整串命中额外加分。

        分数相同时按 bm25 名次、规范代号、条号排序，结果稳定可复现。
        """
        primary = [k for k in (primary or []) if k]
        secondary = [k for k in (secondary or []) if k]
        phrase = primary[0] if primary else ""
        scored = []
        for row in rows:
            title = row.get("title") or ""
            body = row.get("body") or ""
            hits = 0
            matched: List[str] = []
            for kw in primary:
                if kw in title:
                    hits += 3
                    matched.append(kw)
                elif kw in body:
                    hits += 2
                    matched.append(kw)
            for kw in secondary:
                if kw in primary:
                    continue
                if kw in title or kw in body:
                    hits += 1
                    matched.append(kw)
            if len(phrase) >= 4 and phrase in body:
                hits += 4
                matched.append(phrase)
            if hits <= 0:
                continue
            row["score"] = hits
            row["matched_terms"] = list(dict.fromkeys(matched))[:8]
            rank = row.pop("_rank", None)
            row["rank"] = rank
            scored.append(row)
        scored.sort(key=lambda r: (
            -r["score"],
            r["rank"] if r.get("rank") is not None else 1e9,
            r.get("code") or "",
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
