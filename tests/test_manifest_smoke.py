# -*- coding: utf-8 -*-
"""检测项目 manifest 冒烟（P3 试点）：schema、与 Python 插件逐字段对齐、契约查询、技能生成。

运行：python test_manifest_smoke.py
只读：不写工程、不调后端；技能生成写到临时目录。
"""
import os
import shutil
import sys
import tempfile
try:  # 控制台/重定向可能是 cp936，统一按 UTF-8 输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

import structural_items  # noqa: E402
from structural_items import describe_item, discover, find_item  # noqa: E402
from structural_items import __main__ as cli  # noqa: E402
from structural_items.registry import manifest_plugin  # noqa: E402
from structural_items.skills import export_skills, render_skill  # noqa: E402
from structural_items.schema import validate_manifest  # noqa: E402

from modules.concrete_strength.plugin import ConcreteStrengthPlugin  # noqa: E402
from utils.assessment_specs import ASSESSMENT_SPECS  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


def main():
    entries = discover(force=True)
    check("发现 manifest", len(entries) >= 1,
          [os.path.basename(e["path"]) for e in entries])
    by_id = {e["plugin_id"]: e for e in entries}
    entry = by_id.get("concrete_strength")
    check("concrete_strength manifest 存在", entry is not None, sorted(by_id))
    if entry is None:
        return 1
    data = entry["data"]
    check("manifest 校验无错误", not entry["errors"], entry["errors"])

    # 1. 与 Python 插件逐字段对齐
    plugin = ConcreteStrengthPlugin()
    items = data["items"]
    check("检测项目数量一致", len(items) == len(plugin.tree_entries()),
          [len(items), len(plugin.tree_entries())])
    check("树结构一致",
          {i["key"]: list(i["components"]) for i in items}
          == {k: list(v) for k, v in plugin.tree_entries().items()},
          plugin.tree_entries())

    py_columns = plugin.columns()
    py_types = plugin.column_types()
    py_rules = plugin.calc_rules()
    for item in items:
        ckey = item.get("columns_key") or item["key"]
        label = item["key"]
        check("%s 列定义一致" % label,
              item["columns"] == list(py_columns.get(ckey) or []),
              [len(item["columns"]), len(py_columns.get(ckey) or [])])
        check("%s 列类型一致" % label,
              item["column_types"] == list(py_types.get(ckey) or []),
              py_types.get(ckey))
        check("%s 计算规则一致" % label,
              {int(k): v for k, v in (item.get("calc_rules") or {}).items()}
              == dict(py_rules.get(ckey) or {}),
              py_rules.get(ckey))

    # 2. 纯 manifest 插件等价性
    generated = manifest_plugin(data, entry["path"])
    check("ManifestPlugin 插件 id", generated.plugin_id == "concrete_strength",
          generated.plugin_id)
    check("ManifestPlugin 树一致",
          generated.tree_entries() == plugin.tree_entries(),
          generated.tree_entries())
    check("ManifestPlugin 列一致",
          generated.columns() == plugin.columns())
    check("ManifestPlugin 设备并集",
          generated.required_instruments()
          == ["混凝土回弹仪", "微控电液伺服压力试验机", "游标卡尺"],
          generated.required_instruments())

    # 3. 评定规则存在
    spec_ids = {s.get("id") for s in ASSESSMENT_SPECS}
    missing = [i["key"] for i in items
               if (i.get("assessment") or {}).get("spec") not in spec_ids]
    check("评定规则 id 均存在", not missing, missing)

    # 4. 契约查询（含工作表键解析）
    core = describe_item("钻芯法检测")
    check("describe_item 返回钻芯契约", core is not None
          and core["plugin_id"] == "concrete_strength", core and core["item"])
    param_keys = [p["key"] for p in (core["collect"].get("params") or [])]
    check("钻芯采集参数齐全",
          {"building", "components", "diameter"} <= set(param_keys), param_keys)
    check("钻芯工作表键带构件",
          core["sheet_keys"][0] == "钻芯法检测（梁）", core["sheet_keys"][:2])
    rebound = describe_item("回弹法检测（墙）")
    check("带构件后缀也能解析", rebound is not None
          and rebound["item"].startswith("回弹法检测"), rebound and rebound["item"])
    check("未知项目返回 None", find_item("不存在的检测项目") is None)

    # 5. 技能渲染与导出
    skill_texts = []
    for item in items:
        text = render_skill(entry, item)
        skill_texts.append(text)
        lines = text.splitlines()
        check("%s 技能有 frontmatter" % item["key"],
              lines[0] == "---" and any(l.startswith("name: ") for l in lines),
              lines[:3])
        name = [l for l in lines if l.startswith("name: ")][0].split(":", 1)[1].strip()
        check("%s 技能名 kebab-case" % item["key"],
              name.startswith("structural-")
              and all(c.islower() or c.isdigit() or c == "-" for c in name),
              name)
        check("%s 技能含关键章节" % item["key"],
              all(h in text for h in ("## 采集参数", "## 评定", "## 工具", "## 表格列")),
              None)
    check("三个技能名互不相同", len({t.splitlines()[1] for t in skill_texts}) == 3,
          None)

    tmp = tempfile.mkdtemp(prefix="manifest_skills_")
    try:
        only = {t.splitlines()[1].split(":", 1)[1].strip() for t in skill_texts}
        paths = export_skills(tmp, only=only)
        check("技能导出 3 个 SKILL.md", len(paths) == 3,
              [os.path.basename(os.path.dirname(p)) for p in paths])
        check("技能文件落在 <name>/SKILL.md",
              all(os.path.basename(p) == "SKILL.md" for p in paths), paths[:1])
        def _read_all(items):
            return {os.path.basename(os.path.dirname(p)):
                    open(p, "r", encoding="utf-8").read() for p in items}

        first = _read_all(paths)
        second = _read_all(export_skills(tmp, only=only))
        check("重复导出内容稳定", first == second,
              [len(first), len(second)])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 6. schema 拒绝坏 manifest
    bad_cases = {
        "缺 schema": {"id": "x", "name": "x", "structure_type": "x", "items": []},
        "未知顶层字段": dict(data, unknown_key=1),
        "列类型长度不一致": {
            "schema": "structural.item/1", "id": "x", "name": "x",
            "structure_type": "x", "items": [{
                "key": "k", "columns": ["a", "b"], "column_types": ["string"],
                "equipment": []}]},
        "calc_rules 越界": {
            "schema": "structural.item/1", "id": "x", "name": "x",
            "structure_type": "x", "items": [{
                "key": "k", "columns": ["a"], "equipment": [],
                "calc_rules": {"5": {"type": "avg"}}}]},
        "skill slug 非 kebab": {
            "schema": "structural.item/1", "id": "x", "name": "x",
            "structure_type": "x", "items": [{
                "key": "k", "columns": ["a"], "equipment": [],
                "skill": {"slug": "Bad_Slug", "description": "d"}}]},
    }
    for label, payload in bad_cases.items():
        errors, _warnings = validate_manifest(payload)
        check("schema 拒绝：%s" % label, bool(errors), errors[:1])

    # 6b. 纯 manifest 插件可被插件管理器发现；source=python 不覆盖 Python 插件
    import json
    from core.plugin_manager import PluginManager
    from structural_items.registry import MODULES_DIR

    tmp_modules = tempfile.mkdtemp(prefix="manifest_mods_")
    try:
        demo_dir = os.path.join(tmp_modules, "demo_item")
        os.makedirs(demo_dir)
        demo = {
            "schema": "structural.item/1",
            "id": "demo_item",
            "name": "演示检测项目",
            "structure_type": "其他",
            "tree_order": 200,
            "source": "manifest",
            "items": [{
                "key": "演示检测",
                "columns": ["编号", "实测值"],
                "column_types": ["string", "float"],
                "calc_rules": {"1": {"type": "avg", "sources": [0]}},
                "components": [],
                "equipment": ["演示仪器"],
                "skill": {"slug": "demo-item", "description": "演示用"},
            }],
        }
        with open(os.path.join(demo_dir, "plugin.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(demo, fh, ensure_ascii=False)

        pm = PluginManager()
        pm._discover_manifests(tmp_modules)
        plugin = pm.get_by_id("demo_item")
        check("纯 manifest 插件被发现", plugin is not None, pm.all_plugins())
        if plugin is not None:
            check("纯 manifest 插件列一致",
                  plugin.columns() == {"演示检测": ["编号", "实测值"]},
                  plugin.columns())
            check("纯 manifest 插件树与设备",
                  plugin.tree_entries() == {"演示检测": []}
                  and plugin.required_instruments() == ["演示仪器"],
                  [plugin.tree_entries(), plugin.required_instruments()])
    finally:
        shutil.rmtree(tmp_modules, ignore_errors=True)

    pm2 = PluginManager()
    pm2._discover_manifests(MODULES_DIR)
    check("source=python 的 manifest 不会被注册为插件",
          pm2.get_by_id("concrete_strength") is None, pm2.all_plugins())

    # 7. CLI
    check("CLI validate 通过", cli.main(["validate"]) == 0, None)
    check("CLI describe 返回 0", cli.main(["describe", "钻芯法检测"]) == 0, None)

    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
