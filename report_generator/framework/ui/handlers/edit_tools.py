# -*- coding: utf-8 -*-
"""编辑工具 Mixin（查找替换 / 冻结窗格 / 行高列宽 / 求和汇总 / 函数选择 / 批量修改）"""

import math

from PyQt5.QtWidgets import (
    QMessageBox, QInputDialog, QDialog,
    QTableWidgetSelectionRange, QTableWidgetItem,
)

from framework.ui.dialogs import BatchRowHeightDialog, FunctionSelectorDialog, BatchModifyDialog
from framework.engine.formula import col_index_to_letter
from framework.ui import ROLE_FORMULA


class EditToolsMixin:
    """编辑工具相关"""

    def _find_replace(self):
        """打开查找替换对话框"""
        if not self.current_item:
            return
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, \
            QPushButton, QCheckBox, QLabel
        dlg = QDialog(self.win)
        dlg.setWindowTitle("查找与替换")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("查找内容:"))
        find_edit = QLineEdit()
        layout.addWidget(find_edit)
        layout.addWidget(QLabel("替换为:"))
        replace_edit = QLineEdit()
        layout.addWidget(replace_edit)
        match_case = QCheckBox("区分大小写")
        layout.addWidget(match_case)
        btn_layout = QHBoxLayout()
        find_btn = QPushButton("查找下一个")
        replace_btn = QPushButton("替换")
        all_btn = QPushButton("全部替换")
        close_btn = QPushButton("关闭")
        btn_layout.addWidget(find_btn)
        btn_layout.addWidget(replace_btn)
        btn_layout.addWidget(all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        match_count = [0]

        def find_next():
            target = find_edit.text()
            if not target:
                return
            case_sensitive = match_case.isChecked()
            cur = self.table.currentItem()
            start_r = (cur.row() + 1) if cur else 0
            start_c = (cur.column() + 1) if cur else 0
            total_rows = self.table.rowCount()
            total_cols = self.table.columnCount()
            for r in range(start_r, total_rows):
                cols_range = range(start_c if r == start_r else 0, total_cols)
                for c in cols_range:
                    it = self.table.item(r, c)
                    if it and it.text():
                        text = it.text() if case_sensitive else it.text().lower()
                        tgt = target if case_sensitive else target.lower()
                        if tgt in text:
                            self.table.clearSelection()
                            self.table.setRangeSelected(
                                QTableWidgetSelectionRange(r, c, r, c), True
                            )
                            self.table.setCurrentCell(r, c)
                            self._status(f"找到: 行{r+1} 列{c+1}")
                            return
            self._status("未找到")

        def replace_one():
            target = find_edit.text()
            replacement = replace_edit.text()
            if not target:
                return
            cur = self.table.currentItem()
            if not cur:
                find_next()
                return
            case_sensitive = match_case.isChecked()
            text = cur.text() if case_sensitive else cur.text().lower()
            tgt = target if case_sensitive else target.lower()
            if tgt in text:
                cur.setText(cur.text().replace(target, replacement))
                match_count[0] += 1
                self._status(f"已替换 {match_count[0]} 处")
            find_next()

        def replace_all():
            target = find_edit.text()
            replacement = replace_edit.text()
            if not target:
                return
            case_sensitive = match_case.isChecked()
            count = 0
            snapshot = None
            for r in range(self.table.rowCount()):
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    if it and it.text():
                        text = it.text() if case_sensitive else it.text().lower()
                        tgt = target if case_sensitive else target.lower()
                        if tgt in text:
                            if snapshot is None:
                                snapshot = self._snapshot_cells(r, c, r, c)
                            it.setText(it.text().replace(target, replacement))
                            count += 1
            if snapshot:
                self._push_undo(snapshot)
            self._status(f"共替换 {count} 处")

        find_btn.clicked.connect(find_next)
        replace_btn.clicked.connect(replace_one)
        all_btn.clicked.connect(replace_all)
        close_btn.clicked.connect(dlg.accept)
        dlg.exec_()

    def _freeze_panes(self):
        """冻结当前单元格上方和左侧的窗格。

        实现方式：利用 QTableWidget 内置的 setSpan 机制将冻结行/列的单元格
        叠加在滚动区域之上（通过设置 _frozen_pane + 重写滚动事件使冻结
        行列保持位置不动）。实际做法：记录冻结位置，通过 eventFilter
        拦截滚动事件，确保冻结线以上/以左的单元格不参与滚动。
        """
        cur = self.table.currentItem()
        if not cur:
            QMessageBox.information(self.win, "提示", "请先选择冻结位置")
            return
        row = cur.row()
        col = cur.column()
        if self.table._frozen_pane == (row, col):
            self.table._frozen_pane = None
            self.table.viewport().update()
            self._status("已取消冻结")
        else:
            self.table._frozen_pane = (row, col)
            self.table.viewport().update()
            self._status(f"已冻结: 行{row+1} 列{col+1} 上方/左侧")

    def _set_row_height(self):
        """手动设置行高"""
        rng = self._get_selected_range()
        if not rng:
            cur = self.table.currentItem()
            if cur:
                rows = [cur.row()]
            else:
                return
        else:
            top, bottom, _, _ = rng
            rows = list(range(top, bottom + 1))
        height, ok = QInputDialog.getInt(
            self.win, "行高", "输入行高(像素):", 24, 10, 200
        )
        if not ok:
            return
        for r in rows:
            self.table.setRowHeight(r, height)
        self._status(f"已设置行高: {height}px")

    def _batch_row_height(self):
        """批量调整行高"""
        if not self.current_item:
            return
        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择行")
            return
        top, bottom = rng[0], rng[1]
        dlg = BatchRowHeightDialog(self.win, top + 1, bottom + 1)
        if dlg.exec_() != QDialog.Accepted:
            return
        height = dlg.get_height()
        if height is None:
            return
        for r in range(top, bottom + 1):
            self.table.setRowHeight(r, height)
        self._status(f"已设置第 {top+1}~{bottom+1} 行高度为 {height} 像素")

    def _set_col_width(self):
        """手动设置列宽"""
        rng = self._get_selected_range()
        if not rng:
            cur = self.table.currentItem()
            if cur:
                cols = [cur.column()]
            else:
                return
        else:
            _, _, left, right = rng
            cols = list(range(left, right + 1))
        width, ok = QInputDialog.getInt(
            self.win, "列宽", "输入列宽(像素):", 100, 30, 500
        )
        if not ok:
            return
        for c in cols:
            self.table.setColumnWidth(c, width)
        self._status(f"已设置列宽: {width}px")

    def _auto_sum(self):
        """对选中区域求和，在下方写入 SUM 公式"""
        if not self.current_item:
            return
        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择求和区域")
            return
        top, bottom, left, right = rng
        target_row = bottom + 1
        target_col = left
        if target_row >= self.table.rowCount():
            self.table.insertRow(self.table.rowCount())
            self._update_row_headers(self.table.rowCount())

        start_ref = f"{col_index_to_letter(left)}{top + 1}"
        end_ref = f"{col_index_to_letter(right)}{bottom + 1}"
        formula = f"=SUM({start_ref}:{end_ref})"

        self._sync_table_to_data()
        self._ensure_engine()
        it = self.table.item(target_row, target_col)
        if not it:
            it = QTableWidgetItem()
            self.table.setItem(target_row, target_col, it)

        self._loading = True
        try:
            it.setData(ROLE_FORMULA, formula)
            result = self._formula_engine.evaluate(
                formula, self.current_item, target_row, target_col
            )
            it.setText(result)
        finally:
            self._loading = False
        self._status(f"求和: {formula} = {result}")

    def _quick_summary(self, op):
        """快速汇总：计算选中区域的统计值"""
        if not self.current_item:
            return
        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择数据区域")
            return
        top, bottom, left, right = rng
        values = []
        for r in range(top, bottom + 1):
            for c in range(left, right + 1):
                it = self.table.item(r, c)
                if it and it.text():
                    try:
                        values.append(float(it.text()))
                    except ValueError:
                        pass
        if not values:
            self._status("选中区域无数值数据")
            return
        if op == "average":
            result = sum(values) / len(values)
            self._status(f"平均值: {result:.2f} ({len(values)} 个数据)")
        elif op == "max":
            result = max(values)
            self._status(f"最大值: {result} ({len(values)} 个数据)")
        elif op == "min":
            result = min(values)
            self._status(f"最小值: {result} ({len(values)} 个数据)")
        elif op == "sum":
            result = sum(values)
            self._status(f"求和: {result} ({len(values)} 个数据)")

    def _show_quick_summary(self):
        """右键菜单：快速汇总对话框"""
        if not self.current_item:
            return
        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择数据区域")
            return
        top, bottom, left, right = rng
        values = []
        for r in range(top, bottom + 1):
            for c in range(left, right + 1):
                it = self.table.item(r, c)
                if it and it.text():
                    try:
                        values.append(float(it.text()))
                    except ValueError:
                        pass
        n = len(values)
        if n == 0:
            QMessageBox.information(self.win, "快速汇总", "选中区域无数值数据")
            return
        total = sum(values)
        avg = total / n
        vmax = max(values)
        vmin = min(values)
        if n > 1:
            mean = avg
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std = math.sqrt(variance)
        else:
            std = 0.0
        info = (f"数据个数: {n}\n"
                f"求和: {total:.4f}\n"
                f"平均值: {avg:.4f}\n"
                f"最大值: {vmax}\n"
                f"最小值: {vmin}\n"
                f"标准差: {std:.4f}")
        QMessageBox.information(self.win, "快速汇总", info)

    def _show_function_selector(self):
        """右键菜单：函数选择器"""
        if not self.current_item:
            return
        dlg = FunctionSelectorDialog(self.win)
        if dlg.exec_() != QDialog.Accepted:
            return
        result = dlg.get_result()
        if result:
            item = self.table.currentItem()
            if item:
                self._loading = True
                try:
                    item.setText(result)
                    item.setData(ROLE_FORMULA, result)
                finally:
                    self._loading = False
                self._sync_table_to_data()
                self._ensure_engine()
                row = item.row()
                col = item.column()
                eval_result = self._formula_engine.evaluate(result, self.current_item, row, col)
                self._loading = True
                try:
                    item.setText(eval_result)
                finally:
                    self._loading = False
                self._status(f"公式: {result} = {eval_result}")

    def _batch_modify(self):
        """批量修改：算术运算或文本替换"""
        if not self.current_item:
            QMessageBox.information(self.win, "提示", "请先勾选检测项目")
            return
        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择要修改的区域")
            return
        dlg = BatchModifyDialog(self.win)
        if dlg.exec_() != QDialog.Accepted:
            return
        result = dlg.get_result()
        if not result:
            return
        mode, op, value = result
        top, bottom, left, right = rng
        items = self._collect_selected_items(rng)
        snapshot = self._snapshot_from_items(items)
        self._loading = True
        try:
            for it in items:
                if it is None:
                    continue
                text = it.text()
                if mode == "arithmetic" and text:
                    try:
                        num = float(text)
                        if op == "+": num += float(value)
                        elif op == "-": num -= float(value)
                        elif op == "*": num *= float(value)
                        elif op == "/": num = num / float(value) if float(value) != 0 else num
                        if num == int(num):
                            it.setText(str(int(num)))
                        else:
                            it.setText(f"{num:.6g}")
                        it.setData(ROLE_FORMULA, None)
                    except ValueError:
                        pass
                elif mode == "replace" and text:
                    it.setText(text.replace(op, value))
                    it.setData(ROLE_FORMULA, None)
        finally:
            self._loading = False
        if self._is_core_drilling_sheet():
            for r in range(top, bottom + 1):
                self._recalc_core_drilling_row(r)
        self._recompute_formulas()
        self._push_undo(snapshot)
        self._status("批量修改完成")
