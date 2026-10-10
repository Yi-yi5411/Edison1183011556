# -*- coding: utf-8 -*-
"""文档扫描识别 - 配置模块。

集中管理第1~8步流水线的外部配置：OCR / 大模型(通义千问) / 电子数据存储 /
服务器上传 / 字段匹配。提供配置文件 JSON 覆盖 + 内置默认值的两层结构，
保证无配置文件也能运行。

配置文件默认路径：项目根/report_generator/assets/scan_recognition_config.json
"""
import json
import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_REPORT_GEN = _PKG.parent
_ROOT = _REPORT_GEN.parent  # 项目根目录（structural_inspection）

_DEFAULT_CONFIG_PATH = _REPORT_GEN / "assets" / "scan_recognition_config.json"


def project_root() -> Path:
    return _ROOT


def default_config_path() -> Path:
    return _DEFAULT_CONFIG_PATH


_DEFAULTS = {
    # ── 第1步：OCR 识别 ──
    "ocr": {
        "provider": "paddle",         # paddle | mock
        "lang": "ch",
        "model": "ch_PP-OCRv4",       # PaddleOCR 检测+识别模型
        "use_gpu": True,              # 无GPU会自行回退到CPU
        "pdf_dpi": 300,               # PDF 转图片的分辨率
        "low_conf_threshold": 0.85,   # OCR 置信度低于该值的单元格提示人工复核
        "device": "auto",             # 原文：文件来源标注（扫描/拍照）
    },
    # ── 第3步：大模型结构化（Qwen，OpenAI 兼容接口：vLLM 本地 / Ollama 本地 / DashScope 云端）──
    "llm": {
        # vllm | dashscope | openai | ollama | mock
        "provider": "vllm",
        "base_url": "http://172.16.51.69:8000/v1",
        "api_key": "",                # 本地部署通常无需鉴权；DashScope 需填 Key
        "model": "Qwen3.6-35B-A3B",
        "temperature": 0.0,
        "timeout": 120,
        "max_tokens": 4096,
        # 手写记录表视觉识别：auto=自动探测本地视觉模型并优先看图转写；
        # off=关闭（始终走 OCR 文本）；on=强制要求视觉模型；
        # vision_model 留空时在 ollama 本地自动查找（qwen2.5vl 等）
        "use_vision": "auto",
        "vision_model": "",
        # 视觉转写 JSON 解析失败（思考模型带图偶发思考文本占满输出）时的
        # 自动重试次数；0=不重试，重试会追加"直接输出 JSON"强指令
        "vision_retries": 1,
        # Ollama 原生服务专用地址（视觉转写用；provider=ollama 时结构化也走它）。
        # 留空=沿用 base_url 推导。示例：http://172.16.42.7:11434
        # （exe 部署机远程调用识别服务器上的 Ollama）
        "ollama_base_url": "",
        # Qwen 推理模型默认开启思考(reasoning)。disable_thinking 按 provider 分叉：
        # vLLM/DashScope 走 chat_template_kwargs；Ollama 走 system 追加 /no_think，
        # 解析时同时剥离 <think> 标签兜底。
        "disable_thinking": True,
        # AI 判定检测项目时送给大模型的 OCR 文本最大字符数
        "classify_max_chars": 2000,
    },
    # ── 第2步：识别文件存储目录 + 第4步：电子数据数据库 ──
    "storage": {
        # 识别到的扫描原文件/中间文件存储目录（相对项目根或绝对路径）
        "document_dir": "original_record/scanned",
        # 电子数据SQLite数据库路径（相对项目根或绝对路径），空则用默认 data/scan_recognition.db
        "database_path": "data/scan_recognition.db",
        "documents_table": "scan_documents",
        "records_table": "scan_records",
    },
    # ── 第5步：结构化/规范化处理 ──
    "normalizer": {
        "trim": True,                 # 去首尾空白
        "collapse_ws": True,          # 合并连续空白
        # 间距类字段合理量程下限（mm）：手写"未测斜杠/"常被视觉模型误识为数字，
        # 小于该下限的值按未测清空
        "min_plausible_mm": 10,
        # 合理性量程校验（超出仅标记复核，不改写）：字段关键词 -> [下限, 上限]。
        # 留空使用内置默认（回弹值10~90、碳化深度0~60、强度1~200、直径30~300、
        # 荷载0~10000、实测值/设计值/间距10~10000）
        "plausible_ranges": {},
        "remove_units_in_fields": ["强度推定值", "芯样直径", "截面积", "测试荷载", "测试强度",
                                    "推定值", "批评定值", "碳化深度", "平均回弹值"],
    },
    # ── AI 智能体自修复（LangGraph：可疑值带图重问视觉模型修正） ──
    "agent": {
        "enabled": True,          # False=关闭自修复（识别照常，仅提示复核）
        "max_repair_rounds": 2,   # 最大修复轮数（每轮重问一次视觉模型）
    },
    # ── 报告生成 LLM 代理（Ollama 工具调用，逐步编排 utils/report_tools）──
    "report_agent": {
        "enabled": True,          # False=报告生成不接入 LLM（始终直接生成）
        "base_url": "",           # Ollama 原生地址；留空=沿用 llm.ollama_base_url / base_url 推导
        "model": "",              # 工具调用模型；留空=自动探测 capabilities 含 tools 的模型（qwen 优先）
        "max_rounds": 24,         # 工具循环最大轮数（防失控）
        "timeout": 180,           # 单次 /api/chat 超时（秒）
        "num_predict": 1024,      # 单次输出 token 上限
        "temperature": 0.2,       # 工具编排用低随机性
    },
    # ── 识别记忆（长期校正经验 + 短期会话记忆 + 上下文压缩） ──
    "memory": {
        "enabled": True,          # False=关闭记忆学习与召回
        "max_hints": 8,           # 注入提示词的记忆条数上限（其余折叠为摘要）
        "session_cache": True,    # 短期会话记忆（同图重跑立即生效上轮留痕）
    },
    # ── 第6步：字段匹配到检测项目列 ──
    "matcher": {
        # 由系统自动计算的列不直接回填，识别结果遇到这些列时跳过(交由模块自动计算)
        "computed_columns": ["平均回弹值", "截面积", "测试强度", "推定值", "批评定值",
                             "芯样强度均值", "测区1", "测区2", "测区3", "测区4", "测区5",
                             "测区6", "测区7", "测区8", "测区9", "测区10"],
        "fuzzy_match": True,          # 允许表头归一化模糊匹配
    },
    # ── 第8步：上传到服务器（预留可配置接口）──
    "server": {
        "enabled": False,
        "base_url": "",               # 如 https://your-server.com/api
        "api_key": "",                # 鉴权 token
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "upload_endpoint": "/scan_records/upload",
        # 字段映射：服务器字段名 -> 本地字段名（留空则按本地字段名原样上传）
        "field_mapping": {},
        "timeout": 30,
        "dry_run": False,             # 仅打印将要上传的载荷，不发真实请求(联调用)
    },
}

# 运行时允许被环境变量覆盖的键（便于部署不落盘密钥）
_ENV_OVERRIDES = {
    "llm.api_key": "SCAN_LLM_API_KEY",
    "server.api_key": "SCAN_SERVER_API_KEY",
    "server.base_url": "SCAN_SERVER_URL",
}


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_path(p):
    """把配置中的相对路径解析为绝对路径（相对项目根），已是绝对路径则直接用。"""
    if not p:
        return None
    path = Path(os.path.expandvars(os.path.expanduser(str(p))))
    return path if path.is_absolute() else (_ROOT / path)


class Config:
    """扫描识别配置对象。支持从 JSON 文件加载 + 环境变量覆盖。"""

    def __init__(self, data=None):
        self.data = _deep_merge(_DEFAULTS, data or {})

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else default_config_path()
        data = {}
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        cfg = cls(data)
        cfg._apply_env_overrides()
        return cfg

    def _apply_env_overrides(self):
        for key, env in _ENV_OVERRIDES.items():
            val = os.environ.get(env)
            if val == "":
                continue
            if val is not None:
                sec, k = key.split(".", 1)
                if sec in self.data and k in self.data[sec]:
                    if val.strip() == "":
                        continue
                    self.data[sec][k] = val.strip()

    # ── section 访问器 ──
    @property
    def ocr(self):
        return self.data.get("ocr", {})

    @property
    def llm(self):
        return self.data.get("llm", {})

    @property
    def storage(self):
        return self.data.get("storage", {})

    @property
    def normalizer(self):
        return self.data.get("normalizer", {})

    @property
    def agent(self):
        return self.data.get("agent", {})

    @property
    def memory(self):
        return self.data.get("memory", {})

    @property
    def matcher(self):
        return self.data.get("matcher", {})

    @property
    def server(self):
        return self.data.get("server", {})

    # ── 解析后的路径 ──
    @property
    def document_dir(self):
        p = _resolve_path(self.storage.get("document_dir", "original_record/scanned"))
        if p is None:
            p = _ROOT / "original_record" / "scanned"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def database_path(self):
        p = _resolve_path(self.storage.get("database_path", "data/scan_recognition.db"))
        if p is None:
            p = _ROOT / "data" / "scan_recognition.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def save_default(self, path=None):
        """把内置默认配置写入配置文件（供用户编辑 api_key 等）。"""
        path = Path(path) if path else default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_DEFAULTS, f, ensure_ascii=False, indent=2)
        return path

    def save(self, path=None):
        """把当前生效配置（默认值+已加载覆盖项）写回配置文件。

        界面上切换识别模型等运行时修改通过该方法持久化，下次启动仍生效。
        """
        path = Path(path) if path else default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        return path