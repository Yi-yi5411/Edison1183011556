# -*- coding: utf-8 -*-
"""钢结构高强度螺栓连接副检测 - 计算规则

列定义见 modules/steel_bolt/columns.py（0-based）：
  0 楼栋 / 1 螺栓编号 / 2 螺栓规格 / 3 连接部位及名称
  4 螺栓直径(mm) / 5 施拧扭矩(N·m) / 6 预拉力(kN) / 7 扭矩系数
  8 结论 / 9 备注
"""

CALC_RULES = {
    '高强度螺栓扭矩系数检测': {
        # 结论：扭矩系数在 0.110~0.150 范围内 → 符合要求（GB 50205）
        8: {
            'type': 'cond_conclusion',
            'conditions': [
                {'col': 7, 'op': '>=', 'value': 0.11},
                {'col': 7, 'op': '<=', 'value': 0.15},
            ],
            'conclusion_pass': '符合要求',
            'conclusion_fail': '不符合要求',
        },
    },
}
