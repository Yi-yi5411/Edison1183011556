# -*- coding: utf-8 -*-
"""扫描识别流水线异常定义。"""


class RecognitionError(Exception):
    """识别流水线通用异常。"""


class DependencyMissingError(RecognitionError):
    """缺少可选运行依赖（如 paddleocr / dashscope / fitz）。带安装提示。"""

    def __init__(self, message, install_hint=""):
        self.install_hint = install_hint
        super().__init__(message + (f"\n安装提示：{install_hint}" if install_hint else ""))


class ConfiguredApiKeyError(RecognitionError):
    """大模型或服务器缺少 API Key 配置时抛出，提示用户在配置文件中填写。"""

    def __init__(self, section, key, config_path=None):
        self.section = section
        self.key = key
        self.config_path = config_path
        super().__init__(
            f"{section}.{key} 未配置。请在配置文件 {config_path or '<默认配置>'} 中填写，"
            f"或设置环境变量 SCAN_LLM_API_KEY / SCAN_SERVER_API_KEY。"
        )