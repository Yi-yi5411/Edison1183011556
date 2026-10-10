# -*- coding: utf-8 -*-
"""木结构构件挠度检测 - 计算规则

列定义见 modules/wood_deflection/columns.py（0-based）：
  0 楼栋 / 1 构件编号 / 2 构件位置及名称 / 3 跨度L(m)
  4 实测挠度(mm) / 5 允许挠度(mm) / 6 结论 / 7 备注
"""

CALC_RULES = {
    '木构件挠度检测': {
        # 结论：实测挠度 <= 允许挠度 → 符合要求
        6: {
            'type': 'col_conclusion',
            'pairs': [{'left_col': 4, 'op': '<=', 'right_col': 5}],
            'conclusion_pass': '符合要求',
            'conclusion_fail': '不符合要求',
        },
    },
}
