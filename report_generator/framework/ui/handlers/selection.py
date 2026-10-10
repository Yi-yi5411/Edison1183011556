# -*- coding: utf-8 -*-
"""选区操作 Mixin（选区变化 / 行列选择 / 状态栏更新）"""


class SelectionMixin:
    """选区相关操作"""

    def _on_selection_changed(self):
        """选区变化：更新状态栏（区分行选/列选/单元格选）"""
        sel_rows = self._get_sel_rows()
        sel_cols = self._get_sel_cols()
        if sel_rows and sel_cols:
            # 统计选区规模
            rng = self._get_selected_range()
            if rng:
                top, bottom, left, right = rng
                n_rows = bottom - top + 1
                n_cols = right - left + 1
                # 检查是否整行选中
                is_full_row = (n_rows == self.table.rowCount() and
                              len(sel_rows) == self.table.rowCount())
                is_full_col = (n_cols == self.table.columnCount() and
                               len(sel_cols) == self.table.columnCount())
                if is_full_row and not is_full_col:
                    self._status(f"选中: {len(sel_rows)} 行（整行选择）")
                elif is_full_col and not is_full_row:
                    self._status(f"选中: {len(sel_cols)} 列（整列选择）")
                elif len(sel_rows) == 1 and len(sel_cols) == 1:
                    self._status(f"选中: 单元格 ({sel_rows[0]+1}, {sel_cols[0]+1})")
                else:
                    self._status(f"选中: {len(sel_rows)} 行 × {len(sel_cols)} 列")

        if hasattr(self, "current_item") and self.current_item and \
                hasattr(self, "_get_computed_columns"):
            computed = self._get_computed_columns()
            if computed:
                calc_cols = [c for c in sel_cols if c in computed]
                if len(sel_cols) == 1 and calc_cols:
                    self._status("选中: 自动计算列（由系统生成，不可编辑）")
                elif calc_cols and set(sel_cols).issubset(computed):
                    self._status(f"选中: {len(sel_cols)} 列（均为自动计算列）")

    def _select_column(self):
        """Ctrl+Space: 选择当前单元格所在整列"""
        item = self.table.currentItem()
        if item:
            self.table.selectColumn(item.column())

    def _select_row(self):
        """Shift+Space: 选择当前单元格所在整行"""
        item = self.table.currentItem()
        if item:
            self.table.selectRow(item.row())

    def _edit_current_cell(self):
        """F2: 进入当前单元格的编辑模式"""
        item = self.table.currentItem()
        if item:
            self.table.editItem(item)

    def _on_row_header_clicked(self, logical_index):
        """点击行头 → 选中整行"""
        row = logical_index
        self.table.selectRow(row)

    def _on_col_header_clicked(self, logical_index):
        """点击列头 → 选中整列"""
        col = logical_index
        self.table.selectColumn(col)

    def _get_selected_range(self):
        """获取当前选区 (topRow, bottomRow, leftCol, rightCol) 或 None"""
        ranges = self.table.selectedRanges()
        if not ranges:
            return None
        r = ranges[0]
        return (r.topRow(), r.bottomRow(), r.leftColumn(), r.rightColumn())

    def _get_sel_rows(self):
        """获取选中行号集合（支持单元格拖拽选区与行头点击选区）"""
        rows = set()
        # 遍历所有选区范围（行头点击会生成整行选区）
        for r in self.table.selectedRanges():
            for row in range(r.topRow(), r.bottomRow() + 1):
                rows.add(row)
        return sorted(rows)

    def _get_sel_cols(self):
        """获取选中列号集合（支持单元格拖拽选区与列头点击选区）"""
        cols = set()
        # 遍历所有选区范围（列头点击会生成整列选区）
        for r in self.table.selectedRanges():
            for col in range(r.leftColumn(), r.rightColumn() + 1):
                cols.add(col)
        return sorted(cols)

    def _collect_selected_items(self, rng=None):
        """收集选区内所有 QTableWidgetItem"""
        if rng is None:
            rng = self._get_selected_range()
        items = []
        if rng:
            top, bottom, left, right = rng
            for r in range(top, bottom + 1):
                for c in range(left, right + 1):
                    it = self.table.item(r, c)
                    if it:
                        items.append(it)
        else:
            it = self.table.currentItem()
            if it:
                items.append(it)
        return items

    def _status(self, msg):
        """更新状态栏"""
        self.status_label.setText(msg)
