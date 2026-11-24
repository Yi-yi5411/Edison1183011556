# -*- coding: utf-8 -*-
"""盈建科（YJK）结构计算集成。

- model.py    JSON 规格 → YJKAPI 建模脚本 / 读取脚本（纯函数，可测试）
- bridge.py   用盈建科自带 Python 3.10 执行脚本，收集 JSON 结果
- mcp_server.py  MCP stdio 工具：yjk_status / yjk_build_frame / yjk_read_ydb / yjk_run_script

主程序不导入 YJKAPI；它只存在于 YJK 安装目录的 Python 环境。
"""
from . import bridge, model  # noqa: F401

__all__ = ["bridge", "model"]
