# -*- coding: utf-8 -*-
"""砖混结构砌筑砂浆强度检测（贯入法）- 计算规则

列定义见 modules/mortar_strength/columns.py（0-based）：
  0 楼栋 / 1 构件编号 / 2 构件位置及名称 / 3 设计强度等级
  4~6 测点1~3贯入深度(mm) / 7 平均贯入深度(mm) / 8 强度换算值(MPa)
  9 设计要求(MPa) / 10 结论 / 11 备注
"""

CALC_RULES = {
    '砌筑砂浆强度检测': {
        # 平均贯入深度 = 测点1~3 的平均值
        7: {'type': 'avg', 'sources': [4, 5, 6], 'decimals': 2},
        # 结论：强度换算值 >= 设计要求 → 符合要求
        10: {
            'type': 'col_conclusion',
            'pairs': [{'left_col': 8, 'op': '>=', 'right_col': 9}],
            'conclusion_pass': '符合要求',
            'conclusion_fail': '不符合要求',
        },
    },
}
