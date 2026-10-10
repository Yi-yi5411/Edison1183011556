# -*- coding: utf-8 -*-
r"""Structural Inspection Report Generator - Launch Script (login required).

Usage:
    python run.py
    .\.venv\Scripts\python.exe run.py
"""

import os
import sys

_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from login_launcher import main


if __name__ == "__main__":
    sys.exit(main())
