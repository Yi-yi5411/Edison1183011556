# -*- coding: utf-8 -*-
"""混凝土抗压强度检测 - 列头与列类型"""

COLUMNS = {
    '回弹法检测': ['构件名称', '构件轴号', '设计强度等级', '平均强度值(MPa)', '标准差(MPa)', '最小测区强度值(MPa)', '强度推定值(MPa)', '龄期(d)'],
    '钻芯法检测': ['楼栋', '批次','构件编号', '构件位置及名称', '轴线编号', '序号', '芯样直径(mm)', '截面积(mm²)', '测试荷载(kN)', '测试强度(MPa)', '推定值(MPa)', '批评定值(MPa)', '设计等级'],
    '回弹钻芯修正法检测': ['楼栋','批次','构件编号', '构件位置及名称', '构件轴线编号', '钻芯测区', '芯样直径(mm)','截面积(mm²)','测试荷载(kN)', '测试强度(MPa)', '设计强度等级','芯样强度均值(MPa)'],
}

COLUMN_TYPES = {
    '回弹法检测': ['string', 'string', 'string', 'float', 'float', 'float', 'float', 'float'],
    '钻芯法检测': ['string', 'string','string', 'string', 'string', 'string', 'float', 'float', 'float', 'float', 'float', 'float', 'string'],
    '回弹钻芯修正法检测': ['string', 'string', 'string', 'string', 'string', 'string', 'float', 'float', 'float', 'float', 'string', 'float'],
}
