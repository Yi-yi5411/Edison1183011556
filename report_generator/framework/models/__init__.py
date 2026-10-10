# -*- coding: utf-8 -*-
"""数据模型层：项目定义 + 经插件管理器聚合的列定义/计算规则。"""
from framework.models.detection_data import (
    PROJECT_NAME, DETECTION_DATA, SUMMARY_HEADERS,
)
from core.plugin_manager import get_plugin_manager

_pm = get_plugin_manager()
ITEM_COLUMNS = _pm.aggregated_item_columns()
ITEM_COLUMN_TYPES = _pm.aggregated_column_types()
CALC_RULES = _pm.aggregated_calc_rules()

__all__ = ['PROJECT_NAME', 'DETECTION_DATA', 'SUMMARY_HEADERS',
           'ITEM_COLUMNS', 'ITEM_COLUMN_TYPES', 'CALC_RULES']
