# -*- coding: utf-8 -*-
"""登录启动器：先弹出登录界面，认证通过后再启动报告生成器主窗口。

该模块由根目录 run.py（源码运行）与 report_generator/main.py（打包入口）调用。
首次启动时会自动把 user_mobile_1029.sql 中的用户导入到 auth.db，
用户可用“手机号 / 用户名 + 手机号作为密码”登录。

目录：桌面端专属文件（登录/主页/账号库/auth.db/图标）都在 desktop/；
共享业务层仍在 report_generator/。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # desktop/
_FROZEN = bool(getattr(sys, "frozen", False))
# 打包后：auth.db 等数据放在 _MEIPASS 根目录；源码运行：放在 desktop/
_ROOT = getattr(sys, "_MEIPASS", os.path.dirname(_HERE)) if _FROZEN \
    else os.path.dirname(_HERE)
_DATA = _ROOT if _FROZEN else _HERE
_REPORT_GENERATOR = os.path.join(_ROOT, "report_generator")
_LIBS = os.path.join(_REPORT_GENERATOR, "libs")

# 源码运行时把 desktop/、项目根、report_generator 加入 import 路径；
# 打包后模块在 PYZ 中，不需要（也不应该）依赖磁盘路径。
if not _FROZEN:
    for _path in (_HERE, _ROOT, _REPORT_GENERATOR):
        if _path not in sys.path:
            sys.path.insert(0, _path)
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from PyQt5.QtWidgets import QApplication, QDialog

try:  # 作为 desktop 包导入（run.py / report_generator/main.py）
    from .auth_db import AuthDatabase
    from .login import LoginDialog
except ImportError:  # 兼容 python desktop/login_launcher.py 直接运行
    from auth_db import AuthDatabase
    from login import LoginDialog


def _ensure_seed_users(auth_db):
    """首次运行时把 SQL 中的用户导入 auth.db。"""
    sql_path = os.path.join(_DATA, "user_mobile_1029.sql")
    if not os.path.exists(sql_path):
        return

    # 初始库中只有 admin，说明还没有导入过手机号用户
    if len(auth_db.get_user_list()) > 1:
        return

    try:
        auth_db.import_users_from_sql(sql_path)
    except Exception:
        # 导入失败不应阻止登录，admin 账户仍可使用
        pass


def main():
    """登录后先进入功能选择主页，再按选择启动对应模块。"""
    app = QApplication.instance() or QApplication(sys.argv)

    auth_db = AuthDatabase(os.path.join(_DATA, "auth.db"))
    _ensure_seed_users(auth_db)

    login_dialog = LoginDialog(auth_db)
    if login_dialog.exec_() != QDialog.Accepted:
        return 1

    current_user = login_dialog.get_current_user()

    # 登录成功后先加载功能选择主页，再按选择进入对应模块
    try:
        from .home_menu import HomeMenu
    except ImportError:  # 兼容直接运行 desktop/login_launcher.py
        from home_menu import HomeMenu
    from PyQt5.QtWidgets import QMessageBox

    home = HomeMenu(current_user)
    while True:
        if home.exec_() != QDialog.Accepted:
            return 0  # 用户在主页选择退出

        action = home.choice

        if action == "scan":
            # 原始记录识别：直接打开 AI 扫描识别（OCR + 大模型结构化）
            from report_generator.scan_recognition.test_tool import ScanRecognitionTestDialog
            try:
                ScanRecognitionTestDialog(parent=home).exec_()
            except Exception as e:
                QMessageBox.critical(home, "打开失败", f"无法打开扫描识别：{e}")

        elif action == "scan_history":
            # 识别记录查看：所有识别过的检测项目默认保留位置
            from report_generator.scan_recognition.history import ScanHistoryDialog
            try:
                ScanHistoryDialog(parent=home).exec_()
            except Exception as e:
                QMessageBox.critical(home, "打开失败", f"无法打开识别记录：{e}")

        elif action in ("concrete", "steel", "wood", "masonry"):
            # 结构检测模块：进入报告数据管理主程序。各结构类型的检测
            # 项目由插件注册（core.plugin_manager 按结构类型聚合），
            # 每个入口只展示各自结构类型的检测项目。
            from framework.ui.main_window import ReportGeneratorApp

            structure_map = {
                "concrete": "混凝土结构",
                "steel": "钢结构",
                "wood": "木结构",
                "masonry": "砖混结构",
            }
            report_app = ReportGeneratorApp(
                structure_type=structure_map.get(action))
            report_app.current_user = current_user

            title = "工程检测harness"
            title += f" - {home.choice_label}"
            display_name = (current_user or {}).get("real_name") \
                or (current_user or {}).get("username")
            if display_name:
                title += f" - {display_name}"
            report_app.win.setWindowTitle(title)

            # 主窗口关闭后事件循环返回，回到功能选择主页
            report_app.win.show()
            app.exec_()
            report_app.win.close()
            report_app.win.deleteLater()

        else:
            # 其余结构模块：参照混凝土结构功能预留
            QMessageBox.information(
                home, "提示",
                f"「{home.choice_label}」模块参照混凝土结构检测的功能建设中，敬请期待。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
