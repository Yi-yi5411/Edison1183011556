# -*- coding: utf-8 -*-
"""钢筋配置 - 计算规则"""

CALC_RULES = {
    '剪力墙构件钢筋间距检测': {
        11: {'type': 'avg', 'sources': [5, 6, 7, 8, 9, 10], 'decimals': 0},
        12: {'type': 'deviation', 'design_col': 4, 'source_col': 5, 'force_sign': True},
        13: {'type': 'deviation', 'design_col': 4, 'source_col': 6, 'force_sign': True},
        14: {'type': 'deviation', 'design_col': 4, 'source_col': 7, 'force_sign': True},
        15: {'type': 'deviation', 'design_col': 4, 'source_col': 8, 'force_sign': True},
        16: {'type': 'deviation', 'design_col': 4, 'source_col': 9, 'force_sign': True},
        17: {'type': 'deviation', 'design_col': 4, 'source_col': 10, 'force_sign': True},
        18: {'type': 'avg_marked', 'sources': [12, 13, 14, 15, 16, 17], 'decimals': 0, 'force_sign': True, 'format_col': 18, 'lower': -10.0, 'upper': 10.0},
    },
    '现浇板钢筋间距检测': {
        11: {'type': 'avg', 'sources': [5, 6, 7, 8, 9, 10], 'decimals': 0},
        12: {'type': 'deviation', 'design_col': 4, 'source_col': 5, 'force_sign': True},
        13: {'type': 'deviation', 'design_col': 4, 'source_col': 6, 'force_sign': True},
        14: {'type': 'deviation', 'design_col': 4, 'source_col': 7, 'force_sign': True},
        15: {'type': 'deviation', 'design_col': 4, 'source_col': 8, 'force_sign': True},
        16: {'type': 'deviation', 'design_col': 4, 'source_col': 9, 'force_sign': True},
        17: {'type': 'deviation', 'design_col': 4, 'source_col': 10, 'force_sign': True},
        18: {'type': 'avg_marked', 'sources': [12, 13, 14, 15, 16, 17], 'decimals': 0, 'force_sign': True, 'format_col': 18, 'lower': -10.0, 'upper': 10.0},
    },
}
