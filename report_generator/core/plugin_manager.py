# -*- coding: utf-8 -*-
"""插件管理器：启动时扫描 ``modules`` 目录动态发现并注册检测项目插件。

新增检测项目只需在 ``modules/<name>/`` 下新建 ``plugin.py`` 实现
``BaseDetectionPlugin``，无需修改本文件或主框架代码——主界面会自动出现
该项目的选项。

设计要点：
  - 本模块顶层仅依赖标准库，不在 import 期触发 ``modules`` 包初始化，
    以避免与 ``modules/__init__.py`` 之间的循环导入；
    ``BaseDetectionPlugin`` 在 ``discover()`` 内按需导入。
  - 通过单例 ``get_plugin_manager()`` 提供全局访问。
"""

import importlib
import os
import pkgutil


class PluginManager:
    """检测项目插件注册表。"""

    def __init__(self):
        self._by_id = {}        # plugin_id -> plugin
        self._by_name = {}      # display_name -> plugin
        self._plugins = []      # 有序列表

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
