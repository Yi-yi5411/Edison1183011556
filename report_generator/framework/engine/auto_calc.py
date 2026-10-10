# -*- coding: utf-8 -*-
"""General auto calculation engine for CALC_RULES."""

import math
import re
from typing import Callable, List, Optional

PASS_RATE_THRESHOLD_SPACING = 10.0
PASS_RATE_THRESHOLD_THICKNESS = 3.0
PASS_RATE_THRESHOLD_COVER = 3.0


class CalcEngine:
    """Apply CALC_RULES to derive columns.

    get_cell_func(row, col) -> str | None
    set_cell_func(row, col, value) -> None
    set_font_func(row, col, fail) -> None
    """

    def __init__(self, get_cell_func: Callable[[int, int], Optional[str]],
                 set_cell_func: Callable[[int, int, str], None],
                 set_font_func: Callable[[int, int, bool], None] = None):
        self._get_cell = get_cell_func
        self._set_cell = set_cell_func
        self._set_font_func = set_font_func

    @staticmethod
    def _round_half_up(value):
        if value >= 0:
            return math.floor(value + 0.5)
        return math.ceil(value - 0.5)

    def apply_calc_rules(self, row, item_name, column_count, calc_rules_dict,
                         row_count=None):

        if not item_name or not calc_rules_dict:
            return
        rules = calc_rules_dict.get(item_name)
        if not rules:
            return
        self._column_count = column_count
        for target_col, rule in rules.items():
            if column_count is not None and target_col >= column_count:
                continue
            calc_type = rule.get("type")
            try:
                if calc_type == "avg":
                    values = self._collect_numeric_values(row, rule["sources"])
                    if values:
                        avg = sum(values) / len(values)
                        decimals = rule.get("decimals")
                        if decimals == 0:
                            text = f"{self._round_half_up(avg)}"
                        elif decimals is not None:
                            text = f"{avg:.{decimals}f}"
                        else:
                            text = f"{avg:.2f}" if avg != int(avg) else f"{int(avg)}"
                        self._set_cell_text(row, target_col, text)
                    else:
                        self._set_cell_text(row, target_col, "")
                elif calc_type == "batch_stat":
                    self._apply_batch_stat_rule(row, target_col, rule, row_count)
                elif calc_type == "batch_brick_grade":
                    self._apply_batch_brick_grade_rule(row, target_col, rule,
                                                       row_count)
                elif calc_type == "deviation":
                    design_val = self._get_cell_float(row, rule["design_col"])
                    source_val = self._get_cell_float(row, rule["source_col"])
                    if design_val is not None and source_val is not None:
                        raw_dev = source_val - design_val
                        dev = self._round_half_up(raw_dev)
                        text = str(dev)
                        if rule.get("force_sign") and dev > 0:
                            text = "+" + text
                        self._set_cell_text(row, target_col, text)
                        lower = rule.get("lower")
                        upper = rule.get("upper")
                        if lower is not None and upper is not None and self._set_font_func is not None:
                            # ??????????????????????????
                            # ?????????????? Excel ????????
                            # ?????COUNTIF "<??" ? ">??"??
                            fail = not (lower <= dev <= upper)
                            mark_col = rule.get("format_col", target_col)
                            self._set_font_func(row, mark_col, fail)
                    else:
                        self._set_cell_text(row, target_col, "")
                        lower = rule.get("lower")
                        upper = rule.get("upper")
                        if lower is not None and upper is not None and self._set_font_func is not None:
                            mark_col = rule.get("format_col", target_col)
                            self._set_font_func(row, mark_col, False)
                elif calc_type in ("pass_rate_spacing", "pass_rate_thickness", "pass_rate_cover"):
                    self._apply_pass_rate_rule(row, target_col, rule, calc_type)
                elif calc_type == "conclusion":
                    self._apply_conclusion_rule(row, target_col, rule)
                elif calc_type == "cond_conclusion":
                    self._apply_cond_conclusion_rule(row, target_col, rule)
                elif calc_type == "col_conclusion":
                    self._apply_col_conclusion_rule(row, target_col, rule)
                elif calc_type == "avg_marked":
                    self._apply_avg_marked_rule(row, target_col, rule)
                elif calc_type == "rebound_strength":
                    self._apply_rebound_strength_rule(row, target_col, rule)
            except Exception:
                pass

    @staticmethod
    def get_item_name_for_calc(current_item, calc_rules):
        if not current_item:
            return None
        name = current_item.split("-")[0] if "-" in current_item else current_item
        if name in calc_rules:
            return name
        for key in calc_rules:
            if key in current_item:
                return key
        return None

    def _apply_pass_rate_rule(self, row, target_col, rule, calc_type):
        lower, upper = self._resolve_threshold(rule, calc_type)
        sources = rule.get("sources", [])
        values = self._collect_numeric_values(row, sources)
        if values:
            pass_count = sum(1 for v in values if lower <= v <= upper)
            rate = pass_count / len(values) * 100
            self._set_cell_text(row, target_col, f"{rate:.2f}%")

        conclusion_col = rule.get("conclusion_col")
        if conclusion_col is not None:
            conclusion = self._resolve_conclusion(values, lower, upper, rule)
            self._set_cell_text(row, conclusion_col, conclusion)

        self._apply_fail_fonts(row, rule, lower, upper)

    def _apply_rebound_strength_rule(self, row, target_col, rule):
        """回弹法测强曲线：f = coef_a * Rm^exp_b * 10^(-0.0173*d)。

        JGJ/T 23-2011 混凝土统一测强曲线：coef_a=0.034488、exp_b=1.94，
        d 取“碳化深度(mm)”（未填时按 0mm 计算）。
        砖回弹（烧结普通砖常用换算公式）：coef_a=0.0254、exp_b=2.1429，
        无碳化深度参与（rule 不配 carbonation_col 时跳过该因子）。
        """
        rm = self._get_cell_float(row, rule.get("rm_col", 0))
        if rm is None or rm <= 0:
            self._set_cell_text(row, target_col, "")
            return
        coef_a = rule.get("coef_a", 0.034488)
        exp_b = rule.get("exp_b", 1.94)
        carbonation = 0.0
        if rule.get("carbonation_col") is not None:
            carbonation = self._get_cell_float(row, rule["carbonation_col"])
            if carbonation is None:
                carbonation = 0.0
        try:
            strength = coef_a * (rm ** exp_b) * (10 ** (-0.0173 * carbonation))
            decimals = rule.get("decimals", 1)
            self._set_cell_text(row, target_col, f"{strength:.{decimals}f}")
        except (ValueError, TypeError, OverflowError):
            self._set_cell_text(row, target_col, "")

    # ── 批次统计（跨行聚合）───────────────────────────────────────

    def _batch_values(self, row, rule, row_count):
        """按 batch_col 分组，收集当前行所在批次的 source_col 数值列表。

        row_count 未提供（旧调用方）或批号为空时返回空列表。
        """
        if not row_count:
            return []
        batch_col = rule.get("batch_col", 0)
        source_col = rule.get("source_col", 0)
        batch_id = (self._get_cell(row, batch_col) or "").strip()
        if not batch_id:
            return []
        values = []
        for r in range(row_count):
            bid = (self._get_cell(r, batch_col) or "").strip()
            if bid != batch_id:
                continue
            val = self._get_cell_float(r, source_col)
            if val is not None:
                values.append(val)
        return values

    def _apply_batch_stat_rule(self, row, target_col, rule, row_count):
        """批次统计：对同批次所有行的 source_col 数值做聚合。

        stat 支持 avg / var（样本方差） / std（样本标准差 n-1） /
        cv（变异系数=std/avg，as_percent 时以百分数显示） /
        std_value（强度标准值 = avg − 1.8×std） / min。
        统计列在该批次的每一行上都写入相同结果（单格编辑后
        全批次同步刷新）。
        """
        values = self._batch_values(row, rule, row_count)
        if not values:
            self._set_cell_text(row, target_col, "")
            return
        n = len(values)
        avg = sum(values) / n
        if n >= 2:
            var = sum((v - avg) ** 2 for v in values) / (n - 1)
            std = math.sqrt(var)
        else:
            var = None
            std = None
        stat = rule.get("stat", "avg")
        decimals = rule.get("decimals", 2)
        if stat == "avg":
            text = f"{avg:.{decimals}f}"
        elif stat == "var":
            text = "" if var is None else f"{var:.{decimals}f}"
        elif stat == "std":
            text = "" if std is None else f"{std:.{decimals}f}"
        elif stat == "cv":
            if std is None or avg == 0:
                text = ""
            elif rule.get("as_percent"):
                text = f"{std / avg * 100:.{decimals}f}%"
            else:
                text = f"{std / avg:.{decimals}f}"
        elif stat == "std_value":
            text = "" if std is None else f"{avg - 1.8 * std:.{decimals}f}"
        elif stat == "min":
            text = f"{min(values):.{decimals}f}"
        else:
            text = ""
        if not text:
            self._set_cell_text(row, target_col, "")
            return
        # 同批次所有行同步写入
        batch_col = rule.get("batch_col", 0)
        batch_id = (self._get_cell(row, batch_col) or "").strip()
        for r in range(row_count):
            bid = (self._get_cell(r, batch_col) or "").strip()
            if bid == batch_id:
                self._set_cell_text(r, target_col, text)

    # 烧结普通砖强度等级评定阈值（GB 5101）：
    # (等级, 平均值下限, 强度标准值下限, 单块最小值下限)
    _BRICK_GRADES = (
        ("MU30", 30.0, 23.0, 26.0),
        ("MU25", 25.0, 19.0, 21.0),
        ("MU20", 20.0, 14.0, 16.0),
        ("MU15", 15.0, 10.0, 12.0),
        ("MU10", 10.0, 6.5, 7.5),
    )

    def _apply_batch_brick_grade_rule(self, row, target_col, rule, row_count):
        """批次砖强度等级评定（GB 5101 烧结普通砖）。

        变异系数 δ=std/avg ≤ 0.21 时按 平均值+强度标准值(f̄−1.8s) 评定，
        否则按 平均值+单块最小值 评定；取满足的最高等级，
        全部不满足输出 grade_fail（默认“不满足”）。
        """
        values = self._batch_values(row, rule, row_count)
        if not values:
            self._set_cell_text(row, target_col, "")
            return
        n = len(values)
        avg = sum(values) / n
        if n >= 2:
            std = math.sqrt(sum((v - avg) ** 2 for v in values) / (n - 1))
            cv = std / avg if avg > 0 else None
        else:
            std = None
            cv = None
        batch_min = min(values)
        grade = rule.get("grade_fail", "不满足")
        for name, g_avg, g_stdval, g_min in self._BRICK_GRADES:
            if avg < g_avg:
                continue
            if cv is not None and cv <= 0.21:
                ok = (avg - 1.8 * std) >= g_stdval
            else:
                ok = batch_min >= g_min
            if ok:
                grade = name
                break
        # 同批次所有行同步写入
        batch_col = rule.get("batch_col", 0)
        batch_id = (self._get_cell(row, batch_col) or "").strip()
        for r in range(row_count):
            bid = (self._get_cell(r, batch_col) or "").strip()
            if bid == batch_id:
                self._set_cell_text(r, target_col, grade)

    def _apply_avg_marked_rule(self, row, target_col, rule):
        values = self._collect_numeric_values(row, rule.get("sources", []))
        format_col = rule.get("format_col", target_col)
        if values:
            avg = sum(values) / len(values)
            decimals = rule.get("decimals", 0)
            display_num = avg
            if decimals is None:
                text = f"{int(avg)}" if avg == int(avg) else f"{avg:.2f}"
            elif decimals == 0:
                display_num = self._round_half_up(avg)
                text = str(display_num)
            else:
                text = f"{avg:.{decimals}f}"
            if rule.get("force_sign") and display_num > 0:
                text = "+" + text
            self._set_cell_text(row, target_col, text)
            lower = rule.get("lower")
            upper = rule.get("upper")
            fail = False
            if lower is not None and upper is not None:
                fail = not (lower <= avg <= upper)
            if self._set_font_func is not None:
                self._set_font_func(row, format_col, fail)
        else:
            self._set_cell_text(row, target_col, "")
            if self._set_font_func is not None:
                self._set_font_func(row, format_col, False)

    def _apply_conclusion_rule(self, row, target_col, rule):
        lower = rule.get("lower")
        upper = rule.get("upper")
        if lower is None or upper is None:
            return
        values = self._collect_numeric_values(row, rule.get("sources", []))
        conclusion = self._resolve_conclusion(values, lower, upper, rule)
        self._set_cell_text(row, target_col, conclusion)

    def _apply_cond_conclusion_rule(self, row, target_col, rule):
        """多条件结论：所有条件满足 → conclusion_pass，任一不满足 → conclusion_fail。

        conditions 每项形如 {'col': 6, 'op': '>=', 'value': 6.0}（数值比较，
        支持 '>=', '<=', '>', '<', '==', '!='）或
        {'col': 8, 'op': 'contains', 'value': '基材无裂缝、钢筋无滑移'}（文本包含）。
        数值条件同时接受小数（0.05）、百分比（5%）及尾部带单位
        （6.5kN / 6.5 kN）三种输入格式。
        所有源格均为空时清空结论；任一源格有值即参与判定（缺失视为不满足）。
        条件带 'mark': True 时，不满足的源格加粗加下划线标识。
        """
        conditions = rule.get("conditions", [])
        if not conditions:
            return
        has_any_value = False
        all_pass = True
        for cond in conditions:
            col = cond.get("col")
            op = cond.get("op", "==")
            expected = cond.get("value")
            if op == "contains":
                text = (self._get_cell(row, col) or "").strip()
                if text:
                    has_any_value = True
                ok = bool(text) and str(expected) in text
            else:
                raw = self._get_cell(row, col)
                if raw is not None and str(raw).strip():
                    has_any_value = True
                val = self._parse_number(raw)
                ok = val is not None and self._compare(val, op, expected)
            if not ok:
                all_pass = False
            if cond.get("mark") and self._set_font_func is not None:
                self._set_font_func(row, col, not ok)
        if not has_any_value:
            self._set_cell_text(row, target_col, "")
            return
        if all_pass:
            self._set_cell_text(row, target_col, rule.get("conclusion_pass", "符合规范要求"))
        else:
            self._set_cell_text(row, target_col, rule.get("conclusion_fail", "不符合规范要求"))

    @staticmethod
    def _compare(val, op, expected):
        if op == ">=":
            return val >= expected
        if op == "<=":
            return val <= expected
        if op == ">":
            return val > expected
        if op == "<":
            return val < expected
        if op == "!=":
            return val != expected
        return val == expected

    def _apply_col_conclusion_rule(self, row, target_col, rule):
        """列对列比较结论：每对 (left_col, right_col) 按 op 比较。

        pairs 每项形如 {'left_col': 9, 'op': '>=', 'right_col': 3}，
        数值比较（左值 ≥/≤ 右值）。全部对满足 → conclusion_pass，
        任一不满足 → conclusion_fail；两列均为空时清空结论，
        任一列有值即参与判定（左值缺失视为不满足）。
        """
        pairs = rule.get("pairs", [])
        if not pairs:
            return
        has_any_value = False
        all_pass = True
        for pair in pairs:
            left = self._get_cell_float(row, pair.get("left_col", 0))
            right = self._get_cell_float(row, pair.get("right_col", 0))
            if left is None and right is None:
                continue
            has_any_value = True
            ok = (left is not None and right is not None
                  and self._compare(left, pair.get("op", ">="), right))
            if not ok:
                all_pass = False
        if not has_any_value:
            self._set_cell_text(row, target_col, "")
            return
        if all_pass:
            self._set_cell_text(row, target_col,
                                rule.get("conclusion_pass", "符合要求"))
        else:
            self._set_cell_text(row, target_col,
                                rule.get("conclusion_fail", "不符合要求"))

    # 数值 + 尾部单位（字母/中文单位，如 kN、MPa、mm、千牛）
    _NUM_WITH_UNIT_RE = re.compile(
        r'^([-+]?(?:\d+\.?\d*|\.\d+))\s*[A-Za-z\u4e00-\u9fff·℃]+$'
    )

    @staticmethod
    def _parse_number(text):
        """解析数值：支持小数（0.05）、百分比（5% → 0.05）及尾部带单位
        （6.5kN / 6.5 kN → 6.5）三种格式，失败返回 None"""
        if text is None:
            return None
        s = str(text).strip()
        if not s:
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            pass
        if s.endswith("%"):
            try:
                return float(s[:-1].strip()) / 100.0
            except (ValueError, TypeError):
                return None
        m = CalcEngine._NUM_WITH_UNIT_RE.match(s)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, TypeError):
                return None
        return None

    def _resolve_threshold(self, rule, calc_type):
        if calc_type == "pass_rate_spacing":
            default_low = -PASS_RATE_THRESHOLD_SPACING
            default_high = PASS_RATE_THRESHOLD_SPACING
        elif calc_type == "pass_rate_thickness":
            default_low = -PASS_RATE_THRESHOLD_THICKNESS
            default_high = PASS_RATE_THRESHOLD_THICKNESS
        else:
            default_low = -PASS_RATE_THRESHOLD_COVER
            default_high = PASS_RATE_THRESHOLD_COVER
        lower = rule.get("lower")
        upper = rule.get("upper")
        if lower is None:
            lower = default_low
        if upper is None:
            upper = default_high
        return lower, upper

    def _resolve_conclusion(self, values, lower, upper, rule):
        if not values:
            return ""
        if all(lower <= v <= upper for v in values):
            return rule.get("conclusion_pass", "符合规范")
        if any(v > upper for v in values):
            return rule.get("conclusion_fail_high", "不符合规范")
        return rule.get("conclusion_fail_low", "不符合要求")

    def _apply_fail_fonts(self, row, rule, lower, upper):
        if self._set_font_func is None:
            return
        sources = rule.get("sources", [])
        input_cols = rule.get("input_cols", [])
        if not input_cols:
            return
        for i in range(min(len(sources), len(input_cols))):
            val = self._get_cell_float(row, sources[i])
            fail = False
            if val is not None:
                fail = not (lower <= val <= upper)
            self._set_font_func(row, input_cols[i], fail)

    def _collect_numeric_values(self, row, col_indices) -> List[float]:
        values = []
        for c in col_indices:
            val = self._get_cell_float(row, c)
            if val is not None:
                values.append(val)
        return values

    def _get_cell_float(self, row, col) -> Optional[float]:
        text = self._get_cell(row, col)
        if text is None:
            return None
        s = str(text).strip()
        if not s:
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def _set_cell_text(self, row, col, text):
        self._set_cell(row, col, text)
