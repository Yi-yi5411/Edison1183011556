# -*- coding: utf-8 -*-
"""第5步：将数据库中的电子数据做结构化 / 规范化处理。

输入：大模型返回的每条记录 {"字段名": "值"}。
输出：清洗、去单位、转类型后的规范记录，便于后续按列匹配回填。

字段治理（确定性规则，只做无歧义修正，不改写原义）：
- 轴线编号：全角转半角、去内部空格、统一破折号/斜杠、去首尾标点；
- 方向：去空格标点 + 同义写法归一（垂直向→垂直、竖直向→竖向、水平向→水平）；
- 数值字段：严格模式提取（仅认"纯数字+可选单位"），避免把
  "C30"→30.0、"178 1/8"→178.0 之类含字母/多段文本错误改写为数字；
- validate_records：对轴线编号格式、方向用词、设计值是否为数字做复核标记。
"""
import re

from report_generator.scan_recognition.config import Config


def _strip_brackets(text):
    return re.sub(r"[（(].*?[)）]", "", text)


def _full_to_half(text):
    """全角字符（数字/字母/符号/空格）转半角。"""
    out = []
    for ch in str(text):
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


# 破折号/连字符变体 → "-"
_DASH_RE = re.compile(r"[－—–ー﹣]")
# 数值严格提取：整段必须是"数字(可带负号/小数) + 可选单位"
_NUM_STRICT_RE = re.compile(
    r"^(-?\d+(?:\.\d+)?)\s*(mm|cm|m|km|m2|m3|mm2|kN|N|KN|MPa|mpa|kPa|kg|t|%|°|℃)?$",
    re.IGNORECASE,
)


class Normalizer:
    """结构化/规范化处理：文本清洗 + 数值提取 + 单位剥离 + 字段治理。"""

    # 方向字段的常用词表（小写比较）；超出词表的值仅标记复核，不自动改写
    _DIRECTION_VOCAB = ("垂直", "水平", "竖向", "横向", "纵向", "竖", "横",
                        "x向", "y向", "x", "y", "东西", "南北")
    # 无歧义的同义写法归一（同一含义，仅去掉多余"向"/统一叫法）
    _DIRECTION_SYNONYMS = {
        "垂直向": "垂直",
        "竖直向": "竖向",
        "水平向": "水平",
    }

    # 数值合理性量程（仅标记复核，不改写）：按字段关键词首个命中项校验
    _DEFAULT_RANGES = (
        ("回弹值", (10.0, 90.0)),
        ("碳化深度", (0.0, 60.0)),
        ("强度", (1.0, 200.0)),
        ("直径", (30.0, 300.0)),
        ("荷载", (0.0, 10000.0)),
        ("实测值", (10.0, 10000.0)),
        ("设计值", (10.0, 10000.0)),
        ("间距", (10.0, 10000.0)),
    )

    def __init__(self, cfg: Config = None):
        cfg = cfg or Config.load()
        n = cfg.normalizer
        self.trim = n.get("trim", True)
        self.collapse_ws = n.get("collapse_ws", True)
        # 间距类字段合理量程下限（mm）：小于该值的识别结果视为
        # "未测斜杠/"被误识成数字，按未测清空并留痕
        self.min_plausible_mm = n.get("min_plausible_mm", 10)
        # 合理性量程校验（仅标记复核，不改写）：内置默认 + 配置覆盖
        # （normalizer.plausible_ranges：字段关键词 -> [下限, 上限]）
        ranges = {k: r for k, r in self._DEFAULT_RANGES}
        for kw, rng in (n.get("plausible_ranges") or {}).items():
            try:
                ranges[str(kw)] = (float(rng[0]), float(rng[1]))
            except Exception:
                continue
        self.plausible_ranges = list(ranges.items())
        self.remove_units_fields = n.get("remove_units_in_fields", [])
        self._auto_cleared = []

    def normalize_record(self, record):
        out = {}
        for key, raw in (record or {}).items():
            out[key] = self._clean_value(key, raw)
        return self._repair_direction_in_axis(out)

    # 轴号样式：数字/字母与 -、/、括号 组合且至少含一个数字
    _AXIS_PATTERN_RE = re.compile(r"[0-9A-Za-z\-/（）()]+")

    def _repair_direction_in_axis(self, rec):
        """跨字段纠位：轴线编号格被填成方向词（X向/Y向等）时，
        从构件位置字段找回轴号样式值归位，并把方向词填回方向列。
        仅在无歧义（方向列一致或为空）时执行，否则保留待人工复核。
        """
        axis_keys = [k for k in rec if any(t in str(k) for t in ("轴线", "轴号"))]
        dir_keys = [k for k in rec if "方向" in str(k) or "朝向" in str(k)]
        pos_keys = [k for k in rec
                    if any(t in str(k) for t in ("构件位置", "位置及名称", "部位"))]
        for ak in axis_keys:
            v = str(rec.get(ak) or "").strip()
            if not v or v.lower() not in self._DIRECTION_VOCAB:
                continue
            # 方向列已有不同值时不自动纠位，交由复核
            conflict = any(str(rec.get(dk) or "").strip().lower()
                           not in ("", v.lower()) for dk in dir_keys)
            if conflict:
                continue
            for pk in pos_keys:
                pv = str(rec.get(pk) or "").strip()
                if (pv and re.search(r"\d", pv)
                        and self._AXIS_PATTERN_RE.fullmatch(pv)):
                    rec[ak] = pv
                    rec[pk] = ""
                    for dk in dir_keys:
                        if not str(rec.get(dk) or "").strip():
                            rec[dk] = v
                    break
            break
        return rec

    def _clean_value(self, field, raw):
        if raw is None:
            return ""
        text = str(raw).replace("\u3000", " ").replace("\t", " ")
        if self.trim:
            text = text.strip()
        if self.collapse_ws:
            text = re.sub(r"\s+", " ", text)
        # 空值或"/"（未测标记）保留原样
        if text in ("", "-", "—", "/", "None", "nan"):
            return "" if text in ("", "-", "—", "/") else text
        base = _strip_brackets(str(field))
        # 专用字段治理：轴线编号 / 方向
        if any(k in base for k in ("轴线", "轴号")):
            return self._clean_axis_number(text)
        if "方向" in base or "朝向" in base:
            return self._clean_direction(text)
        # 数值/带单位字段：剥离单位、空值或"/"保留原样
        if self._is_numeric_field(base):
            num = self._extract_number(text)
            return num if num is not None else text
        return text

    @staticmethod
    def _clean_axis_number(text):
        """轴线编号治理：全角转半角、去空格、统一横线/斜杠、去首尾标点。"""
        text = _full_to_half(text)
        text = _DASH_RE.sub("-", text)
        text = re.sub(r"\s+", "", text)
        text = text.replace("／", "/").replace("、", "-")
        return text.strip(" .,;:，。；：、")

    @classmethod
    def _clean_direction(cls, text):
        """方向治理：去空格与首尾标点 + 无歧义同义词归一。"""
        text = _full_to_half(text)
        text = re.sub(r"\s+", "", text)
        text = text.strip(" .,;:，。；：、")
        return cls._DIRECTION_SYNONYMS.get(text, text)

    @staticmethod
    def _is_numeric_field(field):
        base = _strip_brackets(str(field))
        num_kw = ("强度", "直径", "截面积", "荷载", "推定值", "评定值", "碳化深度",
                  "回弹值", "均值", "厚度", "尺寸", "偏差", "序号", "芯样", "测点")
        return any(k in base for k in num_kw)

    @staticmethod
    def _extract_number(text):
        """严格数值提取：整段是"数字+可选单位"才转数字，否则原样返回。

        避免 "C30"→30.0、"178 1/8"→178.0 之类把含字母/多段文本的值
        错误截成数字；不匹配时返回 None，由调用方保留原文本待人工复核。
        """
        m = _NUM_STRICT_RE.match(str(text).strip())
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    # ── 字段复核校验：只标记可疑值，不自动改写 ──
    _AXIS_VALUE_RE = re.compile(r"[0-9A-Za-z\-/()]+")
    # 数字紧贴字母（如"11A"、"1A"）：真实轴号写法应为 1/A、1-A 之类，
    # 手写"/"与"1"混淆时常被吞掉分隔符
    _AXIS_NOSEP_RE = re.compile(r"\d[A-Za-z]")
    _PURE_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

    # 强度等级样式：C30 / MU10 / M7.5 / Q235（1~2个大写字母 + 数字可选小数）
    _GRADE_RE = re.compile(r"[CMUQ]{1,2}\d+(?:\.\d+)?", re.IGNORECASE)

    def validate_records(self, records):
        """逐条检查轴线编号/方向/设计值/量程/序号等，返回复核提示列表。

        只标记可疑值，不自动改写。每条：
        {"行": 行号, "字段": 字段名, "值": 当前值, "问题": 原因}
        """
        warnings = []
        for i, rec in enumerate(records or [], 1):
            for field, value in (rec or {}).items():
                base = _strip_brackets(str(field))
                v = str(value if value is not None else "").strip()
                if not v:
                    continue
                if any(k in base for k in ("轴线", "轴号")):
                    if not self._AXIS_VALUE_RE.fullmatch(v):
                        warnings.append(
                            {"行": i, "字段": str(field), "值": v,
                             "问题": "轴线编号含数字/字母、-、/以外的字符，请复核"})
                    elif self._AXIS_NOSEP_RE.search(v):
                        warnings.append(
                            {"行": i, "字段": str(field), "值": v,
                             "问题": "轴号中数字紧贴字母，疑似丢失“/”或“-”（如1A应为1/A），请复核"})
                elif "方向" in base or "朝向" in base:
                    if v.lower() not in self._DIRECTION_VOCAB:
                        warnings.append(
                            {"行": i, "字段": str(field), "值": v,
                             "问题": "方向不在常用词表（垂直/水平/竖向/横向等），请复核"})
                elif "强度等级" in base or "设计等级" in base:
                    if not self._GRADE_RE.fullmatch(v):
                        warnings.append(
                            {"行": i, "字段": str(field), "值": v,
                             "问题": "强度等级格式异常（应为 C30/MU10/M7.5/Q235 样式），请复核"})
                elif "设计值" in base or "实测值" in base or "间距" in base:
                    if not self._PURE_NUM_RE.fullmatch(v):
                        warnings.append(
                            {"行": i, "字段": str(field), "值": v,
                             "问题": "不是纯数字，请复核"})
                    elif v in ("1", "1.0"):
                        warnings.append(
                            {"行": i, "字段": str(field), "值": v,
                             "问题": "疑似未测斜杠/勾选被误识为1，请复核"})
                    else:
                        self._append_range_warning(warnings, i, field, v, base)
                elif any(kw in base for kw, _ in self.plausible_ranges):
                    self._append_range_warning(warnings, i, field, v, base)
        # 整行级复核：全空行 / 完全重复行 / 序号连续性
        warnings.extend(self._validate_duplicate_rows(records))
        warnings.extend(self._validate_sequence(records))
        return warnings

    def _append_range_warning(self, warnings, i, field, v, base):
        """数值量程校验：超出合理量程仅标记复核（首个命中的关键词生效）。"""
        if not self._PURE_NUM_RE.fullmatch(v):
            return
        try:
            num = float(v)
        except ValueError:
            return
        for kw, (lo, hi) in self.plausible_ranges:
            if kw in base:
                if num < lo or num > hi:
                    warnings.append(
                        {"行": i, "字段": str(field), "值": v,
                         "问题": f"数值超出{kw}合理量程（{lo:g}~{hi:g}），请复核"})
                return

    def _validate_duplicate_rows(self, records):
        """整行级复核：全空行与完全重复行（疑似误识别/重复识别，仅标记）。"""
        warnings = []
        seen = {}
        for i, rec in enumerate(records or [], 1):
            key = tuple(sorted(
                (str(k), str(v)) for k, v in (rec or {}).items()
                if str(v if v is not None else "").strip()))
            if not key:
                warnings.append(
                    {"行": i, "字段": "(整行)", "值": "",
                     "问题": "整行未识别到内容，疑似误识别行，请复核"})
                continue
            if key in seen:
                warnings.append(
                    {"行": i, "字段": "(整行)", "值": "",
                     "问题": f"与第{seen[key]}行内容完全相同，疑似重复识别，请复核"})
            else:
                seen[key] = i
        return warnings

    def _validate_sequence(self, records):
        """序号连续性复核：重复序号/跳号仅标记，不自动改写。"""
        warnings = []
        if not records:
            return warnings
        seq_fields = set()
        for rec in records:
            for k in (rec or {}):
                if "序号" in str(k):
                    seq_fields.add(str(k))
        for field in seq_fields:
            seen = {}
            last = None
            for i, rec in enumerate(records, 1):
                v = str((rec or {}).get(field) or "").strip()
                if not self._PURE_NUM_RE.fullmatch(v):
                    continue
                try:
                    num = float(v)
                except ValueError:
                    continue
                if num != int(num):
                    continue
                numi = int(num)
                if numi in seen:
                    warnings.append(
                        {"行": i, "字段": field, "值": v,
                         "问题": f"序号与第{seen[numi]}行重复，请复核"})
                elif last is not None and numi > last + 1:
                    warnings.append(
                        {"行": i, "字段": field, "值": v,
                         "问题": f"序号从{last}跳到{numi}，中间疑似缺行，请复核"})
                seen.setdefault(numi, i)
                last = numi
        return warnings

    def normalize_records(self, records):
        self._auto_cleared = []
        out = []
        for i, rec in enumerate(records or [], 1):
            r = self.normalize_record(rec)
            # 间距类字段量程治理：手写斜杠"/"常被误识为 1，
            # 小于量程下限的值不可能是真实测量，按未测清空并留痕
            for k, v in list(r.items()):
                base = _strip_brackets(str(k))
                if not any(t in base for t in ("实测值", "设计值", "间距")):
                    continue
                m = self._PURE_NUM_RE.fullmatch(str(v).strip())
                if not m:
                    continue
                num = float(m.group())
                if 0 < abs(num) < self.min_plausible_mm:
                    self._auto_cleared.append(
                        {"行": i, "字段": str(k), "值": str(v)})
                    r[k] = ""
            out.append(r)
        return out

    def take_auto_cleared(self):
        """取走本轮被量程治理清空的值清单（取后清空）。"""
        cleared = self._auto_cleared
        self._auto_cleared = []
        return cleared
