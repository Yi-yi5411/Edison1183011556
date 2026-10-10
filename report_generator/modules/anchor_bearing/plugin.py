# -*- coding: utf-8 -*-
"""化学植筋锚固承载力检测 插件。"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class AnchorBearingPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "anchor_bearing"

    @property
    def display_name(self):
        return "化学植筋锚固承载力检测"

    @property
    def tree_order(self):
        return 50

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES
