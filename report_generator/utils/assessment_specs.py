# -*- coding: utf-8 -*-
"""检测评定规则的机器可读定义（纯数据，无 Qt / docx 依赖）。

每套规则来自 prompt/01~13 的检测评定提示词。字段：
  - id/name/base_items：规则标识、名称、匹配的检测项目基础名
  - family：rebound / core / section / thickness / spacing / count / cover / anchor / record_check / brick
  - implemented：当前是否已实现评定
  - needs_raw_input：是否需要额外原始数据（如回弹测区值、回弹钻芯修正对）
  - required_fields：填写要求（供表单/校验/Agent 使用）
  - templates：结论句式（占位符由 assessment_engine 填充）
  - thresholds：允许偏差/合格点率/正负偏差比例等阈值

结论模板中的占位符统一为 {component}/{count}/{value_range}/{rate}/
{failed_details}/{table_no}/{thickness_label} 等，由引擎填充。
"""
from copy import deepcopy

# ── 通用结论句式 ──────────────────────────────────────────────
def _strength_templates(prefix):
    return {
        "single_pass": prefix + "所检{component}构件混凝土抗压强度推定值范围为{value_range}，均满足相应设计强度等级要求。",
        "single_partial": prefix + "所抽检{count}个{component}构件中，有{failed_count}个混凝土抗压强度推定值不满足设计要求，其余构件均满足设计要求。详见表{table_no}。",
        "single_all_fail": prefix + "所抽检的全部（{count}个）{component}构件混凝土抗压强度推定值均未达到相应设计强度等级要求。",
        "batch_pass": prefix + "所抽检{component}构件批混凝土抗压强度推定值为{value_range}，满足相应设计强度等级要求。",
        "batch_partial": prefix + "所抽检{component}构件批混凝土抗压强度推定值为{value_range}，其中{failed_details}。",
        "batch_all_fail": prefix + "所抽检的全部批量检验批评定值均未达到相应设计强度等级要求。",
        "no_drawing": prefix + "所检{component}构件混凝土抗压强度推定值范围为{value_range}，详见表{table_no}。",
    }


def _section_templates(component, project):
    return {
        "pass": "所检%s构件%s实测偏差平均值合格点率为{rate}%%，符合《混凝土结构工程施工质量验收规范》GB 50204-2015第3.0.4条之规定。" % (component, project),
        "fail_rate": "所检%s构件%s实测偏差平均值合格点率为{rate}%%，不符合《混凝土结构工程施工质量验收规范》GB 50204-2015第3.0.4条之规定。" % (component, project),
        "fail_high": "检测结果表明：所抽检%s构件%s实测偏差平均值合格点率为{rate}%%，主要表现为实测正偏差超出规范要求，即%s截面尺寸偏大，不会对结构安全产生不利影响。" % (component, project, component),
        "component_stats": "所抽检%s构件%s为实测值；全楼共抽取了{component_count}处%s构件%s（构件数），其中符合规范共{qualified}处，占所检总数的{qualified_rate}%%；符合要求共{meets}处，占所检总数的{meets_rate}%%；不符合规范共{unqualified}处，占所检总数的{unqualified_rate}%%。" % (component, project, component, project),
        "no_drawing": "所检%s构件%s实测偏差为{value_range}，详见表{table_no}。" % (component, project),
    }


def _thickness_templates(thickness_label):
    return {
        "pass": "所检混凝土结构构件结构厚度实测偏差平均值合格点率为{rate}%，符合《混凝土结构工程施工质量验收规范》GB 50204-2015第3.0.4条之规定。",
        "fail_rate": "所检混凝土结构构件结构厚度实测偏差平均值合格点率为{rate}%，不符合《混凝土结构工程施工质量验收规范》GB 50204-2015第3.0.4条之规定。",
        "fail_high": "检测结果表明：所抽检混凝土结构构件结构厚度实测偏差平均值合格点率为{rate}%%，主要表现为实测正偏差超出规范要求，即%s偏厚，不会对结构安全产生不利影响。" % thickness_label,
        "component_stats": "所抽检混凝土结构构件结构厚度为实测值；全楼共抽取了{component_count}处混凝土结构构件结构厚度（构件数），其中符合规范共{qualified}处，占所检总数的{qualified_rate}%；符合要求共{meets}处，占所检总数的{meets_rate}%；不符合规范共{unqualified}处，占所检总数的{unqualified_rate}%。",
        "no_drawing": "所检混凝土结构构件结构厚度实测偏差为{value_range}，详见表{table_no}。",
    }


def _spacing_templates(component):
    return {
        "pass": "所检%s构件钢筋间距实测偏差平均值合格点率为{rate}%%，符合《混凝土结构工程施工质量验收规范》GB 50204-2015第3.0.4条之规定。" % component,
        "fail_rate": "所检%s构件钢筋间距实测偏差平均值合格点率为{rate}%%，不符合《混凝土结构工程施工质量验收规范》GB 50204-2015第3.0.4条之规定。" % component,
        "fail_high": "检测结果表明：所抽检%s构件钢筋间距实测偏差平均值合格点率为{rate}%%，主要表现为实测负偏差超出规范要求，即钢筋间距偏密，不会对结构安全产生不利影响。" % component,
        "component_stats": "所抽检%s构件钢筋间距为实测值；全楼共抽取了{component_count}处%s构件钢筋间距（构件数），其中符合规范共{qualified}处，占所检总数的{qualified_rate}%%；符合要求共{meets}处，占所检总数的{meets_rate}%%；不符合规范共{unqualified}处，占所检总数的{unqualified_rate}%%。" % (component, component),
        "no_drawing": "所检%s构件钢筋间距实测偏差为{value_range}，详见表{table_no}。" % component,
    }


def _count_templates(component, project):
    return {
        "pass": "所检%s构件%s均符合设计要求。" % (component, project),
        "fail": "所检%s构件%s符合设计要求的有{qualified}个，不符合设计要求的有{unqualified}个。" % (component, project),
        "no_drawing": "所检%s构件%s为实测值，详见表{table_no}。" % (component, project),
    }


def _cover_templates(component):
    return {
        "pass": "所检%s构件受力钢筋保护层厚度实测偏差值合格点率为{rate}%%，符合《混凝土结构工程施工质量验收规范》GB 50204-2015第E.0.5条之规定。" % component,
        "fail_rate": "所检%s构件受力钢筋保护层厚度实测偏差值合格点率为{rate}%%，不符合《混凝土结构工程施工质量验收规范》GB 50204-2015第E.0.5条之规定。" % component,
        "veto": "所检%s构件受力钢筋保护层厚度实测偏差值合格点率为{rate}%%，但{location}受力钢筋保护层厚度实测偏差已超过允许偏差的1.5倍，不符合《混凝土结构工程施工质量验收规范》GB 50204-2015第E.0.5条之规定。" % component,
        "no_drawing": "由于设计值缺失，本次检测仅提供所抽检%s构件受力钢筋保护层厚度实测值，详见表{table_no}。" % component,
    }


def _record_templates(label):
    """逐行结论汇总型句式；没有判定依据时明确只记录、不判定。"""
    return {
        "pass": "经检测，所检%s满足设计及规范要求。" % label,
        "fail": "经检测，所检%s有{failed_count}处不满足设计及规范要求，应进行复核处理。{failed_details}" % label,
        "partial": "所检%s部分项目未提供判定结论，本次仅提供检测结果，不作整体判定。" % label,
        "no_judgement": "所检%s已记录实测值；因缺少设计允许值/判定依据，本次仅提供检测结果，不作合格判定。" % label,
    }


# ── 规则清单 ──────────────────────────────────────────────────
_COMMON_STRENGTH_FIELDS = [
    {"key": "floor", "label": "楼层", "type": "string", "required": False},
    {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
    {"key": "axis", "label": "轴线编号", "type": "string", "required": False},
    {"key": "grade", "label": "设计强度等级", "type": "string", "required": False,
     "note": "如 C30；设计值为 / 表示无图纸"},
]

ASSESSMENT_SPECS = [
    {
        "id": "rebound",
        "base_items": ["回弹法检测"],
        "name": "回弹法检测",
        "family": "rebound",
        "implemented": True,
        "needs_raw_input": True,
        "component_label": "混凝土{component}",
        "project_label": "回弹法",
        "required_fields": _COMMON_STRENGTH_FIELDS + [
            {"key": "zones", "label": "测区混凝土强度换算值", "type": "list[number]",
             "required": True, "note": "每个构件至少 1 个测区值；n<10 取最小值，n≥10 取 m-1.645s"},
        ],
        "templates": _strength_templates("回弹法"),
        "thresholds": {"pass_rate": 80.0, "batch_min_n": 10,
                       "std_low_mean": 25.0, "std_low": 4.5,
                       "std_normal": 5.5, "min_zone_value": 10.0},
        "description": "回弹法：按构件类型+设计等级分批评定；无有效批时按单构件评定；无图纸走类型三。",
    },
    {
        "id": "rebound_core",
        "base_items": ["回弹钻芯修正法检测"],
        "name": "回弹钻芯修正法检测",
        "family": "rebound_core",
        "implemented": True,
        "needs_raw_input": True,
        "component_label": "混凝土{component}",
        "project_label": "回弹-钻芯修正法",
        "required_fields": _COMMON_STRENGTH_FIELDS + [
            {"key": "zones", "label": "测区混凝土强度换算值", "type": "list[number]", "required": True},
            {"key": "cores", "label": "芯样实测强度与对应测区换算值", "type": "list[{actual, zone}]", "required": True},
            {"key": "diameter", "label": "芯样直径(mm)", "type": "number", "required": True},
            {"key": "method", "label": "修正方式", "type": "string", "required": False,
             "note": "修正系数法（默认）/ 修正量法"},
        ],
        "templates": _strength_templates("回弹-钻芯修正法"),
        "thresholds": {"pass_rate": 80.0, "batch_min_n": 10, "correction_min_n": 6,
                       "std_low_mean": 25.0, "std_low": 4.5, "std_normal": 5.5,
                       "min_zone_value": 10.0},
        "description": "回弹钻芯修正法：先按修正批（同构件类型+等级+直径，n≥6）计算修正系数/修正量，再按回弹法推定与批评定。",
    },
    {
        "id": "core",
        "base_items": ["钻芯法检测"],
        "name": "钻芯法检测",
        "family": "core",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土{component}",
        "project_label": "钻芯法",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "axis", "label": "轴线编号", "type": "string", "required": False},
            {"key": "grade", "label": "设计强度等级", "type": "string", "required": False},
            {"key": "diameter", "label": "芯样直径D(mm)", "type": "number", "required": True},
            {"key": "strength", "label": "芯样测试强度(MPa)", "type": "number", "required": True},
        ],
        "templates": _strength_templates("钻芯法"),
        "thresholds": {"pass_rate": 80.0, "d100_min_n": 15, "small_min_n": 20,
                       "min_zone_value": 10.0},
        "description": "钻芯法：单构件 n<3 取最小值并提示补钻；批评定 D=100 n≥15、D<100 n≥20，K1/K2 推定上限。",
    },
    {
        "id": "section_beam",
        "base_items": ["混凝土梁结构尺寸检测"],
        "name": "混凝土梁结构尺寸检测",
        "family": "section",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土梁",
        "project_label": "截面尺寸",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design_b", "label": "设计宽度B(mm)", "type": "number", "required": True},
            {"key": "design_h", "label": "设计高度H(mm)", "type": "number", "required": True},
            {"key": "measured_b", "label": "实测宽度B1~B3(mm)", "type": "list[number]", "required": True},
            {"key": "measured_h", "label": "实测高度H1~H3(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _section_templates("混凝土梁", "截面尺寸"),
        "thresholds": {"lower": -5.0, "upper": 10.0, "pass_rate": 80.0,
                       "high_ratio": 0.6},
        "description": "截面尺寸：宽度/高度分别作为一个测点；偏差在[-5,+10]为符合规范；测点合格点率≥80%合格。",
    },
    {
        "id": "section_column",
        "base_items": ["混凝土柱结构尺寸检测"],
        "name": "混凝土柱结构尺寸检测",
        "family": "section",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土柱",
        "project_label": "截面尺寸",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design_b", "label": "设计宽度B(mm)", "type": "number", "required": True},
            {"key": "design_h", "label": "设计高度H(mm)", "type": "number", "required": True},
            {"key": "measured_b", "label": "实测宽度B1~B3(mm)", "type": "list[number]", "required": True},
            {"key": "measured_h", "label": "实测高度H1~H3(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _section_templates("混凝土柱", "截面尺寸"),
        "thresholds": {"lower": -5.0, "upper": 10.0, "pass_rate": 80.0,
                       "high_ratio": 0.6},
        "description": "截面尺寸：宽度/高度分别作为一个测点；偏差在[-5,+10]为符合规范；测点合格点率≥80%合格。",
    },
    {
        "id": "thickness_wall",
        "base_items": ["剪力墙厚度检测"],
        "name": "剪力墙厚度检测",
        "family": "thickness",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土结构构件结构厚度",
        "project_label": "混凝土结构构件结构厚度",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计厚度(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~3(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _thickness_templates("混凝土剪力墙厚度"),
        "thresholds": {"lower": -5.0, "upper": 10.0, "pass_rate": 80.0,
                       "high_ratio": 0.6},
        "description": "剪力墙厚度：逐测点计算偏差；直接以已有偏差判定三类；测点合格点率≥80%合格。",
    },
    {
        "id": "thickness_slab",
        "base_items": ["楼板构件厚度检测"],
        "name": "楼板构件厚度检测",
        "family": "thickness",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土结构构件结构厚度",
        "project_label": "混凝土结构构件结构厚度",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计厚度(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~3(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _thickness_templates("混凝土板厚度"),
        "thresholds": {"lower": -5.0, "upper": 10.0, "pass_rate": 80.0,
                       "high_ratio": 0.6},
        "description": "板厚：逐测点计算偏差；直接以已有偏差判定三类；测点合格点率≥80%合格。",
    },
    {
        "id": "spacing_slab",
        "base_items": ["现浇板钢筋间距检测"],
        "name": "现浇板钢筋间距检测",
        "family": "spacing",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土板",
        "project_label": "钢筋间距",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "direction", "label": "方向", "type": "string", "required": True,
             "note": "竖向/横向"},
            {"key": "design", "label": "设计值(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~6(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _spacing_templates("混凝土板"),
        "thresholds": {"lower": -10.0, "upper": 10.0, "pass_rate": 80.0,
                       "low_ratio": 0.6},
        "description": "板钢筋间距：每个方向为一个测点；偏差±10mm；负偏差偏密为符合要求；合格点率≥80%合格。",
    },
    {
        "id": "spacing_wall",
        "base_items": ["剪力墙构件钢筋间距检测"],
        "name": "剪力墙构件钢筋间距检测",
        "family": "spacing",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土剪力墙",
        "project_label": "钢筋间距",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "direction", "label": "方向", "type": "string", "required": True,
             "note": "水平/竖向"},
            {"key": "design", "label": "设计值(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~6(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _spacing_templates("混凝土剪力墙"),
        "thresholds": {"lower": -10.0, "upper": 10.0, "pass_rate": 80.0,
                       "low_ratio": 0.6},
        "description": "墙钢筋间距：每个方向为一个测点；偏差±10mm；负偏差偏密为符合要求；合格点率≥80%合格。",
    },
    {
        "id": "count_beam",
        "base_items": ["梁构件底排受力钢筋根数检测"],
        "name": "梁构件底排受力钢筋根数检测",
        "family": "count",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土梁",
        "project_label": "底排受力钢筋根数",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计根数", "type": "number", "required": True},
            {"key": "measured", "label": "实测根数", "type": "number", "required": True},
        ],
        "templates": _count_templates("混凝土梁", "底排受力钢筋根数"),
        "thresholds": {},
        "description": "梁根数：实测=设计为合格；结论禁止出现楼层范围。",
    },
    {
        "id": "count_column",
        "base_items": ["柱构件主要受力钢筋根数检测"],
        "name": "柱构件主要受力钢筋根数检测",
        "family": "count",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土柱",
        "project_label": "受力钢筋（b边、h边）根数",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design_b", "label": "设计根数-b", "type": "number", "required": True},
            {"key": "design_h", "label": "设计根数-h", "type": "number", "required": True},
            {"key": "measured_b", "label": "实测根数-b", "type": "number", "required": True},
            {"key": "measured_h", "label": "实测根数-h", "type": "number", "required": True},
        ],
        "templates": _count_templates("混凝土柱", "受力钢筋（b边、h边）根数"),
        "thresholds": {},
        "description": "柱根数：b边与h边均相等才合格。",
    },
    {
        "id": "count_wall",
        "base_items": ["剪力墙钢筋根数检测"],
        "name": "剪力墙钢筋根数检测",
        "family": "count",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土剪力墙",
        "project_label": "受力钢筋（b边、h边）根数",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design_b", "label": "设计根数-b", "type": "number", "required": True},
            {"key": "design_h", "label": "设计根数-h", "type": "number", "required": True},
            {"key": "measured_b", "label": "实测根数-b", "type": "number", "required": True},
            {"key": "measured_h", "label": "实测根数-h", "type": "number", "required": True},
        ],
        "templates": _count_templates("混凝土剪力墙", "受力钢筋（b边、h边）根数"),
        "thresholds": {},
        "description": "墙根数：b边与h边均相等才合格。",
    },
    {
        "id": "cover_beam",
        "base_items": ["混凝土梁保护层厚度检测"],
        "name": "混凝土梁保护层厚度检测",
        "family": "cover",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土梁",
        "project_label": "受力钢筋保护层厚度",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计值(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~10(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _cover_templates("混凝土梁"),
        "thresholds": {"lower": -7.0, "upper": 10.0, "pass_rate": 90.0,
                       "veto_lower": -10.5, "veto_upper": 15.0},
        "description": "保护层：合格点率≥90%合格，80~90%再抽检，<80%不合格；偏差超过允许偏差1.5倍一票否决。",
    },
    {
        "id": "cover_column",
        "base_items": ["混凝土柱保护层厚度检测"],
        "name": "混凝土柱保护层厚度检测",
        "family": "cover",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土柱",
        "project_label": "受力钢筋保护层厚度",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计值(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~10(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _cover_templates("混凝土柱"),
        "thresholds": {"lower": -7.0, "upper": 10.0, "pass_rate": 90.0,
                       "veto_lower": -10.5, "veto_upper": 15.0},
        "description": "保护层：合格点率≥90%合格，80~90%再抽检，<80%不合格；偏差超过允许偏差1.5倍一票否决。",
    },
    {
        "id": "cover_wall",
        "base_items": ["剪力墙保护层厚度检测"],
        "name": "剪力墙保护层厚度检测",
        "family": "cover",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土剪力墙",
        "project_label": "受力钢筋保护层厚度",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计值(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~10(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _cover_templates("混凝土剪力墙"),
        "thresholds": {"lower": -5.0, "upper": 8.0, "pass_rate": 90.0,
                       "veto_lower": -7.5, "veto_upper": 12.0},
        "description": "保护层：合格点率≥90%合格，80~90%再抽检，<80%不合格；偏差超过允许偏差1.5倍一票否决。",
    },
    {
        "id": "cover_slab",
        "base_items": ["混凝土板保护层厚度检测"],
        "name": "混凝土板保护层厚度检测",
        "family": "cover",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "混凝土板",
        "project_label": "受力钢筋保护层厚度",
        "required_fields": [
            {"key": "floor", "label": "楼层", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": True},
            {"key": "design", "label": "设计值(mm)", "type": "number", "required": True},
            {"key": "measured", "label": "实测值1~10(mm)", "type": "list[number]", "required": True},
        ],
        "templates": _cover_templates("混凝土板"),
        "thresholds": {"lower": -5.0, "upper": 8.0, "pass_rate": 90.0,
                       "veto_lower": -7.5, "veto_upper": 12.0},
        "description": "保护层：合格点率≥90%合格，80~90%再抽检，<80%不合格；偏差超过允许偏差1.5倍一票否决。",
    },
    {
        "id": "anchor_bearing",
        "base_items": ["化学植筋锚固承载力检测", "填充砌体墙锚固承载力检测"],
        "name": "填充砌体墙锚固承载力检测",
        "family": "anchor",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "填充砌体墙化学植筋",
        "project_label": "锚固承载力",
        "required_fields": [
            {"key": "component", "label": "构件名称", "type": "string", "required": True},
            {"key": "axis", "label": "构件轴线编号", "type": "string", "required": False},
            {"key": "grade", "label": "钢筋牌号/植筋规格", "type": "string", "required": False},
            {"key": "diameter", "label": "公称直径(mm)", "type": "number", "required": False},
            {"key": "load", "label": "检测荷载(kN)", "type": "number", "required": True},
            {"key": "drop", "label": "持荷2min内荷载值降低率", "type": "number", "required": True},
            {"key": "phenomenon", "label": "实测现象", "type": "string", "required": False},
            {"key": "conclusion", "label": "结论", "type": "string", "required": False},
        ],
        "templates": {
            "pass": "经检测，所检填充砌体墙化学植筋锚固承载力满足设计要求。",
            "fail": "经检测，所检填充砌体墙化学植筋锚固承载力有{failed_count}根不满足设计要求，应进行复核处理。{failed_details}",
        },
        "thresholds": {"min_load": 6.0, "max_drop": 0.05},
        "description": "化学植筋锚固承载力：逐根检查检测荷载、持荷2min荷载降低率、试验现象/结论；全部满足为合格，任一根不满足进入复核。",
    },
    {
        "id": "brick",
        "base_items": ["砖强度检测"],
        "name": "砖强度检测（回弹法）",
        "family": "brick",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": "砖砌体",
        "project_label": "砖强度",
        "required_fields": [
            {"key": "batch", "label": "批次", "type": "string", "required": False},
            {"key": "component_code", "label": "构件编号", "type": "string", "required": False},
            {"key": "design_grade", "label": "设计强度等级", "type": "string", "required": False,
             "note": "如 MU10；不填则只报告评定等级"},
        ],
        "templates": {
            "pass": "所检砖砌体砖强度评定为{grade}，满足设计强度等级{design_grade}要求。",
            "fail": "所检砖砌体砖强度评定为{grade}，不满足设计强度等级{design_grade}要求。",
            "no_design": "所检砖砌体砖强度评定为{grade}，本次仅提供检测结果。",
        },
        "thresholds": {
            "cv_split": 0.21,
            "grades": {"MU30": [30.0, 23.0, 26.0],
                       "MU25": [25.0, 19.0, 21.0],
                       "MU20": [20.0, 14.0, 16.0],
                       "MU15": [15.0, 10.0, 12.0],
                       "MU10": [10.0, 6.5, 7.5]},
        },
        "description": "砖回弹法：按构件平均强度统计批次平均值、标准差、变异系数和强度标准值，按 GB 5101 评定 MU10~MU30；可填写设计等级判断是否满足设计要求。",
    },
]


# 逐行结论汇总型项目：采集表已有“结论/等级评定”列时按逐行结论汇总；
# 没有判定列的项目（砌体尺寸、木尺寸、木缺陷）只记录实测值，不擅自判定。
_RECORD_CHECK_ITEMS = [
    ("masonry_dimension", "砌体构件尺寸偏差检测", "砌体构件尺寸偏差"),
    ("mortar_strength", "砌筑砂浆强度检测", "砌筑砂浆强度"),
    ("steel_bolt_torque", "高强度螺栓扭矩系数检测", "高强度螺栓扭矩系数"),
    ("coating_anti_corrosion", "防腐涂层厚度检测", "防腐涂层厚度"),
    ("coating_fireproof", "防火涂层厚度检测", "防火涂层厚度"),
    ("steel_strength", "钢材强度检测", "钢材强度"),
    ("weld_ut", "焊缝超声波探伤检测", "焊缝超声波探伤"),
    ("wood_defect", "木构件缺陷检测", "木构件缺陷"),
    ("wood_deflection", "木构件挠度检测", "木构件挠度"),
    ("wood_dimension", "木构件尺寸偏差检测", "木构件尺寸偏差"),
    ("wood_moisture", "木材含水率检测", "木材含水率"),
]

for _id, _base, _label in _RECORD_CHECK_ITEMS:
    ASSESSMENT_SPECS.append({
        "id": _id,
        "base_items": [_base],
        "name": _base,
        "family": "record_check",
        "implemented": True,
        "needs_raw_input": False,
        "component_label": _label,
        "project_label": _label,
        "required_fields": [],
        "templates": _record_templates(_label),
        "thresholds": {},
        "description": "按采集表逐行结论/等级评定汇总；没有判定依据时仅记录实测值，不作合格判定。",
    })


def get_spec(base_item):
    """按检测项目基础名取规则（支持带说明后缀的树名）。"""
    base = str(base_item or "").strip()
    if not base:
        return None
    for spec in ASSESSMENT_SPECS:
        if base in spec["base_items"]:
            return deepcopy(spec)
    for spec in ASSESSMENT_SPECS:
        for name in spec["base_items"]:
            if base.startswith(name):
                return deepcopy(spec)
    return None


def list_specs():
    """返回规则摘要列表（供 API/前端/Agent 读取）。"""
    out = []
    for spec in ASSESSMENT_SPECS:
        item = {k: deepcopy(v) for k, v in spec.items() if k != "templates"}
        item["template_count"] = len(spec.get("templates") or {})
        out.append(item)
    return out
