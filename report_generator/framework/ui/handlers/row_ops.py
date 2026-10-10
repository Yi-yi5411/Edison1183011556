# -*- coding: utf-8 -*-
"""行操作 Mixin（行头更新 / 数据同步 / 插入删除行 / 清除 / 批量填充）"""

from PyQt5.QtWidgets import QTableWidgetItem, QMessageBox, QDialog

from framework.ui import (
    ROLE_FORMULA, ROLE_BOLD, ROLE_ITALIC, ROLE_UNDERLINE, ROLE_ALIGN,
    ROLE_BG, ROLE_FG, ROLE_NUMFMT, ROLE_BORDER,
)
from framework.ui.dialogs import BatchInsertRowsDialog, BatchFillDialog


class RowOpsMixin:
    """行操作相关"""

    def _update_row_headers(self, count):
        """更新行头为 1, 2, 3, ..."""
        self.table.setVerticalHeaderLabels([str(i + 1) for i in range(count)])

    def _sync_table_to_data(self):
        """将表格数据同步到 sheet_data（公式保留原文），同时收集单元格格式"""
        if not self.current_item:
            return
        rows = self.table.rowCount()
        cols = self.table.columnCount()
        data = []
        cell_formats = {}  # {(r,c): {"bold":bool,"italic":bool,"underline":bool,"align":str,"bg":str,"fg":str,"numfmt":str,"border":dict}}
        for r in range(rows):
            row_data = []
            for c in range(cols):
                item = self.table.item(r, c)
                if item:
                    formula = item.data(ROLE_FORMULA)
                    if formula:
                        row_data.append(formula)
                    else:
                        row_data.append(item.text())
                    # 收集非默认格式的单元格
                    fmt = {}
                    if item.data(ROLE_BOLD):
                        fmt["bold"] = True
                    if item.data(ROLE_ITALIC):
                        fmt["italic"] = True
                    if item.data(ROLE_UNDERLINE):
                        fmt["underline"] = True
                    if item.data(ROLE_ALIGN):
                        fmt["align"] = item.data(ROLE_ALIGN)
                    bg = item.data(ROLE_BG)
                    if bg:
                        fmt["bg"] = bg
                    fg = item.data(ROLE_FG)
                    if fg:
                        fmt["fg"] = fg
                    numfmt = item.data(ROLE_NUMFMT)
                    if numfmt:
                        fmt["numfmt"] = numfmt
                    border = item.data(ROLE_BORDER)
                    if border:
                        fmt["border"] = border
                    if fmt:
                        cell_formats[(r, c)] = fmt
                else:
                    row_data.append("")
            data.append(row_data)
        self.sheet_data[self.current_item] = data
        self._cell_formats[self.current_item] = cell_formats
        if hasattr(self, '_ensure_rebar_axis_merges'):
            self._ensure_rebar_axis_merges(self.current_item)
        # 剪除尾部全空行，避免默认空行污染数据
        self._trim_sheet_data_tail(self.current_item)

    def _trim_sheet_data_tail(self, sheet_key):
        """剪除 sheet_data 中指定工作表的尾部全空行。

        调用 _sync_table_to_data 后，表格可能包含 _default_rows 个行，
        其中尾部为空行。此方法剪除这些空行，仅保留最后一个非空行之前的数据。
        """
        data = self.sheet_data.get(sheet_key, [])
        if not data:
            return
        # 从尾部向前找最后一个非空行
        last_non_empty = len(data) - 1
        while last_non_empty >= 0:
            if any(cell for cell in data[last_non_empty] if cell):
                break
            last_non_empty -= 1
        if last_non_empty < 0:
            self.sheet_data[sheet_key] = []
        elif last_non_empty < len(data) - 1:
            self.sheet_data[sheet_key] = data[:last_non_empty + 1]

    def _insert_row_above(self):
        """在当前行上方插入行"""
        if not self.current_item:
            return
        item = self.table.currentItem()
        row = item.row() if item else 0
        self._reset_spans()
        self.table.insertRow(row)
        for c in range(self.table.columnCount()):
            self.table.setItem(row, c, QTableWidgetItem())
        self._adjust_merges_for_insert_row(row)
        self._apply_merges_to_table()
        self._update_row_headers(self.table.rowCount())
        if hasattr(self, "_apply_column_access"):
            self._apply_column_access()
        self._status(f"在第 {row + 1} 行上方插入行")

    def _insert_row_below(self):
        """在当前行下方插入行"""
        if not self.current_item:
            return
        item = self.table.currentItem()
        row = item.row() if item else 0
        self._reset_spans()
        self.table.insertRow(row + 1)
        for c in range(self.table.columnCount()):
            self.table.setItem(row + 1, c, QTableWidgetItem())
        self._adjust_merges_for_insert_row(row + 1)
        self._apply_merges_to_table()
        self._update_row_headers(self.table.rowCount())
        if hasattr(self, "_apply_column_access"):
            self._apply_column_access()
        self._status(f"在第 {row + 1} 行下方插入行")

    def _batch_insert_rows(self):
        """Ctrl+Shift+N: 批量插入多行"""
        if not self.current_item:
            QMessageBox.information(self.win, "提示", "请先勾选检测项目")
            return
        dlg = BatchInsertRowsDialog(self.win)
        if dlg.exec_() != QDialog.Accepted:
            return
        result = dlg.get_result()
        if not result:
            return
        insert_row, count = result
        self._reset_spans()
        for i in range(count):
            self.table.insertRow(insert_row + i)
            for c in range(self.table.columnCount()):
                self.table.setItem(insert_row + i, c, QTableWidgetItem())
        self._adjust_merges_for_insert_row(insert_row)
        self._apply_merges_to_table()
        self._update_row_headers(self.table.rowCount())
        if hasattr(self, "_apply_column_access"):
            self._apply_column_access()
        self._status(f"在第 {insert_row + 1} 行插入了 {count} 行")

    def _delete_rows(self):
        """删除选中行"""
        if not self.current_item:
            return
        rng = self._get_selected_range()
        if not rng:
            return
        top, bottom = rng[0], rng[1]
        reply = QMessageBox.question(
            self.win, "确认删除",
            f"确定删除第 {top + 1}~{bottom + 1} 行？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._reset_spans()
        self._loading = True
        try:
            for r in range(bottom, top - 1, -1):
                self.table.removeRow(r)
                self._adjust_merges_for_delete_row(r)
        finally:
            self._loading = False
        self._apply_merges_to_table()
        self._update_row_headers(self.table.rowCount())
        if hasattr(self, "_apply_column_access"):
            self._apply_column_access()
        self._status(f"已删除 {bottom - top + 1} 行")

    def _clear_cells(self):
        """清除选中单元格内容"""
        if not self.current_item:
            return
        rng = self._get_selected_range()
        self._loading = True
        try:
            for it in self._collect_selected_items(rng):
                it.setText("")
                it.setData(ROLE_FORMULA, None)
        finally:
            self._loading = False
        self._recompute_formulas()
        if self._is_core_drilling_sheet():
            self._recalc_core_drilling_all()
            self._sync_table_to_data()
        self._status("已清除内容")

    def _run_batch_fill(self):
        """批量填充：固定值/递增序列/向下填充首值"""
        if not self.current_item:
            QMessageBox.information(self.win, "提示", "请先勾选检测项目")
            return

        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择要填充的单元格区域")
            return

        top, bottom, left, right = rng
        n_rows = bottom - top + 1
        n_cols = right - left + 1

        dlg = BatchFillDialog(self.win, n_rows, n_cols)
        if dlg.exec_() != QDialog.Accepted:
            return

        result = dlg.get_result()
        if result is None:
            return

        mode, value, step = result

        # 把选区内的每个单元格重映射到其合并锚点，避免写入被合并覆盖的隐藏子格；
        # 这样批量填充/向下填充只作用于可见锚点，选区与显示结果保持一致。
        anchor_cells = []
        seen = set()
        for r in range(top, bottom + 1):
            for c in range(left, right + 1):
                ar, ac = self._resolve_anchor(r, c)
                if (ar, ac) in seen:
                    continue
                seen.add((ar, ac))
                anchor_cells.append((ar, ac))
        anchor_cells.sort()

        # 撤销快照：仅对将要写入的锚点单元格做快照
        items = [self.table.item(ar, ac) for ar, ac in anchor_cells]
        snapshot = self._snapshot_from_items([it for it in items if it is not None])

        self._loading = True
        try:
            if mode == BatchFillDialog.MODE_FIXED:
                # 固定值填充
                for ar, ac in anchor_cells:
                    it = self.table.item(ar, ac)
                    if it is None:
                        it = QTableWidgetItem()
                        self.table.setItem(ar, ac, it)
                    it.setText(value)
                    it.setData(ROLE_FORMULA, None)

            elif mode == BatchFillDialog.MODE_INCREMENT:
                # 递增序列填充（按可见锚点的行列顺序递增）
                try:
                    start_val = float(value) if value else 0.0
                    step_val = float(step) if step else 1.0
                except (ValueError, TypeError):
                    QMessageBox.warning(self.win, "提示", "起始值和步长必须为数字")
                    return
                for idx, (ar, ac) in enumerate(anchor_cells):
                    it = self.table.item(ar, ac)
                    if it is None:
                        it = QTableWidgetItem()
                        self.table.setItem(ar, ac, it)
                    cur_val = start_val + idx * step_val
                    if cur_val == int(cur_val):
                        it.setText(str(int(cur_val)))
                    else:
                        it.setText(f"{cur_val:.6g}")
                    it.setData(ROLE_FORMULA, None)

            elif mode == BatchFillDialog.MODE_DOWN_FILL:
                # 向下填充首值：每列从第一个非空锚点向下填充
                for c in range(left, right + 1):
                    col_anchors = [(ar, ac) for ar, ac in anchor_cells if ac == c]
                    first_val = None
                    for ar, ac in col_anchors:
                        it = self.table.item(ar, ac)
                        text = it.text() if it is not None else ""
                        if first_val is None:
                            if text:
                                first_val = text
                        else:
                            if it is None:
                                it = QTableWidgetItem()
                                self.table.setItem(ar, ac, it)
                            it.setText(first_val)
                            it.setData(ROLE_FORMULA, None)

        finally:
            self._loading = False

        # 钻芯法检测：统一重算
        if self._is_core_drilling_sheet():
            for r in range(top, bottom + 1):
                self._recalc_core_drilling_row(r)
            self._recalc_core_drilling_batch_value()

        self._sync_table_to_data()
        self._recompute_formulas()
        self._push_undo(snapshot)

        mode_names = {BatchFillDialog.MODE_FIXED: "固定值",
                      BatchFillDialog.MODE_INCREMENT: "递增序列",
                      BatchFillDialog.MODE_DOWN_FILL: "向下填充首值"}
        self._status(f"批量填充完成（{mode_names.get(mode, '?')}）")
