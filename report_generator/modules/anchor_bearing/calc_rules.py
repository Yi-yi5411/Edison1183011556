# -*- coding: utf-8 -*-
"""化学植筋锚固承载力检测 - 计算规则"""

# 列定义（0-based）：
#   0 楼栋 / 1 序号 / 2 构件名称 / 3 构件轴线编号 / 4 钢筋牌号/植筋规格
#   5 公称直径(mm) / 6 检测荷载（kN） / 7 持荷2min内荷载值降低率
#   8 实测现象 / 9 结论
#
# 结论判定（cond_conclusion 规则在 framework/engine/auto_calc.py 的
# CalcEngine.apply_calc_rules 分支 calc_type == "cond_conclusion" 中实现）：
#   实测现象为“基材无裂缝、钢筋无滑移”，且持荷2min内荷载值降低率 ≤ 0.05
#   （支持输入 5% 等百分比格式），检测试验荷载 ≥ 6.0 kN，
#   三项全部满足 → “符合规范要求”；否则 → “不符合规范要求”。
CALC_RULES = {
    '化学植筋锚固承载力检测': {
        # 目标列 9 = 结论
        9: {
            'type': 'cond_conclusion',
            'conditions': [
                # 检测荷载（kN）≥ 6.0
                {'col': 6, 'op': '>=', 'value': 6.0, 'mark': True},
                # 持荷2min内荷载值降低率 ≤ 0.05
                {'col': 7, 'op': '<=', 'value': 0.05, 'mark': True},
                # 实测现象须包含“基材无裂缝、钢筋无滑移”
                {'col': 8, 'op': 'contains', 'value': '基材无裂缝、钢筋无滑移', 'mark': True},
            ],
            'conclusion_pass': '符合规范要求',
            'conclusion_fail': '不符合规范要求',
        },
    },
}
