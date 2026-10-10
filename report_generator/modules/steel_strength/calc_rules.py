# -*- coding: utf-8 -*-
"""钢结构钢材强度检测（硬度法）- 计算规则

列定义见 modules/steel_strength/columns.py（0-based）：
  0 楼栋 / 1 构件编号 / 2 构件位置及名称 / 3 构件类型 / 4 钢材牌号
  5~9 测点1~5 / 10 平均硬度值(HLD) / 11 抗拉强度换算值(MPa)
  12 设计要求(MPa) / 13 结论 / 14 备注
"""

CALC_RULES = {
    '钢材强度检测': {
        # 平均硬度值 = 测点1~5 的平均值
        10: {'type': 'avg', 'sources': [5, 6, 7, 8, 9], 'decimals': 0},
        # 结论：抗拉强度换算值 >= 设计要求 → 符合要求
        13: {
            'type': 'col_conclusion',
            'pairs': [{'left_col': 11, 'op': '>=', 'right_col': 12}],
            'conclusion_pass': '符合要求',
            'conclusion_fail': '不符合要求',
        },
    },
}
