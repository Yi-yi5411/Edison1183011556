# -*- coding: utf-8 -*-
"""钢结构高强度螺栓连接副检测插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class SteelBoltPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "steel_bolt"

    @property
    def display_name(self):
        return "钢结构高强度螺栓连接副检测"

    @property
    def structure_type(self):
        return "钢结构"

    @property
    def tree_order(self):
        return 40

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
