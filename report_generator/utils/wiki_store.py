# -*- coding: utf-8 -*-
"""LLM Wiki 知识库（SQLite，无 Qt / FastAPI 依赖）。

职责：
  - Wiki 页面的增删改查、分类、标签、修订；
  - 中文友好的关键词检索（LIKE 评分 + FTS5 补充）；
  - 内置知识种子：检测方法提示词、操作步骤、计算规则、规范摘录、
    Harness 使用说明；
  - 为 Harness 生成带来源引用的检索上下文（Wiki + 规范库）。

数据库：data/wiki/wiki.db（可用 STRUCTURAL_WIKI_DB 覆盖）
"""

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DB_DIR = _ROOT / "data" / "wiki"
_DEFAULT_DB = _DB_DIR / "wiki.db"
_DB_PATH = Path(os.environ.get("STRUCTURAL_WIKI_DB") or _DEFAULT_DB)

_LOCK = threading.RLock()
_READY = False
SEED_VERSION = 3

STOPWORDS = {
    "请问", "咨询", "什么", "怎么", "如何", "要求", "规定", "规范", "标准",
    "检测", "检查", "进行", "需要", "应该", "必须", "以及", "关于", "哪里",
    "多少", "值是", "方法", "内容", "说明", "解释", "意思", "含义",
    "帮我", "一下", "这个", "那个", "可以", "是否", "有没有", "哪些",
    "的", "吗", "呢", "是", "了", "和", "与", "或", "对", "在", "中",
    "应", "需", "有", "其", "及", "并", "按", "时", "当", "为",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '未分类',
    summary TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    tags_json TEXT DEFAULT '[]',
    detection_items_json TEXT DEFAULT '[]',
    source TEXT DEFAULT '',
    builtin INTEGER DEFAULT 0,
    source_hash TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wiki_category ON wiki_pages(category);
CREATE INDEX IF NOT EXISTS idx_wiki_updated ON wiki_pages(updated_at DESC);

CREATE TABLE IF NOT EXISTS wiki_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id TEXT NOT NULL,
    title TEXT,
    content TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_wiki_revision_page ON wiki_revisions(page_id);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value):
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return "[]"


def _json_loads(text, default):
    try:
        data = json.loads(text or "")
        return data if data is not None else default
    except Exception:  # noqa: BLE001
        return default


def _sha1(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


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
    global _READY
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        with _connect() as conn:
            conn.executescript(_SCHEMA)
            _ensure_fts(conn)
        seed_builtin()
        _READY = True


def _ensure_fts(conn):
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts "
            "USING fts5(title, summary, content, tags)")
    except sqlite3.OperationalError:
        pass


def _reindex(conn):
    try:
        conn.execute("DELETE FROM wiki_pages_fts")
        conn.execute(
            "INSERT INTO wiki_pages_fts(rowid, title, summary, content, tags)"
            " SELECT rowid, title, summary, content,"
            " COALESCE(tags_json, '') FROM wiki_pages")
    except sqlite3.OperationalError:
        pass


# ═══════════════════════════════════════════════════════════
#  内置知识种子
# ═══════════════════════════════════════════════════════════
_HARNESS_HELP = """# Harness 使用说明

本系统采用 Harness 模式：启动时先做只读预演，随后进入对话；说出检测意图后，
助手会给出“进入数据采集”的入口，并在各个页面持续显示工具调用轨迹。

## 四个概念

1. **启动预演**：只读检查后端、项目、模板/设备、记录库、Wiki 与规范库，
   不会修改项目数据。
2. **模拟执行**：默认开启。助手可以演示勾选、录数、评定、生成报告等步骤，
   但写工具只返回“将执行什么”，不会真的写入。
3. **真实执行**：关闭模拟开关并确认后，写工具才会修改项目或生成文件。
4. **工具轨迹**：每次工具调用都会记录阶段、参数、结果摘要和耗时，
   可在右侧执行抽屉或 Harness 会话页查看。

## 建议流程

1. 用一句话说明本次检测任务，例如“我要做回弹法检测，梁和墙”。
2. 确认意图卡，进入数据采集页；先勾选检测项目，再录入或导入数据。
3. 运行评定；需要时选择报告模板、原始记录模板和设备。
4. 生成检测报告与原始记录；文件会登记到报告记录库 / 原始记录库。

## 安全约定

- 检测数值、构件和结论不得由大模型编造；
- 强度、尺寸、厚度、间距、保护层、根数等结论必须调用评定引擎；
- 未开启真实执行时，所有写操作都不会生效。
"""

_DETECTION_ALIASES = [
    ("回弹法检测", ["回弹法", "回弹", "rebound"]),
    ("钻芯法检测", ["钻芯法", "钻芯", "芯样"]),
    ("回弹钻芯修正法检测", ["回弹钻芯修正", "修正法"]),
    ("剪力墙构件钢筋间距检测", ["剪力墙钢筋间距", "剪力墙间距"]),
    ("现浇板钢筋间距检测", ["板钢筋间距", "现浇板间距"]),
    ("梁构件底排受力钢筋根数检测", ["梁钢筋根数", "梁底排根数"]),
    ("柱构件主要受力钢筋根数检测", ["柱钢筋根数", "柱根数"]),
    ("剪力墙钢筋根数检测", ["墙钢筋根数", "剪力墙根数"]),
    ("楼板构件厚度检测", ["楼板厚度", "板厚"]),
    ("剪力墙厚度检测", ["剪力墙厚度", "墙厚"]),
    ("混凝土梁结构尺寸检测", ["梁截面尺寸", "梁尺寸"]),
    ("混凝土柱结构尺寸检测", ["柱截面尺寸", "柱尺寸"]),
    ("混凝土梁保护层厚度检测", ["梁保护层"]),
    ("混凝土柱保护层厚度检测", ["柱保护层"]),
    ("剪力墙保护层厚度检测", ["墙保护层", "剪力墙保护层"]),
    ("混凝土板保护层厚度检测", ["板保护层"]),
    ("化学植筋锚固承载力检测", ["植筋", "锚固承载力", "拉拔"]),
    ("碳化深度", ["碳化深度", "碳化"]),
]


def _detection_items_for(text):
    text = str(text or "")
    hits = []
    for item, aliases in _DETECTION_ALIASES:
        if item in text or any(a in text for a in aliases):
            hits.append(item)
    return hits


def _read_text(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _first_heading(text, fallback):
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                return title
    return fallback


def _summary_line(text, fallback=""):
    """取第一行有意义的正文（跳过标题、代码围栏、引用符号）。"""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        return line.lstrip(">").strip()[:120]
    return fallback


def _seed_page(slug, title, category, summary, content, tags=None,
               detection_items=None, source=""):
    slug = str(slug or "").strip()
    if not slug or not title or not content:
        return
    now = _now()
    content_hash = _sha1(content)
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM wiki_pages WHERE slug=?",
                           (slug,)).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO wiki_pages
                   (id, slug, title, category, summary, content, tags_json,
                    detection_items_json, source, builtin, source_hash,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, slug, title, category or "未分类",
                 summary or "", content, _json_dumps(tags or []),
                 _json_dumps(detection_items or []), source or "",
                 1, content_hash, now, now))
            _reindex(conn)
            return
        # 内置页且未被用户编辑过 → 跟随种子更新；用户改过的不覆盖
        if not row["builtin"]:
            return
        if row["source_hash"] and row["source_hash"] != _sha1(row["content"]):
            return
        if (row["content"] == content and row["title"] == title
                and (row["summary"] or "") == (summary or "")):
            return
        conn.execute(
            """UPDATE wiki_pages SET title=?, category=?, summary=?, content=?,
               tags_json=?, detection_items_json=?, source=?, source_hash=?,
               updated_at=? WHERE slug=?""",
            (title, category or "未分类", summary or "", content,
             _json_dumps(tags or []), _json_dumps(detection_items or []),
             source or "", content_hash, now, slug))
        _reindex(conn)


def _seed_prompt_pages():
    prompt_dir = _ROOT / "prompt"
    if not prompt_dir.is_dir():
        return
    for path in sorted(prompt_dir.glob("*.md")):
        try:
            content = _read_text(path)
        except Exception:  # noqa: BLE001
            continue
        stem = path.stem
        title = _first_heading(content, stem)
        items = _detection_items_for(stem + "\n" + content[:300])
        _seed_page(
            "prompt-" + stem, title, "检测方法与评定",
            "检测评定提示词：%s" % stem, content,
            tags=["提示词", "评定规则"], detection_items=items,
            source="prompt/%s" % path.name)


def _seed_operation_guide():
    path = _ROOT / "docs" / "操作步骤说明与菜单优化方案.md"
    if not path.is_file():
        return
    try:
        text = _read_text(path)
    except Exception:  # noqa: BLE001
        return
    start = text.find("## 一、")
    end = text.find("## 二、")
    if start >= 0 and end > start:
        text = text[start:end]
    parts = re.split(r"^####\s+(.+)$", text, flags=re.M)
    # re.split 结果：[前言, 标题1, 正文1, 标题2, 正文2, ...]
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip()
        body = parts[i + 1].strip()
        # 操作步骤原文常包在代码围栏里；去掉围栏，正文按普通段落显示
        body = "\n".join(
            line for line in body.splitlines()
            if not line.strip().startswith("```")).strip()
        if not title or not body:
            continue
        items = _detection_items_for(title + "\n" + body)
        _seed_page(
            "guide-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:12],
            title, "操作指南", _summary_line(body), body,
            tags=["操作步骤"], detection_items=items,
            source="docs/操作步骤说明与菜单优化方案.md")


def _seed_single_file(path, slug, category, tags, source_name=None):
    if not path.is_file():
        return
    try:
        text = _read_text(path)
    except Exception:  # noqa: BLE001
        return
    title = _first_heading(text, path.stem)
    summary = _summary_line(text)
    _seed_page(slug, title, category, summary, text, tags=tags,
               detection_items=_detection_items_for(text[:800]),
               source=source_name or path.name)


def _seed_norm_examples():
    base = _ROOT / "report_generator" / "data" / "norm_qa" / "input"
    if not base.is_dir():
        return
    for idx, path in enumerate(sorted(base.glob("*.md"))):
        _seed_single_file(
            path, "norm-example-%02d" % idx, "规范摘录",
            ["规范", "条文"], source_name="norm_qa/input/%s" % path.name)


def seed_builtin():
    """写入/更新内置知识页；幂等且不覆盖用户编辑。"""
    with _LOCK:
        with _connect() as conn:
            version = int(_meta_get(conn, "seed_version", "0") or 0)
            has_pages = conn.execute(
                "SELECT COUNT(*) FROM wiki_pages WHERE builtin=1").fetchone()[0]
            if version >= SEED_VERSION and has_pages:
                return
        _seed_prompt_pages()
        _seed_operation_guide()
        _seed_single_file(
            _ROOT / "docs" / "钻芯法计算规则.md", "calc-core-drilling",
            "计算规则", ["计算", "钻芯法"])
        _seed_norm_examples()
        _seed_page(
            "system-harness-help", "Harness 使用说明", "系统说明",
            "启动预演、模拟执行、工具轨迹与安全约定", _HARNESS_HELP,
            tags=["Harness", "使用说明"], detection_items=[],
            source="wiki_store")
        with _LOCK, _connect() as conn:
            _meta_set(conn, "seed_version", SEED_VERSION)


# ═══════════════════════════════════════════════════════════
#  CRUD
# ═══════════════════════════════════════════════════════════
def _page_view(row, with_content=True):
    data = dict(row)
    data["tags"] = _json_loads(data.pop("tags_json", ""), [])
    data["detection_items"] = _json_loads(
        data.pop("detection_items_json", ""), [])
    data["builtin"] = bool(data.get("builtin"))
    if not with_content:
        data.pop("content", None)
    return data


def get_page(page_id):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM wiki_pages WHERE id=?",
                           (str(page_id),)).fetchone()
        if not row:
            return None
        view = _page_view(row)
        view["revision_count"] = conn.execute(
            "SELECT COUNT(*) FROM wiki_revisions WHERE page_id=?",
            (str(page_id),)).fetchone()[0]
    return view


def get_page_by_slug(slug):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM wiki_pages WHERE slug=?",
                           (str(slug),)).fetchone()
    return _page_view(row) if row else None


def list_pages(category="", query="", limit=100, offset=0):
    ensure_schema()
    where, params = [], []
    category = str(category or "").strip()
    if category:
        where.append("category=?")
        params.append(category)
    query = str(query or "").strip()
    if query:
        like = "%" + query + "%"
        where.append("(title LIKE ? OR summary LIKE ? OR content LIKE ? "
                     "OR tags_json LIKE ? OR detection_items_json LIKE ?)")
        params.extend([like] * 5)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with _LOCK, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM wiki_pages" + clause,
                             params).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM wiki_pages" + clause
            + " ORDER BY category, updated_at DESC, title LIMIT ? OFFSET ?",
            params + [int(limit), int(offset)]).fetchall()
    return [_page_view(r, with_content=False) for r in rows], int(total)


def list_categories():
    ensure_schema()
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM wiki_pages"
            " GROUP BY category ORDER BY category").fetchall()
    return [{"name": r["category"], "count": r["count"]} for r in rows]


def save_page(page_id=None, title="", category="未分类", summary="",
              content="", tags=None, detection_items=None, source="",
              slug="", builtin=0):
    ensure_schema()
    title = str(title or "").strip()
    content = str(content or "")
    if not title:
        raise ValueError("标题不能为空")
    if not content.strip():
        raise ValueError("正文不能为空")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("正文超过 2MB，已拒绝保存")
    category = str(category or "未分类").strip() or "未分类"
    summary = str(summary or "").strip()
    tags = tags if isinstance(tags, list) else []
    items = detection_items if isinstance(detection_items, list) else []
    now = _now()
    with _LOCK, _connect() as conn:
        if page_id:
            row = conn.execute("SELECT * FROM wiki_pages WHERE id=?",
                               (str(page_id),)).fetchone()
            if not row:
                raise ValueError("Wiki 页面不存在：%s" % page_id)
            conn.execute(
                """UPDATE wiki_pages SET title=?, category=?, summary=?,
                   content=?, tags_json=?, detection_items_json=?, source=?,
                   updated_at=? WHERE id=?""",
                (title, category, summary, content, _json_dumps(tags),
                 _json_dumps(items), source or row["source"] or "", now,
                 str(page_id)))
            conn.execute(
                "INSERT INTO wiki_revisions(page_id, title, content, created_at)"
                " VALUES(?,?,?,?)",
                (str(page_id), title, content, now))
            new_id = str(page_id)
        else:
            new_id = uuid.uuid4().hex
            slug = str(slug or "").strip() or ("page-" + new_id[:12])
            exists = conn.execute("SELECT 1 FROM wiki_pages WHERE slug=?",
                                  (slug,)).fetchone()
            if exists:
                slug = "%s-%s" % (slug, new_id[:6])
            conn.execute(
                """INSERT INTO wiki_pages
                   (id, slug, title, category, summary, content, tags_json,
                    detection_items_json, source, builtin, source_hash,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id, slug, title, category, summary, content,
                 _json_dumps(tags), _json_dumps(items), source or "",
                 1 if builtin else 0, _sha1(content), now, now))
        _reindex(conn)
    return get_page(new_id)


def delete_page(page_id):
    ensure_schema()
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM wiki_pages WHERE id=?",
                           (str(page_id),)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM wiki_pages WHERE id=?", (str(page_id),))
        conn.execute("DELETE FROM wiki_revisions WHERE page_id=?",
                     (str(page_id),))
        _reindex(conn)
    return True


# ═══════════════════════════════════════════════════════════
#  检索
# ═══════════════════════════════════════════════════════════
def _clean(text):
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", str(text or "")).strip()


def _keywords(question):
    text = _clean(question)
    if not text:
        return []
    compact = text.replace(" ", "")
    kws = []
    if len(compact) >= 2:
        kws.append(compact[:24])
    cleaned = text
    for stop in sorted(STOPWORDS, key=len, reverse=True):
        cleaned = cleaned.replace(stop, " ")
    for seg in cleaned.split():
        if len(seg) >= 2 and seg not in kws:
            kws.append(seg[:16])
    for n in (2, 3, 4):
        for i in range(len(compact) - n + 1):
            gram = compact[i:i + n]
            if any(stop == gram for stop in STOPWORDS):
                continue
            if gram not in kws:
                kws.append(gram)
            if len(kws) >= 24:
                break
        if len(kws) >= 24:
            break
    return list(dict.fromkeys(kws))


def _score_page(row, keywords, detection_items):
    title = row.get("title") or ""
    summary = row.get("summary") or ""
    content = row.get("content") or ""
    tags = " ".join(_json_loads(row.get("tags_json"), []))
    items = _json_loads(row.get("detection_items_json"), [])
    score = 0
    for kw in keywords:
        if kw in title:
            score += 8
        if kw in tags:
            score += 4
        if kw in " ".join(items):
            score += 4
        if kw in summary:
            score += 3
        if kw in content:
            score += 1 + min(content.count(kw), 4)
    for item in detection_items or []:
        if item and (item in " ".join(items) or item in title
                     or item in content[:500]):
            score += 6
    return score


def _snippet(content, keywords, length=160):
    text = str(content or "")
    pos = -1
    for kw in keywords:
        if kw and kw in text:
            pos = text.index(kw)
            break
    if pos < 0:
        return text[:length].replace("\n", " ")
    start = max(0, pos - length // 3)
    return text[start:start + length].replace("\n", " ")


def search(question, top_k=3, detection_items=None):
    ensure_schema()
    top_k = max(1, min(int(top_k or 3), 10))
    keywords = _keywords(question)
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT * FROM wiki_pages").fetchall()
    scored = []
    for row in rows:
        data = dict(row)
        score = _score_page(data, keywords, detection_items)
        if score > 0:
            scored.append((score, data))
    scored.sort(key=lambda x: (-x[0], x[1].get("updated_at") or ""))
    hits = []
    for score, row in scored[:top_k]:
        hits.append({
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "summary": row.get("summary") or "",
            "snippet": _snippet(row.get("content") or "", keywords),
            "score": score,
        })
    return {"items": hits, "total": len(scored), "query": question,
            "keywords": keywords[:12]}


def _norm_context(question, top_k=5):
    try:
        from utils.norm_qa import NormQueryEngine
        result = NormQueryEngine().query(question)
    except Exception:  # noqa: BLE001
        return []
    clauses = result.get("clauses") or []
    out = []
    for clause in clauses[:top_k]:
        out.append({
            "code": clause.get("code") or "",
            "code_name": clause.get("code_name") or "",
            "chapter": clause.get("chapter") or "",
            "title": clause.get("title") or "",
            "body": (clause.get("body") or "")[:1200],
        })
    return out


def build_context(question, top_k=3, detection_items=None):
    """为 LLM 组装带来源的 Wiki + 规范上下文。"""
    ensure_schema()
    result = search(question, top_k=top_k,
                    detection_items=detection_items)
    wiki = []
    for hit in result.get("items") or []:
        page = get_page(hit["id"])
        if not page:
            continue
        wiki.append({
            "id": page["id"],
            "title": page["title"],
            "category": page["category"],
            "summary": page["summary"],
            "content": (page["content"] or "")[:1600],
        })
    norms = _norm_context(question, top_k=5) if question else []
    chunks = []
    for page in wiki:
        chunks.append("【知识库】《%s》（%s）\n%s\n%s" % (
            page["title"], page["category"], page["summary"],
            page["content"]))
    for clause in norms:
        chunks.append("【规范】%s %s %s %s\n%s" % (
            clause["code"], clause["code_name"], clause["chapter"],
            clause["title"], clause["body"]))
    text = "\n\n".join(chunks)[:6000]
    return {"wiki": wiki, "norms": norms, "text": text,
            "query": question, "keywords": result.get("keywords") or []}


# ═══════════════════════════════════════════════════════════
#  导入 / 状态
# ═══════════════════════════════════════════════════════════
def _docx_text(path):
    from docx import Document
    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def read_import_text(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return _docx_text(path)
    if suffix in (".md", ".markdown", ".txt"):
        return _read_text(path)
    raise ValueError("仅支持 .md / .markdown / .txt / .docx 文件")


def import_file(path, category="未分类", title="", detection_items=None):
    path = Path(path)
    if not path.is_file():
        raise ValueError("文件不存在：%s" % path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("文件超过 20MB：%s" % path.name)
    text = read_import_text(path)
    if not text.strip():
        raise ValueError("文件内容为空：%s" % path.name)
    final_title = str(title or "").strip() or _first_heading(text, path.stem)
    summary = _summary_line(text)
    items = list(detection_items or []) or _detection_items_for(final_title)
    return save_page(
        title=final_title, category=category, summary=summary, content=text,
        tags=["导入"], detection_items=items, source=path.name)


def status():
    ensure_schema()
    with _LOCK, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0]
        categories = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM wiki_pages").fetchone()[0]
    return {"pages": total, "categories": categories,
            "db_path": str(_DB_PATH), "exists": _DB_PATH.exists(),
            "seed_version": SEED_VERSION}
