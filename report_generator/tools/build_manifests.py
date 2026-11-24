# -*- coding: utf-8 -*-
"""把现有 Python 插件的契约导出为 structural.item/1 manifest。

用法（在 report_generator 目录下执行）：
    python -m tools.build_manifests --check    # 只比对，不写文件
    python -m tools.build_manifests            # 写 modules/<id>/plugin.json

约定：
- 手写 manifest（concrete_strength）默认不覆盖，除非 --force；
- 树中隐藏的插件（carbonation）不生成；
- 生成结果由 test_manifest_smoke.py 逐字段回归（树/列/列类型/计算规则）。
"""
import json
import os
import sys

if __name__ == "__main__":
    _here = os.path.dirname(os.path.abspath(__file__))
    _report_gen = os.path.dirname(_here)
    for _path in (os.path.join(_report_gen, "libs"), _report_gen,
                  os.path.dirname(_report_gen)):
        if _path not in sys.path:
            sys.path.insert(0, _path)

from core.plugin_manager import get_plugin_manager  # noqa: E402
from structural_items.equipment import lookup as _equipment_lookup  # noqa: E402
from structural_items.schema import MANIFEST_NAME, SCHEMA_ID  # noqa: E402
from utils.assessment_specs import ASSESSMENT_SPECS  # noqa: E402
from utils.original_record_templates import match_builtin_template  # noqa: E402
from utils.report_narrative import equipment_for  # noqa: E402

SKIP_PLUGINS = {"carbonation"}
HAND_WRITTEN = {"concrete_strength"}

# 技能 slug：kebab-case，全局唯一；键为 (plugin_id, 树中的检测项目名)
SLUGS = {
    ("anchor_bearing", "化学植筋锚固承载力检测"): "anchor-bearing",
    ("brick_strength", "砖强度检测"): "brick-strength",
    ("concrete_members", "楼板构件厚度检测"): "slab-thickness",
    ("concrete_members", "剪力墙厚度检测"): "wall-thickness",
    ("concrete_members", "混凝土梁结构尺寸检测"): "beam-section",
    ("concrete_members", "混凝土柱结构尺寸检测"): "column-section",
    ("cover_thickness", "混凝土梁保护层厚度检测"): "cover-beam",
    ("cover_thickness", "混凝土柱保护层厚度检测"): "cover-column",
    ("cover_thickness", "剪力墙保护层厚度检测"): "cover-wall",
    ("cover_thickness", "混凝土板保护层厚度检测"): "cover-slab",
    ("masonry_dimension", "砌体构件尺寸偏差检测"): "masonry-dimension",
    ("mortar_strength", "砌筑砂浆强度检测"): "mortar-strength",
    ("steel_bolt", "高强度螺栓扭矩系数检测"): "steel-bolt-torque",
    ("steel_coating", "防腐涂层厚度检测"): "coating-anti-corrosion",
    ("steel_coating", "防火涂层厚度检测"): "coating-fireproof",
    ("steel_rebar", "剪力墙构件钢筋间距检测"): "rebar-spacing-wall",
    ("steel_rebar", "现浇板钢筋间距检测"): "rebar-spacing-slab",
    ("steel_rebar", "梁构件底排受力钢筋根数检测"): "rebar-count-beam",
    ("steel_rebar", "柱构件主要受力钢筋根数检测"): "rebar-count-column",
    ("steel_rebar", "剪力墙钢筋根数检测"): "rebar-count-wall",
    ("steel_strength", "钢材强度检测"): "steel-strength",
    ("steel_weld", "焊缝超声波探伤检测"): "steel-weld-ut",
    ("wood_defect", "木构件缺陷检测"): "wood-defect",
    ("wood_deflection", "木构件挠度检测"): "wood-deflection",
    ("wood_dimension", "木构件尺寸偏差检测"): "wood-dimension",
    ("wood_moisture", "木材含水率检测"): "wood-moisture",
}

# Web 端已有的参数对话框（Python 插件未声明，但界面确实要参数）
SETUP_PARAMS = {
    "砖强度检测": [
        {"key": "batch", "label": "批次", "type": "string", "default": "1"},
        {"key": "components", "label": "构件数", "type": "int",
         "required": True, "default": 10, "min": 1, "max": 200},
        {"key": "zones_per_component", "label": "每构件测区数", "type": "int",
         "required": True, "default": 10, "min": 1, "max": 50},
    ],
}


def _strip(text):
    base = str(text or "")
    for sep in ("（", "("):
        if sep in base:
            base = base.split(sep)[0]
    return base.strip()


def _resolve_columns_key(plugin, tree_key):
    columns = plugin.columns() or {}
    if tree_key in columns:
        return tree_key
    stripped = _strip(tree_key)
    if stripped in columns:
        return stripped
    for key in columns:
        if stripped.startswith(key) or key.startswith(stripped):
            return key
    return tree_key


def _assessment_for(item_name):
    for spec in ASSESSMENT_SPECS:
        for base in spec.get("base_items") or []:
            if base and (base == item_name or base.startswith(item_name)
                         or item_name.startswith(base)):
                return {"spec": spec.get("id"),
                        "family": spec.get("family"),
                        "input": "raw_components" if spec.get("family") in
                                 ("rebound", "rebound_core") else "sheet_rows"}
    return None


def _template_for(item_name):
    try:
        found = match_builtin_template(item_name) or {}
    except Exception:  # noqa: BLE001
        return {}
    template_id = found.get("id") or ""
    return {"template": template_id} if template_id else {}


def _describe(plugin, item_name):
    """生成不重复的项目说明与技能文案（插件名可能等于或包含项目名）。"""
    if item_name == plugin.display_name:
        item_text = "%s：录入或导入检测数据，按规范评定并生成报告与原始记录。" % item_name
        skill_text = "%s：数据采集、按规范评定、生成报告与原始记录。" % item_name
    else:
        item_text = ("%s · %s：录入或导入检测数据，按规范评定并生成报告与原始记录。"
                     % (plugin.display_name, item_name))
        skill_text = ("%s · %s：数据采集、按规范评定、生成报告与原始记录。"
                      % (plugin.display_name, item_name))
    return item_text, skill_text


def _equipment_for(item_name):
    """manifest 设备名：先查项目级显式映射，未覆盖时回退 report_narrative。"""
    mapped = _equipment_lookup(item_name)
    if mapped is not None:
        return mapped
    try:
        names = [entry.get("设备名称") for entry in equipment_for([item_name])]
    except Exception:  # noqa: BLE001
        return []
    return [name for name in names if name]


def build_manifest(plugin):
    items = []
    for tree_key, components in (plugin.tree_entries() or {}).items():
        columns_key = _resolve_columns_key(plugin, tree_key)
        columns = list((plugin.columns() or {}).get(columns_key) or [])
        types = list((plugin.column_types() or {}).get(columns_key) or [])
        rules = (plugin.calc_rules() or {}).get(columns_key) or {}
        slug = SLUGS.get((plugin.plugin_id, tree_key))
        if not slug:
            raise SystemExit("缺少技能 slug：%s / %s（请补 SLUGS）"
                             % (plugin.plugin_id, tree_key))
        params = list(SETUP_PARAMS.get(tree_key) or [])
        item = {
            "key": tree_key,
            "columns_key": columns_key,
            "family": (_assessment_for(columns_key) or {}).get("family") or "",
            "description": _describe(plugin, tree_key)[0],
            "components": list(components or []),
            "columns": columns,
            "column_types": types,
            "calc_rules": {str(target): rule for target, rule in rules.items()},
            "collect": {
                "params": params,
                "layout": "components_x_zones" if components else "records",
                "entry": "setup_dialog" if params else "grid",
                "importers": [
                    {"kind": "excel"},
                    {"kind": "word_table", "anchor": tree_key},
                ],
            },
            "equipment": _equipment_for(columns_key),
            "original_record": _template_for(columns_key),
            "report": {"chapter": "四、检测内容", "result_group": tree_key},
            "skill": {
                "slug": slug,
                "description": _describe(plugin, tree_key)[1],
                "when_to_use": "用户要采集、导入、评定或核对「%s」数据时。" % tree_key,
            },
        }
        assessment = _assessment_for(columns_key)
        if assessment:
            item["assessment"] = assessment
        if not item["family"]:
            item.pop("family")
        items.append(item)

    return {
        "schema": SCHEMA_ID,
        "id": plugin.plugin_id,
        "name": plugin.display_name,
        "structure_type": plugin.structure_type,
        "tree_order": int(plugin.tree_order),
        "source": "python",
        "items": items,
    }


def render(manifest):
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in argv
    force = "--force" in argv
    modules_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "modules")

    changed = []
    written = []
    same = 0
    skipped = []
    for plugin in get_plugin_manager().all_plugins():
        if plugin.plugin_id in SKIP_PLUGINS:
            skipped.append((plugin.plugin_id, "树中隐藏"))
            continue
        if plugin.plugin_id in HAND_WRITTEN and not force:
            skipped.append((plugin.plugin_id, "手写 manifest，保留"))
            continue
        target = os.path.join(modules_dir, plugin.plugin_id, MANIFEST_NAME)
        text = render(build_manifest(plugin))
        current = ""
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8") as fh:
                current = fh.read()
        if current == text:
            same += 1
            continue
        changed.append(plugin.plugin_id)
        if not check_only:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(text)
            written.append(target)

    for plugin_id, reason in skipped:
        print("SKIP %s（%s）" % (plugin_id, reason))
    print("一致 %d 个，变化 %d 个%s"
          % (same, len(changed),
             "" if check_only else "，已写入 %d 个" % len(written)))
    if changed:
        print("变化：%s" % "、".join(changed))
    if check_only and changed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
