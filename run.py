# -*- coding: utf-8 -*-
r"""Structural Inspection Report Generator - Launch Script (login required).

Usage:
    python run.py
    .\.venv\Scripts\python.exe run.py

桌面端实现都在 desktop/（登录 / 功能主页 / 账号库 / 启动器）；本文件只是外部入口。
"""

import os
import sys

_BASE = os.path.dirname(os.path.abspath(__file__))
for _path in (_BASE, os.path.join(_BASE, "report_generator", "libs")):
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from desktop.login_launcher import main


if __name__ == "__main__":
    sys.exit(main())
