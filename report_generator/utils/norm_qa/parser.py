# -*- coding: utf-8 -*-
"""规范文件解析：Markdown / Txt / Docx → ClauseRecord 列表。

解析约定（沿用 Civil_check）：
1. Markdown：以三级标题「### 条号 标题」为一条条款；正文为该标题到下一个
   标题之间的文本；「<!-- tags: 4.2.2, 4.2.3 -->」使正文同时归属多个条号。
2. Txt / Docx：以条号行开头为一条条款（"5.1.2 条文标题" 或 "第5.1.2条 ..."），
   正文为该行到下一个条号行之间。
3. 章节路径：Markdown 用 H1/H2 组成 "H1 / H2"；Txt 用最近的章/节标题行。
4. 规范代号：从文件名按第一个空格拆分
   （"GB55001-2021 工程结构通用规范.md" → code + code_name）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .store import ClauseRecord

# ── Markdown 约定正则 ──
RE_CLAUSE_HEADING = re.compile(r"^###\s+([\d.\s、,]+)\s*(.*)$")       # ### 2.1.1 标题
RE_TAGS = re.compile(r"<!--\s*tags:\s*([\d.\s,、]+)\s*-->")            # 多条款归属
RE_SINGLE_CLAUSE = re.compile(r"\d{1,2}\.\d{1,2}(?:\.\d{1,2})?")      # x.y / x.y.z
RE_H1 = re.compile(r"^#\s+(.+)$")
RE_H2 = re.compile(r"^##\s+(.+)$")

# ── Txt / Docx 条号行 ──
RE_TXT_CLAUSE_LINE = re.compile(
    r"^(?:第)?(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?:条)?[\s、,，:：]?\s*(.*)$")
RE_TXT_HEADING = re.compile(r"^第?[一二三四五六七八九十\d]{1,3}[章节篇]\s*[、.:：\s]?\s*(.*)$")


def split_file_code(filename: str) -> Tuple[str, str]:
    """文件名按第一个空格拆为 (code, code_name)。

    "JGJ 23-2011 回弹法检测混凝土抗压强度技术规程.md"
    → ("JGJ", "23-2011 回弹法检测混凝土抗压强度技术规程")
    注意：仅按"文件名不含扩展名"处理，空格拆分可能不理想，
    导入时允许调用方覆盖（GUI 中可编辑确认）。
    """
    stem = Path(filename).stem.strip()
    parts = stem.split(" ", 1)
    code = parts[0] if parts and parts[0] else stem
    code_name = parts[1].strip() if len(parts) > 1 else ""
    return code, code_name


def parse_text_to_clauses(text: str, code: str, code_name: str,
                          source_file: str = "",
                          fmt: str = "md") -> List[ClauseRecord]:
    """将一篇规范文本解析为条款列表（fmt: "md" 或 "txt"）。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if fmt == "md":
        return _parse_md_lines(lines, code, code_name, source_file)
    return _parse_txt_lines(lines, code, code_name, source_file)


def parse_file_to_clauses(file_path, code: str = "", code_name: str = ""
                          ) -> List[ClauseRecord]:
    """按扩展名读取文件并解析为条款列表。

    .md/.markdown → Markdown 约定；.txt → 条号行约定；
    .docx → python-docx 读段落后按条号行约定（未安装 python-docx 时抛异常）。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        fmt = "md"
    elif suffix in (".txt",):
        text = path.read_text(encoding="utf-8", errors="ignore")
        fmt = "txt"
    elif suffix in (".docx",):
        text = _read_docx_paragraphs(path)
        fmt = "txt"
    else:
        raise ValueError("不支持的规范文件格式：%s（支持 md/txt/docx）" % suffix)

    if not code:
        auto_code, auto_name = split_file_code(path.name)
        code = auto_code
        if not code_name:
            code_name = auto_name
    return parse_text_to_clauses(text, code, code_name, path.name, fmt)


def _read_docx_paragraphs(path) -> str:
    """用 python-docx 读出全部段落文本（延迟导入，缺失时报可读错误）。"""
    try:
        import docx  # noqa
    except ImportError:
        raise RuntimeError(
            "读取 docx 需要 python-docx 库（打包环境已内置）；"
            "源码环境请 pip install python-docx，或改用 txt/markdown 文件")
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _parse_tags(body: str) -> Tuple[List[str], str]:
    match = RE_TAGS.search(body)
    if not match:
        return [], body
    clauses = list(dict.fromkeys(RE_SINGLE_CLAUSE.findall(match.group(1))))
    return clauses, RE_TAGS.sub("", body).strip()


def _clause_nums(clause_part: str) -> List[str]:
    nums = list(dict.fromkeys(RE_SINGLE_CLAUSE.findall(clause_part)))
    return nums or [clause_part.split("、")[0].split(",")[0].strip()]


def _parse_md_lines(lines, code, code_name, source_file) -> List[ClauseRecord]:
    """Markdown 解析：### 条号行 + H1/H2 章节路径 + tags 多归属。"""
    clauses: List[ClauseRecord] = []
    cur_h1 = cur_h2 = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        h1 = RE_H1.match(line)
        if h1:
            cur_h1, cur_h2 = h1.group(1).strip(), ""
            i += 1
            continue
        h2 = RE_H2.match(line)
        if h2:
            cur_h2 = h2.group(1).strip()
            i += 1
            continue
        cm = RE_CLAUSE_HEADING.match(line)
        if cm:
            title = cm.group(2).strip()
            body_lines = []
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("#"):
                body_lines.append(lines[j])
                j += 1
            body = "\n".join(body_lines).strip()
            tag_clauses, body = _parse_tags(body)
            if cur_h1 and cur_h2:
                chapter_path = "%s / %s" % (cur_h1, cur_h2)
            else:
                chapter_path = cur_h2 or cur_h1 or None
            for ch in (tag_clauses or _clause_nums(cm.group(1))):
                if ch:
                    clauses.append(ClauseRecord(
                        code=code, chapter=ch, title=title, body=body,
                        code_name=code_name or None, chapter_path=chapter_path,
                        source_file=source_file))
            i = j
            continue
        i += 1
    return clauses


def _parse_txt_lines(lines, code, code_name, source_file) -> List[ClauseRecord]:
    """Txt/Docx 解析：条号行开头为一条条款，章/节标题行进章节路径。"""
    clauses: List[ClauseRecord] = []
    cur_path = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        hm = RE_TXT_HEADING.match(line)
        if hm and not RE_TXT_CLAUSE_LINE.match(line):
            cur_path = line.strip()
            i += 1
            continue
        cm = RE_TXT_CLAUSE_LINE.match(line)
        if cm:
            chapter = cm.group(1)
            title = cm.group(2).strip()
            body_lines = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and (RE_TXT_CLAUSE_LINE.match(nxt)
                            or (RE_TXT_HEADING.match(nxt)
                                and not RE_TXT_CLAUSE_LINE.match(nxt))):
                    break
                body_lines.append(lines[j])
                j += 1
            body = "\n".join(body_lines).strip()
            tag_clauses, body = _parse_tags(body)
            for ch in (tag_clauses or [chapter]):
                clauses.append(ClauseRecord(
                    code=code, chapter=ch, title=title, body=body,
                    code_name=code_name or None, chapter_path=cur_path or None,
                    source_file=source_file))
            i = j
            continue
        i += 1
    return clauses
