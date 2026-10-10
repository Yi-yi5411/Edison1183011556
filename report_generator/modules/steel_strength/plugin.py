# -*- coding: utf-8 -*-
"""钢结构钢材强度检测（硬度法）插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class SteelStrengthPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "steel_strength"

    @property
    def display_name(self):
        return "钢结构钢材强度检测（硬度法）"

    @property
    def structure_type(self):
        return "钢结构"

    @property
    def tree_order(self):
        return 10

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
