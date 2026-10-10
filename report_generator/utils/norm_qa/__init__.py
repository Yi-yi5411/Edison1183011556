# -*- coding: utf-8 -*-
"""规范条文问答检索子包（移植自 Civil_check 检索核心思路）。

链路：规范 Markdown/Txt/Docx → parser 解析条文 → store 建 SQLite FTS5
→ engine 检索（条号精确命中 / 自然语言 FTS+LIKE 降级 / 术语候选）
→ llm 本地 Ollama 生成中文解释。

子包不引入任何第三方依赖（docx 读取延迟导入），py3.8 源环境安全。
"""

from .store import ClauseRecord, get_db_path, init_schema, build_from_records
from .parser import parse_text_to_clauses, parse_file_to_clauses, split_file_code
from .engine import NormQueryEngine
from .ingest import import_files, db_status
from .llm import explain_clauses
from .batch_review import (attach_norm_basis, chunk_text, extract_candidates,
                           extract_text, export_review_docx, run_batch_review)

__all__ = [
    "ClauseRecord", "get_db_path", "init_schema", "build_from_records",
    "parse_text_to_clauses", "parse_file_to_clauses", "split_file_code",
    "NormQueryEngine", "import_files", "db_status", "explain_clauses",
    "run_batch_review", "extract_text", "chunk_text", "extract_candidates",
    "attach_norm_basis", "export_review_docx",
]
