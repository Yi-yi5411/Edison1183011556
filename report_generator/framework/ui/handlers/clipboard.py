# -*- coding: utf-8 -*-
"""剪贴板操作 Mixin（复制 / 剪切 / 粘贴 / 填充柄自动填充）"""

from PyQt5.QtWidgets import QApplication, QTableWidgetItem, QAbstractItemView, QComboBox

from framework.ui import ROLE_FORMULA


class ClipboardMixin:
    """剪贴板相关操作"""

    # ── 编辑状态辅助：单元格正在编辑时，把快捷键转给编辑器（文本复制粘贴）────
    def _is_editing(self):
        return (
            hasattr(self, "table")
            and self.table.state() == QAbstractItemView.EditingState
        )

    @staticmethod
    def _dispatch_to_focused_editor(verb):
        """把 copy/cut/paste 操作转发给当前获得焦点的编辑器（QLineEdit 等）。

        当 QShortcut 以 WidgetWithChildrenShortcut 上下文绑到 table 时，
        Ctrl+C/V/X 会优先命中 QShortcut，导致编辑器（QLineEdit）内部的文本
        复制粘贴失效。此方法取回焦点编辑器并调用其原生方法，保证编辑中的
        文字复制/剪切/粘贴行为符合预期。
        """
        w = QApplication.focusWidget()
        if w is None:
            return False
        target = w
        if isinstance(w, QComboBox):
            line_edit = w.lineEdit()
            if line_edit is not None:
                target = line_edit
        method = getattr(target, verb, None)
        if callable(method):
            try:
                method()
                return True
            except Exception:
                return False
        return False

    def _resolve_anchor(self, row, col):
        """返回 (row, col) 所在合并单元格的左上角锚点坐标。"""
        r, c, _rs, _cs = self._merge_block(row, col)
        return r, c

    def _merge_block(self, row, col):
        """返回覆盖 (row, col) 的合并区域 (r, c, rowSpan, colSpan)。

        未命中任何合并区域时返回 (row, col, 1, 1)。
        """
        for (r, c, rs, cs) in getattr(self, "_merges", {}).get(self.current_item, []):
            if r <= row < r + rs and c <= col < c + cs:
                return r, c, rs, cs
        return row, col, 1, 1

    def _copy(self):
        """复制选中区域到剪贴板（Tab 分隔）"""
        if self._is_editing():
            self._dispatch_to_focused_editor("copy")
            return
        rng = self._get_selected_range()
        if not rng:
            return
        top, bottom, left, right = rng
        lines = []
        for r in range(top, bottom + 1):
            cells = []
            for c in range(left, right + 1):
                ar, ac = self._resolve_anchor(r, c)
                it = self.table.item(ar, ac)
                cells.append(it.text() if it else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
        self._status("已复制")

    def _cut(self):
        """剪切：复制后清除内容"""
        if self._is_editing():
            self._dispatch_to_focused_editor("cut")
            return
        self._copy()
        self._clear_cells()
        self._status("已剪切")

    def _paste(self):
        """从剪贴板粘贴（Tab 分隔）"""
        if self._is_editing():
            self._dispatch_to_focused_editor("paste")
            return
        if not self.current_item:
            return
        text = QApplication.clipboard().text()
        if not text:
            return
        start_row = self.table.currentRow()
        start_col = self.table.currentColumn()
        if start_row < 0:
            start_row = 0
        if start_col < 0:
            start_col = 0
        start_row, start_col = self._resolve_anchor(start_row, start_col)
        lines = text.split("\n")
        # Excel / 记事本复制的文本常带末尾换行，去掉多余空行
        while lines and lines[-1] == "":
            lines.pop()

        # 是否为“单列清单”粘贴（例如从 Excel/文档复制的一列位置值）。
        # 只有单列且目标列是纵向合并列时，才按“每个值占一个合并块”跳过锚点；
        # 多列（矩形区域）粘贴保持逐行逐列对应，避免“批量复制”被拆散。
        single_column = all("\t" not in line for line in lines)

        # 先规划每个粘贴单元的目标锚点。
        used = set()
        targets = []  # [(anchor_row, anchor_col, value), ...]
        for ri, line in enumerate(lines):
            cells = line.split("\t")
            for ci, val in enumerate(cells):
                r = start_row + ri
                c = start_col + ci
                while r >= self.table.rowCount():
                    self.table.insertRow(self.table.rowCount())
                    self._update_row_headers(self.table.rowCount())
                if c >= self.table.columnCount():
                    continue
                ar, ac = self._resolve_anchor(r, c)
                if single_column:
                    while (ar, ac) in used:
                        _rr, _cc, rs, _cs = self._merge_block(ar, ac)
                        r = _rr + rs
                        while r >= self.table.rowCount():
                            self.table.insertRow(self.table.rowCount())
                            self._update_row_headers(self.table.rowCount())
                        ar, ac = self._resolve_anchor(r, c)
                targets.append((ar, ac, val))
                used.add((ar, ac))

        if not targets:
            return

        # 合并单元格会导致多个源单元格映射到同一锚点；如果粘贴块中含有空
        # 单元格，后续空值会覆盖前面的非空值，造成“复制后数据消失”。这里按
        # 锚点去重，并优先保留最后一个非空值。
        final_targets = {}
        for ar, ac, val in targets:
            if val != "":
                final_targets[(ar, ac)] = val
            elif (ar, ac) not in final_targets:
                final_targets[(ar, ac)] = ""
        targets = [(ar, ac, val) for (ar, ac), val in final_targets.items()]

        top = min(t[0] for t in targets)
        bottom = max(t[0] for t in targets)
        left = min(t[1] for t in targets)
        right = max(t[1] for t in targets)
        # 撤销快照
        self._snapshot_before_edit = self._snapshot_cells(top, left, bottom, right)
        self._loading = True
        try:
            for ar, ac, val in targets:
                it = self.table.item(ar, ac)
                if not it:
                    it = QTableWidgetItem()
                    self.table.setItem(ar, ac, it)
                it.setText(val)
        finally:
            self._loading = False
        self._push_undo(self._snapshot_before_edit)
        self._sync_table_to_data()
        if self._is_core_drilling_sheet():
            self._recalc_core_drilling_all()
        elif self._is_rebound_core_drilling_sheet():
            self._recalc_rebound_core_drilling_all()
        self._apply_all_calc_rules()
        self._sync_table_to_data()
        self._recompute_formulas()
        self._status("已粘贴")

    def _on_fill_handle_dragged(self, start_rng, end_rng):
        """填充柄拖拽回调：将 start_rng 的内容/格式填充到 end_rng"""
        if not self.current_item:
            return
        s_top, s_bottom, s_left, s_right = start_rng
        e_top, e_bottom, e_left, e_right = end_rng
        src_rows = s_bottom - s_top + 1
        src_cols = s_right - s_left + 1
        snapshot = self._snapshot_cells(e_top, e_left, e_bottom, e_right)
        self._loading = True
        try:
            written = set()
            for r in range(e_top, e_bottom + 1):
                for c in range(e_left, e_right + 1):
                    # 合并单元格：只写到左上角锚点，跳过被覆盖的隐藏子格，
                    # 避免“填充后看不到结果”。源单元格同样重映射到其锚点。
                    dst_ar, dst_ac = self._resolve_anchor(r, c)
                    if (dst_ar, dst_ac) in written:
                        continue
                    written.add((dst_ar, dst_ac))
                    # 周期性映射回源区域（Excel 的填充规则）
                    src_r = s_top + (dst_ar - e_top) % src_rows
                    src_c = s_left + (dst_ac - e_left) % src_cols
                    src_ar, src_ac = self._resolve_anchor(src_r, src_c)
                    src_it = self.table.item(src_ar, src_ac)
                    dst_it = self.table.item(dst_ar, dst_ac)
                    if not dst_it:
                        dst_it = QTableWidgetItem()
                        self.table.setItem(dst_ar, dst_ac, dst_it)
                    if src_it:
                        dst_it.setText(src_it.text())
                        # 复制公式（相对引用偏移后续可由公式引擎处理）
                        formula = src_it.data(ROLE_FORMULA)
                        if formula:
                            dst_it.setData(ROLE_FORMULA, formula)
                        # 复制格式
                        self._copy_format(src_it, dst_it)
        finally:
            self._loading = False
        self._push_undo(snapshot)
        self._recompute_formulas()
        self._status(f"已填充 {e_bottom - e_top + 1}×{e_right - e_left + 1}")
