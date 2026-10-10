# -*- coding: utf-8 -*-
"""项目静态资源统一解析入口。

项目所有静态资源（图标、模板、Excel、样式表等）都集中存放于
``<项目根目录>/report_generator/assets/`` 下。任何模块需要读取资源
都必须通过本模块导出的函数定位路径，禁止在业务代码中手写
``Path(__file__).resolve().parents[N]`` 之类的脆弱路径。

典型用法::

    from report_generator.framework.resources import get_asset
    icon_path = get_asset("logo.jpg")                    # Path 对象
    icon_path = get_asset("images/icon.png", must_exist=True)

也可以直接取常量::

    from report_generator.framework.resources import PROJECT_ROOT, ASSETS_DIR
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Union


__all__ = ["PROJECT_ROOT", "ASSETS_DIR", "get_asset", "resolve_path"]


# ── 项目根目录定位（稳健处理源码运行 / PyInstaller exe 运行两种场景）────
def _locate_project_root() -> Path:
    """定位 structural_inspection 项目根目录。

    策略：
    1) PyInstaller 打包运行：优先使用 _MEIPASS（sys._MEIPASS 指向解压
       临时目录），再回退到 sys.executable 所在目录。
    2) 源码运行：以本文件所在位置为基准，
       report_generator/framework/resources.py → parents[2] = PROJECT_ROOT。
    """
    frozen = getattr(sys, "frozen", False)
    if frozen:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        # 兼容 Nuitka / 其他打包方式
        return Path(sys.executable).resolve().parent
    # 源码模式：resources.py 在 report_generator/framework/ 下，
    # 向上两级即 PROJECT_ROOT（structural_inspection/）。
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT: Path = _locate_project_root()
"""项目根目录（structural_inspection/），代码中所有路径都应从此目录出发。"""

ASSETS_DIR: Path = PROJECT_ROOT / "report_generator" / "assets"
"""静态资源集中目录，所有图标/模板/样式表都应存放在此或其子目录下。"""

# 确保运行时资源目录存在（源码运行时若缺失会提示）
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def get_asset(
    *rel_parts: Union[str, "os.PathLike[str]"],
    must_exist: bool = False,
) -> Path:
    """获取静态资源文件的绝对路径。

    :param rel_parts: 相对于 ``ASSETS_DIR`` 的路径片段（可多级）。
        示例：``get_asset("logo.jpg")``、``get_asset("images", "icon.ico")``。
    :param must_exist: 为 True 时若文件不存在则抛出 FileNotFoundError，
        否则直接返回 Path 对象，由调用方自行判断。
    :return: 资源的绝对 ``Path`` 对象。
    """
    path = ASSETS_DIR.joinpath(*rel_parts)
    if must_exist and not path.exists():
        raise FileNotFoundError(
            f"静态资源不存在：{path}。请把资源文件放到 {ASSETS_DIR} 下。"
        )
    return path


def resolve_path(
    *rel_parts: Union[str, "os.PathLike[str]"],
    must_exist: bool = False,
) -> Path:
    """获取相对于 ``PROJECT_ROOT`` 的任意路径（除静态资源外的其他目录定位）。

    建议：静态资源一律使用 :func:`get_asset`；只有确实需要定位项目根下
    的非资源文件（如 ``目录配置.xlsx``、``data/`` 输出目录等）时才使用本函数。
    """
    path = PROJECT_ROOT.joinpath(*rel_parts)
    if must_exist and not path.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    return path
