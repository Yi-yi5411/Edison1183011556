# -*- coding: utf-8 -*-
"""检测项目 → 报告第三章「主要检测设备」。

名称必须在设备库（data/equipment/equipment.db）里能匹配到仪器；没有专用仪器的
项目显式给空列表，不再用兜底名称「检测设备」占位——那会让报告和设备推荐都失去意义。

用途：
- tools/build_manifests.py 生成 manifest 的 equipment 字段（单一事实来源）；
- 运行期 equipment_store._required_instruments 优先读 manifest 的 equipment。
"""
# 未列出的项目继续沿用 report_narrative.equipment_for 的既有映射
ITEM_EQUIPMENT = {
    # 混凝土抗压强度（与手写 manifest 保持一致）
    "回弹法检测(主要来源为仪器数据，可选用)": ["混凝土回弹仪"],
    "钻芯法检测": ["微控电液伺服压力试验机", "游标卡尺"],
    "回弹钻芯修正法检测": ["混凝土回弹仪", "微控电液伺服压力试验机"],
    # 砖混 / 砌体
    "砖强度检测": ["砖回弹仪"],
    "砌筑砂浆强度检测": ["贯入式砂浆强度检测仪"],
    "砌体构件尺寸偏差检测": ["钢卷尺"],
    # 钢结构
    "化学植筋锚固承载力检测": ["锚杆拉拔仪"],
    "高强度螺栓扭矩系数检测": ["高强螺栓扭矩系数测定仪"],
    "防腐涂层厚度检测": ["涂层测厚仪"],
    "防火涂层厚度检测": ["涂层测厚仪"],
    "钢材强度检测": ["金属硬度计"],
    "焊缝超声波探伤检测": ["超声波探伤仪"],
    # 混凝土构件尺寸
    "混凝土梁结构尺寸检测": ["钢卷尺"],
    "混凝土柱结构尺寸检测": ["钢卷尺"],
    # 木结构
    "木构件尺寸偏差检测": ["钢卷尺"],
    "木构件挠度检测": ["百分表"],
    "木构件缺陷检测": ["钢直尺"],
    # 设备库里没有对应仪器：显式留空，由推荐接口如实报告「无可用仪器」
    "木材含水率检测": [],
}


def lookup(item_name):
    """返回该项目的设备名列表；未覆盖时返回 None（调用方回退到既有映射）。"""
    name = str(item_name or "").strip()
    if not name:
        return None
    if name in ITEM_EQUIPMENT:
        return list(ITEM_EQUIPMENT[name])
    for key, value in ITEM_EQUIPMENT.items():
        if name.startswith(key) or key.startswith(name):
            return list(value)
    return None
