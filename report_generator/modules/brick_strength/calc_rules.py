# -*- coding: utf-8 -*-
"""砖混结构砖强度检测（回弹法）- 计算规则

列定义见 modules/brick_strength/columns.py（0-based）：
  0 批次 / 1 构件编号 / 2 构件位置及类型 / 3 轴号编号 / 4 测区号
  5~9 回弹值1~5 / 10 测区平均回弹值 / 11 强度换算值(MPa)
  12 构件平均强度(MPa) / 13 批次平均值(MPa) / 14 方差(MPa²)
  15 标准差(MPa) / 16 变异系数 / 17 强度标准值(MPa)
  18 评定等级 / 19 备注

强度换算公式（与现场 Excel 表一致）：
  f = 0.02 × R² − 0.45 × R + 1.25（R 为测区平均回弹值）。

聚合规则：
  1. 每个构件先对本构件各测区的强度换算值求平均；
  2. 批次统计以“批次”分组，统计对象为各构件平均强度（不是全部测区）；
     平均值、方差（离差平方和）、标准差（样本 n−1）、
     变异系数 δ=标准差/平均值、强度标准值=平均值−1.8×标准差；
  3. 评定等级按 GB 5101 烧结普通砖：δ≤0.21 用 平均值+标准值法，
     δ>0.21 用 平均值+最小值法，取满足的最高等级（MU10~MU30）。
"""

_BRICK_COMPONENT_COLS = [1, 2, 3]  # 构件编号 / 构件位置 / 轴号，联合识别构件
_BRICK_CURVE = {
    "source_rm_col": 10,
    "coef_a": 0.02,
    "coef_b": -0.45,
    "constant": 1.25,
}

CALC_RULES = {
    '砖强度检测': {
        # 测区平均回弹值 = 回弹值1~5 的平均值
        10: {
            'type': 'avg',
            'sources': [5, 6, 7, 8, 9],
            'decimals': 1,
        },
        # 强度换算值 = 0.02R² − 0.45R + 1.25
        11: {
            'type': 'brick_rebound_strength',
            'rm_col': 10,
            'coef_a': 0.02,
            'coef_b': -0.45,
            'constant': 1.25,
            'decimals': 2,
        },
        # 构件平均强度：同一构件各测区强度换算值的平均
        12: {
            'type': 'component_stat',
            'stat': 'avg',
            'source_col': 11,
            'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'decimals': 2,
        },
        # 以下按“批次”聚合，统计对象为各构件平均强度
        13: {
            'type': 'batch_stat', 'stat': 'avg',
            'source_col': 11, 'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'decimals': 2,
        },
        14: {
            'type': 'batch_stat', 'stat': 'var',
            'source_col': 11, 'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'sum_squares': True,
            'decimals': 2,
        },
        15: {
            'type': 'batch_stat', 'stat': 'std',
            'source_col': 11, 'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'decimals': 2,
        },
        16: {
            'type': 'batch_stat', 'stat': 'cv',
            'source_col': 11, 'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'decimals': 2,
            'as_percent': True,
        },
        17: {
            'type': 'batch_stat', 'stat': 'std_value',
            'source_col': 11, 'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'decimals': 2,
        },
        18: {
            'type': 'batch_brick_grade',
            'source_col': 11, 'batch_col': 0,
            'component_cols': _BRICK_COMPONENT_COLS, **_BRICK_CURVE,
            'min_from_all': True,
        },
    },
}
