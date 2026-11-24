# -*- coding: utf-8 -*-
"""由 manifest 生成检测项目技能（SKILL.md），供 DSH 技能目录直接加载。

生成位置默认 <项目根>/.dsh/skills/<skill-name>/SKILL.md；技能名 kebab-case，
由 manifest 的 items[].skill.slug 决定（如 structural-concrete-rebound）。
"""
import os

from structural_items.registry import PROJECT_ROOT, iter_items

SKILLS_DIR = os.path.join(PROJECT_ROOT, ".dsh", "skills")

_TOOL_HINTS = """- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
"""


def skill_name(entry, item):
    slug = str((item.get("skill") or {}).get("slug") or "").strip()
    return "structural-" + (slug or entry["plugin_id"])


def _yaml_quote(text):
    return '"%s"' % str(text or "").replace('"', "'").strip()


def _param_line(param):
    label = param.get("label") or param.get("key")
    ptype = param.get("type") or "string"
    parts = ["- %s（%s，%s" % (param.get("key"), label, ptype)]
    if param.get("required"):
        parts.append("，必填")
    if param.get("default") not in (None, ""):
        parts.append("，默认 %s" % param["default"])
    if param.get("options"):
        parts.append("，可选 %s" % " / ".join(str(o) for o in param["options"]))
    parts.append("）")
    note = param.get("note")
    if note:
        parts.append("：%s" % note)
    return "".join(parts)


def render_skill(entry, item):
    """把一条 manifest item 渲染成 SKILL.md 文本。"""
    data = entry["data"]
    key = item.get("key") or ""
    skill = item.get("skill") or {}
    collect = item.get("collect") or {}
    assessment = item.get("assessment") or {}
    report = item.get("report") or {}
    original = item.get("original_record") or {}
    columns = item.get("columns") or []
    types = item.get("column_types") or []

    description = skill.get("description") or ("%s %s 的采集、导入、评定与出报告"
                                               % (data.get("name"), key))
    when = skill.get("when_to_use") or "用户要录入、导入、评定或核对%s数据时" % key

    lines = [
        "---",
        "name: %s" % skill_name(entry, item),
        "description: %s" % _yaml_quote(description),
        "whenToUse: %s" % _yaml_quote(when),
        "---",
        "",
        "# %s · %s" % (data.get("name"), key),
        "",
    ]
    if item.get("description"):
        lines += [item["description"], ""]

    components = item.get("components") or []
    lines += ["## 构件维度", ""]
    lines.append("- " + " / ".join(components) if components else "- 无构件维度")
    sheet_keys = [(key + "（%s）" % c) if c else key for c in components] or [key]
    lines += ["- 工作表键：%s" % "、".join(sheet_keys), ""]

    lines += ["## 采集参数", ""]
    params = collect.get("params") or []
    if params:
        lines += [_param_line(p) for p in params]
    else:
        lines.append("- 无参数：直接录入或在采集页导入表格")
    layout = collect.get("layout")
    if layout:
        lines += ["", "- 表格形态：%s" % layout]
    validators = collect.get("validators") or []
    if validators:
        lines += ["- 校验：%s" % "、".join(str(v) for v in validators)]
    lines.append("")

    lines += ["## 表格列", ""]
    for index, column in enumerate(columns):
        ctype = types[index] if index < len(types) else ""
        lines.append("- %d. %s%s" % (index + 1, column,
                                     "（%s）" % ctype if ctype else ""))
    lines.append("")

    importers = collect.get("importers") or []
    if importers:
        lines += ["## 导入", ""]
        for importer in importers:
            kind = importer.get("kind")
            text = "- %s" % kind
            aliases = importer.get("header_aliases") or {}
            if aliases:
                text += "：表头别名 %s" % "、".join(
                    "%s←%s" % (k, "/".join(v)) for k, v in list(aliases.items())[:6])
            if importer.get("target"):
                text += "：扫描目标 %s" % importer["target"]
            lines.append(text)
        lines.append("")

    lines += ["## 评定", ""]
    if assessment:
        lines.append("- 规则：%s（family=%s），结论由评定引擎生成"
                     % (assessment.get("spec"), assessment.get("family") or "-"))
        if assessment.get("input"):
            lines.append("- 输入形态：%s" % assessment["input"])
    else:
        lines.append("- 该项目暂未配置评定规则")
    lines.append("- 必须调用 run_assessment，不要自行计算或编造结论")
    lines.append("")

    lines += ["## 报告与原始记录", ""]
    if report.get("chapter"):
        lines.append("- 报告章节：%s" % report["chapter"])
    if original.get("template"):
        lines.append("- 原始记录模板：%s" % original["template"])
    if item.get("equipment"):
        lines.append("- 报告设备：%s" % "、".join(item["equipment"]))
    lines.append("")

    lines += ["## 工具", "", _TOOL_HINTS.strip(), ""]
    return "\n".join(lines)


def export_skills(out_dir=None, only=()):
    """生成全部技能，返回写入的 SKILL.md 路径列表。"""
    target_root = out_dir or SKILLS_DIR
    written = []
    for entry, item in iter_items():
        if entry["errors"]:
            continue
        name = skill_name(entry, item)
        if only and name not in only:
            continue
        folder = os.path.join(target_root, name)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "SKILL.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_skill(entry, item))
        written.append(path)
    return written
