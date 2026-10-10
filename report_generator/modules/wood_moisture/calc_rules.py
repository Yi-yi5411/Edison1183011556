# -*- coding: utf-8 -*-
"""木结构木材含水率检测 - 计算规则

列定义见 modules/wood_moisture/columns.py（0-based）：
  0 楼栋 / 1 构件编号 / 2 构件位置及名称 / 3 构件类型
  4~6 测点1~3(%) / 7 平均值(%) / 8 结论 / 9 备注
"""

CALC_RULES = {
    '木材含水率检测': {
        # 平均值 = 测点1~3 的平均值
        7: {'type': 'avg', 'sources': [4, 5, 6], 'decimals': 1},
        # 结论：平均值 <= 25% → 符合要求（GB 50005 原木/方木结构限值）
        8: {
            'type': 'cond_conclusion',
            'conditions': [{'col': 7, 'op': '<=', 'value': 25.0}],
            'conclusion_pass': '符合要求',
            'conclusion_fail': '不符合要求',
        },
    },
}
