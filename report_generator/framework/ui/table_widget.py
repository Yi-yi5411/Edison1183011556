# -*- coding: utf-8 -*-
"""MergeTableWidget - 支持 Excel 风格合并单元格的 QTableWidget 子类

参考 ONLYOFFICE EventsController + WorksheetView 设计：
1. 完全接管左键拖选流程，绕过 Qt 在 setSpan 后选区收缩的 bug
2. _calcTarget 区分 Cell/ColumnHeader/RowHeader/Corner/FillHandle 五种命中目标
3. _remap_merged_cell 把命中合并区从属 cell 重映射到 anchor，避免拖选卡顿
4. 支持填充柄拖拽（fill handle）触发 fillHandleDragged 信号
"""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QTableWidget, QTableWidgetSelectionRange,
)

from .constants import TargetType, ROLE_ALIGN, ROLE_BORDER


class MergeTableWidget(QTableWidget):
    """QTableWidget 子类：参考 ONLYOFFICE EventsController + WorksheetView 设计。

    1. 完全接管左键拖选流程，绕过 Qt 在 setSpan 后选区收缩的 bug
    2. _calcTarget 区分 Cell/ColumnHeader/RowHeader/Corner/FillHandle 五种命中目标
    3. _remap_merged_cell 把命中合并区从属 cell 重映射到 anchor，避免拖选卡顿
    4. 支持填充柄拖拽（fill handle）触发 fillHandleDragged 信号
    """

    # 填充柄拖拽完成时发射 (start_row, start_col, end_row, end_col)
    fillHandleDragged = None  # 延迟到实例化时绑定

    FILL_HANDLE_SIZE = 6  # 填充柄方块的边长（像素）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_start = None       # (row, col) 鼠标按下时的单元格
        self._is_dragging = False
        self._drag_target = TargetType.Cell   # 当前拖拽命中类型
        self._fill_start = None        # 填充柄拖拽起始选区 (top, bottom, left, right)
        # 延迟创建信号（PyQt5 信号需在类层级定义，这里改用回调）
        self._fill_callback = None     # 外部注册: callback(start_rng, end_rng)
        self._frozen_pane = None       # (row, col) 冻结位置；None = 未冻结

    def set_fill_callback(self, callback):
        """注册填充柄拖拽回调：callback(start_rng, end_rng)
        start_rng/end_rng = (top, bottom, left, right)
        """
        self._fill_callback = callback

    def setItem(self, row, column, item):
        """Ensure new table cells are centered by default.

        Explicit alignment actions store ROLE_ALIGN on the item, so this hook only
        applies the default centre alignment when the user has not chosen one.
        """
        if item is not None and item.data(ROLE_ALIGN) is None:
            item.setTextAlignment(Qt.AlignCenter)
        super().setItem(row, column, item)

    def _merged_ranges(self):
        """获取当前所有合并区域列表 [(row, col, rowSpan, colSpan)]。
        子类可覆盖；默认从 self._merges 字典读取（由 ReportGeneratorApp 注入）。
        """
        merges = getattr(self, "_merges", None)
        if merges is None:
            return []
        # _merges 是 {sheet_key: [(r,c,rs,cs)]}，取当前 sheet
        current = getattr(self, "_current_sheet", None)
        if current and current in merges:
            return merges[current]
        # 当前 sheet 无合并，返回空列表（不再退化到其他 sheet）
        return []

    def _remap_merged_cell(self, row, col):
        """合并单元格坐标重映射（参考 ONLYOFFICE _calcTarget 的合并处理）。
        若 (row, col) 落在某个合并区域的从属单元格（非左上角），
        返回该合并区的范围 (r, c, r2, c2)，调用方可据此扩展选区。
        否则返回 (row, col, row, col)。
        """
        for (r, c, rs, cs) in self._merged_ranges():
            if r <= row < r + rs and c <= col < c + cs:
                return (r, c, r + rs - 1, c + cs - 1)
        return (row, col, row, col)

    def _cell_at(self, x, y):
        """根据 viewport 像素坐标精确定位单元格。

        rowAt/columnAt 在命中合并区域时会返回 anchor，
        无法选中被合并覆盖的子单元格。这里按行高/
        列宽的几何边界计算实际命中的 row/col。
        """
        col = -1
        for c in range(self.columnCount()):
            pos = self.columnViewportPosition(c)
            if pos <= x < pos + self.columnWidth(c):
                col = c
                break
        row = -1
        for r in range(self.rowCount()):
            pos = self.rowViewportPosition(r)
            if pos <= y < pos + self.rowHeight(r):
                row = r
                break
        return row, col

    def _calc_target(self, event):
        """判断鼠标命中的 UI 元素。

        鼠标事件传入的是 viewport 坐标；列头、行头和
        左上角的点击由 QHeaderView / corner button 自身处理。
        这里只需区分“填充柄”和“普通数据单元格”。
        """
        x, y = event.x(), event.y()
        rng = self._current_selection_range()
        if rng:
            top, bottom, left, right = rng
            rect = self.visualRect(self.model().index(bottom, right))
            handle_x = rect.right() + 1
            handle_y = rect.bottom() + 1
            if (abs(x - handle_x) <= self.FILL_HANDLE_SIZE and
                abs(y - handle_y) <= self.FILL_HANDLE_SIZE):
                return (TargetType.FillHandle, bottom, right)
        row, col = self._cell_at(x, y)
        if row >= 0 and col >= 0:
            return (TargetType.Cell, row, col)
        return (TargetType.Cell, -1, -1)

    def _current_selection_range(self):
        """获取当前选区 (top, bottom, left, right) 或 None"""
        ranges = self.selectedRanges()
        if not ranges:
            return None
        r = ranges[0]
        return (r.topRow(), r.bottomRow(), r.leftColumn(), r.rightColumn())

    def _clamp_pos_to_cell(self, event):
        """将鼠标坐标转换为 (row, col)，超出表格边界时做钳制。

        rowAt/columnAt 在鼠标移出表格时返回 -1，这里做边缘钳制
        确保拖选不会因为鼠标越界而中断。同时应用合并重映射。
        """
        row = self.rowAt(event.y())
        col = self.columnAt(event.x())
        if row < 0:
            row = 0 if event.y() < 0 else self.rowCount() - 1
        if col < 0:
            col = 0 if event.x() < 0 else self.columnCount() - 1
        row = max(0, min(row, self.rowCount() - 1))
        col = max(0, min(col, self.columnCount() - 1))
        # 合并重映射：若命中从属 cell，扩展到整个合并区
        r1, c1, r2, c2 = self._remap_merged_cell(row, col)
        return r1, c1, r2, c2

    def mousePressEvent(self, event):
        """鼠标按下：仅处理数据单元格和填充柄。

        点击列头/行头由 sectionClicked 信号处理，选择整列/整行；
        点击数据格会先落到合并区域左上角锚点，避免把隐藏子格当作选区。
        """
        if event.button() == Qt.LeftButton:
            target, row, col = self._calc_target(event)
            if target == TargetType.FillHandle:
                # 启动填充柄拖拽
                self._fill_start = self._current_selection_range()
                self._is_dragging = False
                self._drag_target = TargetType.FillHandle
                return
            if target == TargetType.Cell and row >= 0 and col >= 0:
                # 命中合并区域时先落到左上角锚点，避免把隐藏子格当作选区起点；
                # 后续拖选/填充/复制都以锚点为准，否则会写出“看不见”的值。
                row, col, _, _ = self._remap_merged_cell(row, col)
                self._drag_start = (row, col)
                self._is_dragging = True
                self._drag_target = TargetType.Cell
                self.clearSelection()
                self.setRangeSelected(
                    QTableWidgetSelectionRange(row, col, row, col), True
                )
                self.setCurrentCell(row, col)
                return
        # 非左键或无效区域：交给父类处理（右键菜单等）
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动：根据 _drag_target 分流"""
        # 填充柄拖拽
        if (self._drag_target == TargetType.FillHandle and
            self._fill_start and (event.buttons() & Qt.LeftButton)):
            row, col, row2, col2 = self._clamp_pos_to_cell(event)
            top, bottom, left, right = self._fill_start
            # 计算扩展方向（仅支持单方向扩展，与 Excel 一致）
            if row2 > bottom:
                new_bottom = row2
                new_top = top
                new_left, new_right = left, right
            elif col2 > right:
                new_right = col2
                new_left = left
                new_top, new_bottom = top, bottom
            elif row < top:
                new_top = row
                new_bottom = bottom
                new_left, new_right = left, right
            elif col < left:
                new_left = col
                new_right = right
                new_top, new_bottom = top, bottom
            else:
                return
            # 高亮预览扩展区域
            self.clearSelection()
            self.setRangeSelected(
                QTableWidgetSelectionRange(new_top, new_left, new_bottom, new_right), True
            )
            return
        # 普通拖选
        if self._is_dragging and self._drag_start and (event.buttons() & Qt.LeftButton):
            r1, c1, r2, c2 = self._clamp_pos_to_cell(event)
            start_row, start_col = self._drag_start
            # 列头拖拽：扩展列选区
            if start_col >= 0 and start_row < 0:
                left = min(start_col, c1)
                right = max(start_col, c1)
                self.clearSelection()
                self.setRangeSelected(
                    QTableWidgetSelectionRange(0, left, self.rowCount() - 1, right), True
                )
                return
            # 行头拖拽：扩展行选区
            if start_row >= 0 and start_col < 0:
                top = min(start_row, r1)
                bottom = max(start_row, r1)
                self.clearSelection()
                self.setRangeSelected(
                    QTableWidgetSelectionRange(top, 0, bottom, self.columnCount() - 1), True
                )
                return
            # 普通单元格拖选
            # 起止端点都可能落在合并区域上：把端点扩展为完整合并块后取并集，
            # 避免选区只覆盖锚点而漏掉被合并覆盖的子格（导致批量填充失灵）。
            s_top, s_left, s_bottom, s_right = self._remap_merged_cell(start_row, start_col)
            top = min(s_top, r1)
            bottom = max(s_bottom, r2)
            left = min(s_left, c1)
            right = max(s_right, c2)
            self.clearSelection()
            self.setRangeSelected(
                QTableWidgetSelectionRange(top, left, bottom, right), True
            )
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放：结束拖选 / 触发填充柄回调"""
        if event.button() == Qt.LeftButton:
            # 填充柄释放
            if self._drag_target == TargetType.FillHandle and self._fill_start:
                r1, c1, r2, c2 = self._clamp_pos_to_cell(event)
                top, bottom, left, right = self._fill_start
                end_rng = None
                if r2 > bottom:
                    end_rng = (bottom + 1, r2, left, right)
                elif c2 > right:
                    end_rng = (top, bottom, right + 1, c2)
                elif r1 < top:
                    end_rng = (r1, top - 1, left, right)
                elif c1 < left:
                    end_rng = (top, bottom, c1, left - 1)
                if end_rng and self._fill_callback:
                    self._fill_callback((top, bottom, left, right), end_rng)
                self._fill_start = None
                self._drag_target = TargetType.Cell
                return
            # 普通拖选释放
            if self._is_dragging:
                self._is_dragging = False
                self._drag_start = None
                self._drag_target = TargetType.Cell
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击：重置拖选状态，交给父类处理编辑"""
        self._is_dragging = False
        self._drag_start = None
        self._drag_target = TargetType.Cell
        self._fill_start = None
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """键盘事件：重置拖选状态，交给父类处理"""
        self._is_dragging = False
        self._drag_start = None
        self._drag_target = TargetType.Cell
        self._fill_start = None
        super().keyPressEvent(event)

    def edit(self, index, trigger, event):
        """进入编辑状态前，把合并区域内的子单元格重映射到左上角锚点。

        键盘导航（Enter/Tab/方向键）或 F2 可能把当前单元格停在合并区域的
        子格上；若不重映射，编辑器会绑定到隐藏子格，提交后锚点仍为空，
        用户输入的构件位置等文字就会“消失”。
        """
        if index.isValid():
            r, c, _, _ = self._remap_merged_cell(index.row(), index.column())
            if r != index.row() or c != index.column():
                index = self.model().index(r, c)
        return super().edit(index, trigger, event)

    # ── 视觉渲染：边框 + 填充柄指示器 + 合并单元格装饰 ──
    def paintEvent(self, event):
        """参考 ONLYOFFICE WorksheetView._drawSelection + _drawCells。
        在 Qt 默认绘制之后，叠加绘制：
        1) 自定义边框（存储在 ROLE_BORDER 中）
        2) 选区右下角的填充柄小方块
        3) 合并单元格的装饰性边框
        """
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, False)

        # ── 1. 填充柄指示器 ──
        rng = self._current_selection_range()
        if rng:
            top, bottom, left, right = rng
            if bottom < self.rowCount() and right < self.columnCount():
                rect = self.visualRect(self.model().index(bottom, right))
                handle_size = self.FILL_HANDLE_SIZE * 2
                handle_rect = QRectF(
                    rect.right() - handle_size + 1,
                    rect.bottom() - handle_size + 1,
                    handle_size, handle_size
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#4472C4"))
                painter.drawRect(handle_rect)

        # ── 2. 合并单元格装饰边框 ──
        for (r, c, rs, cs) in self._merged_ranges():
            if r >= self.rowCount() or c >= self.columnCount():
                continue
            r2 = min(r + rs - 1, self.rowCount() - 1)
            c2 = min(c + cs - 1, self.columnCount() - 1)
            rect = self.visualRect(self.model().index(r, c))
            r2_rect = self.visualRect(self.model().index(r2, c2))
            if not rect.isValid() or not r2_rect.isValid():
                continue
            # 合并区域的外框（加粗蓝色）
            merge_rect = QRectF(rect.topLeft(), r2_rect.bottomRight())
            pen = QPen(QColor("#2F5496"), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(merge_rect)

        # ── 3. 自定义边框绘制（仅遍历可见区域） ──
        painter.setPen(QPen(QColor("#BFBFBF"), 1))
        first_vis_row = self.rowAt(0)
        last_vis_row = self.rowAt(self.viewport().height())
        if first_vis_row < 0:
            first_vis_row = 0
        if last_vis_row < 0:
            last_vis_row = self.rowCount() - 1
        for r in range(first_vis_row, min(last_vis_row + 1, self.rowCount())):
            for c in range(self.columnCount()):
                it = self.item(r, c)
                if not it:
                    continue
                border = it.data(ROLE_BORDER)
                if not border:
                    continue
                rect = self.visualRect(self.model().index(r, c))
                if not rect.isValid():
                    continue
                top = border.get("top")
                bottom = border.get("bottom")
                left = border.get("left")
                right = border.get("right")
                if top:
                    painter.drawLine(rect.topLeft(), rect.topRight())
                if bottom:
                    painter.drawLine(rect.bottomLeft(), rect.bottomRight())
                if left:
                    painter.drawLine(rect.topLeft(), rect.bottomLeft())
                if right:
                    painter.drawLine(rect.topRight(), rect.bottomRight())

        # ── 4. 冻结窗格视觉提示 ──
        frozen = getattr(self, "_frozen_pane", None)
        if frozen:
            fr, fc = frozen
            # 在冻结线上画一条灰色粗线
            painter.setPen(QPen(QColor("#808080"), 2, Qt.DashLine))
            if fc > 0 and fc <= self.columnCount():
                col_x = self.columnViewportPosition(fc)
                painter.drawLine(col_x, 0, col_x, self.viewport().height())
            if fr > 0 and fr <= self.rowCount():
                row_y = self.rowViewportPosition(fr)
                painter.drawLine(0, row_y, self.viewport().width(), row_y)

        painter.end()

    def scrollContentsBy(self, dx, dy):
        """重写滚动事件：冻结行/列不参与滚动。

        参考 ONLYOFFICE 中对 FrozenPane 的处理。当设置了 _frozen_pane 时，
        通过限制滚动条值使冻结线以上的行和以左的列保持在视口位置。
        """
        frozen = getattr(self, "_frozen_pane", None)
        if not frozen:
            super().scrollContentsBy(dx, dy)
            return

        fr, fc = frozen

        # 计算冻结行累计高度和冻结列累计宽度
        frozen_row_h = sum(self.rowHeight(r) for r in range(fr))
        frozen_col_w = sum(self.columnWidth(c) for c in range(fc))

        vbar = self.verticalScrollBar()
        hbar = self.horizontalScrollBar()

        # 垂直滚动：限制不越过冻结线
        if dy != 0 and fr > 0:
            new_v = vbar.value() + dy
            # 不允许滚到冻结线以上
            new_v = max(new_v, frozen_row_h)
            vbar.setValue(new_v)
            super().scrollContentsBy(0, dy)
        elif dy != 0:
            super().scrollContentsBy(0, dy)

        # 水平滚动：限制不越过冻结线
        if dx != 0 and fc > 0:
            new_h = hbar.value() + dx
            # 不允许滚到冻结线以左
            new_h = max(new_h, frozen_col_w)
            hbar.setValue(new_h)
            super().scrollContentsBy(dx, 0)
        elif dx != 0:
            super().scrollContentsBy(dx, 0)

        self.viewport().update()
