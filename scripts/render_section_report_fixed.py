# -*- coding: utf-8 -*-
"""一次性：用修复后的结果表列映射重渲染当前工程报告（不重启后端）。"""
import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(ROOT, "report_generator"),
             os.path.join(ROOT, "report_generator", "libs"), ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from report_generator.utils.word_report import generate_report  # noqa: E402
from report_generator.utils.equipment_store import preview_equipment_for_report  # noqa: E402

BASE = "http://127.0.0.1:8765"


def get_json(path):
    resp = requests.get(BASE + path, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("message") or path)
    return body.get("data")


def main():
    state = get_json("/api/project")
    info = get_json("/api/report/info")
    sheets = state.get("sheets") or {}
    sheet_data = {key: (value.get("rows") or []) for key, value in sheets.items()}
    columns_map = {key: (value.get("columns") or []) for key, value in sheets.items()}
    checked = [key for key in (state.get("checked_items") or []) if key in sheet_data]
    assessments = (state.get("assessment") or {}).get("results") or {}
    equipment = preview_equipment_for_report(checked)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "report_generator", "exports", "section_fix_" + stamp)
    os.makedirs(out_dir, exist_ok=True)
    docx_path = os.path.join(out_dir, "检测报告.docx")
    result = generate_report(
        state.get("project_name") or info.get("project_name") or "未命名工程",
        info,
        sheet_data,
        columns_map,
        checked,
        docx_path,
        assessment_results=assessments,
        equipment=equipment,
    )
    result["filepath"] = docx_path
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
