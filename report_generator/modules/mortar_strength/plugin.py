# -*- coding: utf-8 -*-
"""砖混结构砌筑砂浆强度检测（贯入法）插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class MortarStrengthPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "mortar_strength"

    @property
    def display_name(self):
        return "砌筑砂浆强度检测（贯入法）"

    @property
    def structure_type(self):
        return "砖混结构"

    @property
    def tree_order(self):
        return 10

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
