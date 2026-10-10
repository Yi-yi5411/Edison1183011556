# -*- coding: utf-8 -*-
"""UI 主题引擎（借鉴 PyQt-Fluent-Widgets 的 Fluent 视觉规范，零依赖实现）。

设计 token 参考开源项目 zhiyiYo/PyQt-Fluent-Widgets：
- accent 蓝（light #0067c0 / dark #4cc2ff）、6px 圆角控件、
  卡片化面板、克制的 hover/selected 态、斑马纹淡化。

所有视觉常量集中在此，main_window 只负责组合控件与切换主题：
- build_stylesheet(name)  生成 light/dark 两套 QSS
- apply_theme(app, name)  应用主题
- get_saved_theme() / save_theme(name)  经 scan_recognition Config 持久化
"""

from PyQt5.QtGui import QFont

# ── 字体（沿用原约定）──
FONT_FAMILY = "Microsoft YaHei"
FONT_SIZE = 10
DEFAULT_FONT = QFont(FONT_FAMILY, FONT_SIZE)

# ── Fluent 设计 token ──
THEMES = {
    "light": {
        "window_bg": "#f3f3f3",
        "card_bg": "#ffffff",
        "card_border": "#e0e0e0",
        "text": "#1a1a1a",
        "text_sub": "#5d5d5d",
        "accent": "#0067c0",
        "accent_hover": "#1975c5",
        "accent_pressed": "#135a9e",
        "accent_soft": "#cce4f7",      # 表格选中 / 树选中底
        "accent_alt_row": "#f4f9fd",   # 斑马纹（极浅）
        "header_bg": "#2b6cb8",        # 表头主色（现代蓝）
        "header_fg": "#ffffff",
        "header_border": "#245e9f",
        "header_hover": "#3b7cc9",
        "grid": "#d9d9d9",
        "toolbar_bg": "#fbfbfb",
        "statusbar_bg": "#eef1f5",
        "menu_bg": "#ffffff",
        "menu_border": "#d6d6d6",
        "input_bg": "#ffffff",
        "input_border": "#cfcfcf",
        "hover_row": "rgba(0, 103, 192, 18)",
        "scroll_handle": "#c2c6cc",
        "tooltip_bg": "#ffffff",
        "tooltip_fg": "#1a1a1a",
    },
    "dark": {
        "window_bg": "#202020",
        "card_bg": "#272727",
        "card_border": "#3d3d3d",
        "text": "#ffffff",
        "text_sub": "#a8a8a8",
        "accent": "#4cc2ff",
        "accent_hover": "#47b1e8",
        "accent_pressed": "#3a92c4",
        "accent_soft": "#0f3b57",      # 表格选中 / 树选中底
        "accent_alt_row": "#2b2f33",   # 斑马纹
        "header_bg": "#313131",
        "header_fg": "#ffffff",
        "header_border": "#3d3d3d",
        "header_hover": "#3b3b3b",
        "grid": "#3a3a3a",
        "toolbar_bg": "#242424",
        "statusbar_bg": "#242424",
        "menu_bg": "#2b2b2b",
        "menu_border": "#3d3d3d",
        "input_bg": "#303030",
        "input_border": "#4a4a4a",
        "hover_row": "rgba(76, 194, 255, 26)",
        "scroll_handle": "#4d4d4d",
        "tooltip_bg": "#2b2b2b",
        "tooltip_fg": "#ffffff",
    },
}

THEME_NAMES = ("light", "dark")
DEFAULT_THEME = "light"


def get_saved_theme() -> str:
    """读持久化主题（scan_recognition Config 的 ui.theme，缺省 light）。"""
    try:
        from scan_recognition.config import Config
    except ImportError:
        try:
            from report_generator.scan_recognition.config import Config
        except ImportError:
            return DEFAULT_THEME
    try:
        data = Config.load().data or {}
        theme = str((data.get("ui") or {}).get("theme") or "")
        return theme if theme in THEME_NAMES else DEFAULT_THEME
    except Exception:
        return DEFAULT_THEME


def save_theme(name: str) -> None:
    """持久化主题选择到 Config（ui.theme；写失败静默，不影响使用）。"""
    if name not in THEME_NAMES:
        return
    try:
        from scan_recognition.config import Config
    except ImportError:
        try:
            from report_generator.scan_recognition.config import Config
        except ImportError:
            return
    try:
        config = Config.load()
        ui = dict((config.data or {}).get("ui") or {})
        ui["theme"] = name
        config.data["ui"] = ui
        config.save()
    except Exception:
        pass


def apply_theme(app, name: str) -> str:
    """应用主题到 QApplication，返回生效主题名。"""
    if name not in THEME_NAMES:
        name = DEFAULT_THEME
    app.setStyleSheet(build_stylesheet(name))
    return name


def build_stylesheet(name: str = DEFAULT_THEME) -> str:
    """生成指定主题的全局 QSS（Fluent 风格：圆角、克制 hover、卡片化）。"""
    t = THEMES.get(name, THEMES[DEFAULT_THEME])
    f = FONT_FAMILY
    return """
/* ── 基础 ── */
QWidget {{
    font-family: "{f}"; font-size: 10pt; color: {text};
}}
QMainWindow, QDialog {{ background: {window_bg}; }}
QToolTip {{
    background: {tooltip_bg}; color: {tooltip_fg};
    border: 1px solid {card_border}; padding: 4px 8px; border-radius: 4px;
}}

/* ── 工具栏 ── */
QToolBar {{
    background: {toolbar_bg}; border: none;
    border-bottom: 1px solid {card_border};
    spacing: 2px; padding: 4px 6px;
}}
QToolBar QToolButton {{
    padding: 5px 11px; border: 1px solid transparent;
    border-radius: 5px; background: transparent; color: {text};
}}
QToolBar QToolButton:hover {{
    background: {accent_soft}; border-color: {accent};
    color: {text};
}}
QToolBar QToolButton:pressed {{ background: {accent}; color: white; }}
QToolBar::separator {{ width: 1px; background: {card_border}; margin: 4px 5px; }}

/* ── 树面板 ── */
QTreeWidget {{
    border: 1px solid {card_border}; border-radius: 6px;
    background: {card_bg}; color: {text}; padding: 2px;
}}
QTreeWidget::item {{ padding: 4px 2px; border-radius: 4px; }}
QTreeWidget::item:hover {{ background: {hover_row}; }}
QTreeWidget::item:selected {{
    background: {accent_soft}; color: {text};
}}

/* ── 表格（类 Excel 主体：密度优先，克制的现代感）── */
QTableWidget {{
    gridline-color: {grid};
    border: 1px solid {card_border}; border-radius: 6px;
    background: {card_bg}; alternate-background-color: {accent_alt_row};
    selection-background-color: {accent_soft};
    selection-color: {text};
}}
QTableWidget::item {{ padding: 2px; }}
QTableWidget::item:selected {{ background-color: {accent_soft}; color: {text}; }}
QHeaderView::section {{
    background: {header_bg}; color: {header_fg};
    padding: 5px; border: none; border-right: 1px solid {header_border};
    border-bottom: 2px solid {accent};
    font-weight: bold;
}}
QHeaderView::section:hover {{ background: {header_hover}; }}
QHeaderView::section:selected {{ background: {accent_pressed}; }}
QTableCornerButton::section {{
    background: {header_bg}; border: none;
    border-right: 1px solid {header_border};
    border-bottom: 2px solid {accent};
}}

/* ── 输入控件（圆角 Fluent 输入框）── */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {input_bg}; color: {text};
    border: 1px solid {input_border}; border-radius: 5px;
    padding: 4px 7px; selection-background-color: {accent};
    selection-color: white;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{
    border: none; width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {menu_bg}; color: {text};
    border: 1px solid {menu_border};
    selection-background-color: {accent_soft};
    selection-color: {text};
}}

/* ── 按钮 ── */
QPushButton {{
    background: {card_bg}; color: {text};
    border: 1px solid {input_border}; border-radius: 5px;
    padding: 5px 14px;
}}
QPushButton:hover {{ background: {accent_soft}; border-color: {accent}; }}
QPushButton:pressed {{ background: {accent}; color: white; }}
QPushButton:disabled {{ color: {text_sub}; background: {window_bg}; }}

/* ── 菜单（卡片化 + 分隔线弱化）── */
QMenuBar {{
    background: {toolbar_bg}; color: {text};
    border-bottom: 1px solid {card_border};
}}
QMenuBar::item {{ padding: 5px 10px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {accent_soft}; }}
QMenu {{
    background: {menu_bg}; color: {text};
    border: 1px solid {menu_border}; border-radius: 7px; padding: 4px;
}}
QMenu::item {{ padding: 6px 26px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {text}; }}
QMenu::item:disabled {{ color: {text_sub}; }}
QMenu::separator {{ height: 1px; background: {card_border}; margin: 4px 8px; }}

/* ── 状态栏 / 分组框 / 标签页 ── */
QStatusBar {{
    background: {statusbar_bg}; color: {text_sub};
    border-top: 1px solid {card_border};
}}
QGroupBox {{
    border: 1px solid {card_border}; border-radius: 6px;
    margin-top: 10px; padding-top: 6px; color: {text};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QTabBar::tab {{
    background: transparent; color: {text_sub};
    padding: 6px 14px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {accent}; border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover {{ color: {text}; }}
QTabWidget::pane {{ border: 1px solid {card_border}; border-radius: 6px; }}

/* ── 复选框 / 滚动条 ── */
QCheckBox {{ spacing: 6px; color: {text}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {input_border}; border-radius: 3px; background: {input_bg};
}}
QCheckBox::indicator:checked {{
    background: {accent}; border-color: {accent};
    image: url(none);
}}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {scroll_handle}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {scroll_handle}; border-radius: 4px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ── 对话框按钮盒 ── */
QDialogButtonBox QPushButton {{ min-width: 74px; }}
""".format(f=f, **t)


# 兼容旧引用：main_window 直接 import 的全局样式（启动时按保存主题生成）
GLOBAL_STYLESHEET = build_stylesheet(get_saved_theme())
