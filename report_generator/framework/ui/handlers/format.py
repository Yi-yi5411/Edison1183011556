# -*- coding: utf-8 -*-
"""格式操作 Mixin（对齐 / 字体 / 颜色 / 边框 / 数字格式 / 格式刷）"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QFont
from PyQt5.QtWidgets import QTableWidgetItem, QColorDialog

from framework.ui import (
    ROLE_FORMULA, ROLE_BOLD, ROLE_ALIGN, ROLE_BG, ROLE_FG,
    ROLE_ITALIC, ROLE_UNDERLINE, ROLE_NUMFMT, ROLE_BORDER,
)


class FormatMixin:
    """格式相关操作"""

    def _align(self, direction):
        """设置对齐方式（同步更新合并格式记录）"""
        if not self.current_item:
            return
        flag = {
            "left": Qt.AlignLeft,
            "center": Qt.AlignCenter,
            "right": Qt.AlignRight,
        }[direction]
        items = self._collect_selected_items()
        snapshot = self._snapshot_from_items(items)
        for it in items:
            it.setTextAlignment(flag | Qt.AlignVCenter)
            it.setData(ROLE_ALIGN, direction)
        # 更新合并格式记录
        if self.current_item in self._merge_formats:
            for it in items:
                r, c = it.row(), it.column()
                # 如果是合并锚点，更新格式
                for mr, mc, _rs, _cs in self._merges.get(self.current_item, []):
                    if mr == r and mc == c:
                        self._merge_formats[self.current_item][(r, c)]["align"] = direction
                        break
                    elif mr <= r <= mr + _rs - 1 and mc <= c <= mc + _cs - 1:
                        self._merge_formats[self.current_item][(mr, mc)]["align"] = direction
                        break
        self._push_undo(snapshot)
        self._status(f"对齐: {direction}")

    def _toggle_bold(self):
        """切换加粗（同步更新合并格式记录）"""
        if not self.current_item:
            return
        items = self._collect_selected_items()
        if not items:
            return
        first_bold = items[0].font().bold()
        snapshot = self._snapshot_from_items(items)
        for it in items:
            f = it.font()
            f.setBold(not first_bold)
            it.setFont(f)
            it.setData(ROLE_BOLD, not first_bold)
        # 更新合并格式记录中的 bold 状态
        if self.current_item in self._merge_formats:
            for it in items:
                r, c = it.row(), it.column()
                for mr, mc, _rs, _cs in self._merges.get(self.current_item, []):
                    if (mr == r and mc == c) or (mr <= r <= mr + _rs - 1 and mc <= c <= mc + _cs - 1):
                        self._merge_formats[self.current_item][(mr, mc)]["bold"] = not first_bold
                        break
        self._push_undo(snapshot)
        self._status("加粗" if not first_bold else "取消加粗")

    def _font_bigger(self):
        """字号增大"""
        self._adjust_font_size(1)

    def _font_smaller(self):
        """字号减小"""
        self._adjust_font_size(-1)

    def _adjust_font_size(self, delta):
        """调整字号"""
        if not self.current_item:
            return
        items = self._collect_selected_items()
        if not items:
            return
        snapshot = self._snapshot_from_items(items)
        for it in items:
            f = it.font()
            f.setPointSize(max(6, f.pointSize() + delta))
            it.setFont(f)
        self._push_undo(snapshot)
        self._status(f"字号: {items[0].font().pointSize()}")

    def _set_bg_color(self):
        """设置背景颜色"""
        if not self.current_item:
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        items = self._collect_selected_items()
        snapshot = self._snapshot_from_items(items)
        for it in items:
            it.setBackground(QBrush(color))
            it.setData(ROLE_BG, color.name())
        self._push_undo(snapshot)
        self._status(f"背景色: {color.name()}")

    def _set_font_color(self):
        """设置字体颜色"""
        if not self.current_item:
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        items = self._collect_selected_items()
        snapshot = self._snapshot_from_items(items)
        for it in items:
            it.setForeground(QBrush(color))
            it.setData(ROLE_FG, color.name())
        self._push_undo(snapshot)
        self._status(f"字体色: {color.name()}")

    def _copy_format(self, src_item, dst_item):
        """复制单元格格式（不含内容）"""
        if not src_item or not dst_item:
            return
        font = src_item.font()
        dst_item.setFont(QFont(font))
        dst_item.setTextAlignment(src_item.textAlignment())
        for role in (ROLE_BOLD, ROLE_ITALIC, ROLE_UNDERLINE,
                     ROLE_ALIGN, ROLE_BG, ROLE_FG, ROLE_NUMFMT, ROLE_BORDER):
            dst_item.setData(role, src_item.data(role))
        bg = src_item.background()
        if bg is not None:
            dst_item.setBackground(QBrush(bg.color()))

    def _format_painter_copy(self):
        """格式刷：复制当前选区的格式"""
        rng = self._get_selected_range()
        if not rng:
            self._status("请先选择源区域")
            return
        top, bottom, left, right = rng
        self._format_painter_data = {}
        for r in range(top, bottom + 1):
            for c in range(left, right + 1):
                it = self.table.item(r, c)
                if it:
                    self._format_painter_data[(r - top, c - left)] = {
                        "font_family": it.font().family(),
                        "font_size": it.font().pointSize(),
                        "bold": it.font().bold(),
                        "italic": it.font().italic(),
                        "underline": it.font().underline(),
                        "text_align": it.textAlignment(),
                        "bg": it.background().color() if it.background() else None,
                        "fg": it.foreground().color() if it.foreground() else None,
                        "role_bold": it.data(ROLE_BOLD),
                        "role_italic": it.data(ROLE_ITALIC),
                        "role_underline": it.data(ROLE_UNDERLINE),
                        "role_align": it.data(ROLE_ALIGN),
                        "role_bg": it.data(ROLE_BG),
                        "role_fg": it.data(ROLE_FG),
                        "role_numfmt": it.data(ROLE_NUMFMT),
                        "role_border": it.data(ROLE_BORDER),
                    }
        self._status(f"已复制格式 ({len(self._format_painter_data)} 格)")

    def _format_painter_paste(self):
        """格式刷：粘贴格式到当前选区"""
        if not self._format_painter_data:
            self._status("请先用格式刷复制格式 (Ctrl+Shift+C)")
            return
        rng = self._get_selected_range()
        if not rng:
            self._status("请先选择目标区域")
            return
        top, bottom, left, right = rng
        snapshot = self._snapshot_cells(top, left, bottom, right)
        self._loading = True
        try:
            src_rows = max(k[0] for k in self._format_painter_data) + 1
            src_cols = max(k[1] for k in self._format_painter_data) + 1
            for r in range(top, bottom + 1):
                for c in range(left, right + 1):
                    src_key = ((r - top) % src_rows, (c - left) % src_cols)
                    fmt = self._format_painter_data.get(src_key)
                    if not fmt:
                        continue
                    it = self.table.item(r, c)
                    if not it:
                        it = QTableWidgetItem()
                        self.table.setItem(r, c, it)
                    font = QFont(fmt["font_family"], fmt["font_size"])
                    font.setBold(fmt["bold"])
                    font.setItalic(fmt["italic"])
                    font.setUnderline(fmt["underline"])
                    it.setFont(font)
                    it.setTextAlignment(fmt["text_align"])
                    if fmt["bg"]:
                        it.setBackground(QBrush(fmt["bg"]))
                    if fmt["fg"]:
                        it.setForeground(QBrush(fmt["fg"]))
                    it.setData(ROLE_BOLD, fmt["role_bold"])
                    it.setData(ROLE_ITALIC, fmt["role_italic"])
                    it.setData(ROLE_UNDERLINE, fmt["role_underline"])
                    it.setData(ROLE_ALIGN, fmt["role_align"])
                    it.setData(ROLE_BG, fmt["role_bg"])
                    it.setData(ROLE_FG, fmt["role_fg"])
                    it.setData(ROLE_NUMFMT, fmt["role_numfmt"])
                    it.setData(ROLE_BORDER, fmt["role_border"])
        finally:
            self._loading = False
        self._push_undo(snapshot)
        self._status("已粘贴格式")

    def _toggle_italic(self):
        """切换斜体"""
        items = self._collect_selected_items()
        if not items:
            return
        first_italic = items[0].font().italic()
        snapshot = self._snapshot_from_items(items)
        self._loading = True
        try:
            for it in items:
                font = it.font()
                font.setItalic(not first_italic)
                it.setFont(font)
                it.setData(ROLE_ITALIC, not first_italic)
        finally:
            self._loading = False
        self._push_undo(snapshot)
        self._status(f"斜体: {'开' if not first_italic else '关'}")

    def _toggle_underline(self):
        """切换下划线"""
        items = self._collect_selected_items()
        if not items:
            return
        first_ul = items[0].font().underline()
        snapshot = self._snapshot_from_items(items)
        self._loading = True
        try:
            for it in items:
                font = it.font()
                font.setUnderline(not first_ul)
                it.setFont(font)
                it.setData(ROLE_UNDERLINE, not first_ul)
        finally:
            self._loading = False
        self._push_undo(snapshot)
        self._status(f"下划线: {'开' if not first_ul else '关'}")

    def _snapshot_from_items(self, items):
        """从 item 列表生成快照"""
        snapshot = {"sheet": self.current_item, "cells": {}}
        for it in items:
            r = it.row()
            c = it.column()
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

    def _set_border(self, border_type):
        """设置边框：border_type ∈ all/outer/inner/top/bottom/left/right/none"""
        rng = self._get_selected_range()
        if not rng:
            return
        top, bottom, left, right = rng
        snapshot = self._snapshot_cells(top, left, bottom, right)
        self._loading = True
        try:
            for r in range(top, bottom + 1):
                for c in range(left, right + 1):
                    it = self.table.item(r, c)
                    if not it:
                        it = QTableWidgetItem()
                        self.table.setItem(r, c, it)
                    border = it.data(ROLE_BORDER) or {}
                    if border_type == "none":
                        border = {}
                    elif border_type == "all":
                        border = {"top": "thin", "bottom": "thin",
                                  "left": "thin", "right": "thin"}
                    elif border_type == "outer":
                        if r == top:
                            border["top"] = "thin"
                        if r == bottom:
                            border["bottom"] = "thin"
                        if c == left:
                            border["left"] = "thin"
                        if c == right:
                            border["right"] = "thin"
                    elif border_type == "inner":
                        if r < bottom:
                            border["bottom"] = "thin"
                        if c < right:
                            border["right"] = "thin"
                    elif border_type in ("top", "bottom", "left", "right"):
                        border[border_type] = "thin"
                    it.setData(ROLE_BORDER, border if border else None)
        finally:
            self._loading = False
        self._push_undo(snapshot)
        self._status(f"边框: {border_type}")

    def _set_number_format(self, fmt_type):
        """设置数字格式：general/int/dec2/percent/thousands"""
        items = self._collect_selected_items()
        if not items:
            return
        snapshot = self._snapshot_from_items(items)
        self._loading = True
        try:
            for it in items:
                it.setData(ROLE_NUMFMT, fmt_type)
                text = it.text()
                if text:
                    try:
                        num = float(text)
                        if fmt_type == "int":
                            it.setText(str(int(round(num))))
                        elif fmt_type == "dec2":
                            it.setText(f"{num:.2f}")
                        elif fmt_type == "percent":
                            it.setText(f"{num * 100:.2f}%")
                        elif fmt_type == "thousands":
                            it.setText(f"{num:,.2f}")
                    except (ValueError, TypeError):
                        pass
        finally:
            self._loading = False
        self._push_undo(snapshot)
        self._status(f"数字格式: {fmt_type}")
