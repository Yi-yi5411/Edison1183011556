# -*- coding: utf-8 -*-
"""保护层厚度检测 插件（梁/柱/剪力墙/板，10 测点）。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class CoverThicknessPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "cover_thickness"

    @property
    def display_name(self):
        return "保护层厚度检测"

    @property
    def tree_order(self):
        return 40

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES

    def get_gui_mixins(self):
        """主窗口混入的 GUI 逻辑（保护层合格点率汇总重算）。"""
        from .handlers import CoverThicknessMixin
        return [CoverThicknessMixin]
