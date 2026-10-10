# -*- coding: utf-8 -*-
"""检测报告模板映射与句式数据（纯数据，无 Qt 依赖）。

内容：
  - TEMPLATE_DIR：report_template/ 目录定位
  - CHAPTER_TEMPLATES：封面与各章节模板文件名
  - SHEET_TEMPLATE_MAP：工作表键（基础项目名, 构件）→ 结果一览表模板
  - REPORT_INFO_FIELDS：报告抬头信息字段
  - CONCLUSION_TEMPLATES：六、检测结论的按项目句式

键名核对依据：各插件 ``tree_entries()``（未覆盖者即 ``columns()`` 键）；
模板文件名以 report_template/五、实际检测内容模板/ 实际文件为准。
"""
from datetime import datetime
import re

try:
    from report_generator.framework.resources import resolve_path
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from framework.resources import resolve_path

TEMPLATE_DIR = resolve_path("report_template")
RESULT_DIR_NAME = "五、实际检测内容模板"

# ── 封面与章节模板 ──
CHAPTER_TEMPLATES = {
    "cover_main": "封面-项目名称.docx",      # 基准文档
    "cover_home": "封面-首页.docx",
    "overview": "一、工程概况-概况.docx",
    "basis": "二、主要检测依据-依据.docx",
    "equipment": "三、主要检测设备-设备.docx",
    "content": "四、检测内容-内容概述.docx",
    "result_intro": "五、检测结果-概述.docx",
    "conclusion": "六、检测结论-结论.docx",
}

# ── 钻芯/修正法共用别名：模板表头文本 → 可接受的 GUI 列名 ──
_CORE_ALIASES = {
    "芯样砼抗压强度测试值": ["测试强度(MPa)"],
    "构件混凝土抗压强度推定值": ["推定值(MPa)"],
    "批混凝土强度推定值": ["批评定值(MPa)"],
    "设计强度等级": ["设计等级"],
    "构件名称": ["构件位置及名称"],
    "构件轴号": ["轴线编号", "构件轴线编号"],
}
# 偏差值类（钢筋间距/保护层）：实测偏差值N ← 实测偏差值N / 实测值N
_DEVIATION_ALIASES = {
    **{f"实测偏差值{i}": [f"实测偏差值{i}", f"实测值{i}"] for i in range(1, 11)},
    # 模板"实测偏差平均值"对应录入的偏差值平均值（difflib 会误配到实测值平均值）
    "实测偏差平均值": ["偏差值平均值"],
    "构件轴号": ["构件轴线编号", "轴线编号"],
    "结论": ["合格/不合格"],
}

def _t(name):
    return f"{RESULT_DIR_NAME}/{name}"

# ── 工作表键 → 结果一览表模板 ──
# 值 = (模板相对文件名, 表头行数, 列别名dict)
SHEET_TEMPLATE_MAP = {
    # 回弹法检测（构件：梁/墙/柱/基础）
    ("回弹法检测", "墙"): (_t("五、检测结果-表5.1.1 回弹法检测混凝土墙构件抗压强度结果一览表.docx"), 1, {}),
    ("回弹法检测", "柱"): (_t("五、检测结果-表5.1.2 回弹法检测混凝土柱构件抗压强度结果一览表.docx"), 1, {}),
    ("回弹法检测", "梁"): (_t("五、检测结果-表5.1.3 回弹法检测混凝土梁构件抗压强度结果一览表.docx"), 1, {}),
    ("回弹法检测", "基础"): (_t("五、检测结果-表5.1.5 回弹法检测混凝土基础构件抗压强度结果一览表.docx"), 1, {}),
    # 钻芯法检测（构件：梁/柱/板/剪力墙/基础）
    ("钻芯法检测", "剪力墙"): (_t("五、检测结果-表5.2.1 钻芯法检测混凝土墙构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("钻芯法检测", "柱"): (_t("五、检测结果-表5.2.2 钻芯法检测混凝土柱构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("钻芯法检测", "梁"): (_t("五、检测结果-表5.2.3 钻芯法检测混凝土梁构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("钻芯法检测", "板"): (_t("五、检测结果-表5.2.4 钻芯法检测混凝土板构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("钻芯法检测", "基础"): (_t("五、检测结果-表5.2.5 钻芯法检测混凝土基础构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    # 回弹钻芯修正法检测（构件：梁/柱/板/剪力墙/基础）
    ("回弹钻芯修正法检测", "剪力墙"): (_t("五、检测结果-表5.3.1 回弹钻芯法修正法检测混凝土（墙）构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("回弹钻芯修正法检测", "柱"): (_t("五、检测结果-表5.3.2 回弹钻芯法修正法检测混凝土（柱）构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("回弹钻芯修正法检测", "梁"): (_t("五、检测结果-表5.3.3 回弹钻芯法修正法检测混凝土（梁）构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("回弹钻芯修正法检测", "板"): (_t("五、检测结果-表5.3.4 回弹钻芯法修正法检测混凝土（板）构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    ("回弹钻芯修正法检测", "基础"): (_t("五、检测结果-表5.3.5 回弹钻芯法修正法检测混凝土（基础）构件抗压强度结果一览表.docx"), 1, _CORE_ALIASES),
    # 钢筋配置（无构件维度）
    ("剪力墙钢筋根数检测", None): (_t("五、检测结果-表5.4.1 剪力墙构件钢筋数量检测结果一览表.docx"), 1, {}),
    ("剪力墙构件钢筋间距检测", None): (_t("五、检测结果-表5.4.2 剪力墙墙身钢筋间距检测结果一览表.docx"), 2, _DEVIATION_ALIASES),
    ("梁构件底排受力钢筋根数检测", None): (_t("五、检测结果-表5.4.3 混凝土梁构件钢筋数量检测结果一览表.docx"), 1, {}),
    ("柱构件主要受力钢筋根数检测", None): (_t("五、检测结果-表5.4.4 混凝土柱构件钢筋数量检测结果一览表.docx"), 1, {}),
    ("现浇板钢筋间距检测", None): (_t("五、检测结果-表5.4.5 现浇混凝土板构件钢筋间距检测结果一览表.docx"), 2, _DEVIATION_ALIASES),
    # 钢筋保护层厚度（无构件维度）
    ("剪力墙保护层厚度检测", None): (_t("五、检测结果-表5.5.1 混凝土剪力墙构件钢筋保护层厚度检测结果一览表.docx"), 2, _DEVIATION_ALIASES),
    ("混凝土板保护层厚度检测", None): (_t("五、检测结果-表5.5.2 混凝土现浇板构件钢筋保护层厚度检测结果一览表.docx"), 2, _DEVIATION_ALIASES),
    ("混凝土柱保护层厚度检测", None): (_t("五、检测结果-表5.5.3 混凝土柱构件钢筋保护层厚度检测结果一览表.docx"), 2, _DEVIATION_ALIASES),
    ("混凝土梁保护层厚度检测", None): (_t("五、检测结果-表5.5.4 混凝土梁构件钢筋保护层厚度检测结果一览表.docx"), 2, _DEVIATION_ALIASES),
    # 混凝土构件尺寸/厚度
    ("剪力墙厚度检测", None): (_t("五、检测结果-表5.6.1 混凝土剪力墙构件结构厚度检测一览表.docx"), 1, {}),
    ("楼板构件厚度检测", None): (_t("五、检测结果-表5.6.2 楼板构件结构厚度检测结果一览表.docx"), 1, {}),
    ("混凝土梁结构尺寸检测", None): (_t("五、检测结果-表5.6.3 混凝土梁构件截面尺寸检测结果一览表.docx"), 1, {}),
    ("混凝土柱结构尺寸检测", None): (_t("五、检测结果-表5.6.4 混凝土柱构件截面尺寸检测结果一览表.docx"), 1, {}),
    # 填充墙化学植筋锚固承载力
    ("化学植筋锚固承载力检测", None): (_t("五、检测结果-表5.7 填充墙化学植筋锚固承载力试验结果一览表.docx"), 1, {}),
}

# 已知基础项目名（用于 sheet_key 归一化），长名优先匹配
_KNOWN_BASES = sorted({b for b, _c in SHEET_TEMPLATE_MAP}, key=len, reverse=True)


def resolve_sheet_key(sheet_key):
    """把 GUI 工作表键解析为映射表键 (基础项目名, 构件或None)。

    工作表键格式为 ``项目名（构件）``（全角括号）；项目名内部只含半角
    括号（如“回弹法检测(主要来源为仪器数据，可选用)”），按全角括号
    切分即可安全剥离构件后缀。
    """
    base, comp = sheet_key, None
    if "（" in sheet_key and sheet_key.endswith("）"):
        base, comp = sheet_key.split("（", 1)
        comp = comp.rstrip("）") or None
    if base in SHEET_TEMPLATE_MAP:
        return base, comp
    for known in _KNOWN_BASES:
        if base.startswith(known):
            return known, comp
    return base, comp


# ── 报告抬头信息字段 ──
# (键, 界面标签, 空值默认)。报告日期默认由弹窗填充当天。
REPORT_INFO_FIELDS = [
    ("report_no", "报告编号", ""),
    ("project_name", "工程名称", ""),
    ("project_location", "工程地点", ""),
    ("client", "委托单位", ""),
    ("witness", "见证单位", ""),
    ("tester", "检测人", ""),
    ("writer", "报告编写人", ""),
    ("checker", "复核人", ""),
    ("reviewer", "审核人", ""),
    ("approver", "批准人", ""),
    ("test_date", "检测日期", ""),
    ("report_date", "报告日期", ""),
]


def default_report_info(project_name=""):
    """生成抬头信息默认值（报告日期=今天）。"""
    return {
        "project_name": project_name or "",
        "report_date": datetime.now().strftime("%Y年%m月%d日"),
    }


# ── 六、检测结论句式 ──
# value_col：用于取 min~max 数值范围的列（无则不取值）。
# bad_keywords：行内出现这些词时改用 bad 后缀句。
CONCLUSION_TEMPLATES = {
    "回弹法检测": {
        "text": "经回弹法检测，混凝土{comp}构件抗压强度推定值为{value}MPa，满足设计强度等级要求。",
        "no_value": "经回弹法检测，混凝土{comp}构件抗压强度满足设计强度等级要求。",
        "bad": "经回弹法检测，混凝土{comp}构件部分测区强度不满足设计强度等级要求，应进行复核处理。",
        "not_meet": "经回弹法检测，混凝土{comp}构件抗压强度推定值为{value}MPa，不满足设计强度等级要求，应进行复核处理。",
        "value_col": "强度推定值",
    },
    "钻芯法检测": {
        "text": "经钻芯法检测，混凝土{comp}构件芯样抗压强度为{value}MPa，满足设计强度等级要求。",
        "no_value": "经钻芯法检测，混凝土{comp}构件芯样抗压强度满足设计强度等级要求。",
        "bad": "经钻芯法检测，混凝土{comp}构件部分芯样强度不满足设计强度等级要求，应进行复核处理。",
        "not_meet": "经钻芯法检测，混凝土{comp}构件芯样抗压强度为{value}MPa，不满足设计强度等级要求，应进行复核处理。",
        "value_col": "推定值",
    },
    "回弹钻芯修正法检测": {
        "text": "经回弹钻芯修正法检测，混凝土{comp}构件抗压强度修正结果为{value}MPa，满足设计强度等级要求。",
        "no_value": "经回弹钻芯修正法检测，混凝土{comp}构件抗压强度满足设计强度等级要求。",
        "bad": "经回弹钻芯修正法检测，混凝土{comp}构件部分测区强度不满足设计强度等级要求，应进行复核处理。",
        "not_meet": "经回弹钻芯修正法检测，混凝土{comp}构件抗压强度修正结果为{value}MPa，不满足设计强度等级要求，应进行复核处理。",
        "value_col": "芯样强度均值",
    },
    "剪力墙构件钢筋间距检测": {
        "text": "经检测，剪力墙构件钢筋间距偏差满足规范允许偏差要求。", "value_col": None},
    "现浇板钢筋间距检测": {
        "text": "经检测，现浇板构件钢筋间距偏差满足规范允许偏差要求。", "value_col": None},
    "剪力墙钢筋根数检测": {
        "text": "经检测，剪力墙构件主要受力钢筋根数满足设计要求。", "value_col": None},
    "梁构件底排受力钢筋根数检测": {
        "text": "经检测，混凝土梁构件底排受力钢筋根数满足设计要求。", "value_col": None},
    "柱构件主要受力钢筋根数检测": {
        "text": "经检测，混凝土柱构件主要受力钢筋根数满足设计要求。", "value_col": None},
    "剪力墙保护层厚度检测": {
        "text": "经检测，剪力墙构件钢筋保护层厚度满足设计及规范允许偏差要求。", "value_col": None},
    "混凝土板保护层厚度检测": {
        "text": "经检测，混凝土板构件钢筋保护层厚度满足设计及规范允许偏差要求。", "value_col": None},
    "混凝土柱保护层厚度检测": {
        "text": "经检测，混凝土柱构件钢筋保护层厚度满足设计及规范允许偏差要求。", "value_col": None},
    "混凝土梁保护层厚度检测": {
        "text": "经检测，混凝土梁构件钢筋保护层厚度满足设计及规范允许偏差要求。", "value_col": None},
    "剪力墙厚度检测": {
        "text": "经检测，剪力墙构件结构厚度满足设计及规范允许偏差要求。", "value_col": None},
    "楼板构件厚度检测": {
        "text": "经检测，楼板构件结构厚度满足设计及规范允许偏差要求。", "value_col": None},
    "混凝土梁结构尺寸检测": {
        "text": "经检测，混凝土梁构件截面尺寸满足设计及规范允许偏差要求。", "value_col": None},
    "混凝土柱结构尺寸检测": {
        "text": "经检测，混凝土柱构件截面尺寸满足设计及规范允许偏差要求。", "value_col": None},
    "化学植筋锚固承载力检测": {
        "text": "经检测，填充墙化学植筋锚固承载力满足设计要求。", "value_col": None},
}
_CONCLUSION_DEFAULT = {
    "text": "经检测，{item}{comp_part}相关指标满足设计要求。",
    "no_value": "经检测，{item}{comp_part}相关指标满足设计要求。",
    "bad": "经检测，{item}{comp_part}部分测点不满足设计要求，应进行复核处理。",
    "value_col": None,
}

# 合格/不合格类列名（判断是否存在不合格行）
_PASS_FAIL_COLUMNS = ("合格/不合格", "结论")
# 设计等级类列名（用于推定值与设计要求的规则比对）
_DESIGN_COLUMNS = ("设计强度等级", "设计等级")


def _parse_grade(text):
    """从设计等级文本提取数值（C30→30.0、MU10→10.0、M7.5→7.5），无数字返回 None。"""
    m = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
    return float(m.group(1)) if m else None


def _find_col(columns, names):
    """按归一化列名（去单位后缀）查找列索引，找不到返回 None。"""
    for i, c in enumerate(columns):
        cs = str(c).strip().replace("（", "(").split("(")[0].strip()
        if cs in names:
            return i
    return None


def _fmt_num(v):
    return f"{v:g}"


def build_conclusion(base, comp, rows, columns):
    """按规则推理生成单个检测项目的结论句（30~60 字，不含修复步骤）。

    推理链（句式模板即提示词，逐级降级）：
      1. 「合格/不合格」列出现不合格/不符合 → bad 句（部分不满足，复核处理）；
      2. 强度类（配置 value_col）：推定值与设计等级逐行比对，
         任一行推定值 < 设计等级数值 → not_meet 句（不满足，复核处理）；
         否则 → text 句（取 min~max 数值范围，判定满足）；
      3. 无数值可比 → no_value 句（不作满足性判定）。
    """
    tpl = CONCLUSION_TEMPLATES.get(base, _CONCLUSION_DEFAULT)
    comp_part = f"（{comp}）" if comp else ""
    ctx = {"item": base, "comp": comp or "", "comp_part": comp_part, "value": ""}

    # 1) 不合格行（合格/不合格、结论列）
    fail_idx = [i for i, c in enumerate(columns)
                if str(c).strip() in _PASS_FAIL_COLUMNS]
    for row in rows:
        if any(i < len(row) and any(k in str(row[i])
                                    for k in ("不合格", "不符合"))
               for i in fail_idx):
            return tpl.get("bad", tpl["text"]).format(**ctx)

    # 2) 强度类：推定值 vs 设计等级 逐行比对推理
    value_idx = _find_col(columns, (tpl.get("value_col"),)) \
        if tpl.get("value_col") else None
    if value_idx is not None:
        design_idx = _find_col(columns, _DESIGN_COLUMNS)
        nums = []
        below_design = False
        for row in rows:
            try:
                value = float(str(row[value_idx]).strip())
            except (ValueError, TypeError, IndexError):
                continue
            nums.append(value)
            if design_idx is not None and design_idx < len(row):
                design = _parse_grade(row[design_idx])
                if design is not None and value < design - 1e-9:
                    below_design = True
        if nums:
            lo, hi = min(nums), max(nums)
            ctx["value"] = (f"{_fmt_num(lo)}~{_fmt_num(hi)}"
                            if hi > lo else _fmt_num(hi))
            if below_design:
                not_meet = tpl.get("not_meet")
                if not_meet:
                    return not_meet.format(**ctx)
                # 无专用句式时由 text 句式变换推导
                return (tpl["text"].format(**ctx)
                        .replace("满足", "不满足", 1).rstrip("。")
                        + "，应进行复核处理。")
            return tpl["text"].format(**ctx)

    # 3) 无数值可比：不作满足性判定
    return tpl.get("no_value", tpl["text"]).format(**ctx)
