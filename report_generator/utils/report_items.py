# -*- coding: utf-8 -*-
"""报告“检测内容”使用的标准检测项目名称。

数据采集表按“项目（构件）”建键（如 钻芯法检测（梁）），但报告
“四、检测内容”和首页“检测项目”应使用标准项目名，而不是内部表键。

本模块只做名称归一化，不改数据、不改模板表格标题。
"""
try:
    from report_generator.utils.report_template_map import resolve_sheet_key
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_template_map import resolve_sheet_key


# 用户给定的报告检测项目层级（父级 → 子项）
CATEGORIES = [
    ("混凝土抗压强度检测", [
        "回弹法检测构件混凝土抗压强度",
        "钻芯法检测构件混凝土抗压强度",
        "回弹钻芯修正法检测构件混凝土抗压强度",
    ]),
    ("混凝土构件钢筋配置检测", [
        "剪力墙构件钢筋间距检测",
        "现浇板钢筋间距检测",
        "剪力墙主要受力钢筋根数检测",
        "梁构件底排受力钢筋根数检测",
        "柱构件主要受力钢筋根数检测",
    ]),
    ("混凝土构件尺寸检测", [
        "混凝土板构件结构厚度检测",
        "混凝土剪力墙构件结构厚度检测",
        "混凝土梁构件结构尺寸检测",
        "混凝土柱构件结构尺寸检测",
    ]),
    ("混凝土构件保护层厚度检测", [
        "混凝土梁构件保护层厚度检测",
        "混凝土板构件保护层厚度检测",
        "混凝土剪力墙构件保护层厚度检测",
        "混凝土柱构件保护层厚度检测",
    ]),
    ("填充砌体墙锚固承载力检测", []),
]

# 内部基础项目名 → 报告标准名称
CANONICAL_NAMES = {
    # 混凝土抗压强度
    "回弹法检测": "回弹法检测构件混凝土抗压强度",
    "回弹法检测(主要来源为仪器数据，可选用)": "回弹法检测构件混凝土抗压强度",
    "钻芯法检测": "钻芯法检测构件混凝土抗压强度",
    "回弹钻芯修正法检测": "回弹钻芯修正法检测构件混凝土抗压强度",
    # 钢筋配置
    "剪力墙构件钢筋间距检测": "剪力墙构件钢筋间距检测",
    "现浇板钢筋间距检测": "现浇板钢筋间距检测",
    "剪力墙钢筋根数检测": "剪力墙主要受力钢筋根数检测",
    "梁构件底排受力钢筋根数检测": "梁构件底排受力钢筋根数检测",
    "柱构件主要受力钢筋根数检测": "柱构件主要受力钢筋根数检测",
    # 尺寸/厚度
    "楼板构件厚度检测": "混凝土板构件结构厚度检测",
    "混凝土板结构厚度检测": "混凝土板构件结构厚度检测",
    "剪力墙厚度检测": "混凝土剪力墙构件结构厚度检测",
    "混凝土剪力墙结构厚度检测": "混凝土剪力墙构件结构厚度检测",
    "混凝土梁结构尺寸检测": "混凝土梁构件结构尺寸检测",
    "混凝土柱结构尺寸检测": "混凝土柱构件结构尺寸检测",
    # 保护层
    "混凝土梁保护层厚度检测": "混凝土梁构件保护层厚度检测",
    "混凝土柱保护层厚度检测": "混凝土柱构件保护层厚度检测",
    "剪力墙保护层厚度检测": "混凝土剪力墙构件保护层厚度检测",
    "混凝土板保护层厚度检测": "混凝土板构件保护层厚度检测",
    # 锚固
    "化学植筋锚固承载力检测": "填充砌体墙锚固承载力检测",
}

_CATEGORY_OF = {}
for _category, _children in CATEGORIES:
    _CATEGORY_OF[_category] = _category
    for _child in _children:
        _CATEGORY_OF[_child] = _category


def canonical_name(base, component=None):
    """基础项目名 + 构件 → 报告标准名称。"""
    name = CANONICAL_NAMES.get(str(base or "").strip(), str(base or "").strip())
    component = str(component or "").strip()
    if component and component not in ("构件", "None") and component not in name:
        name = f"{name}（{component}）"
    return name


def display_name(sheet_key):
    """工作表键（项目（构件））→ 报告标准名称。"""
    base, component = resolve_sheet_key(sheet_key)
    return canonical_name(base, component)


def content_names(checked_order):
    """按勾选顺序返回“四、检测内容”/首页使用的名称列表。"""
    names = []
    for key in checked_order or []:
        name = display_name(key)
        if name and name not in names:
            names.append(name)
    return names


def content_groups(checked_order):
    """按父级分类分组，返回 [{category, items}]，保持首次出现顺序。

    叶级项目（分类名与项目名相同，如“填充砌体墙锚固承载力检测”）
    不重复放子项；未收录项目作为独立叶级项保留原名。
    """
    groups = []
    index = {}
    for key in checked_order or []:
        name = display_name(key)
        if not name:
            continue
        category = category_of(key)
        if not category:
            category = name
        child = "" if category == name else name
        if category not in index:
            index[category] = len(groups)
            groups.append({"category": category, "items": []})
        bucket = groups[index[category]]["items"]
        if child and child not in bucket:
            bucket.append(child)
    return groups


def category_of(sheet_key):
    """返回报告父级分类；未收录的项目返回空串。"""
    base, _component = resolve_sheet_key(sheet_key)
    name = CANONICAL_NAMES.get(str(base or "").strip(), "")
    return _CATEGORY_OF.get(name, "")


def category_key(sheet_key):
    """结论编号使用的分类键：父级分类，未收录项目用项目名。"""
    return category_of(sheet_key) or display_name(sheet_key)


def category_number_map(checked_order):
    """父级分类在本次报告中的序号：{分类: 1,2,...}。"""
    return {group["category"]: index
            for index, group in enumerate(content_groups(checked_order), 1)}


def report_order(checked_order):
    """按报告分类顺序重排勾选项，保证表格/结论按“分类 → 子项”排列。

    同一分类内保持原勾选顺序；未收录项目作为独立分类排在最后。
    """
    groups = []
    index = {}
    for key in checked_order or []:
        category = category_key(key)
        if category not in index:
            index[category] = len(groups)
            groups.append([])
        groups[index[category]].append(key)
    ordered = []
    for bucket in groups:
        ordered.extend(bucket)
    return ordered
