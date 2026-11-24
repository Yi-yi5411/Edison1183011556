# -*- coding: utf-8 -*-
"""运行配置冒烟（P0）：TOML 子集解析、文件覆盖、环境变量优先级、路径解析。

运行：python test_config_smoke.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "webapp"))

import structural_config as sc  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


def test_parse():
    text = (
        "# 注释行\n"
        "[server]\n"
        "host = \"127.0.0.1\"\n"
        "port = 8765\n"
        "ratio = 0.5\n"
        "enabled = false\n"
        "tags = [\"a\", \"b\"]\n"
        "label = \"含 # 的字符串\"\n"
        "inline = 12  # 行尾注释\n"
    )
    data = sc.parse_toml(text)
    server = data.get("server") or {}
    check("解析字符串", server.get("host") == "127.0.0.1", server.get("host"))
    check("解析整数", server.get("port") == 8765, server.get("port"))
    check("解析浮点", server.get("ratio") == 0.5, server.get("ratio"))
    check("解析布尔", server.get("enabled") is False, server.get("enabled"))
    check("解析数组", server.get("tags") == ["a", "b"], server.get("tags"))
    check("引号里的 # 不当注释",
          server.get("label") == "含 # 的字符串", server.get("label"))
    check("行尾注释被忽略", server.get("inline") == 12, server.get("inline"))

    try:
        sc.parse_toml("[a]\nbad line")
        check("坏行报错", False, "未抛错")
    except ValueError as e:
        check("坏行报错", "无法解析" in str(e), str(e)[:40])


def test_file_and_env():
    tmp = tempfile.mkdtemp(prefix="cfg_")
    try:
        missing = os.path.join(tmp, "none.toml")
        data = sc.load(missing, force=True)
        check("缺文件用默认值",
              data["server"]["api_base"] == "http://127.0.0.1:8765/api",
              data["server"]["api_base"])

        path = os.path.join(tmp, "structural.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('[server]\nport = 9999\n[dsh]\ngui_url = "http://x:1"\n')
        data = sc.load(path, force=True)
        check("文件覆盖默认值", data["server"]["port"] == 9999,
              data["server"]["port"])
        check("未写字段保留默认",
              data["server"]["host"] == "127.0.0.1", data["server"]["host"])
        check("新增节生效", data["dsh"]["gui_url"] == "http://x:1",
              data["dsh"]["gui_url"])

        os.environ["STRUCTURAL_PORT"] = "8123"
        os.environ["STRUCTURAL_API_BASE"] = "http://127.0.0.1:8123/api/"
        try:
            data = sc.load(path, force=True)
            check("环境变量覆盖文件", data["server"]["port"] == 8123,
                  data["server"]["port"])
            check("api_base 去尾斜杠逻辑", sc.api_base() == "http://127.0.0.1:8123/api"
                  or sc.api_base().endswith("/api"), sc.api_base())
            check("server_address 返回元组", sc.server_address() == ("127.0.0.1", 8123),
                  sc.server_address())
        finally:
            os.environ.pop("STRUCTURAL_PORT", None)
            os.environ.pop("STRUCTURAL_API_BASE", None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_real_config():
    sc.reload()
    check("真实配置 api_base", sc.api_base() == "http://127.0.0.1:8765/api",
          sc.api_base())
    check("真实配置 host/port", sc.server_address() == ("127.0.0.1", 8765),
          sc.server_address())
    check("DSH GUI 地址非空", bool(sc.get("dsh", "gui_url")),
          sc.get("dsh", "gui_url"))
    check("项目根目录正确",
          os.path.isdir(os.path.join(sc.root(), "report_generator")), sc.root())
    check("data_path 指向项目内",
          sc.data_path("projects").startswith(sc.root()), sc.data_path("projects"))


def test_mcp_uses_config():
    import mcp_server
    check("MCP BASE_URL 来自配置",
          mcp_server.BASE_URL == sc.api_base().rstrip("/"),
          [mcp_server.BASE_URL, sc.api_base()])


def main():
    test_parse()
    test_file_and_env()
    test_real_config()
    test_mcp_uses_config()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
