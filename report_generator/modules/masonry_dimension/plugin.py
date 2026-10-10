# -*- coding: utf-8 -*-
"""砖混结构砌体构件尺寸偏差检测插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class MasonryDimensionPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "masonry_dimension"

    @property
    def display_name(self):
        return "砌体构件尺寸偏差检测"

    @property
    def structure_type(self):
        return "砖混结构"

    @property
    def tree_order(self):
        return 30

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
