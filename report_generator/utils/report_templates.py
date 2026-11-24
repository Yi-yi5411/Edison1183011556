# -*- coding: utf-8 -*-
"""检测报告模板集合（纯数据/纯函数，无 Qt 依赖）。

一个模板集合 = 一个根目录 + 8 个章节 docx 相对路径 + 若干“结果一览表”映射。
内置集合直接复用 report_template/ 与 report_template_map.py 中的常量；
导入集合从模板包的 manifest.json 构造。

本模块只负责“模板在哪里、结果表怎么配”，不负责文件上传/数据库等
Web 侧逻辑（见 utils/template_library.py）。
"""
from pathlib import Path

try:
    from report_generator.utils.report_template_map import (
        CHAPTER_TEMPLATES,
        SHEET_TEMPLATE_MAP,
        TEMPLATE_DIR,
    )
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_template_map import (
        CHAPTER_TEMPLATES,
        SHEET_TEMPLATE_MAP,
        TEMPLATE_DIR,
    )


SCHEMA = "report_template_v1"
REQUIRED_CHAPTERS = (
    "cover_main",
    "cover_home",
    "overview",
    "basis",
    "equipment",
    "content",
    "result_intro",
    "conclusion",
)
CHAPTER_LABELS = {
    "cover_main": "封面（基准文档）",
    "cover_home": "首页/目录",
    "overview": "一、工程概况",
    "basis": "二、主要检测依据",
    "equipment": "三、主要检测设备",
    "content": "四、检测内容",
    "result_intro": "五、检测结果概述",
    "conclusion": "六、检测结论",
}


def _safe_rel(rel):
    """把 manifest 中的相对路径规范化为安全形式（禁止绝对路径与 ..）。"""
    text = str(rel or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("模板路径不允许包含 ..：%s" % rel)
    return "/".join(parts)


class ReportTemplateSet(object):
    """一份可生成报告的模板集合。"""

    def __init__(self, root, chapters, result_tables, name="", template_id=""):
        self.root = Path(root)
        self.chapters = {}
        for key, value in (chapters or {}).items():
            rel = _safe_rel(value)
            if rel:
                self.chapters[str(key)] = rel
        self.result_tables = {}
        for item in result_tables or []:
            if not isinstance(item, dict):
                continue
            base = str(item.get("base") or "").strip()
            rel = _safe_rel(item.get("file"))
            if not base or not rel:
                continue
            comp = item.get("component")
            comp = None if comp in (None, "", "null") else str(comp).strip()
            try:
                header_rows = int(item.get("header_rows", 1) or 1)
            except (TypeError, ValueError):
                header_rows = 1
            aliases = item.get("aliases") or {}
            if not isinstance(aliases, dict):
                aliases = {}
            self.result_tables[(base, comp)] = {
                "base": base,
                "component": comp,
                "file": rel,
                "header_rows": max(0, min(header_rows, 5)),
                "aliases": aliases,
            }
        self.name = name or "标准检测报告模板"
        self.template_id = template_id or "builtin_standard"

    # ── 查询 ──
    def chapter_path(self, key):
        """章节 key → 绝对路径。缺失时抛 KeyError（由调用方转中文提示）。"""
        rel = self.chapters.get(str(key))
        if not rel:
            raise KeyError("报告模板缺少章节：%s" % key)
        return self.root / rel

    def result_entry(self, base, component=None):
        """按 (基础项目名, 构件) 取结果表配置；无构件时回退 (base, None)。"""
        entry = self.result_tables.get((base, component))
        if entry is None:
            entry = self.result_tables.get((base, None))
        return entry

    def result_path(self, entry):
        return self.root / entry["file"]

    def missing_chapters(self):
        """返回缺失的章节描述列表（生成前强校验）。"""
        missing = []
        for key in REQUIRED_CHAPTERS:
            rel = self.chapters.get(key)
            if not rel:
                missing.append("缺少章节：%s" % CHAPTER_LABELS.get(key, key))
            elif not (self.root / rel).is_file():
                missing.append("章节文件不存在：%s" % rel)
        return missing

    def missing_files(self):
        """返回缺失的章节/结果表描述列表（用于模板库 available 标记）。"""
        missing = []
        for key in REQUIRED_CHAPTERS:
            rel = self.chapters.get(key)
            if not rel:
                missing.append("缺少章节：%s" % CHAPTER_LABELS.get(key, key))
            elif not (self.root / rel).is_file():
                missing.append("章节文件不存在：%s" % rel)
        for entry in self.result_tables.values():
            if not (self.root / entry["file"]).is_file():
                missing.append("结果表文件不存在：%s" % entry["file"])
        return missing

    def to_manifest(self, description=""):
        """导出为 manifest dict（写入模板包/数据库）。"""
        return {
            "schema": SCHEMA,
            "name": self.name,
            "description": description or "",
            "chapters": dict(self.chapters),
            "result_tables": [
                {
                    "base": e["base"],
                    "component": e["component"],
                    "file": e["file"],
                    "header_rows": e["header_rows"],
                    "aliases": e["aliases"],
                }
                for e in self.result_tables.values()
            ],
        }

    # ── 构造 ──
    @classmethod
    def builtin(cls):
        """用项目现有 report_template/ 常量构造内置模板集合。"""
        entries = []
        for (base, comp), value in SHEET_TEMPLATE_MAP.items():
            rel_name, header_rows, aliases = value
            entries.append({
                "base": base,
                "component": comp,
                "file": rel_name,
                "header_rows": header_rows,
                "aliases": aliases or {},
            })
        return cls(TEMPLATE_DIR, CHAPTER_TEMPLATES, entries,
                   name="标准检测报告模板", template_id="builtin_standard")

    @classmethod
    def from_manifest(cls, root, manifest, template_id="", name=""):
        manifest = dict(manifest or {})
        return cls(
            root,
            manifest.get("chapters") or {},
            manifest.get("result_tables") or [],
            name=name or manifest.get("name") or "",
            template_id=template_id,
        )


def build_builtin_manifest(description="系统内置标准检测报告模板"):
    """生成内置模板的 manifest（模板库种子使用）。"""
    manifest = ReportTemplateSet.builtin().to_manifest(description)
    manifest["name"] = "标准检测报告模板"
    return manifest


def validate_manifest(manifest):
    """校验 manifest 基本结构；返回中文错误消息，合法时返回 None。

    只做结构/键校验，文件存在性与 docx 有效性由模板库导入流程检查。
    """
    if not isinstance(manifest, dict):
        return "manifest.json 必须是对象"
    if manifest.get("schema") and manifest.get("schema") != SCHEMA:
        return "不支持的模板包版本：%s（应为 %s）" % (
            manifest.get("schema"), SCHEMA)
    chapters = manifest.get("chapters")
    if not isinstance(chapters, dict):
        return "manifest.json 缺少 chapters 对象"
    missing = [key for key in REQUIRED_CHAPTERS
               if not str(chapters.get(key) or "").strip()]
    if missing:
        labels = "、".join(CHAPTER_LABELS.get(k, k) for k in missing)
        return "模板包缺少章节：%s" % labels
    tables = manifest.get("result_tables")
    if tables is None:
        tables = []
    if not isinstance(tables, list):
        return "manifest.json 的 result_tables 必须是数组"
    for i, item in enumerate(tables):
        if not isinstance(item, dict):
            return "result_tables 第 %d 项不是对象" % (i + 1)
        if not str(item.get("base") or "").strip():
            return "result_tables 第 %d 项缺少 base" % (i + 1)
        if not str(item.get("file") or "").strip():
            return "result_tables 第 %d 项缺少 file" % (i + 1)
    return None
