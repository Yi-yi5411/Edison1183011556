# -*- coding: utf-8 -*-
"""撤销 / 重做 Mixin（快照、入栈、恢复）"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QTableWidgetItem

from framework.ui import (
    ROLE_FORMULA, ROLE_BOLD, ROLE_ITALIC, ROLE_UNDERLINE, ROLE_ALIGN,
    ROLE_BG, ROLE_FG, ROLE_NUMFMT, ROLE_BORDER,
)

# 字体默认值（与 gui_qt.py 模块常量保持一致，供快照恢复使用）
FONT_FAMILY = "Microsoft YaHei"
FONT_SIZE = 10


class UndoRedoMixin:
    """撤销 / 重做相关操作"""

    def _snapshot_cells(self, top, left, bottom, right):
        """对指定区域做快照，返回 {(r,c): (text, formula, format_dict)}"""
        snapshot = {"sheet": self.current_item, "cells": {}}
        for r in range(max(0, top), min(self.table.rowCount(), bottom + 1)):
            for c in range(max(0, left), min(self.table.columnCount(), right + 1)):
                it = self.table.item(r, c)
                if it:
                    fmt = {
                        "bold": it.data(ROLE_BOLD),
                        "italic": it.data(ROLE_ITALIC),
                        "underline": it.data(ROLE_UNDERLINE),
                        "align": it.data(ROLE_ALIGN),
                        "bg": it.data(ROLE_BG),
                        "fg": it.data(ROLE_FG),
                        "numfmt": it.data(ROLE_NUMFMT),
                        "border": it.data(ROLE_BORDER),
                        "font_family": it.font().family(),
                        "font_size": it.font().pointSize(),
                        "text_align": it.textAlignment(),
                    }
                    snapshot["cells"][(r, c)] = (it.text(), it.data(ROLE_FORMULA), fmt)
        return snapshot

    def _push_undo(self, snapshot):
        """入栈撤销快照"""
        if not snapshot or not snapshot["cells"]:
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore_snapshot(self, snapshot):
        """恢复快照"""
        if not snapshot or snapshot["sheet"] != self.current_item:
            return
        self._loading = True
        try:
            for (r, c), (text, formula, fmt) in snapshot["cells"].items():
                if r >= self.table.rowCount() or c >= self.table.columnCount():
                    continue
                it = self.table.item(r, c)
                if not it:
                    it = QTableWidgetItem()
                    self.table.setItem(r, c, it)
                it.setText(text)
                it.setData(ROLE_FORMULA, formula)
                if fmt:
                    font = QFont(fmt.get("font_family", FONT_FAMILY),
                                 fmt.get("font_size", FONT_SIZE))
                    it.setFont(font)
                    it.setTextAlignment(fmt.get("text_align", Qt.AlignCenter))
                    for role, key in [(ROLE_BOLD, "bold"), (ROLE_ITALIC, "italic"),
                                       (ROLE_UNDERLINE, "underline"), (ROLE_ALIGN, "align"),
                                       (ROLE_BG, "bg"), (ROLE_FG, "fg"),
                                       (ROLE_NUMFMT, "numfmt"), (ROLE_BORDER, "border")]:
                        it.setData(role, fmt.get(key))
        finally:
            self._loading = False
        self._recompute_formulas()

    def _undo(self):
        """撤销"""
        if not self._undo_stack:
            self._status("无可撤销操作")
            return
        snapshot = self._undo_stack.pop()
        # 当前状态入重做栈
        cells = snapshot["cells"]
        if cells:
            r = next(iter(cells.keys()))
            top = min(k[0] for k in cells)
            bottom = max(k[0] for k in cells)
            left = min(k[1] for k in cells)
            right = max(k[1] for k in cells)
            current = self._snapshot_cells(top, left, bottom, right)
            self._redo_stack.append(current)
        self._restore_snapshot(snapshot)
        self._status("已撤销")

    def _redo(self):
        """重做"""
        if not self._redo_stack:
            self._status("无可重做操作")
            return
        snapshot = self._redo_stack.pop()
        cells = snapshot["cells"]
        if cells:
            top = min(k[0] for k in cells)
            bottom = max(k[0] for k in cells)
            left = min(k[1] for k in cells)
            right = max(k[1] for k in cells)
            current = self._snapshot_cells(top, left, bottom, right)
            self._undo_stack.append(current)
        self._restore_snapshot(snapshot)
        self._status("已重做")
