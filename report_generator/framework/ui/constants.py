# -*- coding: utf-8 -*-
"""GUI 公共常量：命中目标类型、数据槽位、默认行数"""

from PyQt5.QtCore import Qt

DEFAULT_ROWS = 30

# Qt.UserRole 数据槽位（参考 ONLYOFFICE Cell.flags 扩展）
ROLE_FORMULA   = Qt.UserRole + 1   # 公式原文（=SUM(...)）
ROLE_BOLD      = Qt.UserRole + 2   # 是否加粗
ROLE_ALIGN     = Qt.UserRole + 3   # 对齐方式 left/center/right
ROLE_BG        = Qt.UserRole + 4   # 背景色
ROLE_FG        = Qt.UserRole + 5   # 字体颜色
ROLE_ITALIC    = Qt.UserRole + 6   # 斜体
ROLE_UNDERLINE = Qt.UserRole + 7   # 下划线
ROLE_NUMFMT    = Qt.UserRole + 8   # 数字格式 general/int/dec2/percent/thousands
ROLE_BORDER    = Qt.UserRole + 9   # 边框样式 (top/bottom/left/right 样式 dict)


# ── 命中目标类型枚举（参考 ONLYOFFICE c_oTargetType）──
class TargetType:
    """鼠标命中的 UI 元素类型，用于区分不同交互模式"""
    Cell          = 0x0001   # 普通单元格
    ColumnHeader  = 0x0002   # 列头（点击选整列 / 拖拽改列宽）
    RowHeader     = 0x0003   # 行头（点击选整行 / 拖拽改行高）
    Corner        = 0x0004   # 左上角（全选）
    FillHandle    = 0x0009   # 填充柄（右下角小方块，拖拽自动填充）
