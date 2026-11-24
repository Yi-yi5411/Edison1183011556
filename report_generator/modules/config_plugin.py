# -*- coding: utf-8 -*-
"""声明式检测项目插件：只写 JSON 即可增加列头、列类型和计算规则。

适用场景：
- 新增检测项目只需要“项目名 + 结构类型 + 列头 + 列类型 + 计算规则”；
- 不需要参数对话框、特殊建表逻辑或自定义 GUI；
- 复杂项目仍使用 modules/<name>/plugin.py 的 Python 插件。

配置目录：report_generator/modules/_configs/*.json
"""
from modules.base_plugin import BaseDetectionPlugin


class ConfigDetectionPlugin(BaseDetectionPlugin):
    """由 JSON 配置驱动的只读检测项目插件。"""

    def __init__(self, config, source=""):
        self._config = dict(config or {})
        self._source = source

    @property
    def plugin_id(self):
        return str(self._config.get("id") or "").strip()

    @property
    def display_name(self):
        return str(self._config.get("name") or "").strip()

    @property
    def structure_type(self):
        return str(self._config.get("structure_type") or "其他").strip()

    @property
    def tree_order(self):
        try:
            return int(self._config.get("tree_order") or 100)
        except (TypeError, ValueError):
            return 100

    def tree_entries(self):
        tree = self._config.get("tree")
        if isinstance(tree, dict) and tree:
            return {str(k): [str(x) for x in (v or [])]
                    for k, v in tree.items()}
        return super().tree_entries()

    def columns(self):
        value = self._config.get("columns") or {}
        return {str(k): [str(x) for x in (v or [])]
                for k, v in value.items()} if isinstance(value, dict) else {}

    def column_types(self):
        value = self._config.get("column_types") or {}
        return {str(k): list(v or [])
                for k, v in value.items()} if isinstance(value, dict) else {}

    def calc_rules(self):
        value = self._config.get("calc_rules") or {}
        if not isinstance(value, dict):
            return {}
        result = {}
        for item, mapping in value.items():
            if not isinstance(mapping, dict):
                continue
            converted = {}
            for target, rule in mapping.items():
                try:
                    target = int(target)
                except (TypeError, ValueError):
                    target = str(target)
                converted[target] = rule
            result[str(item)] = converted
        return result

    def required_instruments(self):
        value = self._config.get("equipment") or []
        if isinstance(value, str):
            value = [value]
        return [str(x).strip() for x in value if str(x).strip()]

    def requires_setup_dialog(self, sub_item):
        return bool(self._config.get("requires_setup"))

    def source(self):
        return self._source
