# -*- coding: utf-8 -*-
"""文档扫描识别 - 运行依赖安装脚本。

安装第1/3步可选依赖：
    python install_scan_deps.py          # 安装全部(PaddleOCR + PyMuPDF + 通义SDK)
    python install_scan_deps.py --ocr    # 仅OCR(PaddleOCR + PyMuPDF)
    python install_scan_deps.py --llm    # 仅通义千问SDK
"""
import subprocess
import sys
import os

# 按依赖分层安装：每个包单独安装，避免 pip 解析多个 sdist 的 pyproject.toml
# 时因校验器/解析器兼容问题(尤其旧版 pip) 一起失败。
# 先装无依赖冲突的小包，再装重包。
DEPS_OCR_ORDER = ["PyMuPDF", "paddlepaddle", "paddleocr"]
DEPS_LLM = []          # 大模型通过 OpenAI 兼容 HTTP 直接调用，无需额外SDK
DEPS_COMMON = ["requests"]  # vLLM/服务器上传走 HTTP 调用

# 国内速度更稳的镜像源（默认阿里云）。可用参数 --mirror aliyun|tsinghua|off
MIRRORS = {
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "default": "https://pypi.org/simple",
}
_TIMEOUT = 300
_RETRIES = 10


def run_pip(args, label):
    print(f"[安装] {label}: python -m pip {' '.join(args)}")
    subprocess.check_call([sys.executable, "-m", "pip", *args])


def base_pip_args(mirror):
    args = ["install"]
    if mirror:
        args += ["--index-url", mirror]
    args += ["--timeout", str(_TIMEOUT), "--retries", str(_RETRIES)]
    return args


def ensure_pip():
    """先把 pip 升级到较新版本，规避旧版 pip 解析 pyproject.toml 的已知 bug。"""
    try:
        import pip
        if int(pip.__version__.split(".")[0]) < 22:
            print("[准备] 当前 pip 较旧，先升级 pip ...")
            run_pip(["install", "--upgrade", "pip"], "升级 pip")
    except Exception:
        run_pip(["install", "--upgrade", "pip"], "升级 pip")


def main():
    args = set(sys.argv[1:])
    want_ocr = not args or "--ocr" in args or "--all" in args
    want_llm = not args or "--llm" in args or "--all" in args
    skip_pip = "--no-upgrade-pip" in args

    # paddlepaddle 官方 wheel 仅覆盖 3.8~3.13（2.6.x: 3.8~3.12；3.x: 至 3.13）。
    # Python 3.14+ 目前无任何可用 wheel，换镜像也没用，直接给出明确指引。
    if want_ocr and not (3, 8) <= sys.version_info[:2] <= (3, 13):
        print(
            f"[错误] 当前 Python {sys.version_info.major}.{sys.version_info.minor} "
            "无法安装 paddlepaddle（官方未提供该版本的 wheel）。\n"
            "请改用系统 Python 3.8 运行本脚本与应用：\n"
            '  "C:\\Program Files\\python\\python.exe" '
            "report_generator\\scan_recognition\\install_scan_deps.py\n"
            '  "C:\\Program Files\\python\\python.exe" run.py'
        )
        sys.exit(1)

    # 解析镜像参数
    mirror_key = "aliyun"
    for a in args:
        if a.startswith("--mirror="):
            mirror_key = a.split("=", 1)[1]
    mirror = MIRRORS.get(mirror_key) if mirror_key != "off" else None
    if mirror:
        print(f"[准备] 使用镜像源: {mirror}")

    if not skip_pip:
        ensure_pip()

    if want_ocr:
        for pkg in DEPS_OCR_ORDER:
            try:
                run_pip(base_pip_args(mirror) + [pkg], pkg)
            except subprocess.CalledProcessError as e:
                print(f"\n[失败] 安装 {pkg} 出错。可手动重试（增大超时/换镜像）：\n"
                      f"  {sys.executable} -m pip install {pkg} --timeout 300 --retries 10"
                      f" --index-url {mirror}")
                sys.exit(e.returncode)
    if want_llm:
        for pkg in DEPS_COMMON + DEPS_LLM:
            run_pip(base_pip_args(mirror) + [pkg], pkg)
    print(
        "\n完成。请随后在 报告生成器/文档扫描识别 对话框中使用。\n"
        "项目已带 data/models/paddleocr 模型；若目录缺失，PaddleOCR 首次识别会自动下载，需联网。\n"
        "通义千问请在配置文件 report_generator/assets/scan_recognition_config.json 填写 api_key。"
    )


if __name__ == "__main__":
    main()