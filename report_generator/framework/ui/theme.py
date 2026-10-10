# -*- coding: utf-8 -*-
"""UI theme constants and global stylesheet.

All visual constants live here so main_window stays focused on composing widgets,
not defining colours/fonts/styles.
"""

from PyQt5.QtGui import QColor, QFont


FONT_FAMILY = "Microsoft YaHei"
FONT_SIZE = 10
DEFAULT_FONT = QFont(FONT_FAMILY, FONT_SIZE)
HEADER_BG = QColor("#4472C4")
HEADER_FG = QColor("#FFFFFF")
ALT_ROW_COLOR = QColor("#D9E2F3")
GRID_COLOR = QColor("#BFBFBF")

GLOBAL_STYLESHEET = """
QMainWindow { background: #f5f5f5; }
QToolBar { background: #fafafa; border: none; border-bottom: 1px solid #dcdcdc;
           spacing: 2px; padding: 3px; }
QToolBar QToolButton { padding: 5px 10px; border-radius: 3px;
                       font-family: "Microsoft YaHei"; font-size: 10pt; }
QToolBar QToolButton:hover { background: #e5f0ff; border: 1px solid #b3d4ff; }
QToolBar QToolButton:pressed { background: #cce0ff; }
QTreeWidget { border: 1px solid #dcdcdc; background: #ffffff;
              font-family: "Microsoft YaHei"; font-size: 10pt; }
QTreeWidget::item { padding: 4px 2px; }
QTreeWidget::item:selected { background: #4472C4; color: white; }
QTableWidget { gridline-color: #BFBFBF; border: 1px solid #dcdcdc;
               background: #ffffff; alternate-background-color: #D9E2F3;
               font-family: "Microsoft YaHei"; font-size: 10pt; }
QTableWidget::item:selected { background-color: #d6e4f7; color: #1a1a1a; }
QTableWidget::item { padding: 2px; }
QHeaderView::section { background: #4472C4; color: white;
                       padding: 5px; border: 1px solid #3a5fa8;
                       font-weight: bold;
                       font-family: "Microsoft YaHei"; font-size: 10pt; }
QHeaderView::section:selected { background: #2f5496; color: #ffff99; }
QHeaderView::section:hover { background: #5b8bd9; }
QTableCornerButton::section { background: #4472C4; border: 1px solid #3a5fa8; }
QStatusBar { background: #ececec; color: #333;
             font-family: "Microsoft YaHei"; font-size: 9pt; }
QMenu { background: #ffffff; border: 1px solid #c0c0c0;
        font-family: "Microsoft YaHei"; font-size: 10pt; }
QMenu::item { padding: 5px 25px; }
QMenu::item:selected { background: #4472C4; color: white; }
"""
