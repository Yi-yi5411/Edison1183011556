# -*- coding: utf-8 -*-
"""检测项目插件抽象基类。

所有检测项目插件继承此类，统一暴露表头 / 列类型 / 计算规则 / 校验接口，
使主框架无需感知具体项目类型即可驱动表格生成与自动计算。

新增检测项目时，只需在 ``modules/<name>/plugin.py`` 实现一个子类，
``core.plugin_manager`` 会自动发现并注册，无需修改主框架代码。
"""

from abc import ABC, abstractmethod


class BaseDetectionPlugin(ABC):
    """检测项目插件基类。

    子类应实现 ``plugin_id`` / ``display_name``，并覆盖 ``columns`` /
    ``column_types`` / ``calc_rules`` 返回该项目专属的数据字典。
    其余方法提供合理默认值，按需覆盖。
    """

    # ── 元信息（子类必须实现）──
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """唯一标识，如 'concrete_strength'。"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """展示名（与 DETECTION_DATA 顶层键一致），如 '混凝土抗压强度检测'。"""

    # ── 结构类型 / 树结构声明 ──
    @property
    def structure_type(self) -> str:
        """所属结构类型（混凝土结构/钢结构/木结构…），决定树中分组排序。"""
        return "混凝土结构"

    @property
    def tree_order(self) -> int:
        """同类结构内的树排序权重（越小越靠前）。"""
        return 100

    def tree_entries(self):
        """声明左侧勾选树的目录条目：{项目名: [构件, ...]}。

        默认取 ``columns()`` 的键（无构件维度）；带构件维度或项目名带
        说明后缀的项目（如回弹法）应覆盖本方法精确声明树结构，
        使 DETECTION_DATA 由插件聚合生成而非框架硬编码。
        返回空字典表示该项目不在树中展示。
        """
        return {name: [] for name in self.columns().keys()}

    # ── 表头 / 列类型 / 计算规则 ──
    def columns(self):
        """返回 {子检测项: [列头, ...]} 字典，默认空。"""
        return {}

    def column_types(self):
        """返回 {子检测项: [列类型, ...]} 字典，默认空。"""
        return {}

    def calc_rules(self):
        """返回 {子检测项: {目标列: 规则}} 字典，默认空。"""
        return {}

    def get_sub_items(self):
        """返回该项目下所有子检测项名。"""
        return list(self.columns().keys())

    def get_headers(self, sub_item):
        """返回指定子项的列头列表。"""
        return self.columns().get(sub_item, [])

    def get_column_types(self, sub_item):
        """返回指定子项的列类型列表。"""
        return self.column_types().get(sub_item, [])

    def get_calc_rules(self, sub_item=None):
        """返回计算规则。

        sub_item 为 None 时返回该项目全部规则字典；
        否则返回该子项的规则 {目标列: 规则}。
        """
        rules = self.calc_rules()
        if sub_item is None:
            return rules
        return rules.get(sub_item, {})

    # ── 可选：项目专属 GUI 混入类 ──
    def get_gui_mixins(self):
        """返回需混入主窗口的 GUI Mixin 类列表（默认空）。

        钻芯法等需要专属表格构建/合并/自动计算的项目在此返回其 Mixin。
        """
        return []

    # ── 可选：能力判定（替代 UI 中散落的项目名字符串判断）──
    def requires_setup_dialog(self, sub_item):
        """该子项勾选时是否需要弹出参数设置对话框（默认否）。"""
        return False

    def create_setup_dialog(self, parent, sub_item, sheet_key=""):
        """创建参数设置对话框实例（默认返回 None，表示无需对话框）。

        框架在勾选需参数设置的检测项时调用此方法，由插件决定具体弹出的
        对话框类型；框架层不感知任何具体对话框类，实现解耦。
        返回值应为 QDialog 实例或 None。
        """
        return None

    def build_sheet(self, app, sub_item, sheet_key, params):
        """根据参数对话框结果构建工作表（与 create_setup_dialog 配对）。

        框架在用户确认参数对话框后调用此方法，由插件决定具体的表格
        构建方式（调用其 GUI Mixin 暴露的构建方法）。
        返回 True 表示已构建，False 表示本项目不支持。
        """
        return False

    # ── 可选：业务计算 / 校验 / 汇总（无 GUI 依赖）──
    def calculate(self, worksheet_data):
        """项目专属批量计算，返回结果字典（默认无）。"""
        return {}

    def validate(self, row_data):
        """单行数据校验，返回 (ok, message)，默认通过。"""
        return True, ""

    def summary(self, worksheet_data):
        """生成汇总信息，返回 dict，默认空。"""
        return {}

    def __repr__(self):
        return f"<{type(self).__name__} id={self.plugin_id} name={self.display_name}>"
