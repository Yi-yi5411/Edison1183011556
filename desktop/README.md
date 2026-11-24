# 桌面端（PyQt5）

独立套件：登录、功能主页、本地账号库与启动器。共享业务层（评定/报告/规则/存储）
仍在 `report_generator/`，Web 与桌面共用。

## 目录

| 文件 | 说明 |
|---|---|
| `login_launcher.py` | 启动器：登录 → 功能主页 → 按选择打开模块 |
| `login.py` | 登录对话框（手机号/用户名 + 手机号密码） |
| `home_menu.py` | 登录后的功能选择主页（混凝土/钢/木/砖混/扫描） |
| `auth_db.py` | 本地账号库（SQLite） |
| `auth.db` | 运行时账号库（含全部已注册用户，不入库） |
| `user_mobile_1029.sql` | 首次启动导入的种子用户 SQL |
| `app.ico` | 窗口/EXE 图标 |

## 入口（保留在项目根目录）

```text
run.py                  python run.py            → desktop.login_launcher.main
run_app.bat             双击                     → python run.py
report_generator.spec   build.bat                → PyInstaller 打包（入口 report_generator/main.py）
compress.bat            打 7z 包
```

`report_generator/main.py` 打包入口同样导入 `desktop.login_launcher`，
所以源码运行与 EXE 运行走同一条登录链路。

## 打包时的路径约定

- `desktop` 作为包被 PyInstaller 收集（spec 的 `hiddenimports` 已列）；
- `auth.db`、`user_mobile_1029.sql` 打包到 `_MEIPASS` 根目录；
- frozen 模式下 `login_launcher` 用 `sys._MEIPASS` 定位这两个文件，
  源码模式用 `desktop/` 目录。

## 运行

```powershell
python run.py                 # 系统 Python 3.8（含 paddleocr，扫描识别可用）
.\run_app.bat                 # 同上，双击入口
```
