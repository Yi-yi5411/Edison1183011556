# -*- coding: utf-8 -*-
"""规范文件导入编排：选择文件 → 解析 → 入库。

DB 全量重建或按规范增量追加均可；code/code_name 可由文件名自动拆分，
GUI 弹窗中允许人工确认修改。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from .parser import parse_file_to_clauses, split_file_code
from .store import (ClauseRecord, append_records, build_from_records,
                    db_status, get_db_path)

SUPPORTED_SUFFIX = (".md", ".markdown", ".txt", ".docx")


def plan_import(file_paths, code_overrides: Optional[Dict[str, Dict]] = None
                ) -> List[Dict]:
    """解析文件（不入库），返回 [{file, code, code_name, count, records, error}]。

    code_overrides: {文件名: {"code": .., "code_name": ..}} 人工确认后覆盖。
    """
    overrides = code_overrides or {}
    plans = []
    for fp in file_paths:
        p = Path(fp)
        entry = {"file": str(p), "code": "", "code_name": "",
                 "count": 0, "records": [], "error": ""}
        try:
            auto_code, auto_name = split_file_code(p.name)
            ov = overrides.get(p.name) or {}
            entry["code"] = (ov.get("code") or "").strip() or auto_code
            name_val = ov.get("code_name")
            if isinstance(name_val, str) and name_val.strip():
                entry["code_name"] = name_val.strip()
            else:
                entry["code_name"] = auto_name
            records = parse_file_to_clauses(p, entry["code"], entry["code_name"])
            entry["records"] = records
            entry["count"] = len(records)
            if not records:
                entry["error"] = "未解析出任何条文（检查标题格式）"
        except Exception as e:
            entry["error"] = str(e)
        plans.append(entry)
    return plans


def import_files(file_paths, mode: str = "append",
                 code_overrides: Optional[Dict[str, Dict]] = None,
                 on_log: Optional[Callable[[str], None]] = None) -> Dict:
    """导入规范文件入库。

    mode: "append"=按规范追加（同 code+chapter 覆盖），
          "rebuild"=全量重建（先清空所有已导入规范）。
    返回 {"total", "imported", "files": [{file, code, count, error}]}。
    """
    log = on_log or (lambda msg: None)
    plans = plan_import(file_paths, code_overrides)
    records: List[ClauseRecord] = []
    for entry in plans:
        if entry["error"]:
            log("跳过 %s：%s" % (Path(entry["file"]).name, entry["error"]))
            continue
        log("解析 %s：%s %s，%d 条条文" % (
            Path(entry["file"]).name, entry["code"],
            entry["code_name"], entry["count"]))
        records.extend(entry["records"])

    if not records:
        return {"total": db_status()["total"], "imported": 0,
                "files": [{k: entry[k] for k in ("file", "code", "count",
                                                 "error")} for entry in plans]}

    db_path = get_db_path()
    if mode == "rebuild":
        total = build_from_records(db_path, records)
        log("全量重建：%d 条条文入库" % total)
    else:
        total = append_records(db_path, records)
        log("增量导入完成，库内共 %d 条条文" % total)

    return {"total": total, "imported": len(records),
            "files": [{k: entry[k] for k in ("file", "code", "count", "error")}
                      for entry in plans]}
