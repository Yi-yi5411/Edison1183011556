# -*- coding: utf-8 -*-
"""外部检测项目插件加载器。

外部插件目录结构（与内置 modules/<id>/ 一致）：

    <root>/<plugin_id>/
        plugin.json      # structural.item/1 manifest（必需）
        plugin.py        # 可选；存在时按 Python 插件加载
        helpers.py ...   # 可选；同目录模块可直接 import

调用方（PluginManager）负责把返回的插件实例注册进注册表；本模块只负责
发现、校验、导入和错误收集，不修改主框架内置插件。
"""
import importlib.util
import json
import os
import sys
import uuid

_REPORT_GEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_REPORT_GEN)          # 项目根 structural_inspection
_DEFAULT_ROOT = os.path.join(_ROOT, "plugins", "external")
_SOURCES_FILE = os.path.join(_ROOT, "data", "plugins", "sources.json")


def default_root():
    os.makedirs(_DEFAULT_ROOT, exist_ok=True)
    return _DEFAULT_ROOT


def load_sources():
    """返回去重后的外部插件根目录（默认目录 + 配置文件 + 环境变量）。"""
    roots = [default_root()]
    try:
        with open(_SOURCES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            roots.extend(str(x) for x in data if str(x).strip())
        elif isinstance(data, dict):
            roots.extend(str(x) for x in (data.get("roots") or []) if str(x).strip())
    except Exception:  # noqa: BLE001
        pass
    env = os.environ.get("STRUCTURAL_PLUGIN_DIRS", "")
    if env:
        roots.extend(x for x in env.split(os.pathsep) if x.strip())
    out = []
    seen = set()
    for path in roots:
        path = os.path.abspath(os.path.expanduser(path))
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def save_sources(roots):
    paths = []
    seen = set()
    for path in roots or []:
        path = os.path.abspath(os.path.expanduser(str(path).strip()))
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    os.makedirs(os.path.dirname(_SOURCES_FILE), exist_ok=True)
    with open(_SOURCES_FILE, "w", encoding="utf-8") as fh:
        json.dump(paths, fh, ensure_ascii=False, indent=1)
    return paths


def _read_manifest(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_python_plugin(plugin_dir, manifest_path, manifest):
    """从外部目录的 plugin.py 导入 BaseDetectionPlugin 子类。"""
    from modules.base_plugin import BaseDetectionPlugin
    plugin_file = os.path.join(plugin_dir, "plugin.py")
    if not os.path.isfile(plugin_file):
        raise RuntimeError("manifest source=python 但缺少 plugin.py")
    added = []
    for path in (plugin_dir, os.path.dirname(plugin_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)
            added.append(path)
    module_name = "structural_external_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法创建 plugin.py 导入器")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        # 保留 sys.path 以便插件运行期 import 同目录模块；模块本身留在
        # sys.modules 中，避免插件内部相对引用被回收。
        pass
    plugins = []
    for attr in dir(module):
        obj = getattr(module, attr)
        if (isinstance(obj, type)
                and issubclass(obj, BaseDetectionPlugin)
                and obj is not BaseDetectionPlugin):
            try:
                instance = obj()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("插件类 %s 实例化失败：%s" % (attr, exc))
            plugins.append(instance)
    if not plugins:
        raise RuntimeError("plugin.py 中没有 BaseDetectionPlugin 子类")
    return plugins


def scan_external_plugins(roots=None):
    """扫描外部插件目录，返回 (plugins, records)。

    plugins: [(plugin_instance, record)]；record 用于 API/UI 展示。
    单个插件失败只记录错误，不影响其他插件。
    """
    roots = load_sources() if roots is None else [os.path.abspath(p) for p in roots]
    plugins = []
    records = []
    for root in roots:
        if not os.path.isdir(root):
            records.append({
                "root": root, "path": "", "id": "", "name": "",
                "source": "external", "status": "missing",
                "errors": ["目录不存在"], "warnings": [], "plugin": None,
            })
            continue
        for name in sorted(os.listdir(root)):
            plugin_dir = os.path.join(root, name)
            if not os.path.isdir(plugin_dir):
                continue
            manifest_path = os.path.join(plugin_dir, "plugin.json")
            if not os.path.isfile(manifest_path):
                continue
            record = {
                "root": root, "path": plugin_dir, "id": "", "name": "",
                "source": "external", "status": "error",
                "errors": [], "warnings": [], "plugin": None,
            }
            try:
                from structural_items.schema import validate_manifest
                manifest = _read_manifest(manifest_path)
                errors, warnings = validate_manifest(manifest)
                record["errors"].extend(errors)
                record["warnings"].extend(warnings)
                record["id"] = str(manifest.get("id") or name)
                record["name"] = str(manifest.get("name") or "")
                if errors:
                    records.append(record)
                    continue
                source = str(manifest.get("source") or "python")
                has_py = os.path.isfile(os.path.join(plugin_dir, "plugin.py"))
                if source == "python" and has_py:
                    instances = _load_python_plugin(plugin_dir, manifest_path, manifest)
                    for instance in instances:
                        record_copy = dict(record)
                        record_copy["id"] = instance.plugin_id
                        record_copy["name"] = instance.display_name
                        record_copy["source"] = "python"
                        record_copy["status"] = "loaded"
                        record_copy["plugin"] = instance
                        plugins.append((instance, record_copy))
                        records.append(record_copy)
                elif source == "manifest":
                    from structural_items.registry import manifest_plugin
                    instance = manifest_plugin(manifest, manifest_path)
                    record["id"] = instance.plugin_id
                    record["name"] = instance.display_name
                    record["source"] = "manifest"
                    record["status"] = "loaded"
                    record["plugin"] = instance
                    plugins.append((instance, record))
                    records.append(record)
                else:
                    record["errors"].append(
                        "source=%s 但目录中没有可加载的 plugin.py" % source)
                    records.append(record)
            except Exception as exc:  # noqa: BLE001
                record["errors"].append("%s: %s" % (type(exc).__name__, exc))
                records.append(record)
    return plugins, records


def status(roots=None):
    """只读状态：根目录 + 扫描结果（不含插件对象）。"""
    roots = load_sources() if roots is None else [os.path.abspath(p) for p in roots]
    _, records = scan_external_plugins(roots)
    clean = []
    for rec in records:
        item = dict(rec)
        item.pop("plugin", None)
        clean.append(item)
    return {"roots": roots, "records": clean,
            "loaded": sum(1 for r in clean if r.get("status") == "loaded"),
            "errors": sum(1 for r in clean if r.get("status") == "error")}
