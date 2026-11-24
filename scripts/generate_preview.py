# -*- coding: utf-8 -*-
"""生成“预览稿”：跳过正式报告预检，但不占用设备、不写入报告历史。

用法：python scripts/generate_preview.py
输出：data/previews/draft_<时间>/检测报告_预览稿.docx + .pdf
"""
import json
import os
import sys
import time
import urllib.parse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(ROOT, "report_generator"), os.path.join(ROOT, "report_generator", "libs"), ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Pt, RGBColor  # noqa: E402
from core.app_controller import AppController  # noqa: E402
from report_generator.utils.word_report import generate_report  # noqa: E402
from report_generator.utils.equipment_store import preview_equipment_for_report  # noqa: E402

BASE = "http://127.0.0.1:8765"


def get_json(path):
    response = requests.get(BASE + path, timeout=30)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("message") or path)
    return body.get("data")


def mark_draft(docx_path):
    """在页眉加红色“预览稿”，避免被当成正式报告。"""
    doc = Document(docx_path)
    seen = set()
    for section in doc.sections:
        header = section.header
        # linked header 继承前一节，只改第一节即可；未链接的节单独加
        key = id(header._element)
        if key in seen:
            continue
        seen.add(key)
        paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        paragraph.text = "预览稿 · 非正式报告（未通过报告预检）"
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for run in paragraph.runs:
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    doc.core_properties.title = "检测报告（预览稿）"
    doc.core_properties.comments = "预览稿：跳过正式报告预检，不作为正式报告使用。"
    doc.save(docx_path)


def main():
    state = get_json("/api/project")
    info = get_json("/api/report/info")
    sheets = state.get("sheets") or {}
    sheet_data = {key: (value.get("rows") or []) for key, value in sheets.items()}
    checked = [key for key in (state.get("checked_items") or []) if key in sheet_data]
    if not checked:
        raise RuntimeError("当前工程没有可生成报告的检测项")
    controller = AppController()
    columns_map = {
        key: (sheets.get(key) or {}).get("columns") or controller.get_columns(key)
        for key in sheet_data
    }
    assessments = (state.get("assessment") or {}).get("results") or {}
    equipment = preview_equipment_for_report(checked)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "data", "previews", "draft_" + stamp)
    os.makedirs(out_dir, exist_ok=True)
    docx_path = os.path.join(out_dir, "检测报告_预览稿.docx")
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
    mark_draft(docx_path)
    preview_url = "/api/report/preview?filepath=" + urllib.parse.quote(docx_path, safe="")
    print(json.dumps({
        "ok": True,
        "filepath": docx_path,
        "preview_url": preview_url,
        "checked": checked,
        "warnings": result.get("warnings") or [],
        "skipped": result.get("skipped") or [],
        "equipment": len(equipment or []),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
