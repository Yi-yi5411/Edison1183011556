# -*- coding: utf-8 -*-
"""钢结构涂层厚度检测（防腐/防火）插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class SteelCoatingPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "steel_coating"

    @property
    def display_name(self):
        return "钢结构涂层厚度检测"

    @property
    def structure_type(self):
        return "钢结构"

    @property
    def tree_order(self):
        return 20

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
