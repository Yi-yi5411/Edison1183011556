# -*- coding: utf-8 -*-
"""Structural Inspection Report Generator - Entry Point (PyQt5)"""
import sys
import os

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base)
_libs = os.path.join(_base, "libs")
if os.path.isdir(_libs):
    sys.path.insert(0, _libs)

# 桌面端登录/主页/账号库位于 desktop/（包），项目根只保留外部入口
_root = os.path.dirname(_base)
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from desktop.login_launcher import main
except ImportError:  # 兼容旧布局（登录模块曾在根目录）
    from login_launcher import main


if __name__ == "__main__":
    sys.exit(main())
