# -*- coding: utf-8 -*-
"""砖混结构砖强度检测（回弹法）- 计算规则

列定义见 modules/brick_strength/columns.py（0-based）：
  0 批次 / 1 构件位置及类型 / 2 轴号编号 / 3 测区号
  4~8 回弹值1~5 / 9 测区平均回弹值 / 10 强度换算值(MPa)
  11 批次平均值(MPa) / 12 方差(MPa²) / 13 标准差(MPa)
  14 变异系数 / 15 强度标准值(MPa) / 16 评定等级 / 17 备注

强度换算公式（烧结普通砖常用换算公式）：
  f = 0.0254 × R^2.1429（R 为测区平均回弹值）。
批次统计以“批次”列分组：平均值、样本方差、样本标准差(n-1)、
变异系数 δ=标准差/平均值、强度标准值=平均值−1.8×标准差；
评定等级按 GB 5101 烧结普通砖：δ≤0.21 用 平均值+标准值法，
δ>0.21 用 平均值+最小值法，取满足的最高等级（MU10~MU30）。
"""

CALC_RULES = {
    '砖强度检测': {
        # 测区平均回弹值 = 回弹值1~5 的平均值
        9: {
            'type': 'avg',
            'sources': [4, 5, 6, 7, 8],
            'decimals': 1,
        },
        # 强度换算值 = 0.0254 × R^2.1429（R=测区平均回弹值）
        10: {
            'type': 'rebound_strength',
            'rm_col': 9,
            'coef_a': 0.0254,
            'exp_b': 2.1429,
            'decimals': 2,
        },
        # 以下按“批次”列聚合，同批次每行写入相同结果
        11: {
            'type': 'batch_stat', 'stat': 'avg',
            'source_col': 10, 'batch_col': 0, 'decimals': 2,
        },
        12: {
            'type': 'batch_stat', 'stat': 'var',
            'source_col': 10, 'batch_col': 0, 'decimals': 2,
        },
        13: {
            'type': 'batch_stat', 'stat': 'std',
            'source_col': 10, 'batch_col': 0, 'decimals': 2,
        },
        14: {
            'type': 'batch_stat', 'stat': 'cv',
            'source_col': 10, 'batch_col': 0, 'decimals': 2,
            'as_percent': True,
        },
        15: {
            'type': 'batch_stat', 'stat': 'std_value',
            'source_col': 10, 'batch_col': 0, 'decimals': 2,
        },
        16: {
            'type': 'batch_brick_grade',
            'source_col': 10, 'batch_col': 0,
        },
    },
}
