# -*- coding: utf-8 -*-
"""manifest 发现、查询与「纯 manifest 插件」构造。"""
import json
import os

from structural_items.schema import (MANIFEST_NAME, SOURCE_MANIFEST,
                                     SOURCE_PYTHON, validate_manifest)

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(PACKAGE_DIR, "modules")
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)

_cache = None


def discover(modules_dir=None, force=False):
    """扫描 modules/*/plugin.json，返回 [{path, plugin_id, data, errors, warnings}]。"""
    global _cache
    if modules_dir is None and _cache is not None and not force:
        return _cache
    root = modules_dir or MODULES_DIR
    found = []
    if not os.path.isdir(root):
        return found
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, MANIFEST_NAME)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:  # noqa: BLE001
            found.append({"path": path, "plugin_id": name, "data": {},
                          "errors": ["读取失败：%s" % e], "warnings": []})
            continue
        errors, warnings = validate_manifest(data)
        plugin_id = str(data.get("id") or name)
        if plugin_id != name:
            warnings.append("manifest id=%r 与目录名 %r 不一致" % (plugin_id, name))
        found.append({"path": path, "plugin_id": plugin_id, "data": data,
                      "errors": errors, "warnings": warnings})
    if modules_dir is None:
        _cache = found
    return found


def reload():
    return discover(force=True)


def all_manifests():
    return discover()


def manifest_for(plugin_id):
    for entry in discover():
        if entry["plugin_id"] == plugin_id and not entry["errors"]:
            return entry
    return None


def iter_items():
    for entry in discover():
        if entry["errors"]:
            continue
        for item in entry["data"].get("items") or []:
            yield entry, item


def _strip(text):
    base = str(text or "")
    for sep in ("（", "("):
        if sep in base:
            base = base.split(sep)[0]
    return base.strip()


def find_item(item_name):
    """按 工作表键 / 检测项目名 / 列名键 找 (manifest, item)。"""
    name = str(item_name or "").strip()
    if not name:
        return None
    stripped = _strip(name)
    exact = []
    fuzzy = []
    for entry, item in iter_items():
        key = str(item.get("key") or "")
        columns_key = str(item.get("columns_key") or key)
        if name == key or name == columns_key or stripped in (key, columns_key):
            exact.append((entry, item))
        elif key and (name.startswith(key) or key.startswith(stripped)):
            fuzzy.append((entry, item))
        elif columns_key and name.startswith(columns_key):
            fuzzy.append((entry, item))
    if exact:
        return exact[0]
    if fuzzy:
        return fuzzy[0]
    return None


def describe_item(item_name):
    """把某个检测项目的完整契约摊平成可返回给前端的字典。"""
    found = find_item(item_name)
    if not found:
        return None
    entry, item = found
    data = entry["data"]
    key = item.get("key") or ""
    return {
        "plugin_id": data.get("id"),
        "plugin_name": data.get("name"),
        "structure_type": data.get("structure_type"),
        "source": data.get("source", SOURCE_PYTHON),
        "manifest_path": entry["path"],
        "item": key,
        "columns_key": item.get("columns_key") or key,
        "components": list(item.get("components") or []),
        "sheet_keys": ([(key + "（%s）" % c) if c else key
                        for c in (item.get("components") or [])] or [key]),
        "columns": list(item.get("columns") or []),
        "column_types": list(item.get("column_types") or []),
        "calc_rules": dict(item.get("calc_rules") or {}),
        "collect": dict(item.get("collect") or {}),
        "assessment": dict(item.get("assessment") or {}),
        "equipment": list(item.get("equipment") or []),
        "original_record": dict(item.get("original_record") or {}),
        "report": dict(item.get("report") or {}),
        "skill": dict(item.get("skill") or {}),
        "description": item.get("description") or "",
    }


def manifest_plugin(data, source_path=""):
    """把 source=manifest 的 manifest 变成 BaseDetectionPlugin 实例。

    source=python 的项目仍由 Python 插件提供列与计算，本函数只用于纯 manifest 项目
    或校验「manifest 与 Python 插件是否等价」。
    """
    from modules.base_plugin import BaseDetectionPlugin

    class ManifestDetectionPlugin(BaseDetectionPlugin):
        def __init__(self, manifest, source):
            self._manifest = manifest
            self._source = source

        def _items(self):
            return self._manifest.get("items") or []

        @staticmethod
        def _columns_key(item):
            return item.get("columns_key") or item.get("key") or ""

        @property
        def plugin_id(self):
            return self._manifest.get("id") or ""

        @property
        def display_name(self):
            return self._manifest.get("name") or ""

        @property
        def structure_type(self):
            return self._manifest.get("structure_type") or "其他"

        @property
        def tree_order(self):
            try:
                return int(self._manifest.get("tree_order") or 100)
            except (TypeError, ValueError):
                return 100

        def tree_entries(self):
            return {item["key"]: list(item.get("components") or [])
                    for item in self._items() if item.get("key")}

        def columns(self):
            return {self._columns_key(item): list(item.get("columns") or [])
                    for item in self._items()}

        def column_types(self):
            return {self._columns_key(item): list(item.get("column_types") or [])
                    for item in self._items() if item.get("column_types")}

        def calc_rules(self):
            out = {}
            for item in self._items():
                rules = {}
                for target, rule in (item.get("calc_rules") or {}).items():
                    try:
                        target = int(target)
                    except (TypeError, ValueError):
                        pass
                    rules[target] = rule
                out[self._columns_key(item)] = rules
            return out

        def required_instruments(self):
            names = []
            for item in self._items():
                for name in item.get("equipment") or []:
                    if name not in names:
                        names.append(name)
            return names

        def source(self):
            return self._source

    plugin = ManifestDetectionPlugin(data, source_path)
    plugin.__class__.__name__ = "ManifestDetectionPlugin"
    return plugin
