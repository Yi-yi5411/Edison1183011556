# -*- coding: utf-8 -*-
"""混凝土抗压强度检测 插件。

涵盖回弹法 / 钻芯法 / 回弹钻芯修正法。钻芯法的专属 GUI 逻辑通过
``get_gui_mixins`` 暴露给主窗口混入。
"""
from modules.base_plugin import BaseDetectionPlugin

from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class ConcreteStrengthPlugin(BaseDetectionPlugin):
    @property
    def plugin_id(self):
        return "concrete_strength"

    @property
    def display_name(self):
        return "混凝土抗压强度检测"

    @property
    def tree_order(self):
        return 10

    def tree_entries(self):
        # 回弹法项目名带说明后缀，且带构件维度，需精确声明树结构
        return {
            '回弹法检测(主要来源为仪器数据，可选用)': ['梁', '墙', '柱', '基础'],
            '钻芯法检测': ['梁', '柱', '板', '剪力墙', '基础'],
            '回弹钻芯修正法检测': ['梁', '柱', '板', '剪力墙', '基础'],
        }

    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES

    def get_gui_mixins(self):
        # 钻芯法检测的表格构建 / 合并 / 自动计算 / 批推定逻辑
        from .handlers import CoreDrillingMixin
        return [CoreDrillingMixin]

    def requires_setup_dialog(self, sub_item):
        # 钻芯法检测/回弹钻芯修正法检测需在勾选时弹出参数对话框
        return sub_item in ("钻芯法检测", "回弹钻芯修正法检测")

    def create_setup_dialog(self, parent, sub_item, sheet_key=""):
        # 钻芯法检测：返回参数输入对话框实例（框架层不感知具体对话框类）
        if sub_item == "钻芯法检测":
            from .dialogs import CoreDrillingInputDialog
            return CoreDrillingInputDialog(parent, sheet_key)
        if sub_item == "回弹钻芯修正法检测":
            from .dialogs import ReboundCoreDrillingInputDialog
            return ReboundCoreDrillingInputDialog(parent, sheet_key)
        return None

    def build_sheet(self, app, sub_item, sheet_key, params):
        # 由插件决定工作表构建方式（调用 GUI Mixin 的构建方法）
        if sub_item == "回弹钻芯修正法检测":
            app._build_rebound_core_drilling_sheet(sheet_key, params)
            return True
        if sub_item == "钻芯法检测":
            app._build_core_drilling_sheet(sheet_key, params)
            return True
        return False
