# -*- coding: utf-8 -*-
"""文档扫描识别流水线（report_generator.scan_recognition）。

对应需求文档《图片文档扫描识别文件》的 8 步流程：

1. 扫描仪PDF识别、相片拍照识别          -> ocr 模块（PaddleOCR 本地 + PDF 转图片）
2. 将识别到的文件存储到某个目录中         -> pipeline 把原文件复制到 config.document_dir
3. 识别文件后采用大模型进行识别、自动识别格式 -> llm 模块（通义千问 Qwen 结构化）
4. 电子版数据存储到数据库中               -> storage 模块（SQLite）
5. 将数据库的数据进行结构化处理           -> normalizer 模块
6. 结构化数据匹配到 report_generator 的对应检测项目 -> matcher 模块（数据驱动全模块）
7. 原始记录模板识别，将数据填写到模板       -> pipeline 输出对齐行 + matcher 回填当前表
8. 将匹配到的检测项目数据上传到服务器         -> uploader 模块（可配置接口）

对外主要入口：
    from report_generator.scan_recognition.pipeline import ScanRecognitionPipeline
    from report_generator.scan_recognition.gui import ScanRecognitionDialog
"""

from report_generator.scan_recognition.config import Config
from report_generator.scan_recognition.errors import (
    RecognitionError,
    DependencyMissingError,
    ConfiguredApiKeyError,
)

__all__ = [
    "Config",
    "RecognitionError",
    "DependencyMissingError",
    "ConfiguredApiKeyError",
]