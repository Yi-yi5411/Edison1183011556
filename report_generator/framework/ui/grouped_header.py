# -*- coding: utf-8 -*-
"""带分组行表头：在列名上方显示“输入区 / 计算区”两行表头。"""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QHeaderView


class GroupedHeaderView(QHeaderView):
    """横向表头，第一行显示分组名，第二行显示列名。"""

    GROUP_ROW_HEIGHT = 18

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._groups = {}
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setSectionsClickable(True)
        self.setHighlightSections(True)

    def set_group(self, section, text):
        self._groups[section] = text
        self.viewport().update()

    def clear_groups(self):
        self._groups.clear()
        self.viewport().update()

    def sizeHint(self):
        base = super().sizeHint()
        base.setHeight(base.height() + self.GROUP_ROW_HEIGHT)
        return base

    def paintSection(self, painter, rect, logical_index):
        if not rect.isValid():
            return
        painter.save()
        painter.fillRect(rect, self.palette().color(QPalette.Button))
        painter.setPen(QColor(165, 165, 165))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor(60, 60, 60))

        group = self._groups.get(logical_index)
        label = str(
            self.model().headerData(
                logical_index, self.orientation(), Qt.DisplayRole
            ) or ""
        )

        if group:
            label_top = self.GROUP_ROW_HEIGHT
            label_rect = QRectF(
                rect.left() + 2,
                rect.top() + label_top,
                rect.width() - 4,
                rect.height() - label_top - 2,
            )
            painter.drawText(label_rect, Qt.AlignCenter, label)
            group_rect = QRectF(
                rect.left() + 2,
                rect.top() + 1,
                rect.width() - 4,
                self.GROUP_ROW_HEIGHT - 1,
            )
            font = painter.font()
            font.setBold(True)
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
            painter.setFont(font)
            painter.drawText(group_rect, Qt.AlignCenter, group)
        else:
            painter.drawText(QRectF(rect).adjusted(2, 2, -2, -2), Qt.AlignCenter, label)

        painter.restore()
