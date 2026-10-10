# -*- coding: utf-8 -*-
"""Reusable Qt item delegates used by the main window."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStyledItemDelegate, QLineEdit, QCompleter


class FloorLabelDelegate(QStyledItemDelegate):
    """构件位置及名称列编辑器：可自由输入的文本框，附带楼层标签补全。

    键入“1”会弹出候选（例如 1FL），可点选候选，也可继续自由输入；
    提交时始终读取编辑器实际文本，避免“输入后切换单元格内容丢失”。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def set_items(self, items):
        self._items = [str(x) for x in (items or [])]

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        if self._items:
            completer = QCompleter(self._items, editor)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setFilterMode(Qt.MatchStartsWith)
            editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.EditRole)
        if value is None:
            value = index.data(Qt.DisplayRole)
        editor.setText("" if value is None else str(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
