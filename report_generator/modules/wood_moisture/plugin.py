# -*- coding: utf-8 -*-
"""木结构木材含水率检测插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class WoodMoisturePlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "wood_moisture"

    @property
    def display_name(self):
        return "木结构木材含水率检测"

    @property
    def structure_type(self):
        return "木结构"

    @property
    def tree_order(self):
        return 10

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
