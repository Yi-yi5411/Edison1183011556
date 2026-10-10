# -*- coding: utf-8 -*-
"""登录后的功能选择主页。

提供各业务模块入口（卡片式按钮）：
- 原始记录识别：直接接入 AI 扫描识别（OCR + 大模型结构化）
- 混凝土结构检测：进入现有报告数据管理主程序
- 钢结构 / 木结构 / 砖混结构检测：进入同一报告数据管理主程序，
  各结构类型的检测项目已由插件注册到左侧勾选树
  （core/plugin_manager 按结构类型聚合）

该页面由 login_launcher 在登录成功后弹出，用户选择模块后通过
choice / choice_label 属性把选择结果交回调用方。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QMessageBox,
)

# 模块卡片定义：(action_key, 标题, 副标题, 是否立即可用)
MODULES = [
    ("scan", "原始记录识别", "AI 扫描识别 · OCR+大模型自动结构化", True),
    ("scan_history", "识别记录查看", "AI识别历史 · 查看/校正/导出Excel", True),
    ("concrete", "混凝土结构检测", "检测数据管理录入 · 报告生成", True),
    ("steel", "钢结构检测", "检测数据管理录入 · 报告生成", True),
    ("wood", "木结构检测", "检测数据管理录入 · 报告生成", True),
    ("masonry", "砖混结构检测", "检测数据管理录入 · 报告生成", True),
]

_CARD_ENABLED_QSS = """
    QPushButton {
        background-color: white;
        border: 1px solid rgba(255,255,255,0.6);
        border-radius: 12px;
        padding: 12px;
        text-align: center;
    }
    QPushButton:hover {
        background-color: #E3F2FD;
        border: 2px solid #42A5F5;
    }
    QPushButton:pressed { background-color: #BBDEFB; }
"""

_CARD_DISABLED_QSS = """
    QPushButton {
        background-color: rgba(255,255,255,0.55);
        border: 1px dashed rgba(255,255,255,0.8);
        border-radius: 12px;
        padding: 12px;
        text-align: center;
        color: #546E7A;
    }
    QPushButton:hover { background-color: rgba(255,255,255,0.75); }
"""


class HomeMenu(QDialog):
    """功能选择主页：登录后先进入该页面，选择要使用的业务模块。"""

    def __init__(self, current_user=None, parent=None):
        super().__init__(parent)
        self.current_user = current_user or {}
        self.choice = None        # 被选中模块的 action_key
        self.choice_label = ""    # 被选中模块的标题
        self.setWindowTitle("功能选择")
        self.setFixedSize(600, 620)
        self._init_ui()

    # ── UI 构建 ──────────────────────────────────────────────
    def _init_ui(self):
        # 与登录页一致的深蓝渐变背景
        self.setStyleSheet("""
            QDialog {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0D47A1, stop:0.4 #1565C0, stop:1 #1976D2);
            }
            QLabel#title {
                color: white; font-size: 21px; font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#welcome {
                color: rgba(255,255,255,0.85); font-size: 13px;
            }
            QLabel#cardTitle {
                color: #0D47A1; font-size: 16px; font-weight: bold;
            }
            QLabel#cardSub {
                color: #607D8B; font-size: 12px;
            }
            QLabel#company {
                color: rgba(255,255,255,0.65); font-size: 12px;
            }
            QLabel#copyright {
                color: rgba(255,255,255,0.45); font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(28, 24, 28, 16)

        # ===== 标题区 =====
        title = QLabel("主体结构检测数据管理录入系统V1.0")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        display_name = (self.current_user.get("real_name")
                        or self.current_user.get("username") or "")
        welcome = QLabel(f"欢迎您，{display_name}！请选择要使用的功能模块")
        welcome.setObjectName("welcome")
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        layout.addSpacing(10)

        # ===== 模块卡片（2 列网格，最后一个跨两列居中） =====
        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (key, title_txt, sub, enabled) in enumerate(MODULES):
            card = self._make_card(key, title_txt, sub, enabled)
            row, col = divmod(i, 2)
            if i == len(MODULES) - 1 and col == 0:   # 奇数个时最后一个跨两列
                grid.addWidget(card, row, 0, 1, 2)
            else:
                grid.addWidget(card, row, col)
        layout.addLayout(grid, 1)

        layout.addSpacing(6)

        # ===== 退出按钮 =====
        quit_row = QHBoxLayout()
        quit_btn = QPushButton("退出系统")
        quit_btn.setMinimumHeight(36)
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setStyleSheet("""
            QPushButton {
                color: white; background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.4);
                border-radius: 8px; padding: 6px 28px; font-size: 14px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.22); }
        """)
        quit_btn.clicked.connect(self.reject)
        quit_row.addStretch()
        quit_row.addWidget(quit_btn)
        quit_row.addStretch()
        layout.addLayout(quit_row)

        layout.addSpacing(8)

        # ===== 底部信息 =====
        company = QLabel("技术支持：湖北省建筑科学研究设计院股份有限公司")
        company.setObjectName("company")
        company.setAlignment(Qt.AlignCenter)
        layout.addWidget(company)

        copyright_ = QLabel("© 2026 All Rights Reserved")
        copyright_.setObjectName("copyright")
        copyright_.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_)

    def _make_card(self, key, title_txt, sub, enabled):
        """生成一个模块卡片按钮（内部纵向排版：图标字符 + 标题 + 副标题）。"""
        btn = QPushButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumSize(250, 118)
        btn.setSizePolicy(btn.sizePolicy().Expanding, btn.sizePolicy().Expanding)
        btn.setStyleSheet(_CARD_ENABLED_QSS if enabled else _CARD_DISABLED_QSS)

        inner = QVBoxLayout(btn)
        inner.setContentsMargins(10, 12, 10, 12)
        inner.setSpacing(6)

        icon = QLabel({"scan": "🖨", "scan_history": "📋", "concrete": "🏢",
                       "steel": "⚙", "wood": "🪵", "masonry": "🧱"}.get(key, "•"))
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 26px; border: none;")
        inner.addWidget(icon)

        t = QLabel(title_txt)
        t.setObjectName("cardTitle")
        t.setAlignment(Qt.AlignCenter)
        inner.addWidget(t)

        s = QLabel(sub)
        s.setObjectName("cardSub")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        inner.addWidget(s)

        btn.clicked.connect(
            lambda _=False, k=key, lab=title_txt, ok=enabled: self._choose(k, lab, ok))
        return btn

    # ── 交互 ─────────────────────────────────────────────────
    def _choose(self, key, label, enabled):
        """点击卡片：可用模块记录选择并关闭；未启用模块提示建设中。"""
        if not enabled:
            QMessageBox.information(
                self, "提示",
                f"「{label}」模块参照混凝土结构检测的功能建设中，敬请期待。")
            return
        self.choice = key
        self.choice_label = label
        self.accept()
