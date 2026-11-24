# -*- coding: utf-8 -*-
"""报告叙述文字生成：工程概况、检测依据、设备、分项检测说明。

说明：此处用确定性的数据事实生成专业叙述，避免模型改写数值；
如需 LLM 润色，可在上层把本模块输出作为事实底稿交给模型。
"""
from collections import Counter

COMMON_STANDARDS = [
    "《混凝土结构现场检测技术标准》GB/T 50784-2013",
    "《混凝土结构工程施工质量验收规范》GB 50204-2015",
]


def _has(checked_order, *words):
    text = " ".join(checked_order or [])
    return any(w in text for w in words)


def standards_for(checked_order):
    standards = list(COMMON_STANDARDS)
    # 回弹钻芯修正法同时依据回弹法与钻芯法两本规程，
    # 且名称里不含"回弹法/钻芯法"连续子串，需要单独识别。
    rebound_core = _has(checked_order, "回弹钻芯")
    if _has(checked_order, "钻芯法") or rebound_core:
        standards.append("《钻芯法检测混凝土强度技术规程》JGJ/T 384-2016")
    if _has(checked_order, "回弹法") or rebound_core:
        standards.append("《回弹法检测混凝土抗压强度技术规程》JGJ/T 23-2011")
    if _has(checked_order, "钢筋间距", "钢筋根数", "受力钢筋", "保护层"):
        standards.append("《混凝土中钢筋检测技术标准》JGJ/T 152-2019")
    if _has(checked_order, "化学植筋", "锚固"):
        standards.extend([
            "《砌体结构工程施工规范》GB 50924-2014",
            "《砌体结构工程施工质量验收规范》GB 50203-2011",
        ])
    standards.extend([
        "委托方提供的设计图纸及相关资料",
        "本项目主体结构实体检测方案",
    ])
    return standards


def overview_text(info):
    """第一章工程概况：优先使用手填概况，否则按已采集字段自动组织。"""
    info = info or {}
    custom = str(info.get("project_overview") or "").strip()
    if custom:
        return custom if custom.endswith(("。", "；", "！")) else custom + "。"

    def text(key):
        return str(info.get(key) or "").strip()

    name = text("project_name")
    location = text("project_location")
    construction = text("construction_unit")
    contractor = text("contractor")
    design = text("design_unit")
    supervision = text("supervision_unit")
    survey = text("survey_unit")
    client = text("client")
    witness = text("witness")
    structure = text("structure_type")
    area = text("building_area")
    floors = text("floor_count")
    height = text("building_height")
    start = text("start_date")
    completion = text("completion_date")
    purpose = text("inspection_purpose")

    parts = []
    if name:
        parts.append("“%s”" % name)
    if location:
        parts.append("位于%s" % location)
    if construction:
        parts.append("建设单位为%s" % construction)
    elif client:
        parts.append("建设单位为%s" % client)
    if design:
        parts.append("设计单位为%s" % design)
    if supervision:
        parts.append("监理单位为%s" % supervision)
    if survey:
        parts.append("勘察单位为%s" % survey)
    if contractor:
        parts.append("施工单位为%s" % contractor)
    if structure:
        parts.append("主体结构类型为%s" % structure)
    if area:
        parts.append("建筑面积约%s" % area)
    if floors:
        parts.append("地上/地下层数为%s" % floors)
    if height:
        parts.append("建筑高度约%s" % height)
    if start or completion:
        date_text = ""
        if start:
            date_text += "开工日期%s" % start
        if completion:
            date_text += ("，" if date_text else "") + "竣工日期%s" % completion
        parts.append(date_text)
    if witness:
        parts.append("见证单位为%s" % witness)
    if purpose:
        parts.append("检测目的为%s" % purpose)
    paragraph = "，".join(parts) + "。" if parts else ""
    return paragraph + "本次对该项目主体结构实体质量进行现场检测。"


def overview_template(info, checked_order=None):
    """可编辑的工程概况模板：已知字段自动带入，缺失项留下填写提示。"""
    info = info or {}

    def text(key):
        return str(info.get(key) or "").strip()

    def fill(value):
        return value if value else "【请填写】"

    items = []
    for key in checked_order or []:
        name = str(key or "").split("（")[0].split("(")[0]
        if name and name not in items:
            items.append(name)
    scope = "、".join(items) if items else "【请填写检测范围】"
    return (
        "本工程为%s，位于%s，建设单位为%s，设计单位为%s，监理单位为%s，"
        "勘察单位为%s，施工单位为%s。主体结构类型为%s，"
        "建筑面积约%s㎡，楼层信息为%s，建筑高度约%sm，开工日期为%s，竣工日期为%s。"
        "本次检测目的为%s，检测范围包括%s。"
        % (
            fill(text("project_name")),
            fill(text("project_location")),
            fill(text("construction_unit") or text("client")),
            fill(text("design_unit")),
            fill(text("supervision_unit")),
            fill(text("survey_unit")),
            fill(text("contractor")),
            fill(text("structure_type")),
            fill(text("building_area")),
            fill(text("floor_count")),
            fill(text("building_height")),
            fill(text("start_date")),
            fill(text("completion_date")),
            fill(text("inspection_purpose")),
            scope,
        )
    )


def equipment_for(checked_order):
    names = []
    if _has(checked_order, "钻芯法"):
        names.append("钻芯机")
    if _has(checked_order, "回弹法"):
        names.append("混凝土回弹仪")
    if _has(checked_order, "钢筋间距", "钢筋根数", "受力钢筋", "保护层"):
        names.append("一体式钢筋扫描仪")
    if _has(checked_order, "厚度"):
        names.append("一体式楼板测厚仪")
    if _has(checked_order, "化学植筋", "锚固"):
        names.append("一体式墙体拉结筋检测仪")
    if not names:
        names.append("检测设备")
    return [{"设备名称": n, "设备分类编号": "", "最近检定日期": "",
             "检定证书编号": ""} for n in names]


def _component_label(base, component):
    if component and component not in ("构件", "None"):
        return component
    for name in ("板", "梁", "柱", "墙"):
        if name in base:
            return name
    return "构件"


def _component_count(base, rows):
    keys = set()
    for row in rows or []:
        if not isinstance(row, (list, tuple)):
            continue
        if "钻芯法" in base:
            # 同一构件的第 2 个芯样行位置/轴线常为空；按楼层+构件编号
            # 计数，避免批次列只在首行有值时把整批拆成多个构件。
            floor = str(row[13]) if len(row) > 13 else ""
            code = str(row[2]) if len(row) > 2 else ""
            key = (floor, code) if code else (
                str(row[3]) if len(row) > 3 else "",
                str(row[4]) if len(row) > 4 else "")
        elif "保护层" in base or "钢筋根数" in base or "受力钢筋" in base:
            key = tuple(str(row[i]) if i < len(row) else ""
                        for i in (1, 2, 3))
        else:
            key = (str(row[1]) if len(row) > 1 else "",)
        if any(key):
            keys.add(key)
    return len(keys) or len(rows or [])


def item_narrative(base, component, rows, conclusion, table_no, item_no,
                   checked_order):
    """返回分项说明段落列表（不含最终结论句）。"""
    base = str(base or "")
    component = _component_label(base, component)
    count = len(rows or [])
    comp_count = _component_count(base, rows)
    try:
        from report_generator.utils.report_items import canonical_name
    except ImportError:  # 以 report_generator/ 为工作目录导入时
        from utils.report_items import canonical_name
    heading_text = canonical_name(base, component)
    heading = "%d、%s：" % (item_no, heading_text)
    if "钻芯法" in base:
        method = ("采用钻芯法检测混凝土%s构件抗压强度，本次共检测%d个构件、%d个芯样。"
                  % (component, comp_count, count))
        basis = ("检测工作按照《钻芯法检测混凝土强度技术规程》"
                 "（JGJ/T 384-2016）的有关规定执行。")
    elif "回弹" in base:
        method = ("采用回弹法检测混凝土%s构件抗压强度，本次共检测%d个构件。"
                  % (component, comp_count))
        basis = ("检测工作按照《回弹法检测混凝土抗压强度技术规程》"
                 "（JGJ/T 23-2011）的有关规定执行。")
    elif "钢筋间距" in base:
        method = ("采用一体式钢筋扫描仪对混凝土%s构件钢筋间距进行检测，"
                  "本次共检测%d个方向。" % (component, count))
        basis = ("检测工作按照《混凝土中钢筋检测技术标准》（JGJ/T 152-2019）"
                 "的有关规定执行。依据《混凝土结构工程施工质量验收规范》"
                 "（GB 50204-2015），受力钢筋间距允许偏差为±10mm。")
    elif "钢筋根数" in base or "受力钢筋" in base:
        method = ("采用一体式钢筋扫描仪对混凝土%s构件受力钢筋根数进行检测，"
                  "本次共检测%d个构件。" % (component, comp_count))
        basis = ("检测工作按照《混凝土中钢筋检测技术标准》（JGJ/T 152-2019）"
                 "的有关规定执行。")
    elif "保护层" in base:
        method = ("采用一体式钢筋扫描仪对混凝土%s构件受力钢筋保护层厚度进行检测，"
                  "本次共检测%d个构件。" % (component, comp_count))
        basis = ("检测工作按照《混凝土中钢筋检测技术标准》（JGJ/T 152-2019）"
                 "的有关规定执行。依据《混凝土结构工程施工质量验收规范》"
                 "（GB 50204-2015）附录E进行评定。")
    elif "植筋" in base or "锚固" in base:
        method = ("采用一体式墙体拉结筋检测仪对填充墙化学植筋锚固承载力进行检测，"
                  "本次共检测%d根。" % count)
        basis = ("检测工作按照《砌体结构工程施工规范》（GB 50924-2014）及"
                 "《砌体结构工程施工质量验收规范》（GB 50203-2011）的有关规定执行。")
    elif "厚度" in base or "结构尺寸" in base:
        method = ("采用检测设备对混凝土%s构件结构尺寸/厚度进行检测，"
                  "本次共检测%d个构件。" % (component, comp_count))
        basis = ("检测工作按照《混凝土结构工程施工质量验收规范》"
                 "（GB 50204-2015）的有关规定执行。")
    else:
        method = "本次共检测%d个构件。" % comp_count
        basis = ("检测工作按照相关检测技术标准及本项目检测方案的有关规定执行。")
    return [heading, method, basis, "检测结果详见表%s。" % table_no]
