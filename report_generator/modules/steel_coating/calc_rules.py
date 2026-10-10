# -*- coding: utf-8 -*-
"""钢结构涂层厚度检测（防腐/防火）- 计算规则

列定义见 modules/steel_coating/columns.py（0-based）：
  0 楼栋 / 1 构件编号 / 2 构件位置及名称 / 3 设计厚度(μm)
  4~8 测点1~5(μm) / 9 平均厚度(μm) / 10 结论 / 11 备注
"""

_CALCS = {
    # 平均厚度 = 测点1~5 的平均值
    9: {'type': 'avg', 'sources': [4, 5, 6, 7, 8], 'decimals': 1},
    # 结论：平均厚度 >= 设计厚度 → 符合要求
    10: {
        'type': 'col_conclusion',
        'pairs': [{'left_col': 9, 'op': '>=', 'right_col': 3}],
        'conclusion_pass': '符合要求',
        'conclusion_fail': '不符合要求',
    },
}

CALC_RULES = {
    '防腐涂层厚度检测': dict(_CALCS),
    '防火涂层厚度检测': dict(_CALCS),
}
