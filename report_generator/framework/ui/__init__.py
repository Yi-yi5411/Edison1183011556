# -*- coding: utf-8 -*-
"""UI 层：表格控件、常量、对话框、主窗口。"""
from framework.ui.constants import (
    TargetType, DEFAULT_ROWS,
    ROLE_FORMULA, ROLE_BOLD, ROLE_ALIGN, ROLE_BG, ROLE_FG,
    ROLE_ITALIC, ROLE_UNDERLINE, ROLE_NUMFMT, ROLE_BORDER,
)
from framework.ui.table_widget import MergeTableWidget

__all__ = [
    "TargetType", "DEFAULT_ROWS",
    "ROLE_FORMULA", "ROLE_BOLD", "ROLE_ALIGN", "ROLE_BG", "ROLE_FG",
    "ROLE_ITALIC", "ROLE_UNDERLINE", "ROLE_NUMFMT", "ROLE_BORDER",
    "MergeTableWidget",
]
