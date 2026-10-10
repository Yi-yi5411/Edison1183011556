# -*- coding: utf-8 -*-
"""构件厚度检测（楼板/剪力墙）GUI 逻辑（mixin）。

厚度汇总（合格点率/结论列）的配置与重算逻辑从主窗口下沉到此，
与厚度列头、CALC_RULES 同处一模块，主窗口仅负责调度。
"""

# 楼板/剪力墙厚度：偏差平均值列 / 合格点率列 / 结论列 / 允许偏差
THICKNESS_SUMMARY_CONFIG = {
    '楼板构件厚度检测': {'deviation_avg_col': 12, 'pass_rate_col': 13, 'conclusion_col': 14, 'lower': -5.0, 'upper': 10.0},
    '剪力墙厚度检测': {'deviation_avg_col': 11, 'pass_rate_col': 12, 'conclusion_col': 13, 'lower': -5.0, 'upper': 10.0},
}


class MemberThicknessMixin:
    """楼板/剪力墙厚度检测的合格点率汇总重算。"""

    def _recalc_member_thickness_totals(self):
        """重算楼板/剪力墙厚度的合格点率并合并单元格。

        合格结论按每行的实测偏差平均值判定，
        合格点率 = 1 - 不合格的偏差平均值个数 / 偏差平均值总个数 × 100%。
        """
        if not self.current_item:
            return
        base, _comp = self._parse_sheet_key(self.current_item)
        cfg = THICKNESS_SUMMARY_CONFIG.get(base)
        if not cfg:
            return

        pass_rate_col = cfg['pass_rate_col']
        conclusion_col = cfg['conclusion_col']
        lower = cfg['lower']
        upper = cfg['upper']
        deviation_avg_col = cfg['deviation_avg_col']

        for r in range(self.table.rowCount()):
            self._calc_set_cell(r, pass_rate_col, "")
            self._calc_set_cell(r, conclusion_col, "")

        total = 0
        failed = 0
        first = None
        last = -1
        for r in range(self.table.rowCount()):
            v = self._to_float(self.table.item(r, deviation_avg_col))
            if v is None:
                continue
            if first is None:
                first = r
            last = r
            total += 1
            if lower <= v <= upper:
                conclusion = '符合规范'
            else:
                conclusion = '不符合规范'
                failed += 1
            self._calc_set_cell(r, conclusion_col, conclusion)

        merges = self._merges.setdefault(self.current_item, [])
        merges[:] = [m for m in merges if m[1] not in (pass_rate_col, conclusion_col)]

        if total == 0:
            self._apply_merges_to_table()
            return

        rate = (1 - failed / total) * 100
        self._calc_set_cell(first, pass_rate_col, f"{rate:.2f}%")
        merge = (first, pass_rate_col, last - first + 1, 1)
        if merge not in merges:
            merges.append(merge)

        self._apply_merges_to_table()
