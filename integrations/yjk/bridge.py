# -*- coding: utf-8 -*-
"""YJK 执行桥：所有 YJKAPI 调用都通过盈建科自带 Python 3.10 以子进程执行。

主程序（Python 3.8）只负责生成脚本、收集 JSON 结果；不 import YJKAPI
（它只存在于 YJK 安装目录的 Python 环境中）。

配置：config/structural.toml 的 [yjk] 段（python / install_dir / work_dir / timeout）。
"""
import json
import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if os.path.join(_ROOT, "webapp") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "webapp"))

try:
    from structural_config import get as _get
except ImportError:  # pragma: no cover
    def _get(section, key, default=None):
        return default

from . import model as yjk_model  # noqa: E402

DEFAULT_PYTHON = r"C:\YJKS\YJKS_8_0_0\Python310\python.exe"


class YjkUnavailable(Exception):
    """盈建科 Python / YJKAPI 不可用。"""


def paths():
    work_dir = str(_get("yjk", "work_dir", "data/yjk") or "data/yjk")
    if not os.path.isabs(work_dir):
        work_dir = os.path.join(_ROOT, work_dir)
    return {
        "python": str(_get("yjk", "python", DEFAULT_PYTHON) or DEFAULT_PYTHON),
        "install_dir": str(_get("yjk", "install_dir", "") or ""),
        "work_dir": work_dir,
        "timeout": int(_get("yjk", "timeout", 900) or 900),
    }


def status():
    """探测盈建科环境：解释器、安装目录、YJKAPI 是否可导入。"""
    cfg = paths()
    python = cfg["python"]
    info = {
        "python": python,
        "python_exists": os.path.isfile(python),
        "install_dir": cfg["install_dir"],
        "install_exists": bool(cfg["install_dir"]
                               and os.path.isdir(cfg["install_dir"])),
        "work_dir": cfg["work_dir"],
        "available": False,
        "yjk_api": False,
        "version": "",
        "reason": "",
    }
    if not info["python_exists"]:
        info["reason"] = "未找到盈建科 Python 解释器：%s" % python
        return info
    try:
        proc = subprocess.run(
            [python, "-c",
             "import YJKAPI,json;"
             "print(json.dumps({'ok':True,'version':getattr(YJKAPI,'__version__','')}))"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
    except Exception as exc:  # noqa: BLE001
        info["reason"] = "调用盈建科 Python 失败：%s" % exc
        return info
    if proc.returncode != 0:
        info["reason"] = "无法导入 YJKAPI：%s" % (proc.stderr or "")[-300:]
        return info
    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        payload = {"ok": True}
    info["available"] = True
    info["yjk_api"] = True
    info["version"] = str(payload.get("version") or "")
    return info


def run_script(source, workdir=None, timeout=None, name="yjk_run", args=None):
    """把源码写入工作目录并用盈建科 Python 执行，返回 stdout/stderr/JSON。"""
    cfg = paths()
    python = cfg["python"]
    if not os.path.isfile(python):
        raise YjkUnavailable("未找到盈建科 Python 解释器：%s" % python)
    workdir = os.path.abspath(workdir or cfg["work_dir"])
    os.makedirs(workdir, exist_ok=True)
    script_path = os.path.join(
        workdir, "_%s_%s.py" % (name, time.strftime("%Y%m%d_%H%M%S")))
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(source)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    started = time.time()
    proc = subprocess.run(
        [python, script_path] + [str(a) for a in (args or [])],
        cwd=workdir, env=env,
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout or cfg["timeout"])
    duration = round(time.time() - started, 2)
    data = None
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            break
        except ValueError:
            continue
    return {
        "ok": proc.returncode == 0 and (data or {}).get("ok", True) is not False,
        "returncode": proc.returncode,
        "duration_s": duration,
        "script": script_path,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
        "data": data,
        "workdir": workdir,
    }


def build_frame(spec, output_dir=None, timeout=None):
    """按 JSON 规格生成框架模型并输出 .ydb。"""
    cfg = paths()
    output_dir = os.path.abspath(output_dir or os.path.join(
        cfg["work_dir"], "models"))
    script = yjk_model.frame_script(spec, output_dir=output_dir)
    result = run_script(script, workdir=output_dir, timeout=timeout,
                        name="frame")
    result["spec"] = yjk_model.normalize_spec(spec)
    result["output_dir"] = output_dir
    return result


def read_ydb(path, timeout=None):
    """读取 .ydb 的楼层/节点/截面摘要。"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError("ydb 文件不存在：%s" % path)
    script = yjk_model.read_ydb_script()
    return run_script(script, workdir=os.path.dirname(path),
                      timeout=timeout, name="read_ydb", args=[path])
