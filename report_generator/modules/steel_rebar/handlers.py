# -*- coding: utf-8 -*-
"""Steel-rebar detection GUI logic (mixin).

Moved out of the main window so rebar-specific merge/calculation rules live next to
the rebar columns and CALC_RULES instead of inside the generic UI.
"""


class SteelRebarMixin:
    """Rebar-spacing sheet merge and total recalculation handlers."""

    REBAR_AXIS_COLUMN = 2
    REBAR_DEVIATION_AVG_COLUMN = 18
    REBAR_PASS_RATE_COLUMN = 19
    REBAR_CONCLUSION_COLUMN = 20

    def _is_rebar_spacing_sheet(self, sheet_key):
        """Return True when *sheet_key* belongs to rebar spacing items."""
        base, _comp = self._parse_sheet_key(sheet_key)
        return base in (
            '剪力墙构件钢筋间距检测',
            '现浇板钢筋间距检测',
            '剪力墙构件钢筋间距',
            '现浇板钢筋间距',
        )

    def _ensure_rebar_axis_merges(self, sheet_key):
        """Create the two-row axis merges used by rebar spacing sheets.

        Axis values are entered once per two rows, so each non-empty span is merged
        vertically in the axis column.
        """
        if not self._is_rebar_spacing_sheet(sheet_key):
            return

        axis_col = self.REBAR_AXIS_COLUMN
        data = self.sheet_data.get(sheet_key, [])
        first = None
        last = -1
        for r, row in enumerate(data):
            if any(str(cell).strip() for cell in row):
                if first is None:
                    first = r
                last = r

        merges = self._merges.setdefault(sheet_key, [])
        existing = set((r, c, rs, cs) for (r, c, rs, cs) in merges)
        r = first if first is not None else 0
        while r + 1 <= last:
            merge = (r, axis_col, 2, 1)
            if merge not in existing:
                merges.append(merge)
                existing.add(merge)
            r += 2

    def _recalc_rebar_spacing_totals(self):
        """Recalculate pass-rate and conclusion columns for the current rebar sheet.

        The pass-rate is based on the average deviation column and the +-10mm
        tolerance defined by the rebar spacing acceptance rule.
        """
        if not self.current_item or not self._is_rebar_spacing_sheet(self.current_item):
            return

        # Clear previous computed cells.
        for r in range(self.table.rowCount()):
            self._calc_set_cell(r, self.REBAR_PASS_RATE_COLUMN, "")
            self._calc_set_cell(r, self.REBAR_CONCLUSION_COLUMN, "")

        total = 0
        qualified = 0
        first = None
        last = -1
        for r in range(self.table.rowCount()):
            v = self._to_float(self.table.item(r, self.REBAR_DEVIATION_AVG_COLUMN))
            if v is None:
                continue
            if first is None:
                first = r
            last = r
            total += 1
            if -10 <= v <= 10:
                qualified += 1
                conclusion = '符合规范'
            elif v > 10:
                conclusion = '不符合规范'
            else:
                conclusion = '不符合要求'
            self._calc_set_cell(r, self.REBAR_CONCLUSION_COLUMN, conclusion)

        merges = self._merges.setdefault(self.current_item, [])
        merges[:] = [m for m in merges if m[1] not in (self.REBAR_PASS_RATE_COLUMN, self.REBAR_CONCLUSION_COLUMN)]

        if total == 0:
            self._ensure_rebar_axis_merges(self.current_item)
            self._apply_merges_to_table()
            return

        rate = qualified / total * 100
        self._calc_set_cell(first, self.REBAR_PASS_RATE_COLUMN, f"{rate:.2f}%")
        merge = (first, self.REBAR_PASS_RATE_COLUMN, last - first + 1, 1)
        if merge not in merges:
            merges.append(merge)
        self._ensure_rebar_axis_merges(self.current_item)
        self._apply_merges_to_table()
