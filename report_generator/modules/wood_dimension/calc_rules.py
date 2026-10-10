# -*- coding: utf-8 -*-
"""木结构构件尺寸偏差检测 - 计算规则

列定义见 modules/wood_dimension/columns.py（0-based）：
  0 楼栋 / 1 构件编号 / 2 构件位置及名称 / 3 检测部位
  4 设计值(mm) / 5~7 实测值1~3(mm) / 8 平均值(mm) / 9 偏差(mm) / 10 备注
"""

CALC_RULES = {
    '木构件尺寸偏差检测': {
        # 平均值 = 实测值1~3 的平均值
        8: {'type': 'avg', 'sources': [5, 6, 7], 'decimals': 1},
        # 偏差 = 平均值 - 设计值（带符号；允许偏差因部位而异，不做统一标记）
        9: {
            'type': 'deviation',
            'design_col': 4,
            'source_col': 8,
            'force_sign': True,
        },
    },
}
