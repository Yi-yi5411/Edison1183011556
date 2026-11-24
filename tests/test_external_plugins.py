# -*- coding: utf-8 -*-
"""外部插件加载器冒烟：manifest 插件可发现，坏 manifest 不阻塞其他插件。"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from core.external_plugin_loader import scan_external_plugins  # noqa: E402

MANIFEST = {
    "schema": "structural.item/1",
    "id": "external_smoke",
    "name": "外部冒烟检测",
    "structure_type": "其他",
    "tree_order": 999,
    "source": "manifest",
    "items": [{
        "key": "外部冒烟检测",
        "columns": ["构件名称", "检测值"],
        "column_types": ["string", "float"],
        "components": [],
        "equipment": [],
    }],
}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        good = os.path.join(tmp, "external_smoke")
        os.makedirs(good)
        with open(os.path.join(good, "plugin.json"), "w", encoding="utf-8") as fh:
            json.dump(MANIFEST, fh, ensure_ascii=False)
        bad = os.path.join(tmp, "broken_plugin")
        os.makedirs(bad)
        with open(os.path.join(bad, "plugin.json"), "w", encoding="utf-8") as fh:
            json.dump({"schema": "wrong"}, fh)
        plugins, records = scan_external_plugins([tmp])
        assert any(p.plugin_id == "external_smoke" for p, _ in plugins), records
        assert any(r.get("status") == "error" for r in records), records
        print("PASS 外部 manifest 插件加载")
        print("PASS 坏 manifest 被记录且不阻断")
        print("SUMMARY", len(plugins), "loaded,", sum(1 for r in records if r.get("status") == "error"), "errors")


if __name__ == "__main__":
    main()
