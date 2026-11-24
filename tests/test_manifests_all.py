# -*- coding: utf-8 -*-
"""全部检测项目 manifest 的批量回归：与 Python 插件逐字段对齐 + 技能可生成。

覆盖 16 份 manifest（15 份由 tools/build_manifests.py 生成，concrete_strength 手写），
carbonation 按设计隐藏不生成。

运行：python test_manifests_all.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from core.plugin_manager import get_plugin_manager  # noqa: E402
from structural_items import describe_item, discover, export_skills  # noqa: E402
from structural_items.schema import SLUG_RE  # noqa: E402
from tools.build_manifests import main as build_main  # noqa: E402
from utils.assessment_specs import ASSESSMENT_SPECS  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


def main():
    entries = discover(force=True)
    ok_entries = [e for e in entries if not e["errors"]]
    check("manifest 数量 >= 16", len(entries) >= 16, len(entries))
    check("全部 manifest 校验通过", len(ok_entries) == len(entries),
          [e["plugin_id"] for e in entries if e["errors"]])

    pm = get_plugin_manager()
    specs = {s.get("id"): s for s in ASSESSMENT_SPECS}
    slugs = {}
    total_items = 0
    template_checked = 0

    for entry in ok_entries:
        data = entry["data"]
        plugin_id = data.get("id")
        dir_name = os.path.basename(os.path.dirname(entry["path"]))
        check("%s 目录名与 id 一致" % plugin_id, plugin_id == dir_name,
              [plugin_id, dir_name])

        source = data.get("source", "python")
        if source != "python":
            continue
        plugin = pm.get_by_id(plugin_id)
        if plugin is None:
            check("%s 对应 Python 插件存在" % plugin_id, False)
            continue
        check("%s 树结构一致" % plugin_id,
              {i["key"]: list(i.get("components") or [])
               for i in data["items"]}
              == {k: list(v) for k, v in plugin.tree_entries().items()},
              plugin.tree_entries())

        py_columns = plugin.columns() or {}
        py_types = plugin.column_types() or {}
        py_rules = plugin.calc_rules() or {}
        for item in data["items"]:
            total_items += 1
            ckey = item.get("columns_key") or item["key"]
            label = "%s/%s" % (plugin_id, item["key"])
            check("%s 列一致" % label,
                  list(item.get("columns") or []) == list(py_columns.get(ckey) or []),
                  [len(item.get("columns") or []), len(py_columns.get(ckey) or [])])
            check("%s 列类型一致" % label,
                  list(item.get("column_types") or []) == list(py_types.get(ckey) or []),
                  None)
            check("%s 计算规则一致" % label,
                  {int(k): v for k, v in (item.get("calc_rules") or {}).items()}
                  == dict(py_rules.get(ckey) or {}),
                  list((item.get("calc_rules") or {}).keys()))

            assessment = item.get("assessment") or {}
            if assessment:
                check("%s 评定规则存在" % label,
                      assessment.get("spec") in specs,
                      assessment.get("spec"))

            skill = item.get("skill") or {}
            slug = skill.get("slug") or ""
            check("%s 技能 slug 合法" % label,
                  bool(SLUG_RE.match(slug)), slug)
            check("%s 技能 slug 全局唯一" % label, slug not in slugs,
                  slugs.get(slug))
            slugs[slug] = label

            if (item.get("original_record") or {}).get("template"):
                template_checked += 1

    check("检测项目总数 >= 29", total_items >= 29, total_items)
    check("原始记录模板映射已记录", template_checked >= 20, template_checked)

    # 契约查询：每个树键 + 带构件的键都能回到同一项目
    lookup_failures = []
    for entry in ok_entries:
        for item in entry["data"]["items"]:
            key = item["key"]
            got = describe_item(key)
            if not got or got["item"] != key:
                lookup_failures.append(key)
            for component in item.get("components") or []:
                sheet_key = "%s（%s）" % (key, component)
                got = describe_item(sheet_key)
                if not got or got["item"] != key:
                    lookup_failures.append(sheet_key)
    check("契约查询全覆盖", not lookup_failures, lookup_failures[:3])

    # 技能导出
    tmp = tempfile.mkdtemp(prefix="manifests_all_")
    try:
        paths = export_skills(tmp)
        names = [os.path.basename(os.path.dirname(p)) for p in paths]
        check("技能数量等于检测项目数", len(paths) == total_items,
              [len(paths), total_items])
        check("技能名唯一", len(set(names)) == len(names), len(names))
        bad = []
        for path in paths:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            if not text.startswith("---"):
                bad.append(os.path.basename(os.path.dirname(path)))
                continue
            if "\nname: " not in text or "\ndescription: " not in text:
                bad.append(os.path.basename(os.path.dirname(path)))
        check("技能 frontmatter 完整", not bad, bad[:3])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 生成器幂等：manifest 与插件现状一致
    check("tools.build_manifests --check 无差异", build_main(["--check"]) == 0, None)

    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
