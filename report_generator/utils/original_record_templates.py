# -*- coding: utf-8 -*-
"""内置原始记录模板定义（纯数据，无 Qt / docx 依赖）。

原始记录模板按“检测项目基础名”匹配项目树中的项目名（含说明后缀的
全名，如“回弹法检测(主要来源为仪器数据，可选用)”）。真正的 DOCX
渲染见 utils/original_record.py。

字段说明：
  - id/name/code：模板标识、名称、检测编号
  - detection_items：适用的检测项目基础名；空列表表示“通用兜底”
  - columns：参与记录的列；"all" 或列名列表（支持精确/前缀匹配）
  - orientation：portrait / landscape / auto
  - reference_doc：官方 .doc 参考文件（相对项目根，可下载但不参与填充）
  - notes：写入记录底部的备注说明
"""

REBOUND_ITEM = "回弹法检测(主要来源为仪器数据，可选用)"
CORE_ITEM = "钻芯法检测"
REBOUND_CORE_ITEM = "回弹钻芯修正法检测"
REBAR_SPACING_ITEMS = ["剪力墙构件钢筋间距检测", "现浇板钢筋间距检测"]
REBAR_COUNT_ITEMS = ["剪力墙钢筋根数检测", "梁构件底排受力钢筋根数检测",
                     "柱构件主要受力钢筋根数检测"]
COVER_ITEMS = ["混凝土梁保护层厚度检测", "混凝土柱保护层厚度检测",
               "剪力墙保护层厚度检测", "混凝土板保护层厚度检测"]
MEMBER_THICKNESS_ITEMS = ["楼板构件厚度检测", "剪力墙厚度检测"]
MEMBER_SIZE_ITEMS = ["混凝土梁结构尺寸检测", "混凝土柱结构尺寸检测"]
ANCHOR_ITEM = "化学植筋锚固承载力检测"

COVER_COLUMNS = (
    ["楼栋", "楼层", "构件位置及名称", "构件轴线编号", "设计值(mm)", "钢筋根数"]
    + ["实测值%d" % i for i in range(1, 11)]
    + ["合格点率"]
)

REBOUND_DOC = ("original_record/word/"
               "005混凝土抗压强度（回弹法）检测原始记录（JJ0224005）_1733543259775.doc")
CORE_DOC = ("original_record/word/"
            "010钻芯法检测混凝土抗压强度原始记录（JJ0226010）_1784166694983.doc")
REBAR_SPACING_DOC = ("original_record/word/"
                     "013钢筋间距检测原始记录（JJ0226013）_1784167385455.doc")
COVER_DOC = ("original_record/word/"
             "014钢筋保护层厚度检测原始记录（JJ0226014）_1788252756695.doc")
MEMBER_SIZE_DOC = ("original_record/word/"
                   "022截面尺寸检测原始记录（梁柱墙）（JJ0226022）_1784167451005.doc")
MEMBER_THICKNESS_DOC = ("original_record/word/"
                        "027截面尺寸检测原始记录（板厚）（JJ0226027）_1784167529450.doc")
GENERIC_DOC = ("original_record/word/"
               "001现场检测通用原始记录（JJ0226001）_1784166629583.doc")


def _definition(template_id, name, code, items, columns="all",
                orientation="auto", reference_doc="", notes=""):
    return {
        "id": template_id,
        "name": name,
        "code": code,
        "detection_items": list(items or []),
        "columns": columns,
        "orientation": orientation,
        "reference_doc": reference_doc,
        "notes": notes,
    }


BUILTIN_ORIGINAL_TEMPLATES = [
    _definition(
        "builtin_rebound", "混凝土抗压强度（回弹法）检测原始记录",
        "JJ0224005", [REBOUND_ITEM], columns="all", orientation="portrait",
        reference_doc=REBOUND_DOC,
        notes="强度推定值按测区回弹值/碳化深度计算，详见对应检测报告。",
    ),
    _definition(
        "builtin_core_drilling", "钻芯法检测混凝土抗压强度原始记录",
        "JJ0226010", [CORE_ITEM], columns="all", orientation="landscape",
        reference_doc=CORE_DOC,
        notes="同一构件各芯样测试强度的最小值作为该构件推定值。",
    ),
    _definition(
        "builtin_rebound_core", "回弹钻芯修正法检测原始记录",
        "JJ0226010", [REBOUND_CORE_ITEM], columns="all",
        orientation="landscape", reference_doc=CORE_DOC,
        notes="芯样强度用于修正回弹法推定值，批次均值见汇总行。",
    ),
    _definition(
        "builtin_rebar_spacing", "钢筋间距检测原始记录",
        "JJ0226013", REBAR_SPACING_ITEMS, columns="all",
        orientation="landscape", reference_doc=REBAR_SPACING_DOC,
        notes="偏差值 = 实测值 - 设计值；合格点率按允许偏差自动计算。",
    ),
    _definition(
        "builtin_rebar_count", "受力钢筋根数检测原始记录",
        "JJ0226001", REBAR_COUNT_ITEMS, columns="all",
        orientation="portrait", reference_doc=GENERIC_DOC,
        notes="设计根数与实测根数逐构件比对，结论列由录入数据给出。",
    ),
    _definition(
        "builtin_cover", "钢筋保护层厚度检测原始记录",
        "JJ0226014", COVER_ITEMS, columns=COVER_COLUMNS,
        orientation="landscape", reference_doc=COVER_DOC,
        notes="实测值1~10为每根主筋的平均值；同一位置两次读数差>1mm 时该组无效。",
    ),
    _definition(
        "builtin_member_thickness", "构件厚度检测原始记录",
        "JJ0226027", MEMBER_THICKNESS_ITEMS, columns="all",
        orientation="landscape", reference_doc=MEMBER_THICKNESS_DOC,
        notes="允许偏差按构件类型在检测报告中判定。",
    ),
    _definition(
        "builtin_member_size", "截面尺寸检测原始记录",
        "JJ0226022", MEMBER_SIZE_ITEMS, columns="all",
        orientation="landscape", reference_doc=MEMBER_SIZE_DOC,
        notes="宽度/高度平均值与偏差值由系统自动计算。",
    ),
    _definition(
        "builtin_anchor", "化学植筋锚固承载力检测原始记录",
        "JJ0226001", [ANCHOR_ITEM], columns="all",
        orientation="portrait", reference_doc=GENERIC_DOC,
        notes="检测荷载、持荷2min降低率与实测现象共同决定结论。",
    ),
    _definition(
        "builtin_generic", "现场检测通用原始记录",
        "JJ0226001", [], columns="all", orientation="auto",
        reference_doc=GENERIC_DOC,
        notes="通用电子原始记录：表头信息 + 检测数据 + 签字栏。",
    ),
]


def get_builtin_definition(template_id):
    """按 ID 取内置定义副本；不存在返回 None。"""
    for item in BUILTIN_ORIGINAL_TEMPLATES:
        if item["id"] == template_id:
            return dict(item)
    return None


def match_builtin_template(base_item):
    """按检测项目基础名匹配内置模板；未命中返回通用模板。"""
    base = str(base_item or "").strip()
    if base:
        for item in BUILTIN_ORIGINAL_TEMPLATES:
            if base in item.get("detection_items", []):
                return dict(item)
    return get_builtin_definition("builtin_generic")
