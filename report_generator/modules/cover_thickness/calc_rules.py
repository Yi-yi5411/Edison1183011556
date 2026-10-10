# -*- coding: utf-8 -*-
"""保护层厚度检测 - 计算规则（10 测点）"""

CALC_RULES = {
    # 列定义见 modules/cover_thickness/columns.py（0-based）：
    #   0 楼栋 / 1 构件位置及名称 / 2 构件轴线编号 / 3 设计值(mm)/ 4 钢筋根数(mm)
    #   5~14 实测值1~10 / 15~24 偏差值1~10 / 25 合格点率 / 26 合格/不合格
    # 其中 25、26 由本模块 handlers.py 的 CoverThicknessMixin
    # 汇总计算，不放在本文件的 CALC_RULES 中。

    '混凝土梁保护层厚度检测': {
        # 目标列 15~24 = 偏差值1~10；deviation = source_col - design_col，即
        # 对应实测值 - 设计值(col 3)，force_sign 使正数带"+"；
        # 偏差超出允许偏差 [lower, upper]（梁 -7~+10）时通过
        # set_font_func 加粗并加下划线标记。
        15: {'type': 'deviation', 'design_col': 3, 'source_col': 5, 'force_sign': True, 'lower': -7, 'upper': 10},
        16: {'type': 'deviation', 'design_col': 3, 'source_col': 6, 'force_sign': True, 'lower': -7, 'upper': 10},
        17: {'type': 'deviation', 'design_col': 3, 'source_col': 7, 'force_sign': True, 'lower': -7, 'upper': 10},
        18: {'type': 'deviation', 'design_col': 3, 'source_col': 8, 'force_sign': True, 'lower': -7, 'upper': 10},
        19: {'type': 'deviation', 'design_col': 3, 'source_col': 9, 'force_sign': True, 'lower': -7, 'upper': 10},
        20: {'type': 'deviation', 'design_col': 3, 'source_col': 10, 'force_sign': True, 'lower': -7, 'upper': 10},
        21: {'type': 'deviation', 'design_col': 3, 'source_col': 11, 'force_sign': True, 'lower': -7, 'upper': 10},
        22: {'type': 'deviation', 'design_col': 3, 'source_col': 12, 'force_sign': True, 'lower': -7, 'upper': 10},
        23: {'type': 'deviation', 'design_col': 3, 'source_col': 13, 'force_sign': True, 'lower': -7, 'upper': 10},
        24: {'type': 'deviation', 'design_col': 3, 'source_col': 14, 'force_sign': True, 'lower': -7, 'upper': 10},
    },
    '混凝土柱保护层厚度检测': {
        15: {'type': 'deviation', 'design_col': 3, 'source_col': 5, 'force_sign': True, 'lower': -7, 'upper': 10},
        16: {'type': 'deviation', 'design_col': 3, 'source_col': 6, 'force_sign': True, 'lower': -7, 'upper': 10},
        17: {'type': 'deviation', 'design_col': 3, 'source_col': 7, 'force_sign': True, 'lower': -7, 'upper': 10},
        18: {'type': 'deviation', 'design_col': 3, 'source_col': 8, 'force_sign': True, 'lower': -7, 'upper': 10},
        19: {'type': 'deviation', 'design_col': 3, 'source_col': 9, 'force_sign': True, 'lower': -7, 'upper': 10},
        20: {'type': 'deviation', 'design_col': 3, 'source_col': 10, 'force_sign': True, 'lower': -7, 'upper': 10},
        21: {'type': 'deviation', 'design_col': 3, 'source_col': 11, 'force_sign': True, 'lower': -7, 'upper': 10},
        22: {'type': 'deviation', 'design_col': 3, 'source_col': 12, 'force_sign': True, 'lower': -7, 'upper': 10},
        23: {'type': 'deviation', 'design_col': 3, 'source_col': 13, 'force_sign': True, 'lower': -7, 'upper': 10},
        24: {'type': 'deviation', 'design_col': 3, 'source_col': 14, 'force_sign': True, 'lower': -7, 'upper': 10}, 
    },
    '剪力墙保护层厚度检测': {
        # 剪力墙允许偏差 -5~+8，超标的偏差值加粗并加下划线标记。
        15: {'type': 'deviation', 'design_col': 3, 'source_col': 5, 'force_sign': True, 'lower': -5, 'upper': 8},
        16: {'type': 'deviation', 'design_col': 3, 'source_col': 6, 'force_sign': True, 'lower': -5, 'upper': 8},
        17: {'type': 'deviation', 'design_col': 3, 'source_col': 7, 'force_sign': True, 'lower': -5, 'upper': 8},
        18: {'type': 'deviation', 'design_col': 3, 'source_col': 8, 'force_sign': True, 'lower': -5, 'upper': 8},
        19: {'type': 'deviation', 'design_col': 3, 'source_col': 9, 'force_sign': True, 'lower': -5, 'upper': 8},
        20: {'type': 'deviation', 'design_col': 3, 'source_col': 10, 'force_sign': True, 'lower': -5, 'upper': 8},
        21: {'type': 'deviation', 'design_col': 3, 'source_col': 11, 'force_sign': True, 'lower': -5, 'upper': 8},      
        22: {'type': 'deviation', 'design_col': 3, 'source_col': 12, 'force_sign': True, 'lower': -5, 'upper': 8},
        23: {'type': 'deviation', 'design_col': 3, 'source_col': 13, 'force_sign': True, 'lower': -5, 'upper': 8},
        24: {'type': 'deviation', 'design_col': 3, 'source_col': 14, 'force_sign': True, 'lower': -5, 'upper': 8},
    },
    '混凝土板保护层厚度检测': {
        15: {'type': 'deviation', 'design_col': 3, 'source_col': 5, 'force_sign': True, 'lower': -5, 'upper': 8},
        16: {'type': 'deviation', 'design_col': 3, 'source_col': 6, 'force_sign': True, 'lower': -5, 'upper': 8},
        17: {'type': 'deviation', 'design_col': 3, 'source_col': 7, 'force_sign': True, 'lower': -5, 'upper': 8},
        18: {'type': 'deviation', 'design_col': 3, 'source_col': 8, 'force_sign': True, 'lower': -5, 'upper': 8},
        19: {'type': 'deviation', 'design_col': 3, 'source_col': 9, 'force_sign': True, 'lower': -5, 'upper': 8},
        20: {'type': 'deviation', 'design_col': 3, 'source_col': 10, 'force_sign': True, 'lower': -5, 'upper': 8},
        21: {'type': 'deviation', 'design_col': 3, 'source_col': 11, 'force_sign': True, 'lower': -5, 'upper': 8},
        22: {'type': 'deviation', 'design_col': 3, 'source_col': 12, 'force_sign': True, 'lower': -5, 'upper': 8},
        23: {'type': 'deviation', 'design_col': 3, 'source_col': 13, 'force_sign': True, 'lower': -5, 'upper': 8},
        24: {'type': 'deviation', 'design_col': 3, 'source_col': 14, 'force_sign': True, 'lower': -5, 'upper': 8},
    },
}
