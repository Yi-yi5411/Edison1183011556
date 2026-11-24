# -*- coding: utf-8 -*-
"""插件管理器：启动时扫描 ``modules`` 目录动态发现并注册检测项目插件。

新增检测项目有两种方式：
1. 纯配置：在 ``modules/_configs/`` 放一个 JSON（列头/列类型/计算规则）；
2. 复杂项目：在 ``modules/<name>/`` 新建 ``plugin.py`` 实现
   ``BaseDetectionPlugin``。
两种方式都无需修改主框架代码。

设计要点：
  - 本模块顶层仅依赖标准库，不在 import 期触发 ``modules`` 包初始化，
    以避免与 ``modules/__init__.py`` 之间的循环导入；
    ``BaseDetectionPlugin`` 在 ``discover()`` 内按需导入。
  - 通过单例 ``get_plugin_manager()`` 提供全局访问。
"""

import importlib
import json
import os
import pkgutil


class PluginManager:
    """检测项目插件注册表。"""

    def __init__(self):
        self._by_id = {}        # plugin_id -> plugin
        self._by_name = {}      # display_name -> plugin
        self._plugins = []      # 有序列表
        self.external_records = []  # 外部插件扫描/加载记录（含错误）

    # ── 发现与注册 ──
    def discover(self, modules_pkg="modules"):
        """扫描 modules 包下所有子包，导入其 plugin 模块并注册插件。"""
        # 按需导入基类，避免与 modules/__init__ 循环
        from modules.base_plugin import BaseDetectionPlugin

        import modules as _mod_pkg
        pkg_path = os.path.dirname(_mod_pkg.__file__)
        for _, name, ispkg in pkgutil.iter_modules([pkg_path]):
            if not ispkg:
                continue
            try:
                mod = importlib.import_module(f"{modules_pkg}.{name}.plugin")
            except ModuleNotFoundError:
                continue  # 该子包尚未提供 plugin.py
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (isinstance(obj, type)
                        and issubclass(obj, BaseDetectionPlugin)
                        and obj is not BaseDetectionPlugin):
                    self.register(obj())
        self._discover_configs(pkg_path)
        self._discover_manifests(pkg_path)
        self._discover_external()

    def _discover_configs(self, pkg_path):
        """发现 modules/_configs/*.json 声明式检测项目。"""
        from modules.config_plugin import ConfigDetectionPlugin
        config_dir = os.path.join(pkg_path, "_configs")
        if not os.path.isdir(config_dir):
            return
        for filename in sorted(os.listdir(config_dir)):
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.join(config_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                plugin = ConfigDetectionPlugin(data, source=path)
                if plugin.plugin_id and plugin.display_name and plugin.columns():
                    self.register(plugin)
            except Exception:  # noqa: BLE001 - 单个配置失败不影响其它插件
                continue

    def _discover_manifests(self, pkg_path):
        """发现只有 plugin.json、没有 plugin.py 的纯 manifest 插件。

        已在 Python 插件里注册过的 id 不覆盖；只有 source="manifest" 才会注册，
        保证「Python 插件是运行时权威」这条约定不被打破。
        """
        try:
            from structural_items import discover as _discover
            from structural_items.registry import manifest_plugin
        except ImportError:  # 老部署没有 structural_items 包时静默跳过
            return
        try:
            entries = _discover(modules_dir=pkg_path)
        except Exception:  # noqa: BLE001 - manifest 解析失败不影响其它插件
            return
        for entry in entries:
            if entry.get("errors"):
                continue
            data = entry.get("data") or {}
            if data.get("source") != "manifest":
                continue
            plugin_id = entry.get("plugin_id") or data.get("id")
            if not plugin_id or plugin_id in self._by_id:
                continue
            try:
                plugin = manifest_plugin(data, entry.get("path") or "")
            except Exception:  # noqa: BLE001
                continue
            if plugin.plugin_id and plugin.display_name and plugin.columns():
                self.register(plugin)

    def _discover_external(self):
        """加载外部插件目录（默认 plugins/external + data/plugins/sources.json）。"""
        try:
            from core.external_plugin_loader import scan_external_plugins
        except ImportError:  # noqa: F401 - 兼容以 report_generator 为根的导入
            try:
                from report_generator.core.external_plugin_loader import (
                    scan_external_plugins,
                )
            except ImportError:
                return
        try:
            plugins, records = scan_external_plugins()
        except Exception as exc:  # noqa: BLE001
            self.external_records = [{
                "id": "", "name": "", "source": "external",
                "status": "error", "errors": [str(exc)],
                "warnings": [], "root": "", "path": "",
            }]
            return
        self.external_records = []
        for instance, record in plugins:
            rec = dict(record)
            rec.pop("plugin", None)
            if instance.plugin_id in self._by_id:
                rec["status"] = "error"
                rec["errors"] = list(rec.get("errors") or [])
                rec["errors"].append("插件 id 与已加载插件冲突：%s" % instance.plugin_id)
                self.external_records.append(rec)
                continue
            self.register(instance)
            rec["status"] = "loaded"
            self.external_records.append(rec)
        # 扫描失败的记录（没有 plugin 实例）也要保留给 UI
        for record in records:
            if record.get("plugin") is None:
                rec = dict(record)
                rec.pop("plugin", None)
                self.external_records.append(rec)

    def external_status(self):
        """外部插件根目录 + 加载记录（不含 Python 对象）。"""
        try:
            from core.external_plugin_loader import load_sources
        except ImportError:
            try:
                from report_generator.core.external_plugin_loader import load_sources
            except ImportError:
                load_sources = lambda: []
        records = []
        for rec in self.external_records:
            item = dict(rec)
            item.pop("plugin", None)
            records.append(item)
        return {
            "roots": load_sources(),
            "records": records,
            "loaded": sum(1 for r in records if r.get("status") == "loaded"),
            "errors": sum(1 for r in records if r.get("status") == "error"),
        }

    def reload(self):
        """重新发现全部插件（内置 + 外部），用于外部插件热加载。"""
        with_lock = getattr(self, "_reload_lock", None)
        if with_lock is not None:
            with_lock.acquire()
        try:
            self._by_id.clear()
            self._by_name.clear()
            self._plugins.clear()
            self.external_records = []
            self.discover()
        finally:
            if with_lock is not None:
                with_lock.release()

    def source_of(self, plugin_id):
        for record in self.external_records:
            if record.get("id") == plugin_id and record.get("status") == "loaded":
                return "external"
        return "builtin"

    def register(self, plugin):
        """注册一个插件实例（重复 id 将被忽略）。"""
        pid = plugin.plugin_id
        if pid in self._by_id:
            return
        self._by_id[pid] = plugin
        self._by_name[plugin.display_name] = plugin
        self._plugins.append(plugin)

    # ── 查询 ──
    def all_plugins(self):
        return list(self._plugins)

    def get_by_id(self, plugin_id):
        return self._by_id.get(plugin_id)

    def get_by_name(self, display_name):
        return self._by_name.get(display_name)

    def get_plugin_for_item(self, item_name):
        """根据检测项名定位所属插件。

        item_name 可能是 '子检测项'、'子检测项（构件类别）' 或
        '检测项目-构件类别' 形式；先按展示名精确匹配，再按子项名精确
        匹配，然后去掉构件后缀按子项名匹配，最后按展示名模糊匹配。
        """
        if not item_name:
            return None
        # 1. 展示名精确匹配
        if item_name in self._by_name:
            return self._by_name[item_name]
        # 2. 按子项名精确匹配（兼容项目名自带'（说明）'后缀的情况）
        for p in self._plugins:
            if item_name in p.get_sub_items():
                return p
        # 3. 去掉构件后缀（兼容 'sub（comp）' 与 'sub-comp' 两种格式）
        base = item_name
        for sep in ("（", "-"):
            if sep in base:
                base = base.split(sep)[0]
                break
        # 4. 按子项名匹配
        for p in self._plugins:
            if base in p.get_sub_items():
                return p
        # 5. 展示名互含模糊匹配
        for p in self._plugins:
            if p.display_name in item_name or item_name in p.display_name:
                return p
        return None

    # ── 聚合数据（替代原 modules/__init__.py 的硬编码聚合）──
    def aggregated_item_columns(self):
        d = {}
        for p in self._plugins:
            d.update(p.columns())
        return d

    def aggregated_column_types(self):
        d = {}
        for p in self._plugins:
            d.update(p.column_types())
        return d

    def aggregated_calc_rules(self):
        d = {}
        for p in self._plugins:
            d.update(p.calc_rules())
        return d

    # ── 勾选树聚合（替代原 framework/models/detection_data.py 的硬编码树）──
    # 结构类型排序：混凝土 → 钢结构 → 木结构 → 砖混 → 其他新类型（按出现顺序）。
    _STRUCTURE_ORDER = ("混凝土结构", "钢结构", "木结构", "砖混结构")

    def _structure_sort_key(self, plugin):
        try:
            s_idx = self._STRUCTURE_ORDER.index(plugin.structure_type)
        except ValueError:
            s_idx = len(self._STRUCTURE_ORDER)
        return (s_idx, plugin.tree_order, plugin.plugin_id)

    def aggregated_detection_data(self):
        """聚合各插件声明的树目录：{类别: {项目名: [构件, ...]}}。

        按结构类型 → tree_order 排序；插件 tree_entries 返回空字典时
        不在树中展示。
        """
        data = {}
        for p in sorted(self._plugins, key=self._structure_sort_key):
            entries = p.tree_entries()
            if entries:
                data[p.display_name] = entries
        return data

    def detection_data_for_structure(self, structure_type):
        """聚合指定结构类型的树目录（用于各结构类型专属录入界面）。

        structure_type 取插件 structure_type 值（混凝土结构/钢结构/
        木结构/砖混结构…）；无匹配插件时返回空字典。
        """
        data = {}
        for p in sorted(self._plugins, key=self._structure_sort_key):
            if p.structure_type != structure_type:
                continue
            entries = p.tree_entries()
            if entries:
                data[p.display_name] = entries
        return data

    # ── GUI 混入聚合（主窗口构建时调用）──
    def all_gui_mixins(self):
        """收集所有插件声明的 GUI Mixin 类（按插件顺序）。"""
        mixins = []
        for p in self._plugins:
            for m in p.get_gui_mixins():
                if m not in mixins:
                    mixins.append(m)
        return mixins


# ── 模块级单例 ──
_manager = None


def get_plugin_manager():
    global _manager
    if _manager is None:
        _manager = PluginManager()
        _manager.discover()
    return _manager
