# -*- coding: utf-8 -*-
"""碳化深度 插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class CarbonationPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "carbonation"

    @property
    def display_name(self):
        return "碳化深度"

    @property
    def tree_order(self):
        return 60

    def tree_entries(self):
        # 碳化深度暂不在勾选树中展示（与原 DETECTION_DATA 注释掉该分类的行为一致）
        return {}

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
