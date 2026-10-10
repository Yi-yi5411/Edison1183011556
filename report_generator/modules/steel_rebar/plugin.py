# -*- coding: utf-8 -*-
"""钢筋配置 插件（剪力墙/现浇板钢筋间距、梁柱受力钢筋根数）。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class SteelRebarPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "steel_rebar"

    @property
    def display_name(self):
        return "钢筋配置"

    @property
    def tree_order(self):
        return 20

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES

    def get_gui_mixins(self):
        # Rebar-spacing merge/total logic lives in the module, not in the main UI.
        from .handlers import SteelRebarMixin
        return [SteelRebarMixin]
