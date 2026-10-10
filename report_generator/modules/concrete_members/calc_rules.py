# -*- coding: utf-8 -*-
"""混凝土构件 - 计算规则"""

CALC_RULES = {
    '楼板构件厚度检测': {
        8: {'type': 'avg', 'sources': [5, 6, 7], 'decimals': 0},
        9: {'type': 'deviation', 'design_col': 4, 'source_col': 5, 'force_sign': True},
        10: {'type': 'deviation', 'design_col': 4, 'source_col': 6, 'force_sign': True},
        11: {'type': 'deviation', 'design_col': 4, 'source_col': 7, 'force_sign': True},
        12: {'type': 'avg_marked', 'sources': [9, 10, 11], 'decimals': 0, 'force_sign': True, 'format_col': 12, 'lower': -5.0, 'upper': 10.0},
    },
    '剪力墙厚度检测': {
        7: {'type': 'avg', 'sources': [4, 5, 6], 'decimals': 0},
        8: {'type': 'deviation', 'design_col': 3, 'source_col': 4, 'force_sign': True},
        9: {'type': 'deviation', 'design_col': 3, 'source_col': 5, 'force_sign': True},
        10: {'type': 'deviation', 'design_col': 3, 'source_col': 6, 'force_sign': True},
        11: {'type': 'avg_marked', 'sources': [8, 9, 10], 'decimals': 0, 'force_sign': True, 'format_col': 11, 'lower': -5.0, 'upper': 10.0},
    },
    # 混凝土梁结构尺寸检测：列定义见 modules/concrete_members/columns.py 中
    # COLUMNS['混凝土梁结构尺寸检测']（0-based）：
    #   0 楼栋 / 1 构件位置及名称 / 2 轴线编号 / 3 设计宽度B(mm) / 4 设计高度H(mm)
    #   5~7 实测宽度B1~B3 / 8~10 实测高度H1~H3
    #   11 宽度平均值(mm) / 12 高度平均值(mm) / 13 宽度偏差(mm) / 14 高度偏差(mm)
    '混凝土梁结构尺寸检测': {
        # 目标列 11 = 宽度平均值；源列 [5, 6, 7] = 实测宽度B1/B2/B3。
        # avg 规则在 framework/engine/auto_calc.py 的 CalcEngine.apply_calc_rules
        # 分支 calc_type == "avg" 中实现：sum(源列) / 有值源列数。
        11: {'type': 'avg', 'sources': [5, 6, 7], 'decimals': 0},

        # 目标列 12 = 高度平均值；源列 [8, 9, 10] = 实测高度H1/H2/H3。
        12: {'type': 'avg', 'sources': [8, 9, 10], 'decimals': 0},

        # 目标列 13 = 宽度偏差；deviation 规则在 auto_calc.py 的
        # calc_type == "deviation" 分支中实现：偏差 = source_col - design_col，
        # 即 宽度平均值(col 11) - 设计宽度B(col 3)；force_sign 使正数带“+”。
        # lower/upper 为允许偏差范围 [-5, +10]，超出范围时该单元格会加粗并加下划线。
        13: {'type': 'deviation', 'design_col': 3, 'source_col': 11, 'force_sign': True, 'lower': -5.0, 'upper': 10.0},

        # 目标列 14 = 高度偏差：高度平均值(col 12) - 设计高度H(col 4)。
        # 超出 [-5, +10] 同样加粗并加下划线。
        14: {'type': 'deviation', 'design_col': 4, 'source_col': 12, 'force_sign': True, 'lower': -5.0, 'upper': 10.0},

        # 目标列 15 = “合格/不合格”结论；但 columns.py 当前只定义了 15 列
        # （索引 0~14），auto_calc.py 中 target_col >= column_count 的守卫会
        # 跳过本规则。只有同时在 columns.py 增加第 16 列后，本规则才会生效。
        15: {'type': 'conclusion', 'sources': [13, 14], 'lower': -5.0, 'upper': 10.0, 'conclusion_pass': '符合规范', 'conclusion_fail_high': '不符合规范', 'conclusion_fail_low': '不符合规范'},
    },
    # 混凝土柱结构尺寸检测：列结构与混凝土梁结构尺寸检测完全一致，
    # 只是另一个检测项目，因此下面四条计算规则与梁结构相同。
    '混凝土柱结构尺寸检测': {
        # 11 宽度平均值 = AVERAGE(实测宽度B1/B2/B3)，即源列 [5, 6, 7]。
        11: {'type': 'avg', 'sources': [5, 6, 7], 'decimals': 0},

        # 12 高度平均值 = AVERAGE(实测高度H1/H2/H3)，即源列 [8, 9, 10]。
        12: {'type': 'avg', 'sources': [8, 9, 10], 'decimals': 0},

        # 13 宽度偏差 = 宽度平均值(col 11) - 设计宽度B(col 3)；超出 [-5, +10] 加粗加下划线。
        13: {'type': 'deviation', 'design_col': 3, 'source_col': 11, 'force_sign': True, 'lower': -5.0, 'upper': 10.0},

        # 14 高度偏差 = 高度平均值(col 12) - 设计高度H(col 4)；超出 [-5, +10] 加粗加下划线。
        14: {'type': 'deviation', 'design_col': 4, 'source_col': 12, 'force_sign': True, 'lower': -5.0, 'upper': 10.0},

        # 同梁结构：结论列当前未定义，会被 auto_calc.py 的列数守卫跳过。
        15: {'type': 'conclusion', 'sources': [13, 14], 'lower': -5.0, 'upper': 10.0, 'conclusion_pass': '符合规范', 'conclusion_fail_high': '不符合规范', 'conclusion_fail_low': '不符合规范'},
    },
}