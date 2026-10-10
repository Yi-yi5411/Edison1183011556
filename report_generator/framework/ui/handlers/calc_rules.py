# -*- coding: utf-8 -*-
"""计算规则 Mixin（通用自动计算 / 公式引擎适配）

CalcEngine 的 UI 适配层：把 CALC_RULES 声明的衍生列自动计算
（平均值、偏差值、合格点率）应用到表格行；并维护 FormulaEngine
的惰性初始化与全表公式重算（保留合并单元格对齐）。

依赖宿主（主窗口）属性/方法：table、current_item、sheet_data、
_loading、_merges、_calc_engine、_formula_engine。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTableWidgetItem

from framework.engine import CalcEngine
from framework.engine.formula import FormulaEngine
from framework.models import CALC_RULES
from framework.ui.constants import ROLE_FORMULA


class CalcRulesMixin:
    """通用自动计算规则（平均值、偏差值、合格点率）。

    计算逻辑由 engines.CalcEngine 提供，UI 仅负责读写单元格。
    """

    def _apply_calc_rules(self, row):
        """根据 CALC_RULES 自动计算指定行的衍生列（委托 CalcEngine）"""
        if not self.current_item:
            return
        item_name = CalcEngine.get_item_name_for_calc(self.current_item, CALC_RULES)
        if not item_name:
            return
        self._calc_engine.apply_calc_rules(
            row, item_name, self.table.columnCount(), CALC_RULES,
            row_count=self.table.rowCount()
        )

    def _apply_all_calc_rules(self):
        """对当前工作表所有行应用 CALC_RULES 自动计算"""
        if not self.current_item:
            return
        item_name = CalcEngine.get_item_name_for_calc(self.current_item, CALC_RULES)
        if not item_name:
            return
        column_count = self.table.columnCount()
        self._loading = True
        try:
            for row in range(self.table.rowCount()):
                self._calc_engine.apply_calc_rules(
                    row, item_name, column_count, CALC_RULES,
                    row_count=self.table.rowCount()
                )
            self._recalc_module_totals()
        finally:
            self._loading = False

    # ── CalcEngine 回调：读写当前表格单元格 ──
    def _calc_format_cell(self, row, col, fail):
        """CalcEngine 回调：不合格单元格加粗+下划线标识"""
        if not (0 <= row < self.table.rowCount() and 0 <= col < self.table.columnCount()):
            return
        it = self.table.item(row, col)
        if it is None:
            it = QTableWidgetItem()
            self.table.setItem(row, col, it)
        font = it.font()
        font.setBold(fail)
        font.setUnderline(fail)
        it.setFont(font)

    def _calc_get_cell(self, row, col):
        """CalcEngine 回调：读取单元格文本（空返回 None）"""
        if 0 <= row < self.table.rowCount() and 0 <= col < self.table.columnCount():
            it = self.table.item(row, col)
            return it.text() if it and it.text() else None
        return None

    def _calc_set_cell(self, row, col, text):
        """CalcEngine 回调：写入单元格文本（无 item 时自动创建）"""
        if 0 <= row < self.table.rowCount() and 0 <= col < self.table.columnCount():
            it = self.table.item(row, col)
            if it is None:
                it = QTableWidgetItem()
                self.table.setItem(row, col, it)
            it.setText(text)
            if hasattr(self, "_get_computed_columns") and col in self._get_computed_columns():
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)

    @staticmethod
    def _to_float(item_or_text):
        """安全地将 QTableWidgetItem 或字符串转为 float，失败返回 None"""
        if item_or_text is None:
            return None
        if isinstance(item_or_text, QTableWidgetItem):
            text = item_or_text.text().strip()
        else:
            text = str(item_or_text).strip()
        if not text:
            return None
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    def _ensure_engine(self):
        """确保公式引擎已初始化"""
        if self._formula_engine is None:
            self._formula_engine = FormulaEngine(self.sheet_data)

    def _recompute_formulas(self):
        """重新计算所有公式单元格（保留合并格式）"""
        if not self.current_item:
            return
        self._ensure_engine()
        rows = self.table.rowCount()
        cols = self.table.columnCount()
        # 先保存合并单元格格式，公式重算后恢复
        merge_anchors = {}
        if self.current_item in self._merges:
            for (r, c, _rs, _cs) in self._merges[self.current_item]:
                it = self.table.item(r, c)
                if it:
                    merge_anchors[(r, c)] = it.textAlignment()

        for r in range(rows):
            for c in range(cols):
                item = self.table.item(r, c)
                if item and item.data(ROLE_FORMULA):
                    formula = item.data(ROLE_FORMULA)
                    result = self._formula_engine.evaluate(
                        formula, self.current_item, r, c
                    )
                    if item.text() != result:
                        item.setText(result)

        # 恢复合并单元格的对齐（setText 会重置对齐）
        for (r, c), alignment in merge_anchors.items():
            it = self.table.item(r, c)
            if it:
                it.setTextAlignment(alignment)
