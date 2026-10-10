# -*- coding: utf-8 -*-
"""混凝土构件 插件（楼板/剪力墙厚度、梁柱结构尺寸）。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class ConcreteMembersPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "concrete_members"

    @property
    def display_name(self):
        return "混凝土构件"

    @property
    def tree_order(self):
        return 30

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES

    def get_gui_mixins(self):
        """主窗口混入的 GUI 逻辑（厚度汇总重算）。"""
        from .handlers import MemberThicknessMixin
        return [MemberThicknessMixin]
