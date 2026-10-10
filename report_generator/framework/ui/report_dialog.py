# -*- coding: utf-8 -*-
"""检测报告抬头信息录入对话框。

生成《检测报告》前弹出，收集工程名称/地点、委托/见证单位、报告编号、
各签字人与报告日期；预填上次值（由主窗口随项目文件持久化），
确定后返回 dict（键见 report_template_map.REPORT_INFO_FIELDS）。
"""
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDialogButtonBox, QFrame, QFormLayout,
)

from report_generator.utils.report_template_map import REPORT_INFO_FIELDS


def agent_default_enabled():
    """Agent 模式默认勾选状态（读 report_agent.enabled，异常时默认开）。"""
    try:
        from report_generator.scan_recognition.config import Config
    except ImportError:
        try:
            from scan_recognition.config import Config
        except ImportError:
            return True
    try:
        data = Config.load().data or {}
        return bool((data.get("report_agent") or {}).get("enabled", True))
    except Exception:
        return True


class ReportInfoDialog(QDialog):
    """报告抬头信息对话框。"""

    def __init__(self, prefill=None, checked_items=None, parent=None,
                 default_use_agent=None):
        super().__init__(parent)
        self.setWindowTitle("生成检测报告 — 抬头信息")
        self.resize(520, 520)
        self._prefill = dict(prefill or {})
        self._checked_items = list(checked_items or [])
        self._default_use_agent = default_use_agent
        self._edits = {}
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(14, 14, 14, 10)

        # 本次将生成的检测项目清单
        if self._checked_items:
            frame = QFrame()
            frame.setFrameShape(QFrame.StyledPanel)
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(8, 6, 8, 6)
            title = QLabel(f"本次将生成 {len(self._checked_items)} 个检测项目的报告：")
            title.setStyleSheet("font-weight: bold;")
            fv.addWidget(title)
            items = QLabel("\n".join(
                f"{i}．{key}" for i, key in enumerate(self._checked_items, 1)))
            items.setWordWrap(True)
            fv.addWidget(items)
            root.addWidget(frame)

        # 抬头信息表单
        form = QFormLayout()
        form.setSpacing(6)
        for key, label, default in REPORT_INFO_FIELDS:
            edit = QLineEdit(str(self._prefill.get(key, default) or ""))
            self._edits[key] = edit
            form.addRow(f"{label}:", edit)
        root.addLayout(form)

        hint = QLabel("提示：信息随项目文件保存，下次生成时自动带出。")
        hint.setStyleSheet("color: gray;")
        root.addWidget(hint)

        # Agent 模式开关（LLM 编排生成；失败自动回退普通生成）
        self._agent_cb = QCheckBox(
            "Agent 模式（Ollama 大模型编排生成，失败自动回退普通生成）")
        if self._default_use_agent is None:
            self._agent_cb.setChecked(agent_default_enabled())
        else:
            self._agent_cb.setChecked(bool(self._default_use_agent))
        self._agent_cb.setStyleSheet("color: #555;")
        root.addWidget(self._agent_cb)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("生成报告")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)
        root.addLayout(btn_row)

    def get_values(self):
        """收集表单值为 dict（未填字段返回空串）。"""
        return {key: self._edits[key].text().strip()
                for key, _label, _default in REPORT_INFO_FIELDS}

    def use_agent(self):
        """是否启用 Agent 模式（LLM 编排生成）。"""
        return self._agent_cb.isChecked()
