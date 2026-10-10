# -*- coding: utf-8 -*-
"""合并单元格操作 Mixin（setSpan 合并 / 取消 / 索引调整）"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem

from framework.ui import ROLE_FORMULA, ROLE_ALIGN, ROLE_NUMFMT, ROLE_BORDER


class MergeOpsMixin:
    """合并单元格相关操作"""

    def _reset_spans(self):
        """重置表格中所有已应用的合并"""
        for (r, c, rs, cs) in self._displayed_merges:
            if rs <= 1 and cs <= 1:
                continue
            try:
                self.table.setSpan(r, c, 1, 1)
            except Exception:
                pass
        if self.current_item and self.current_item in self._merges:
            for (r, c, rs, cs) in self._merges[self.current_item]:
                if rs <= 1 and cs <= 1:
                    continue
                try:
                    self.table.setSpan(r, c, 1, 1)
                except Exception:
                    pass
        self._displayed_merges = []

    def _apply_merges_to_table(self):
        """将 _merges 中的合并应用到当前表格（同时恢复合并单元格格式）"""
        if not self.current_item:
            return
        merges = self._merges.get(self.current_item, [])
        formats = self._merge_formats.get(self.current_item, {})
        for (r, c, rs, cs) in merges:
            if rs <= 1 and cs <= 1:
                continue
            try:
                self.table.setSpan(r, c, rs, cs)
                # 左上角为空时，把覆盖区中的第一个非空值补回，避免数据不可见
                self._fill_empty_merge_anchor(r, c, rs, cs)
                fmt = formats.get((r, c), {})
                anchor = self.table.item(r, c)
                if anchor:
                    align = fmt.get("align", "center")
                    flag = {"left": Qt.AlignLeft, "center": Qt.AlignCenter, "right": Qt.AlignRight}.get(align, Qt.AlignCenter)
                    anchor.setTextAlignment(flag | Qt.AlignVCenter)
                    if fmt.get("bold"):
                        f = anchor.font()
                        f.setBold(True)
                        anchor.setFont(f)
            except Exception:
                pass
        self._displayed_merges = list(merges)

    def _fill_empty_merge_anchor(self, r, c, rs, cs):
        """合并区域左上角为空时，从覆盖单元格中取第一个非空值填充。

        同时清空被复制到的来源单元格，保持 sheet_data 同步后只保留一份数据。
        """
        anchor = self.table.item(r, c)
        if anchor is not None and anchor.text().strip() != "":
            return

        was_loading = getattr(self, "_loading", False)
        self._loading = True
        try:
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    if rr == r and cc == c:
                        continue
                    it = self.table.item(rr, cc)
                    if not it or it.text().strip() == "":
                        continue
                    if anchor is None:
                        anchor = QTableWidgetItem()
                        self.table.setItem(r, c, anchor)
                    anchor.setText(it.text())
                    formula = it.data(ROLE_FORMULA)
                    anchor.setData(ROLE_FORMULA, formula if formula else None)
                    it.setText("")
                    it.setData(ROLE_FORMULA, None)
                    return
        finally:
            self._loading = was_loading

    def _restore_cell_formats(self):
        """从 _cell_formats 恢复当前工作表的单元格格式"""
        if not self.current_item:
            return
        fmts = self._cell_formats.get(self.current_item, {})
        for (r, c), fmt in fmts.items():
            it = self.table.item(r, c)
            if not it:
                continue
            if fmt.get("bold"):
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            if fmt.get("italic"):
                f = it.font()
                f.setItalic(True)
                it.setFont(f)
            if fmt.get("underline"):
                f = it.font()
                f.setUnderline(True)
                it.setFont(f)
            align = fmt.get("align")
            if align:
                flag = {"left": Qt.AlignLeft, "center": Qt.AlignCenter, "right": Qt.AlignRight}.get(align, Qt.AlignCenter)
                it.setTextAlignment(flag | Qt.AlignVCenter)
            bg = fmt.get("bg")
            if bg:
                it.setBackground(QBrush(QColor(bg)))
            fg = fmt.get("fg")
            if fg:
                it.setForeground(QBrush(QColor(fg)))
            numfmt = fmt.get("numfmt")
            if numfmt:
                it.setData(ROLE_NUMFMT, numfmt)
            border = fmt.get("border")
            if border:
                it.setData(ROLE_BORDER, border)

    def _merge_cells(self):
        """合并选中单元格并居中对齐（可重复调用，支持多次合并）"""
        if not self.current_item:
            QMessageBox.information(self.win, "提示", "请先勾选检测项目")
            return

        rng = self._get_selected_range()
        if not rng:
            QMessageBox.information(self.win, "提示", "请先选择要合并的单元格区域")
            return
        top, bottom, left, right = rng

        if top == bottom and left == right:
            QMessageBox.information(self.win, "提示", "请至少选择 2 个单元格再合并")
            return

        num_rows = bottom - top + 1
        num_cols = right - left + 1

        # 检查是否与已有合并重叠
        if self.current_item in self._merges:
            for (r, c, rs, cs) in self._merges[self.current_item]:
                overlaps = (
                    r <= bottom and r + rs - 1 >= top
                    and c <= right and c + cs - 1 >= left
                )
                if overlaps:
                    QMessageBox.warning(
                        self.win, "合并冲突",
                        f"所选区域与已有合并区域 (行{r+1}-{r+rs}, 列{c+1}-{c+cs}) 重叠，\n"
                        f"请先取消该区域的合并，再重新操作。"
                    )
                    return

        # 清除被覆盖单元格的内容（保留左上角）
        self._loading = True
        try:
            # 若左上角为空，先从选区中取第一个非空值补回，避免合并后数据丢失
            self._fill_empty_merge_anchor(top, left, num_rows, num_cols)

            for r in range(top, bottom + 1):
                for c in range(left, right + 1):
                    if r == top and c == left:
                        continue
                    it = self.table.item(r, c)
                    if it:
                        it.setText("")
                        it.setData(ROLE_FORMULA, None)
        finally:
            self._loading = False

        # 直接应用新合并（不清除已有合并）
        try:
            self.table.setSpan(top, left, num_rows, num_cols)
        except Exception as e:
            QMessageBox.warning(self.win, "合并失败", f"setSpan 出错: {e}")
            return

        # 居中对齐左上角单元格
        anchor = self.table.item(top, left)
        if anchor:
            anchor.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            anchor.setData(ROLE_ALIGN, "center")

        # 记录合并
        if self.current_item not in self._merges:
            self._merges[self.current_item] = []
        merge = (top, left, num_rows, num_cols)
        if merge not in self._merges[self.current_item]:
            self._merges[self.current_item].append(merge)

        # 保存合并格式
        if self.current_item not in self._merge_formats:
            self._merge_formats[self.current_item] = {}
        self._merge_formats[self.current_item][(top, left)] = {
            "align": "center",
            "bold": False,
        }

        self._displayed_merges = list(self._merges[self.current_item])

        # 合并后清除选区，避免旧选区干扰下一次操作
        self.table.clearSelection()
        self.table.setCurrentCell(top, left)

        self._status(f"已合并 {num_rows}×{num_cols} 单元格")

    def _unmerge_cells(self):
        """Unmerge every merge range intersecting the current selection."""
        if not self.current_item:
            return

        rng = self._get_selected_range()
        if not rng:
            item = self.table.currentItem()
            if not item:
                return
            rng = (item.row(), item.column(), item.row(), item.column())
        top, bottom, left, right = rng

        merges = self._merges.get(self.current_item, [])
        targets = []
        for (r, c, rs, cs) in merges:
            if r <= bottom and r + rs - 1 >= top and c <= right and c + cs - 1 >= left:
                targets.append((r, c, rs, cs))

        if not targets:
            self._status("\u5f53\u524d\u9009\u533a\u65e0\u5408\u5e76\u5355\u5143\u683c")
            return

        self._loading = True
        try:
            for (r, c, rs, cs) in targets:
                try:
                    self.table.setSpan(r, c, 1, 1)
                except Exception:
                    pass
                if (r, c, rs, cs) in self._merges.get(self.current_item, []):
                    self._merges[self.current_item].remove((r, c, rs, cs))
                if self.current_item in self._merge_formats:
                    self._merge_formats[self.current_item].pop((r, c), None)
        finally:
            self._loading = False

        self._displayed_merges = list(self._merges.get(self.current_item, []))
        self._status(f"\u5df2\u53d6\u6d88\u5408\u5e76 {len(targets)} \u5904")

    def _clear_overlapping_merges(self, top, bottom, left, right):
        """清除与新合并区域重叠的已有合并"""
        if self.current_item not in self._merges:
            return
        new_merges = []
        for (r, c, rs, cs) in self._merges[self.current_item]:
            # 判断矩形重叠
            overlaps = (
                r <= bottom and r + rs - 1 >= top
                and c <= right and c + cs - 1 >= left
            )
            if overlaps:
                try:
                    self.table.setSpan(r, c, 1, 1)
                except Exception:
                    pass
            else:
                new_merges.append((r, c, rs, cs))
        self._merges[self.current_item] = new_merges

    def _adjust_merges_for_insert_row(self, at_row):
        """插入行后，将 at_row 及以下的合并下移一行"""
        if self.current_item not in self._merges:
            return
        new_merges = []
        for (r, c, rs, cs) in self._merges[self.current_item]:
            if r >= at_row:
                new_merges.append((r + 1, c, rs, cs))
            else:
                new_merges.append((r, c, rs, cs))
        self._merges[self.current_item] = new_merges

    def _adjust_merges_for_delete_row(self, deleted_row):
        """删除行后，调整合并索引"""
        if self.current_item not in self._merges:
            return
        new_merges = []
        for (r, c, rs, cs) in self._merges[self.current_item]:
            if r == deleted_row:
                continue  # 合并锚点在被删行，丢弃
            elif r > deleted_row:
                new_merges.append((r - 1, c, rs, cs))
            else:
                # 锚点在被删行上方；若跨被删行则缩减行高
                if r + rs - 1 >= deleted_row:
                    new_merges.append((r, c, rs - 1, cs))
                else:
                    new_merges.append((r, c, rs, cs))
        self._merges[self.current_item] = new_merges
