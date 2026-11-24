# -*- coding: utf-8 -*-
"""桌面端（PyQt5）独立套件：登录、功能主页、本地账号库与启动器。

外部入口仍保留在项目根目录：
    run.py        -> desktop.login_launcher.main
    run_app.bat   -> python run.py
    report_generator.spec / build.bat  -> 打包（入口 report_generator/main.py）

共享业务层（评定/报告/规则/存储）仍在 report_generator/，Web 与桌面共用。
"""
