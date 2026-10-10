# -*- coding: utf-8 -*-
"""
登录界面模块 (LoginDialog)

功能：
- 用户登录（支持用户名和手机号）
- 用户注册
- 密码修改
"""

import sys
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QTabWidget,
    QWidget, QCheckBox, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPixmap

# 导入认证数据库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth_db import AuthDatabase
# 项目静态资源统一入口（所有图片/模板集中存放在 report_generator/assets/）
from report_generator.framework.resources import get_asset


class RegisterDialog(QDialog):
    """注册对话框"""
    
    def __init__(self, auth_db: AuthDatabase, parent=None):
        super().__init__(parent)
        self.auth_db = auth_db
        self.setWindowTitle("用户注册")
        self.setFixedSize(420, 380)
        self._init_ui()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title = QLabel("创建新账户")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("请填写以下信息完成注册")
        subtitle.setStyleSheet("color: #888;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(10)
        
        # 表单
        form = QFormLayout()
        form.setSpacing(10)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("3-20个字符")
        form.addRow("用户名*:", self.username_input)
        
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("11位手机号码（可选）")
        self.phone_input.setMaxLength(11)
        form.addRow("手机号:", self.phone_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("至少6个字符")
        form.addRow("密码*:", self.password_input)
        
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText("再次输入密码")
        form.addRow("确认密码*:", self.confirm_input)
        
        self.realname_input = QLineEdit()
        self.realname_input.setPlaceholderText("您的姓名（可选）")
        form.addRow("真实姓名:", self.realname_input)
        
        self.dept_input = QLineEdit()
        self.dept_input.setPlaceholderText("所属部门（可选）")
        form.addRow("部门:", self.dept_input)
        
        layout.addLayout(form)
        
        layout.addSpacing(10)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        register_btn = QPushButton("注 册")
        register_btn.setStyleSheet(
            "background-color: #2196F3; color: white; padding: 8px 24px; "
            "border-radius: 4px; font-weight: bold;"
        )
        register_btn.clicked.connect(self._on_register)
        btn_layout.addWidget(register_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_register(self):
        """处理注册"""
        username = self.username_input.text().strip()
        phone = self.phone_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()
        realname = self.realname_input.text().strip()
        dept = self.dept_input.text().strip()
        
        # 验证输入
        if not username or len(username) < 3:
            QMessageBox.warning(self, "提示", "用户名至少需要3个字符")
            return
        
        if not password or len(password) < 6:
            QMessageBox.warning(self, "提示", "密码至少需要6个字符")
            return
        
        if password != confirm:
            QMessageBox.warning(self, "提示", "两次输入的密码不一致")
            return
        
        if phone and not phone.isdigit():
            QMessageBox.warning(self, "提示", "手机号只能包含数字")
            return
        
        success, msg = self.auth_db.register_user(
            username=username,
            password=password,
            phone=phone if phone else None,
            real_name=realname,
            department=dept
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "注册失败", msg)


class LoginDialog(QDialog):
    """登录对话框"""
    
    login_success = pyqtSignal(dict)  # 登录成功信号
    
    def __init__(self, auth_db: AuthDatabase = None, parent=None):
        super().__init__(parent)
        self.auth_db = auth_db or AuthDatabase()
        self.current_user = None
        self.setWindowTitle("系统登录")
        self.setFixedSize(480, 640)
        self._init_ui()
        
        # 自动连接回车键
        self.username_input.returnPressed.connect(self._on_login)
        self.password_input.returnPressed.connect(self._on_login)
    
    def _load_logo(self):
        """加载logo图片（统一从 report_generator/assets/ 读取，兼容 jpg/png 两种扩展名）。"""
        # 静态资源集中存放在 <项目根>/report_generator/assets/，通过 get_asset 定位。
        candidates = [
            get_asset("logo.jpg"),
            get_asset("logo.png"),
        ]
        for logo_path in candidates:
            if logo_path.exists():
                pixmap = QPixmap(str(logo_path))
                if not pixmap.isNull():
                    # 缩放到合适大小
                    return pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # 如果找不到logo，返回一个空的占位图片
        pixmap = QPixmap(140, 140)
        pixmap.fill(Qt.transparent)
        return pixmap
    
    def _init_ui(self):
        """初始化界面"""
        # 设置背景 - 深蓝渐变
        self.setStyleSheet("""
            QDialog {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0D47A1, stop:0.4 #1565C0, stop:1 #1976D2);
            }
            QLabel#title {
                color: white;
                font-size: 22px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#subtitle {
                color: rgba(255,255,255,0.85);
                font-size: 13px;
                letter-spacing: 1px;
            }
            QLabel#company {
                color: rgba(255,255,255,0.65);
                font-size: 12px;
            }
            QLabel#copyright {
                color: rgba(255,255,255,0.45);
                font-size: 11px;
            }
            QLabel#formLabel {
                color: #37474F;
                font-size: 14px;
                font-weight: bold;
            }
            QLabel#bottomHint {
                color: rgba(255,255,255,0.8);
                font-size: 12px;
            }
            QLineEdit {
                padding: 8px 14px;
                border: 2px solid #ECEFF1;
                border-radius: 8px;
                background-color: #F5F7FA;
                font-size: 15px;
                selection-background-color: #1976D2;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                background-color: white;
            }
            QLineEdit:hover {
                border: 2px solid #B0BEC5;
            }
            QCheckBox {
                color: #546E7A;
                font-size: 15px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #B0BEC5;
                background: white;
            }
            QCheckBox::indicator:checked {
                background: #1976D2;
                border: 2px solid #1976D2;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # ===== 顶部留白 =====
        layout.addSpacing(20)
        
        # ===== Logo 区域（带白色圆形背景） =====
        logo_container = QHBoxLayout()
        logo_container.setAlignment(Qt.AlignCenter)
        
        logo_bg = QFrame()
        logo_bg.setFixedSize(120, 120)
        logo_bg.setStyleSheet("""
            QFrame {
                background-color: rgba(255,255,255,0.95);
                border-radius: 60px;
                border: 2px solid rgba(255,255,255,0.3);
            }
        """)
        logo_bg_layout = QHBoxLayout(logo_bg)
        logo_bg_layout.setContentsMargins(10, 10, 10, 10)
        
        logo_label = QLabel()
        logo_pixmap = self._load_logo()
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_bg_layout.addWidget(logo_label)
        
        logo_container.addWidget(logo_bg)
        layout.addLayout(logo_container)
        
        layout.addSpacing(14)
        
        # ===== 标题区域 =====
        title_label = QLabel("主体结构检测数据管理录入系统V1.0")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setMinimumHeight(30)
        layout.addWidget(title_label)
        
        subtitle_label = QLabel("混凝土结构检测")
        subtitle_label.setObjectName("subtitle")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setMinimumHeight(20)
        layout.addWidget(subtitle_label)
        
        layout.addSpacing(16)
        
        # ===== 登录表单卡片 =====
        card_wrapper = QHBoxLayout()
        card_wrapper.setContentsMargins(40, 0, 40, 0)
        
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 14px;
                border: none;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)
        card_layout.setContentsMargins(28, 24, 28, 22)
        
        # --- 用户名 ---
        username_label = QLabel("用户名")
        username_label.setObjectName("formLabel")
        username_label.setMinimumHeight(20)
        card_layout.addWidget(username_label)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名或手机号")
        self.username_input.setFixedHeight(40)
        card_layout.addWidget(self.username_input)
        
        card_layout.addSpacing(12)
        
        # --- 密码 ---
        password_label = QLabel("密码")
        password_label.setObjectName("formLabel")
        password_label.setMinimumHeight(20)
        card_layout.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setFixedHeight(40)
        card_layout.addWidget(self.password_input)
        
        card_layout.addSpacing(10)
        
        # --- 记住密码和忘记密码 ---
        remember_row = QHBoxLayout()
        self.remember_check = QCheckBox("记住我")
        self.remember_check.setMinimumHeight(26)
        remember_row.addWidget(self.remember_check)
        remember_row.addStretch()
        
        forgot_btn = QPushButton("忘记密码?")
        forgot_btn.setFlat(True)
        forgot_btn.setMinimumHeight(26)
        forgot_btn.setCursor(Qt.PointingHandCursor)
        forgot_btn.setStyleSheet("""
            QPushButton {
                color: #1976D2;
                font-size: 13px;
                padding: 2px 6px;
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                color: #0D47A1;
                text-decoration: underline;
            }
        """)
        forgot_btn.clicked.connect(self._on_forgot_password)
        remember_row.addWidget(forgot_btn)
        
        card_layout.addLayout(remember_row)
        
        card_layout.addSpacing(12)
        
        # --- 登录按钮（渐变） ---
        login_btn = QPushButton("登 录")
        login_btn.setMinimumHeight(44)
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1976D2, stop:1 #42A5F5);
                color: white;
                padding: 10px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 16px;
                border: none;
                letter-spacing: 6px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1565C0, stop:1 #1E88E5);
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0D47A1, stop:1 #1565C0);
            }
        """)
        login_btn.clicked.connect(self._on_login)
        card_layout.addWidget(login_btn)
        
        card_layout.addSpacing(8)
        
        # --- 分隔线 ---
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #ECEFF1; background-color: #ECEFF1; border: none; max-height: 1px;")
        divider.setFixedHeight(1)
        card_layout.addWidget(divider)
        
        card_layout.addSpacing(4)
        
        # --- 注册链接 ---
        register_row = QHBoxLayout()
        register_row.setAlignment(Qt.AlignCenter)
        
        register_label = QLabel("还没有账户?")
        register_label.setStyleSheet("color: #78909C; font-size: 13px;")
        register_label.setMinimumHeight(24)
        register_row.addWidget(register_label)
        
        register_btn = QPushButton("立即注册")
        register_btn.setFlat(True)
        register_btn.setMinimumHeight(24)
        register_btn.setCursor(Qt.PointingHandCursor)
        register_btn.setStyleSheet("""
            QPushButton {
                color: #1976D2;
                font-weight: bold;
                font-size: 13px;
                padding: 2px 6px;
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                color: #0D47A1;
                text-decoration: underline;
            }
        """)
        register_btn.clicked.connect(self._on_register)
        register_row.addWidget(register_btn)
        
        card_layout.addLayout(register_row)
        
        card_layout.addSpacing(4)
        
        # --- 文档扫描识别测试入口 ---
        self.scan_test_btn = QPushButton("文档扫描识别测试")
        self.scan_test_btn.setMinimumHeight(30)
        self.scan_test_btn.setCursor(Qt.PointingHandCursor)
        self.scan_test_btn.setStyleSheet("""
            QPushButton {
                color: #1976D2;
                font-size: 13px;
                border: 1px dashed #1976D2;
                border-radius: 6px;
                background: rgba(25, 118, 210, 0.05);
                padding: 6px;
            }
            QPushButton:hover {
                background: rgba(25, 118, 210, 0.12);
            }
        """)
        self.scan_test_btn.clicked.connect(self._on_scan_test)
        card_layout.addWidget(self.scan_test_btn)
        
        card_wrapper.addWidget(card)
        layout.addLayout(card_wrapper)
        
        layout.addSpacing(12)
        
        # ===== 底部提示 =====
        bottom_hint = QLabel("提示：用户名为手机号，密码默认为手机号")
        bottom_hint.setObjectName("bottomHint")
        bottom_hint.setAlignment(Qt.AlignCenter)
        bottom_hint.setMinimumHeight(20)
        layout.addWidget(bottom_hint)
        
        # ===== 底部弹性空间 =====
        layout.addStretch()
        
        # ===== 公司信息 =====
        company_label = QLabel("技术支持：湖北省建筑科学研究设计院股份有限公司")
        company_label.setObjectName("company")
        company_label.setAlignment(Qt.AlignCenter)
        company_label.setMinimumHeight(22)
        layout.addWidget(company_label)
        
        # ===== 版权信息 =====
        copyright_label = QLabel("© 2026 All Rights Reserved")
        copyright_label.setObjectName("copyright")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setMinimumHeight(18)
        layout.addWidget(copyright_label)
        
        layout.addSpacing(10)
    
    def _on_login(self):
        """处理登录"""
        login_id = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not login_id or not password:
            QMessageBox.warning(self, "提示", "请输入用户名和密码")
            return
        
        # 执行认证
        success, user_info, msg = self.auth_db.authenticate(login_id, password)
        
        if success:
            self.current_user = user_info
            self.login_success.emit(user_info)
            self.accept()
        else:
            # 显示错误
            self.password_input.clear()
            self.password_input.setFocus()
            
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("登录失败")
            msg_box.setText(msg)
            msg_box.setStyleSheet("""
                QMessageBox {
                    background: white;
                }
                QMessageBox QLabel {
                    color: #333;
                }
            """)
            msg_box.exec_()
    
    def _on_register(self):
        """打开注册对话框"""
        register_dialog = RegisterDialog(self.auth_db, self)
        register_dialog.exec_()

    def _on_scan_test(self):
        """打开文档扫描识别测试对话框（无需登录即可测试扫描识别流水线）。"""
        try:
            from report_generator.scan_recognition.test_tool import ScanRecognitionTestDialog
            dialog = ScanRecognitionTestDialog(parent=self)
            dialog.exec_()
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.critical(self, "打开失败", f"无法打开扫描识别测试：{e}")
    
    def _on_forgot_password(self):
        """忘记密码提示"""
        QMessageBox.information(
            self, 
            "找回密码", 
            "请联系系统管理员重置密码\n管理员账户: admin"
        )
    
    def get_current_user(self) -> dict:
        """获取当前登录用户信息"""
        return self.current_user


class UserManagementDialog(QDialog):
    """用户管理对话框（管理员功能）"""
    
    def __init__(self, auth_db: AuthDatabase, parent=None):
        super().__init__(parent)
        self.auth_db = auth_db
        self.setWindowTitle("用户管理")
        self.resize(600, 450)
        self._init_ui()
        self._refresh_user_list()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 标题
        title = QLabel("用户管理")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(title)
        
        # 用户列表
        self.user_list_label = QLabel()
        self.user_list_label.setStyleSheet("color: #666;")
        layout.addWidget(self.user_list_label)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_user_list)
        btn_layout.addWidget(refresh_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _refresh_user_list(self):
        """刷新用户列表"""
        users = self.auth_db.get_user_list()
        
        if not users:
            self.user_list_label.setText("暂无用户")
            return
        
        # 生成用户列表文本
        text = "用户名 | 手机号 | 姓名 | 部门 | 角色 | 状态\n"
        text += "-" * 60 + "\n"
        
        for user in users:
            status = "启用" if user['is_active'] else "禁用"
            text += f"{user['username']} | {user['phone'] or '-'} | {user['real_name'] or '-'} | {user['department'] or '-'} | {user['role']} | {status}\n"
        
        self.user_list_label.setText(text)


class ChangePasswordDialog(QDialog):
    """修改密码对话框"""
    
    def __init__(self, auth_db: AuthDatabase, user_id: int, parent=None):
        super().__init__(parent)
        self.auth_db = auth_db
        self.user_id = user_id
        self.setWindowTitle("修改密码")
        self.setFixedSize(350, 250)
        self._init_ui()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 表单
        form = QFormLayout()
        form.setSpacing(10)
        
        self.old_password = QLineEdit()
        self.old_password.setEchoMode(QLineEdit.Password)
        self.old_password.setPlaceholderText("请输入当前密码")
        form.addRow("当前密码:", self.old_password)
        
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.Password)
        self.new_password.setPlaceholderText("至少6个字符")
        form.addRow("新密码:", self.new_password)
        
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.Password)
        self.confirm_password.setPlaceholderText("再次输入新密码")
        form.addRow("确认新密码:", self.confirm_password)
        
        layout.addLayout(form)
        
        layout.addSpacing(10)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确 定")
        ok_btn.setStyleSheet(
            "background-color: #2196F3; color: white; padding: 8px 24px; "
            "border-radius: 4px; font-weight: bold;"
        )
        ok_btn.clicked.connect(self._on_change)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_change(self):
        """处理密码修改"""
        old_pwd = self.old_password.text()
        new_pwd = self.new_password.text()
        confirm_pwd = self.confirm_password.text()
        
        if not old_pwd or not new_pwd or not confirm_pwd:
            QMessageBox.warning(self, "提示", "请填写所有密码字段")
            return
        
        if len(new_pwd) < 6:
            QMessageBox.warning(self, "提示", "新密码至少需要6个字符")
            return
        
        if new_pwd != confirm_pwd:
            QMessageBox.warning(self, "提示", "两次输入的新密码不一致")
            return
        
        if old_pwd == new_pwd:
            QMessageBox.warning(self, "提示", "新密码不能与旧密码相同")
            return
        
        success, msg = self.auth_db.change_password(
            self.user_id, old_pwd, new_pwd
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "修改失败", msg)


def main():
    """测试入口"""
    app = QApplication(sys.argv)
    
    # 创建认证数据库
    auth_db = AuthDatabase()
    
    # 显示登录对话框
    login_dialog = LoginDialog(auth_db)
    
    if login_dialog.exec_() == QDialog.Accepted:
        user = login_dialog.get_current_user()
        print(f"登录成功！欢迎 {user.get('username')}")
        # 这里可以启动主窗口
    else:
        print("用户取消登录")


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    main()
