# -*- coding: utf-8 -*-
"""批量审查管线（借鉴 Civil_check batch_review 流程，按本项目 GUI 风格实现）。

流程：导入检测报告/记录文件（docx/pdf/txt）→ 全文分块 → 本地 Ollama 逐块
提取审查意见候选（JSON）→ 每条候选自动匹配规范库依据（norm_qa 检索）
→ 人工勾选确认 → 导出审查意见 Word 表。

模块不依赖 GUI；LLM 不可达时 extract_candidates 返回空并记录原因。
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .engine import NormQueryEngine
from .llm import _pick_model, _resolve_base_url
from .parser import RE_SINGLE_CLAUSE

CHUNK_SIZE = 1800      # 分块字符数
CHUNK_OVERLAP = 150    # 块间重叠，避免条文被切断漏审

CATEGORIES = ("结论表述", "依据引用", "数据完整性", "用语规范", "签字盖章", "其他")

PROMPT_TEMPLATE = (
    "以下是一份建设工程检测报告的片段（第%s部分，共%s部分）。"
    "请从片段原文中找出值得复核的审查点，只依据原文，不要编造。\n"
    "输出JSON：{\"candidates\": [{\"location\": \"位置（章节/条目/上下文）\","
    " \"excerpt\": \"原文片段（60字以内）\","
    " \"category\": \"问题类型\","
    " \"description\": \"问题描述\","
    " \"suggestion\": \"审查意见建议\"}]}\n"
    "问题类型只能取：%s。\n"
    "若片段没有问题，输出 {\"candidates\": []}。\n"
    "直接输出JSON，禁止任何分析、思考或解释文字。\n\n"
    "片段内容：\n%s"
)

# 原文中的规范条文引用（如 JGJ/T 23-2011 中 4.2.2、GB 50204 第5.1.2条）
RE_CODE_REF = re.compile(r"[A-Z]{1,6}(?:/[A-Z]{1,6})?[^，。；\n]{0,20}?\d{1,2}\.\d{1,2}(?:\.\d{1,2})?")


# ═══════════════════════════════════════════════════════════
#  文本提取
# ═══════════════════════════════════════════════════════════
def extract_text(file_path) -> str:
    """按扩展名提取全文文本。pdf 依赖 pypdf/pdfminer（缺库时提示转 Word）。"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix in (".txt",):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix in (".docx",):
        return _read_docx(path)
    if suffix in (".pdf",):
        return _read_pdf(path)
    raise ValueError("不支持的文件格式：%s（支持 docx/pdf/txt）" % suffix)


def _read_docx(path: Path) -> str:
    try:
        import docx  # noqa
    except ImportError:
        raise RuntimeError("读取 docx 需要 python-docx 库（打包环境已内置）")
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # noqa
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text  # noqa
        return extract_text(str(path)) or ""
    except ImportError:
        raise RuntimeError(
            "读取 PDF 需要 pypdf 或 pdfminer 库；请将 PDF 转为 Word 后导入，"
            "或 pip install pypdf")


# ═══════════════════════════════════════════════════════════
#  分块
# ═══════════════════════════════════════════════════════════
def chunk_text(text: str, size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> List[str]:
    """按字符数分块（带重叠），尽量在换行处断开。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            nl = text.rfind("\n", start + size // 2, end)
            if nl > start + overlap:
                end = nl + 1
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


# ═══════════════════════════════════════════════════════════
#  LLM 候选提取
# ═══════════════════════════════════════════════════════════
def extract_candidates(chunk: str, index: int, total: int,
                       model: str = "", timeout: float = 300.0,
                       retries: int = 1,
                       on_log: Optional[Callable[[str], None]] = None
                       ) -> List[Dict]:
    """对单块文本调用 Ollama 提取审查候选（JSON，think off）。"""
    log = on_log or (lambda m: None)
    base_url = _resolve_base_url()
    if not model:
        model = _pick_model(base_url)
    if not model:
        raise RuntimeError("Ollama 服务不可用（%s），无法提取审查候选" % base_url)

    prompt = PROMPT_TEMPLATE % (index + 1, total, "、".join(CATEGORIES), chunk)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }
    last_err = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                base_url + "/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = ((data.get("message") or {}).get("content") or "").strip()
            return _parse_candidates(content, chunk)
        except Exception as e:
            last_err = str(e)
            if attempt < retries:
                log("第%d部分提取失败（%s），重试……" % (index + 1, last_err))
    log("第%d部分提取失败：%s" % (index + 1, last_err))
    return []


def _parse_candidates(content: str, chunk: str) -> List[Dict]:
    """解析模型 JSON 回复为候选列表（含兜底正则），统一补齐字段。"""
    items = []
    try:
        data = json.loads(content)
        items = data.get("candidates") or []
        if isinstance(items, dict):
            items = [items]
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                items = json.loads(m.group(0)).get("candidates") or []
            except Exception:
                items = []
    result = []
    for it in items:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("description") or "").strip()
        if not desc:
            continue
        cat = str(it.get("category") or "其他").strip()
        if cat not in CATEGORIES:
            cat = "其他"
        result.append({
            "location": str(it.get("location") or "").strip()[:120],
            "excerpt": str(it.get("excerpt") or "").strip()[:200],
            "category": cat,
            "description": desc[:300],
            "suggestion": str(it.get("suggestion") or "").strip()[:300],
            "chunk_hint": chunk[:60].replace("\n", " "),
            "selected": True,
            "basis": "",
        })
    return result


# ═══════════════════════════════════════════════════════════
#  规范依据匹配
# ═══════════════════════════════════════════════════════════
def attach_norm_basis(candidates: List[Dict],
                      engine: Optional[NormQueryEngine] = None) -> None:
    """为每条候选匹配规范依据（原文字面引用优先，关键词检索次之）。"""
    engine = engine or NormQueryEngine()
    for cand in candidates:
        refs = []
        for m in RE_CODE_REF.finditer(
                "%s %s" % (cand.get("excerpt") or "", cand.get("description") or "")):
            refs.extend(RE_SINGLE_CLAUSE.findall(m.group(0)))
        hits: List[Dict] = []
        for num in dict.fromkeys(refs):
            hits.extend(engine.exact_lookup([num]))
        if not hits:
            kws = engine.extract_keywords(
                "%s %s %s" % (cand.get("category") or "",
                              cand.get("description") or "",
                              cand.get("excerpt") or ""))
            if kws:
                hits = engine.search(" ".join(kws[:6]))[:2]
        labels = []
        for h in hits[:2]:
            head = "%s %s" % (h.get("code") or "", h.get("chapter") or "")
            if h.get("title"):
                head += "（%s）" % h["title"]
            labels.append(head)
        cand["basis"] = "；".join(dict.fromkeys(labels))


# ═══════════════════════════════════════════════════════════
#  编排入口 / 导出
# ═══════════════════════════════════════════════════════════
def run_batch_review(file_paths, model: str = "",
                     on_log: Optional[Callable[[str], None]] = None,
                     on_progress: Optional[Callable[[int, int], None]] = None
                     ) -> Dict:
    """批量审查主入口：提取 → 分块 → LLM 候选 → 规范依据。

    返回 {"candidates": [...], "chunks": 总块数, "files": [文件名],
          "model": 实际使用模型}。
    """
    log = on_log or (lambda m: None)
    texts = []
    for fp in file_paths:
        name = Path(fp).name
        log("读取 %s……" % name)
        texts.append(extract_text(fp))
        log("已读取 %s（%d 字）" % (name, len(texts[-1])))

    chunks: List[str] = []
    for text in texts:
        chunks.extend(chunk_text(text))
    if not chunks:
        return {"candidates": [], "chunks": 0,
                "files": [Path(fp).name for fp in file_paths], "model": model}

    log("共分为 %d 个片段，开始提取审查候选（模型：%s）……" % (len(chunks), model or "自动"))
    candidates: List[Dict] = []
    for i, chunk in enumerate(chunks):
        if on_progress:
            on_progress(i, len(chunks))
        candidates.extend(
            extract_candidates(chunk, i, len(chunks), model=model, on_log=log))
    if on_progress:
        on_progress(len(chunks), len(chunks))
    log("提取完成：共 %d 条候选，开始匹配规范依据……" % len(candidates))
    attach_norm_basis(candidates)
    log("规范依据匹配完成。")
    return {"candidates": candidates, "chunks": len(chunks),
            "files": [Path(fp).name for fp in file_paths], "model": model}


def export_review_docx(candidates: List[Dict], output_path,
                       project_name: str = "") -> Path:
    """导出勾选的审查意见为 Word 审查意见表。"""
    try:
        import docx  # noqa
        from docx.shared import Pt
    except ImportError:
        raise RuntimeError("导出 Word 需要 python-docx 库（打包环境已内置）")
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    document = docx.Document()
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("检测报告审查意见表")
    run.bold = True
    run.font.size = Pt(16)
    if project_name:
        p = document.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run("项目名称：%s" % project_name).font.size = Pt(11)

    cols = ["序号", "位置", "原文片段", "问题类型", "问题描述", "审查建议", "规范依据"]
    table = document.add_table(rows=1, cols=len(cols))
    table.style = "Table Grid"
    for i, name in enumerate(cols):
        cell = table.rows[0].cells[i]
        cell.text = name
        for par in cell.paragraphs:
            for r in par.runs:
                r.bold = True
    for idx, c in enumerate(candidates, 1):
        row = table.add_row().cells
        row[0].text = str(idx)
        row[1].text = c.get("location") or ""
        row[2].text = c.get("excerpt") or ""
        row[3].text = c.get("category") or ""
        row[4].text = c.get("description") or ""
        row[5].text = c.get("suggestion") or ""
        row[6].text = c.get("basis") or "（未匹配到规范条文）"

    out = Path(output_path)
    document.save(str(out))
    return out
