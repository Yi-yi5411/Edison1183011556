# -*- coding: utf-8 -*-
"""Structural Inspection Report Generator - Entry Point (PyQt5)"""
import sys
import os

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base)
_libs = os.path.join(_base, "libs")
if os.path.isdir(_libs):
    sys.path.insert(0, _libs)

# 登录模块与 auth_db.py 位于项目根目录
_root = os.path.dirname(_base)
if _root not in sys.path:
    sys.path.insert(0, _root)

from login_launcher import main 


if __name__ == "__main__":
    sys.exit(main())
