# -*- coding: utf-8 -*-
"""混凝土构件 - 列头与列类型"""

COLUMNS = {
    '楼板构件厚度检测': ['楼栋', '构件位置及名称', '板号', '轴线编号', '设计值(mm)', '实测值1(mm)', '实测值2(mm)', '实测值3(mm)', '实测平均值(mm)', '偏差值1(mm)', '偏差值2(mm)', '偏差值3(mm)', '实测偏差平均值', '合格点率', '合格/不合格'],
    '剪力墙厚度检测': ['楼栋', '构件位置及名称', '轴线编号', '设计值', '实测值1', '实测值2', '实测值3', '实测值平均值', '偏差值1', '偏差值2', '偏差值3', '偏差值平均值', '合格点率', '合格/不合格'],
    '混凝土梁结构尺寸检测': ['楼栋', '构件位置及名称', '轴线编号','设计宽度B(mm)', '设计高度H(mm)', '实测宽度B1', '实测宽度B2', '实测宽度B3', '实测高度H1', '实测高度H2', '实测高度H3', '宽度平均值(mm)', '高度平均值(mm)', '宽度偏差(mm)', '高度偏差(mm)'],
    '混凝土柱结构尺寸检测': ['楼栋', '构件位置及名称', '轴线编号', '设计宽度B(mm)', '设计高度H(mm)', '实测宽度B1', '实测宽度B2', '实测宽度B3', '实测高度H1', '实测高度H2', '实测高度H3', '宽度平均值(mm)', '高度平均值(mm)', '宽度偏差(mm)', '高度偏差(mm)'],
}

COLUMN_TYPES = {
    '楼板构件厚度检测': ['string', 'string', 'string', 'string', 'float', 'float', 'float', 'float', 'float', 'float', 'float', 'float', 'float', 'string', 'string'],
    '剪力墙厚度检测': ['string', 'string', 'string', 'float', 'float', 'float', 'float', 'float', 'float', 'float', 'float', 'float', 'string', 'string'],
    '混凝土梁结构尺寸检测': ['string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'float', 'float', 'float', 'float', 'float', 'float'],
    '混凝土柱结构尺寸检测': ['string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'float', 'float', 'float', 'float', 'float', 'float'],
}
