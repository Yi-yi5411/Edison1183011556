# -*- coding: utf-8 -*-
"""钻芯法检测批量推定计算（批评定）- 纯计算函数

从 gui_qt.py 提取，无 GUI 依赖，可独立单测。
"""

import math

# ═══════════════════════════════════════════════════════════════
#  钻芯法检测批量推定计算（批评定）
# ═══════════════════════════════════════════════════════════════
# 内置完整系数表：键为试件数 n，值为 [k1(0.05), k2(0.05), k2(0.10)]
COEFF_TABLE = {
    10: [1.01730, 2.91096, 2.56837], 11: [1.04127, 2.81499, 2.50262],
    12: [1.06247, 2.73634, 2.44825], 13: [1.08141, 2.67050, 2.40240],
    14: [1.09848, 2.61443, 2.36311], 15: [1.11397, 2.56600, 2.32898],
    16: [1.12812, 2.52366, 2.29900], 17: [1.14112, 2.48626, 2.27240],
    18: [1.15311, 2.45295, 2.24862], 19: [1.16423, 2.42304, 2.22720],
    20: [1.17458, 2.39600, 2.20778], 21: [1.18425, 2.37142, 2.19007],
    22: [1.19330, 2.34896, 2.17385], 23: [1.20181, 2.32832, 2.15891],
    24: [1.20982, 2.30929, 2.14510], 25: [1.21739, 2.29167, 2.13229],
    26: [1.22455, 2.27530, 2.12037], 27: [1.23135, 2.26005, 2.10924],
    28: [1.23780, 2.24578, 2.09881], 29: [1.24395, 2.23241, 2.08903],
    30: [1.24981, 2.21984, 2.07982], 31: [1.25540, 2.20800, 2.07113],
    32: [1.26075, 2.19682, 2.06292], 33: [1.26588, 2.18625, 2.05514],
    34: [1.27079, 2.17623, 2.04776], 35: [1.27551, 2.16672, 2.04075],
    36: [1.28004, 2.15768, 2.03407], 37: [1.28441, 2.14906, 2.02771],
    38: [1.28861, 2.14085, 2.02164], 39: [1.29266, 2.13300, 2.01583],
    40: [1.29657, 2.12549, 2.01027], 41: [1.30035, 2.11831, 2.00494],
    42: [1.30399, 2.11142, 1.99983], 43: [1.30752, 2.10481, 1.99493],
    44: [1.31094, 2.09846, 1.99021], 45: [1.31425, 2.09235, 1.98567],
    46: [1.31746, 2.08648, 1.98130], 47: [1.32058, 2.08081, 1.97708],
    48: [1.32360, 2.07535, 1.97302], 49: [1.32653, 2.07008, 1.96909],
    50: [1.32939, 2.06499, 1.96529], 60: [1.35412, 2.02216, 1.93327],
    70: [1.37364, 1.98987, 1.90903], 80: [1.38959, 1.96444, 1.88988],
    90: [1.40294, 1.94376, 1.87428], 100: [1.41433, 1.92654, 1.86125],
    110: [1.42421, 1.91191, 1.85017], 120: [1.43289, 1.89929, 1.84059],
    130: [1.44060, 1.88827, 1.83222], 140: [1.44750, 1.87852, 1.82481],
    150: [1.45372, 1.86984, 1.81820], 160: [1.45938, 1.86203, 1.81225],
    170: [1.46456, 1.85497, 1.80686], 180: [1.46931, 1.84854, 1.80196],
    190: [1.47370, 1.84265, 1.79746], 200: [1.47777, 1.83724, 1.79332],
    250: [1.49443, 1.81547, 1.77667], 300: [1.50687, 1.79964, 1.76454],
    400: [1.52453, 1.77776, 1.74773], 500: [1.53671, 1.76305, 1.73641],
}


def _lookup_coeff(n, D):
    """查表获取 (k1, k2)。

    D == 100 时取 k2(0.05)（置信度 0.90）；D < 100 时取 k2(0.10)（置信度 0.85）。
    若 n 处于两个键值之间，采用线性插值。
    """
    if n < 10 or n > 500:
        raise ValueError("样本数量超出系数表适用范围")
    keys = sorted(COEFF_TABLE.keys())
    if n in COEFF_TABLE:
        k1, k2_05, k2_10 = COEFF_TABLE[n]
    else:
        # 找到 n 所在的相邻键值区间
        lo = max(k for k in keys if k < n)
        hi = min(k for k in keys if k > n)
        t = (n - lo) / (hi - lo)
        a = COEFF_TABLE[lo]
        b = COEFF_TABLE[hi]
        k1    = a[0] + (b[0] - a[0]) * t
        k2_05 = a[1] + (b[1] - a[1]) * t
        k2_10 = a[2] + (b[2] - a[2]) * t
    k2 = k2_05 if D == 100 else k2_10
    return k1, k2


def batch_assess(D, Xi, design_value, mode="batch"):
    """钻芯法批量推定计算（批评定）。

    参数:
        D: 芯样直径 (mm)，仅接受 100 或 <100
        Xi: 芯样抗压强度换算值列表 (MPa)，已剔除异常值
        design_value: 设计强度等级值 (MPa)，如 C40 输入 40；无则 None
        mode: "batch" 批量检测 或 "single" 单构件检测

    返回 dict，字段:
        mode, n, m_fcu, S_fcu, k1, k2, confidence,
        f_cu_e1 (推定上限), f_cu_e2 (推定下限), delta, delta_max,
        valid (区间是否有效), f_cu_e (最终推定值或 None),
        conclusion (结论措辞), warning (警告信息或 None), error (错误或 None),
        insufficient (芯样数量是否少于规范最小样本量), insufficient_msg (数量不足警告措辞)

    说明:
        批量检测芯样数量少于规范最小样本量（100mm 不宜少于15个、小直径不宜
        少于20个，JGJ/T 384-2016 第6.3.1条）时，仍继续计算批评定值，仅在
        insufficient/insufficient_msg 中给出警告；有效芯样数不足10个时因超出
        推定区间系数表适用范围而无法计算，返回 error。
    """
    result = {
        "mode": mode, "n": len(Xi), "m_fcu": None, "S_fcu": None,
        "k1": None, "k2": None, "confidence": None,
        "f_cu_e1": None, "f_cu_e2": None, "delta": None, "delta_max": None,
        "valid": None, "f_cu_e": None, "conclusion": "", "warning": None,
        "error": None, "insufficient": False, "insufficient_msg": None,
    }

    # ── 第一步：数据预处理与样本数量校验 ──
    n = len(Xi)
    if mode == "batch":
        # 系数表适用范围 n=10~500，不足10个无法查表计算推定区间
        if n < 10:
            result["error"] = "有效芯样数不足10个，超出推定区间系数表适用范围，无法计算。"
            return result
        # JGJ/T 384-2016 第6.3.1条：直径100mm芯样不宜少于15个，小直径芯样
        # 不宜少于20个。数量不足时仍进行批评定计算，但给出警告提示。
        if D == 100 and n < 15:
            result["insufficient"] = True
            result["insufficient_msg"] = (
                f"芯样数量（{n}个）少于规范最小样本量：直径100mm芯样不宜少于15个，"
                "计算结果仅供参考（JGJ/T 384-2016第6.3.1条）。"
            )
        elif D < 100 and n < 20:
            result["insufficient"] = True
            result["insufficient_msg"] = (
                f"芯样数量（{n}个）少于规范最小样本量：小直径芯样不宜少于20个，"
                "计算结果仅供参考（JGJ/T 384-2016第6.3.1条）。"
            )
    else:  # single
        if n < 1:
            result["error"] = "单构件检测芯样数不应少于1个"
            return result

    # ── 第二步：统计参数计算 ──
    m_fcu = sum(Xi) / n
    if n == 1:
        S_fcu = 0.0
    else:
        S_fcu = math.sqrt(sum((x - m_fcu) ** 2 for x in Xi) / (n - 1))
    result["m_fcu"] = m_fcu
    result["S_fcu"] = S_fcu

    # ── 第七步：单构件检测特殊逻辑（不走 K1/K2 与推定区间）──
    if mode == "single":
        if n >= 3:
            f_cu_e = min(Xi)
            result["f_cu_e"] = f_cu_e
            result["warning"] = None
        elif n == 2:
            f_cu_e = min(Xi)
            result["f_cu_e"] = f_cu_e
            result["warning"] = "数据离散性大，仅作参考"
        else:  # n == 1
            f_cu_e = Xi[0]
            result["f_cu_e"] = f_cu_e
            result["warning"] = "严禁以此值作为验收依据，必须补钻"

        # 结论措辞
        if design_value is not None:
            meet = f_cu_e >= design_value
            verb = "满足" if meet else "不满足"
            result["conclusion"] = (
                f"该构件混凝土抗压强度推定值为 {f_cu_e:.1f} MPa，{verb}设计强度等级要求。"
            )
        else:
            result["conclusion"] = f"该构件混凝土抗压强度推定值为 {f_cu_e:.1f} MPa。"
        return result

    # ── 第三步：推定系数 K1、K2 取值（仅 batch）──
    try:
        k1, k2 = _lookup_coeff(n, D)
    except ValueError as e:
        result["error"] = str(e)
        return result
    result["k1"] = k1
    result["k2"] = k2
    result["confidence"] = 0.90 if D == 100 else 0.85

    # ── 第四步：推定区间计算（修约至 0.1 MPa）──
    f_cu_e1 = round(m_fcu - k1 * S_fcu, 1)  # 推定上限值（最终取用值）
    f_cu_e2 = round(m_fcu - k2 * S_fcu, 1)  # 推定下限值
    result["f_cu_e1"] = f_cu_e1
    result["f_cu_e2"] = f_cu_e2

    # ── 第五步：推定区间差值判断（合理性审查）──
    # 区间宽度 Δ = |f_cu,e1 - f_cu,e2|（上限减下限，恒为正）
    delta = round(abs(f_cu_e1 - f_cu_e2), 1)
    delta_max = max(5.0, 0.10 * m_fcu)
    result["delta"] = delta
    result["delta_max"] = round(delta_max, 1)

    if delta <= delta_max:
        result["valid"] = True
        # ── 第六步：最终检测批强度推定值（取区间上限值）──
        f_cu_e = f_cu_e1
        result["f_cu_e"] = f_cu_e
        if design_value is not None:
            meet = f_cu_e >= design_value
            verb = "满足" if meet else "不满足"
            result["conclusion"] = (
                f"该批构件混凝土抗压强度推定值为 {f_cu_e:.1f} MPa，{verb}设计强度等级要求。"
            )
        else:
            result["conclusion"] = f"该批构件混凝土抗压强度推定值为 {f_cu_e:.1f} MPa。"
    else:
        result["valid"] = False
        result["warning"] = "推定区间过宽"
        f_cu_e = f_cu_e1
        result["f_cu_e"] = f_cu_e
        result["conclusion"] = (
            "需增加钻芯样本数量（加密取芯），或重新划分检验批，否则推定值无效。"
        )
    return result
