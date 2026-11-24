# -*- coding: utf-8 -*-
"""检测项目 manifest 的 schema 定义与校验（纯数据，无 Qt / FastAPI 依赖）。

manifest 文件名固定为 modules/<plugin_id>/plugin.json，schema 标识为
structural.item/1。它把原先散落在 6 个位置的「检测项目契约」收到一处：

    plugin.py        → id / name / structure_type / tree_order / components
    columns.py       → columns / column_types
    calc_rules.py    → calc_rules
    dialogs.py       → collect.params（采集参数）
    assessment_specs → assessment.spec / family
    report_narrative → equipment / report.chapter
    prompt/NN-*.md   → skill（可加载的技能说明）

Python 插件仍是运行时权威（source="python"）；manifest 是唯一的事实描述，
供工具、技能生成与校验使用。source="manifest" 表示该项目完全由 manifest 驱动。
"""
import re

SCHEMA_ID = "structural.item/1"
MANIFEST_NAME = "plugin.json"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

TOP_KEYS = {"schema", "id", "name", "structure_type", "tree_order", "source",
            "items"}
ITEM_KEYS = {"key", "columns_key", "family", "components", "columns",
             "column_types", "calc_rules", "collect", "assessment",
             "equipment", "original_record", "report", "skill", "description"}
COLLECT_KEYS = {"params", "layout", "entry", "validators", "importers"}
PARAM_KEYS = {"key", "label", "type", "required", "default", "options",
              "note", "min", "max"}
PARAM_TYPES = {"string", "int", "float", "bool", "enum"}
IMPORTER_KINDS = {"excel", "csv", "word_table", "scan"}
LAYOUTS = {"records", "components_x_samples", "components_x_zones", "auto"}

SOURCE_PYTHON = "python"
SOURCE_MANIFEST = "manifest"
SOURCES = {SOURCE_PYTHON, SOURCE_MANIFEST}


def _is_str(value):
    return isinstance(value, str) and bool(value.strip())


def validate_manifest(data, strict=True):
    """校验一份 manifest，返回 (errors, warnings)；errors 为空表示可用。"""
    errors = []
    warnings = []
    if not isinstance(data, dict):
        return ["manifest 必须是 JSON 对象"], warnings

    if data.get("schema") != SCHEMA_ID:
        errors.append("schema 必须是 %s，当前 %r"
                      % (SCHEMA_ID, data.get("schema")))
    unknown = set(data) - TOP_KEYS
    if unknown:
        (errors if strict else warnings).append(
            "未知的顶层字段：%s" % "、".join(sorted(unknown)))

    if not _is_str(data.get("id")):
        errors.append("id 不能为空")
    elif not ID_RE.match(data["id"]):
        errors.append("id 只能是小写字母/数字/下划线：%r" % data["id"])
    if not _is_str(data.get("name")):
        errors.append("name 不能为空")
    if not _is_str(data.get("structure_type")):
        errors.append("structure_type 不能为空")
    order = data.get("tree_order", 100)
    if not isinstance(order, int):
        errors.append("tree_order 必须是整数")
    source = data.get("source", SOURCE_PYTHON)
    if source not in SOURCES:
        errors.append("source 只能是 %s" % " / ".join(sorted(SOURCES)))

    items = data.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items 必须是非空数组")
        return errors, warnings

    seen_keys = set()
    slugs = {}
    for index, item in enumerate(items):
        prefix = "items[%d]" % index
        if not isinstance(item, dict):
            errors.append("%s 必须是对象" % prefix)
            continue
        unknown = set(item) - ITEM_KEYS
        if unknown:
            warnings.append("%s 未知字段：%s" % (prefix, "、".join(sorted(unknown))))

        key = item.get("key")
        if not _is_str(key):
            errors.append("%s.key 不能为空" % prefix)
            continue
        if key in seen_keys:
            errors.append("%s.key 重复：%s" % (prefix, key))
        seen_keys.add(key)
        label = "%s(%s)" % (prefix, key)

        columns = item.get("columns")
        if not isinstance(columns, list) or not columns:
            errors.append("%s.columns 必须是非空数组" % label)
            columns = []
        elif not all(_is_str(c) for c in columns):
            errors.append("%s.columns 只能包含非空字符串" % label)
        if len(set(columns)) != len(columns):
            errors.append("%s.columns 存在重复列名" % label)

        types = item.get("column_types")
        if types is not None:
            if not isinstance(types, list):
                errors.append("%s.column_types 必须是数组" % label)
            elif columns and len(types) != len(columns):
                errors.append("%s.column_types 长度 %d 与 columns %d 不一致"
                              % (label, len(types), len(columns)))

        components = item.get("components", [])
        if not isinstance(components, list):
            errors.append("%s.components 必须是数组" % label)

        rules = item.get("calc_rules")
        if rules is not None:
            if not isinstance(rules, dict):
                errors.append("%s.calc_rules 必须是对象" % label)
            else:
                for target, rule in rules.items():
                    try:
                        target_index = int(target)
                    except (TypeError, ValueError):
                        errors.append("%s.calc_rules 的键必须是列序号：%r"
                                      % (label, target))
                        continue
                    if columns and not (0 <= target_index < len(columns)):
                        errors.append("%s.calc_rules 列序号越界：%s"
                                      % (label, target))
                    if not isinstance(rule, dict) or not _is_str(rule.get("type")):
                        errors.append("%s.calc_rules[%s] 缺少 type"
                                      % (label, target))

        collect = item.get("collect")
        if collect is not None:
            if not isinstance(collect, dict):
                errors.append("%s.collect 必须是对象" % label)
            else:
                unknown = set(collect) - COLLECT_KEYS
                if unknown:
                    warnings.append("%s.collect 未知字段：%s"
                                    % (label, "、".join(sorted(unknown))))
                layout = collect.get("layout")
                if layout is not None and layout not in LAYOUTS:
                    warnings.append("%s.collect.layout 未知：%r（可选 %s）"
                                    % (label, layout,
                                       " / ".join(sorted(LAYOUTS))))
                params = collect.get("params")
                if params is not None:
                    if not isinstance(params, list):
                        errors.append("%s.collect.params 必须是数组" % label)
                    else:
                        seen = set()
                        for p_index, param in enumerate(params):
                            p_prefix = "%s.collect.params[%d]" % (label, p_index)
                            if not isinstance(param, dict):
                                errors.append("%s 必须是对象" % p_prefix)
                                continue
                            pkey = param.get("key")
                            if not _is_str(pkey):
                                errors.append("%s.key 不能为空" % p_prefix)
                            elif pkey in seen:
                                errors.append("%s.key 重复：%s" % (p_prefix, pkey))
                            else:
                                seen.add(pkey)
                            ptype = param.get("type", "string")
                            if ptype not in PARAM_TYPES:
                                errors.append("%s.type 未知：%r"
                                              % (p_prefix, ptype))
                            if ptype == "enum" and not param.get("options"):
                                errors.append("%s.type=enum 需要 options"
                                              % p_prefix)
                            unknown = set(param) - PARAM_KEYS
                            if unknown:
                                warnings.append("%s 未知字段：%s"
                                                % (p_prefix, "、".join(sorted(unknown))))
                importers = collect.get("importers")
                if importers is not None:
                    if not isinstance(importers, list):
                        errors.append("%s.collect.importers 必须是数组" % label)
                    else:
                        for importer in importers:
                            kind = (importer or {}).get("kind")
                            if kind not in IMPORTER_KINDS:
                                errors.append(
                                    "%s.collect.importers.kind 未知：%r（可选 %s）"
                                    % (label, kind,
                                       " / ".join(sorted(IMPORTER_KINDS))))

        assessment = item.get("assessment")
        if assessment is not None:
            if not isinstance(assessment, dict):
                errors.append("%s.assessment 必须是对象" % label)
            elif not _is_str(assessment.get("spec")):
                errors.append("%s.assessment.spec 不能为空" % label)

        equipment = item.get("equipment", [])
        if not isinstance(equipment, list) or not all(_is_str(e) for e in equipment):
            errors.append("%s.equipment 必须是非空字符串数组" % label)

        skill = item.get("skill")
        if skill is not None:
            if not isinstance(skill, dict):
                errors.append("%s.skill 必须是对象" % label)
            else:
                slug = str(skill.get("slug") or "")
                if not slug:
                    errors.append("%s.skill.slug 不能为空（用于生成技能名）" % label)
                elif not SLUG_RE.match(slug):
                    errors.append("%s.skill.slug 必须是 kebab-case：%r"
                                  % (label, slug))
                if not _is_str(skill.get("description")):
                    errors.append("%s.skill.description 不能为空" % label)
                if slug and slug in slugs:
                    errors.append("%s.skill.slug 与 %s 重复：%s"
                                  % (label, slugs[slug], slug))
                elif slug:
                    slugs[slug] = label

    return errors, warnings
