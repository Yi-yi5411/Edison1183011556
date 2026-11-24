# -*- coding: utf-8 -*-
"""运行配置：config/structural.toml + 环境变量覆盖。

后端固定跑在 Python 3.8，标准库没有 tomllib，因此这里实现一个
TOML 子集解析器（[section] + key = value，值支持字符串/整数/浮点/布尔/数组），
足够本项目的扁平配置；出现复杂 TOML 时应升级解释器而不是扩展这里。

优先级：环境变量 > config/structural.toml > 内置默认值。
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(_ROOT, "config", "structural.toml")

DEFAULTS = {
    "app": {"version": "1.0.0"},
    "server": {"host": "127.0.0.1", "port": 8765,
               "api_base": "http://127.0.0.1:8765/api"},
    "dsh": {"gui_url": "http://127.0.0.1:3642",
            "mcp_server_name": "structural_inspection"},
    "paths": {"data_dir": "data",
              "exports_dir": "report_generator/exports",
              "templates_dir": "data/templates"},
    "cad": {"backend": "auto",
            "acad_progid": "AutoCAD.Application.23",
            "acad_exe": "D:\\Program Files\\Autodesk\\AutoCAD 2020\\acad.exe",
            "tsdp_dir": "D:\\Program Files\\TszCAD\\TSDP2024",
            "work_dir": "D:\\TSSDWORK",
            "text_height": 300,
            "axis_label_diameter": 800},
    "yjk": {"install_dir": "C:\\YJKS\\YJKS_8_0_0",
            "python": "C:\\YJKS\\YJKS_8_0_0\\Python310\\python.exe",
            "work_dir": "data/yjk",
            "timeout": 900},
}

ENV_MAP = {
    ("app", "version"): "STRUCTURAL_APP_VERSION",
    ("server", "host"): "STRUCTURAL_HOST",
    ("server", "port"): "STRUCTURAL_PORT",
    ("server", "api_base"): "STRUCTURAL_API_BASE",
    ("dsh", "gui_url"): "STRUCTURAL_DSH_GUI_URL",
    ("dsh", "mcp_server_name"): "STRUCTURAL_MCP_SERVER_NAME",
    ("paths", "data_dir"): "STRUCTURAL_DATA_DIR",
    ("paths", "exports_dir"): "STRUCTURAL_EXPORTS_DIR",
    ("paths", "templates_dir"): "STRUCTURAL_TEMPLATES_DIR",
    ("cad", "backend"): "STRUCTURAL_CAD_BACKEND",
    ("cad", "acad_progid"): "STRUCTURAL_ACAD_PROGID",
    ("cad", "acad_exe"): "STRUCTURAL_ACAD_EXE",
    ("cad", "tsdp_dir"): "STRUCTURAL_TSDP_DIR",
    ("cad", "work_dir"): "STRUCTURAL_CAD_WORK_DIR",
    ("yjk", "install_dir"): "STRUCTURAL_YJK_DIR",
    ("yjk", "python"): "STRUCTURAL_YJK_PYTHON",
    ("yjk", "work_dir"): "STRUCTURAL_YJK_WORK_DIR",
}

_cache = {}


def _parse_value(text):
    text = str(text).strip()
    if not text:
        return ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(part) for part in inner.split(",") if part.strip()]
    # 去掉行尾注释（字符串已在上方处理）
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def parse_toml(text):
    """解析 TOML 子集，返回 {section: {key: value}}。"""
    data = {}
    section = data
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line.strip("[]").strip()
            if not name:
                raise ValueError("配置节名为空：%s" % raw)
            section = data.setdefault(name, {})
            continue
        if "=" not in line:
            raise ValueError("无法解析配置行：%s" % raw)
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("配置键为空：%s" % raw)
        section[key] = _parse_value(value)
    return data


def _coerce(default, value):
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value


def load(path=None, force=False):
    """读取配置（带缓存）；path 缺省用 config/structural.toml。"""
    path = path or _DEFAULT_PATH
    if not force and path in _cache:
        return _cache[path]
    merged = {section: dict(values) for section, values in DEFAULTS.items()}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            file_data = parse_toml(handle.read())
        for section, values in file_data.items():
            merged.setdefault(section, {}).update(values)
    for (section, key), env_name in ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        default = DEFAULTS.get(section, {}).get(key)
        merged.setdefault(section, {})[key] = _coerce(default, raw)
    _cache[path] = merged
    return merged


def get(section, key, default=None):
    return load().get(section, {}).get(key, default)


def reload():
    """清空缓存（测试或热更新用）。"""
    _cache.clear()
    return load(force=True)


def root():
    return _ROOT


def api_base():
    return str(get("server", "api_base",
                   "http://127.0.0.1:8765/api")).rstrip("/")


def server_address():
    return (str(get("server", "host", "127.0.0.1")),
            int(get("server", "port", 8765) or 8765))


def data_path(*parts):
    """data_dir 下的绝对路径。"""
    base = get("paths", "data_dir", "data")
    if not os.path.isabs(base):
        base = os.path.join(_ROOT, base)
    return os.path.join(base, *parts)


def path_value(section, key, default):
    value = str(get(section, key, default) or default)
    return value if os.path.isabs(value) else os.path.join(_ROOT, value)
