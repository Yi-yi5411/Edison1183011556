# -*- mode: python ; coding: utf-8 -*-
"""
Structural Inspection Report Generator - PyInstaller Spec（体积优化版）

在"功能完整版"基础上做体积瘦身，功能不删减：

1. 排除从未被代码使用的重型库：pandas / numpy（word_to_excel.py 的
   死导入已移除）、matplotlib（被 pandas 连带打入）、fontTools、
   tksheet / ttkbootstrap（requirements 遗留，源码未 import）。
2. 过滤 PyQt5 中 Widgets 程序用不到的组件：
   - opengl32sw.dll（软件 OpenGL 后备，约 20MB）
   - QML/Quick 技术栈、DBus、Network、WebSockets、Svg 相关 DLL
   - 非 zh_cn 的 Qt 翻译文件
3. 过滤 PIL 的 AVIF 插件（_avif.pyd，约 7.5MB）。
4. UPX 压缩非 Qt 的二进制（Qt5*.dll 不做 UPX，避免兼容性风险）。
5. modules 插件包仍以真实文件放入 _internal/report_generator/modules/，
   运行时 login_launcher.py 把 _internal/report_generator 加入 sys.path，
   plugin_manager 通过 pkgutil 扫描磁盘动态加载，机制不变。
6. auth.db / user_mobile_1029.sql 原样打包到 _internal 根目录。
"""

import os
from pathlib import Path

PROJECT_DIR = Path(SPECPATH).resolve()
ENTRY = PROJECT_DIR / "report_generator" / "main.py"


def _tree_datas(src_dir, dest_prefix):
    """把整个目录树原样收集为 datas 元组（跳过 __pycache__ 和 .pyc）。"""
    out = []
    src = Path(src_dir)
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        parent = os.path.dirname(rel)
        out.append((str(p), os.path.join(dest_prefix, parent) if parent else dest_prefix))
    return out


def _modules_excludes():
    """枚举 modules 包下全部模块名，整体从 PYZ 排除（强制运行时从磁盘加载）。"""
    root = PROJECT_DIR / "report_generator" / "modules"
    names = ["modules"]
    for p in sorted(root.rglob("*.py")):
        parts = list(p.relative_to(root.parent).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names.append(".".join(parts))
    return names


# ---------- 体积过滤规则 ----------
# 注意：比较时统一转小写（TOC 中文件名大小写不保证）

# Qt5/bin 中 Widgets 程序不需要的 DLL（QML/Quick 技术栈、网络、DBus、SVG）
_QT_DROP_DLLS = {
    "opengl32sw.dll",
    "qt5quick.dll", "qt5qml.dll", "qt5qmlmodels.dll", "qt5qmlworkerscript.dll",
    "qt5quickwidgets.dll", "qt5quickparticles.dll", "qt5quickshapes.dll",
    "qt5quicktest.dll", "qt5quickcontrols2.dll", "qt5quicktemplates2.dll",
    "qt5dbus.dll", "qt5network.dll", "qt5websockets.dll", "qt5svg.dll",
    "qt5positioning.dll", "qt5location.dll", "qt5sensors.dll",
    "qt5serialport.dll", "qt5bluetooth.dll", "qt5nfc.dll",
    "qt5multimedia.dll", "qt5multimediawidgets.dll",
    "qt5test.dll", "qt5sql.dll", "qt5xml.dll", "qt5help.dll",
    "qt5designer.dll", "qt5designercomponents.dll", "qt5uitools.dll",
    "qt5texttospeech.dll", "qt5webchannel.dll", "qt5remoteobjects.dll",
    "qt5gamepad.dll", "qt53danimation.dll", "qt53dcore.dll",
    "qt53dextras.dll", "qt53dinput.dll", "qt53dlogic.dll",
    "qt53dquick.dll", "qt53drender.dll", "qt5charts.dll",
    "qt5datavisualization.dll", "qt5virtualkeyboard.dll", "qt5pdf.dll",
}

# PyQt5 目录下 Widgets 程序用不到的 .pyd（配套上面被删的 DLL）
_QT_DROP_PYD = {
    "qtquick.pyd", "qtqml.pyd", "qtnetwork.pyd", "qtdbus.pyd",
    "qtsvg.pyd", "qtwebsockets.pyd", "qtpositioning.pyd",
    "qtlocation.pyd", "qtsensors.pyd", "qtserialport.pyd",
    "qtbluetooth.pyd", "qtnfc.pyd", "qtmultimedia.pyd",
    "qtmultimediawidgets.pyd", "qttest.pyd", "qtsql.pyd", "qtxml.pyd",
    "qthelp.pyd", "qtdesigner.pyd", "qtuitools.pyd", "qttexttospeech.pyd",
    "qtwebchannel.pyd", "qtremoteobjects.pyd", "qtgamepad.pyd",
    "qtcharts.pyd", "qtdatavisualization.pyd", "qtpdf.pyd",
}

# 图片格式插件：只保留 gif/jpeg/ico（源码仅用 png/jpg/ico/bmp）
_ICONFMT_DROP = {
    "qicns.dll", "qmng.dll", "qsvg.dll", "qtga.dll", "qtiff.dll",
    "qwbmp.dll", "qwebp.dll", "_qpdf.dll", "qtpdf.dll",
}


def _keep_entry(dest_name):
    """PyInstaller TOC 过滤：返回 False 表示从产物中剔除。"""
    name = dest_name.replace("\\", "/")
    base = name.rsplit("/", 1)[-1].lower()

    if "/qt5/bin/" in name.lower() and base in _QT_DROP_DLLS:
        return False
    if "/pyqt5/" in name.lower() and base in _QT_DROP_PYD:
        return False
    # 图片格式插件（platforms/styles 插件不动）
    if "/imageformats/" in name.lower() and base in _ICONFMT_DROP:
        return False
    # SVG 图标引擎依赖 Qt5Svg，一并剔除
    if "/iconengines/" in name.lower():
        return False
    # PIL AVIF 插件
    if base.startswith("_avif."):
        return False
    # Qt 翻译文件：只保留简体中文
    if "/translations/" in name.lower() and base.endswith(".qm") and "zh_cn" not in base:
        return False
    return True


datas = _tree_datas(PROJECT_DIR / "report_generator", "report_generator")
# 报告章节模板目录（utils/word_report.py 经 resolve_path("report_template") 访问，
# frozen 模式下 PROJECT_ROOT = _MEIPASS，必须整体打包到 _internal/report_template/）
datas += _tree_datas(PROJECT_DIR / "report_template", "report_template")
_DESKTOP = PROJECT_DIR / "desktop"
datas += [
    # 登录用户数据库（含全部已注册用户）+ 种子用户 SQL
    # desktop/login_launcher.py 在 frozen 模式下从 _MEIPASS 根目录读取
    (str(_DESKTOP / "auth.db"), "."),
    (str(_DESKTOP / "user_mobile_1029.sql"), "."),
]
datas = [d for d in datas if _keep_entry(d[1] if len(d) == 3 else d[0])]

a = Analysis(
    [str(ENTRY)],
    pathex=[
        str(PROJECT_DIR),
        str(PROJECT_DIR / "report_generator"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # —— modules/ 下的插件以磁盘 .py 形式运行，其依赖必须打进 PYZ ——
        "docx",               # concrete_strength/word_to_excel.py（Word 报告导入）
        "PIL", "PIL.Image",   # openpyxl 插入图片功能（venv 已安装）
        "requests",           # scan_recognition/llm.py、uploader.py（Ollama/上传）
        # —— scan_recognition/agent/（LangGraph 自修复智能体，懒导入需显式收集）——
        "langgraph", "langgraph.graph", "langgraph.graph.state",
        "langgraph.constants", "langgraph.pregel", "langgraph.types",
        "langchain_core", "langchain_core.messages", "langchain_core.runnables",
        "langchain_core.language_models",
        "langchain_core.language_models.chat_models",
        "langchain_core.prompt_values", "langchain_core.output_parsers",
        "langchain_ollama", "langchain_ollama.chat_models",
        "ollama", "ollama._client",
      # —— 桌面端登录/主页（report_generator/main.py 导入 desktop 包）——
      "desktop", "desktop.login_launcher", "desktop.login",
      "desktop.auth_db", "desktop.home_menu",
    ],
    excludes=[
        # 体积优化：源码从未使用的重型依赖（pandas 死导入已删除）
        "pandas", "numpy", "matplotlib", "mpl_toolkits", "fontTools",
        "tksheet", "ttkbootstrap", "PIL._avif",
    ] + _modules_excludes(),
)

# 过滤二进制（Qt 无用 DLL、AVIF 插件、非中文翻译等）
a.binaries = [b for b in a.binaries if _keep_entry(b[0])]
a.datas = [d for d in a.datas if _keep_entry(d[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="工程检测harness",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,                    # Windows 无 strip.exe
    upx=True,                       # UPX 压缩（配合 upx_exclude 保护 Qt DLL）
    console=False,                  # GUI 程序：无控制台黑框
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # EXE 文件图标（资源管理器/任务栏显示，由 assets/logo.jpg 生成）
    icon=str(_DESKTOP / "app.ico") if (_DESKTOP / "app.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    # 不做 UPX：Qt5 运行库与 MS 运行库（压缩后有加载失败风险），
    # 其余大文件（python dll、mupdf、pyd、ssl 等）正常压缩
    upx_exclude=[
        "Qt5*.dll", "Qt6*.dll", "qwindows*.dll", "qminimal*.dll",
        "qoffscreen*.dll", "MSVCP*.dll", "VCRUNTIME*.dll", "ucrtbase.dll",
    ],
    name="工程检测harness",
)
