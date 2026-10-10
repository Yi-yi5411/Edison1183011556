# -*- coding: utf-8 -*-
"""
用户认证数据库模块 (AuthDatabase)

功能：
- 用户注册/登录验证
- 支持用户名和手机号两种登录方式
- 用户信息管理

数据库文件：auth.db (SQLite)
"""

import sqlite3
import hashlib
import os
from datetime import datetime
from typing import Optional, List, Dict, Tuple


class AuthDatabase:
    """用户认证数据库管理类"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为项目目录下的 auth.db
        """
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "auth.db"
            )
        self.db_path = db_path
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                phone TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                real_name TEXT,
                department TEXT,
                role TEXT DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # 创建登录日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                login_type TEXT,  -- username or phone
                login_ip TEXT DEFAULT 'local',
                status TEXT,  -- success or failed
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # 创建默认管理员账户
        admin_exists = cursor.execute(
            "SELECT COUNT(*) FROM users WHERE username = ?", 
            ("admin",)
        ).fetchone()[0]
        
        if not admin_exists:
            self._create_user(
                conn,
                username="admin",
                phone="13800000000",
                password="admin123",
                real_name="系统管理员",
                department="技术部",
                role="admin"
            )
        
        # 初始化种子用户数据（从 seed_users.py 导入）
        user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count <= 1:
            try:
                from seed_users import SEED_USERS
                for username, mobile in SEED_USERS:
                    # 密码默认为手机号
                    self._create_user(
                        conn,
                        username=username,
                        phone=mobile,
                        password=mobile,
                        real_name=username,
                        role="user"
                    )
            except ImportError:
                pass  # 种子数据模块不存在时跳过
        
        conn.commit()
        conn.close()
    
    def _hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """
        哈希密码
        
        Args:
            password: 原始密码
            salt: 盐值，如果为None则自动生成
            
        Returns:
            (hash_value, salt)
        """
        if salt is None:
            salt = os.urandom(16).hex()
        
        # 使用 SHA-256 进行多次哈希
        hashed = password.encode('utf-8')
        salt_bytes = salt.encode('utf-8')
        
        for _ in range(10000):
            hashed = hashlib.sha256(hashed + salt_bytes).digest()
        
        return hashed.hex(), salt
    
    def _create_user(
        self, 
        conn: sqlite3.Connection,
        username: str, 
        phone: str, 
        password: str,
        real_name: str = "",
        department: str = "",
        role: str = "user"
    ) -> bool:
        """
        创建用户（内部方法，需要传入conn）
        """
        password_hash, salt = self._hash_password(password)
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, phone, password_hash, salt, real_name, department, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, phone, password_hash, salt, real_name, department, role))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def register_user(
        self,
        username: str,
        password: str,
        phone: str = None,
        real_name: str = "",
        department: str = ""
    ) -> Tuple[bool, str]:
        """
        注册新用户
        
        Args:
            username: 用户名
            password: 密码
            phone: 手机号（可选）
            real_name: 真实姓名（可选）
            department: 部门（可选）
            
        Returns:
            (成功标志, 消息)
        """
        # 验证输入
        if not username or len(username) < 3:
            return False, "用户名至少3个字符"
        if not password or len(password) < 6:
            return False, "密码至少6个字符"
        if phone and not phone.isdigit():
            return False, "手机号只能包含数字"
        
        conn = self._get_connection()
        
        # 检查用户名是否已存在
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if existing:
            conn.close()
            return False, "用户名已存在"
        
        # 检查手机号是否已存在
        if phone:
            existing = conn.execute(
                "SELECT id FROM users WHERE phone = ?",
                (phone,)
            ).fetchone()
            if existing:
                conn.close()
                return False, "手机号已注册"
        
        success = self._create_user(
            conn, username, phone, password, real_name, department, "user"
        )
        conn.close()
        
        if success:
            return True, "注册成功"
        else:
            return False, "注册失败，请稍后重试"
    
    def authenticate(
        self, 
        login_id: str, 
        password: str
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        用户认证（支持用户名或手机号）
        
        Args:
            login_id: 登录标识（用户名或手机号）
            password: 密码
            
        Returns:
            (成功标志, 用户信息字典或None, 消息)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 尝试用手机号登录
        if login_id.isdigit() and len(login_id) == 11:
            user = cursor.execute(
                "SELECT * FROM users WHERE phone = ?",
                (login_id,)
            ).fetchone()
            login_type = "phone"
        else:
            # 尝试用用户名登录
            user = cursor.execute(
                "SELECT * FROM users WHERE username = ?",
                (login_id,)
            ).fetchone()
            login_type = "username"
        
        if not user:
            self._log_login(conn, None, login_type, "failed")
            conn.close()
            return False, None, "用户不存在"
        
        # 检查账户状态
        if not user['is_active']:
            conn.close()
            return False, None, "账户已被禁用"
        
        # 验证密码
        password_hash, _ = self._hash_password(password, user['salt'])
        if password_hash != user['password_hash']:
            self._log_login(conn, user['id'], login_type, "failed")
            conn.close()
            return False, None, "密码错误"
        
        # 更新最后登录时间
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), user['id'])
        )
        self._log_login(conn, user['id'], login_type, "success")
        conn.commit()
        
        # 返回用户信息
        user_info = {
            'id': user['id'],
            'username': user['username'],
            'phone': user['phone'],
            'real_name': user['real_name'],
            'department': user['department'],
            'role': user['role'],
            'last_login': user['last_login']
        }
        
        conn.close()
        return True, user_info, "登录成功"
    
    def _log_login(
        self, 
        conn: sqlite3.Connection, 
        user_id: Optional[int],
        login_type: str,
        status: str
    ):
        """记录登录日志"""
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO login_logs (user_id, login_type, login_ip, status)
            VALUES (?, ?, ?, ?)
        ''', (user_id, login_type, 'local', status))
    
    def get_user_list(self, role: str = None) -> List[Dict]:
        """
        获取用户列表
        
        Args:
            role: 角色过滤（可选）
            
        Returns:
            用户信息列表
        """
        conn = self._get_connection()
        
        if role:
            users = conn.execute(
                "SELECT id, username, phone, real_name, department, role, is_active, last_login FROM users WHERE role = ?",
                (role,)
            ).fetchall()
        else:
            users = conn.execute(
                "SELECT id, username, phone, real_name, department, role, is_active, last_login FROM users"
            ).fetchall()
        
        result = []
        for user in users:
            result.append({
                'id': user['id'],
                'username': user['username'],
                'phone': user['phone'],
                'real_name': user['real_name'],
                'department': user['department'],
                'role': user['role'],
                'is_active': user['is_active'] == 1,
                'last_login': user['last_login']
            })
        
        conn.close()
        return result
    
    def update_user_status(self, user_id: int, is_active: bool) -> bool:
        """
        更新用户状态（启用/禁用）
        
        Args:
            user_id: 用户ID
            is_active: 是否启用
            
        Returns:
            是否成功
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id)
        )
        conn.commit()
        conn.close()
        return True
    
    def change_password(
        self, 
        user_id: int, 
        old_password: str, 
        new_password: str
    ) -> Tuple[bool, str]:
        """
        修改密码
        
        Args:
            user_id: 用户ID
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            (成功标志, 消息)
        """
        if not new_password or len(new_password) < 6:
            return False, "新密码至少6个字符"
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        user = cursor.execute(
            "SELECT salt, password_hash FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        
        if not user:
            conn.close()
            return False, "用户不存在"
        
        # 验证旧密码
        old_hash, _ = self._hash_password(old_password, user['salt'])
        if old_hash != user['password_hash']:
            conn.close()
            return False, "旧密码错误"
        
        # 更新新密码
        new_hash, new_salt = self._hash_password(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (new_hash, new_salt, user_id)
        )
        conn.commit()
        conn.close()
        
        return True, "密码修改成功"
    
    def delete_user(self, user_id: int) -> bool:
        """
        删除用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        cursor.execute("DELETE FROM login_logs WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    
    def get_login_logs(self, limit: int = 50) -> List[Dict]:
        """
        获取登录日志
        
        Args:
            limit: 返回条数限制
            
        Returns:
            日志列表
        """
        conn = self._get_connection()
        logs = conn.execute('''
            SELECT l.*, u.username 
            FROM login_logs l 
            LEFT JOIN users u ON l.user_id = u.id 
            ORDER BY l.login_time DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        
        result = []
        for log in logs:
            result.append({
                'id': log['id'],
                'user_id': log['user_id'],
                'username': log['username'],
                'login_time': log['login_time'],
                'login_type': log['login_type'],
                'status': log['status']
            })
        
        conn.close()
        return result
    
    def import_users_from_sql(self, sql_file_path: str) -> Tuple[int, int, List[str]]:
        """
        从SQL文件批量导入用户
        
        Args:
            sql_file_path: SQL文件路径
            
        Returns:
            (成功数量, 失败数量, 错误信息列表)
        """
        import re
        
        if not os.path.exists(sql_file_path):
            return 0, 0, ["SQL文件不存在"]
        
        success_count = 0
        fail_count = 0
        errors = []
        
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析INSERT语句
        # 格式: INSERT INTO `table` (`col1`, `col2`, ...) VALUES ('val1', 'val2', ...);
        pattern = r"INSERT INTO\s+`?\w+`?\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)"
        matches = re.findall(pattern, content, re.IGNORECASE)
        
        conn = self._get_connection()
        
        for columns_str, values_str in matches:
            try:
                # 解析列名
                columns = [c.strip().strip('`').strip('"') for c in columns_str.split(',')]
                
                # 解析值 - 简单处理
                values = self._parse_sql_values(values_str)
                
                # 构建字典
                record = {}
                for col, val in zip(columns, values):
                    record[col] = val
                
                # 提取用户名和手机号
                username = record.get('username') or record.get('usercode')
                mobile = record.get('mobile') or record.get('phone')
                
                if not username or not mobile:
                    fail_count += 1
                    errors.append(f"缺少必要字段: username={username}, mobile={mobile}")
                    continue
                
                # 手机号转为字符串
                mobile = str(mobile).strip("'\" ")
                
                # 检查用户是否已存在
                existing = conn.execute(
                    "SELECT id FROM users WHERE username = ? OR phone = ?",
                    (username, mobile)
                ).fetchone()
                
                if existing:
                    fail_count += 1
                    continue
                
                # 创建用户 - 密码默认为手机号
                self._create_user(
                    conn,
                    username=username,
                    phone=mobile,
                    password=mobile,  # 密码为手机号
                    real_name=username,
                    role="user"
                )
                success_count += 1
                
            except Exception as e:
                fail_count += 1
                errors.append(f"导入失败: {str(e)}")
        
        conn.close()
        
        return success_count, fail_count, errors
    
    def _parse_sql_values(self, values_str: str) -> List[str]:
        """
        解析SQL VALUES字符串
        """
        values = []
        current = []
        in_string = False
        escape_next = False
        
        for char in values_str:
            if escape_next:
                current.append(char)
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == "'" and not in_string:
                in_string = True
            elif char == "'" and in_string:
                in_string = False
            elif char == ',' and not in_string:
                value = ''.join(current).strip()
                if value.upper() == 'NULL':
                    values.append(None)
                else:
                    values.append(value)
                current = []
            else:
                current.append(char)
        
        # 处理最后一个值
        if current:
            value = ''.join(current).strip()
            if value.upper() == 'NULL':
                values.append(None)
            else:
                values.append(value)
        
        return values
    
    def reset_user_password_to_phone(self, user_id: int) -> Tuple[bool, str]:
        """
        重置用户密码为手机号
        
        Args:
            user_id: 用户ID
            
        Returns:
            (成功标志, 消息)
        """
        conn = self._get_connection()
        user = conn.execute(
            "SELECT phone FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        
        if not user or not user['phone']:
            conn.close()
            return False, "用户不存在或未设置手机号"
        
        # 使用手机号作为密码
        password = user['phone']
        password_hash, salt = self._hash_password(password)
        
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (password_hash, salt, user_id)
        )
        conn.commit()
        conn.close()
        
        return True, "密码已重置为手机号"
    
    def reset_all_passwords_to_phone(self) -> Tuple[int, int]:
        """
        将所有有手机号的用户密码重置为手机号（不包括管理员）
        
        Returns:
            (成功数量, 失败数量)
        """
        conn = self._get_connection()
        users = conn.execute(
            "SELECT id, phone FROM users WHERE phone IS NOT NULL AND phone != '' AND role != 'admin'"
        ).fetchall()
        
        success_count = 0
        fail_count = 0
        
        for user in users:
            try:
                password = user['phone']
                password_hash, salt = self._hash_password(password)
                conn.execute(
                    "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                    (password_hash, salt, user['id'])
                )
                success_count += 1
            except Exception:
                fail_count += 1
        
        conn.commit()
        conn.close()
        
        return success_count, fail_count
