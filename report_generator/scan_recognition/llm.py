# -*- coding: utf-8 -*-
"""第3步：用大模型把 OCR 全文结构化（通义千问 Qwen）。

调用 OpenAI 兼容接口（chat/completions），同时支持：
- DashScope 云端（api.openai.com 风格）
- 本地 vLLM 部署（http://host:8000/v1）
- 本地 Ollama 部署（http://localhost:11434/v1，provider=ollama）

让大模型根据目标检测项目的列名 schema，把 OCR 识别到的原始记录文字
解析为一个结构化 JSON：{"records": [ {字段名: 值, ...}, ... ]}；
并提供 ``classify_project``：根据 OCR 文本从候选列表中 AI 判定检测项目。

提供 ``MockLLMExtractor`` 可在无 Key / 离线时跑通链路。
"""
import base64
import json
import re

import requests

from report_generator.scan_recognition.errors import (
    ConfiguredApiKeyError,
    RecognitionError,
)
from report_generator.scan_recognition.config import Config

_SYSTEM_PROMPT = (
    "你是检测行业的数据录入助手，负责把原始检测记录如实转写为结构化 JSON。"
    "输入的原始记录是表格结构文本：同一行的单元格以制表符（\\t）分隔，"
    "单元格内以空格连接的文本属同一格。必须逐行逐格如实转写，"
    "禁止计算、推断或编造任何数值。只输出 JSON，不要多余说明。"
)

_CLASSIFY_SYSTEM_PROMPT = (
    "你是检测行业的数据分类助手。给你一份扫描检测原始记录的 OCR 表格文本"
    "和候选检测项目列表，判断该记录属于哪个候选检测项目。"
    "判断依据优先看表头字段名：如出现“回弹值/碳化深度/强度推定值”属回弹法类，"
    "“芯样直径/测试荷载”属钻芯法类，“砂浆”属砂浆强度类，“砖”属砖强度类，"
    "“涂层/焊缝/螺栓”属钢结构类，“含水率/挠度”属木结构类，记录内容为辅。"
    "必须从候选列表中逐字原样选择一个名称，禁止编造或改写；"
    "无法判断时输出空字符串。只输出 JSON，不要多余说明。"
)


def _strip_think(text):
    """剥离 Qwen3 思考模式的 <think>...</think> 内容。

    无闭合标签（输出被截断）时丢弃 <think> 及其后的全部内容。
    """
    if not text or "<think>" not in text:
        return text
    if "</think>" in text:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    # 无闭合：截断场景，<think> 之后的内容不可信
    return text[:text.index("<think>")]


def _build_user_prompt(sheet_text, columns):
    cols = "、".join(columns)
    return (
        f"目标表头字段：{cols}\n"
        "请把下面的表格结构文本整理为一个 JSON 数组，输出格式：\n"
        '{"records": [ {"<字段名>": "<值>", ...}, ... ]}\n'
        "转写规则（严格遵守）：\n"
        "1. 表格文本的每个数据行对应一个对象；单元格之间以制表符分隔，"
        "按从左到右的顺序与目标表头逐格对应，禁止跳格或错位。\n"
        "2. 数值逐字符转写：只保留数字与小数点，不得计算、求和、平均、"
        "四舍五入、补零或改写；单位留在表头，不要写入值。\n"
        "3. 数字混淆按上下文取数字：字母O/o视为0，字母I/l或竖线|视为1，"
        "中文逗号/句号视为小数点。\n"
        "4. 表头行、列名行、汇总/合计行不是数据记录，跳过；"
        "无法确定的内容一律输出空字符串，禁止编造。\n"
        "5. 专用字段逐字符转写：①轴线编号必须保留其中的“-”和“/”，"
        "如9-10-1/A、1-2/C-E，不得省略横线、斜杠或改写字母；"
        "②方向只转写格内原词（如垂直/水平/竖向/横向），不得改写成其他说法；"
        "③设计值为数字（如200），只转写数字与小数点，单位不写入值。\n"
        "6. 字段名必须与目标表头完全一致；表格中没有对应内容的字段留空字符串。\n"
        "7. 只输出 JSON。\n\n"
        "表格结构文本如下（制表符分隔）：\n" + sheet_text
    )


def _build_vision_prompt(columns):
    cols = "、".join(columns)
    return (
        "你是检测行业的数据录入助手。请仔细看这张检测记录表图片，"
        "目标表头字段：\n"
        f"{cols}\n"
        "请把图片表格中的每一数据行转写为一个 JSON 对象，输出格式：\n"
        '{"records": [ {"<字段名>": "<值>", ...}, ... ]}\n'
        "转写规则（严格遵守）：\n"
        "1. 图片为手写或打印的检测记录表：按表格线逐行逐格读取，"
        "每个数据行对应一个对象，与目标表头逐列对应，禁止跳列或错位。\n"
        "2. 数值逐字符忠实转写：只保留数字与小数点，不得计算、求和、"
        "平均、补零或改写；数值列中的斜杠“/”或空白格表示未测，"
        "输出空字符串（注意：仅限数值列，轴线编号中的“/”是编号本身，必须保留）。\n"
        "3. 手写数字按形似理解：O→0、I/l→1、7与1区分、5与6区分；"
        "不确定的数字输出空字符串，禁止编造。\n"
        "4. 专用字段逐字符转写：①轴线编号只填轴号样式的内容（如1-2/D-F、9-10-1/A），"
        "不得把X向/Y向等方向文字填入轴线编号；"
        "方向（X向/Y向/横向/纵向等）只能填入方向列；"
        "轴线编号跨两行书写时合并为一格，必须保留其中的“-”和“/”，不得省略或改写字母；"
        "②设计值为设计间距等数字（如200），只转写数字与小数点，"
        "单位不写入值；空格、斜杠或勾选标记表示未测，输出空字符串，不得识别为数字1"
        "（该规则仅限数值列：轴线编号中的“/”是轴号本身，如1/A、9-10-1/A，"
        "必须原样保留，不得当作未测删掉，也不得误写成数字1）。\n"
        "5. 表头行、备注、签字区不是数据记录，跳过；"
        "汇总/平均值/合格点率等由系统计算的列输出空字符串。\n"
        "6. 字段名必须与目标表头完全一致；图中没有对应内容的字段留空字符串。\n"
        "7. 只输出 JSON。\n"
    )


def _ollama_root_from_base(base_url):
    """由任意 base_url 推导 Ollama 原生服务根地址（去掉 /v1 后缀）。"""
    root = (base_url or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


# 能力查询不可用时的视觉模型命名关键词兜底
_VISION_NAME_KEYWORDS = ("qwen2.5vl", "qwen2-vl", "qwen3-vl", "vl", "vision",
                         "minicpm-v", "llava", "gemma3", "moondream")


def list_ollama_vision_models(base_url, timeout=3):
    """列出 Ollama 服务上可用的视觉(多模态)模型名列表。

    先取 /api/tags 全部模型，再逐个用 /api/show 的 capabilities 含 "vision"
    确认（qwen3.6:35b/qwen2.5vl 等多模态模型均带该能力）；
    能力查询不可用时按模型命名关键词兜底。
    """
    root = _ollama_root_from_base(base_url)
    if not root:
        return []
    try:
        resp = requests.get(root + "/api/tags", timeout=timeout)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        return []
    vision = []
    for n in names:
        if not n:
            continue
        caps = None
        for payload in ({"model": n}, {"name": n}):
            try:
                r = requests.post(root + "/api/show", json=payload,
                                  timeout=timeout)
                if r.status_code == 200:
                    caps = (r.json() or {}).get("capabilities") or []
                    break
            except Exception:
                continue
        if caps is None:
            if any(k in n.lower() for k in _VISION_NAME_KEYWORDS):
                vision.append(n)
        elif "vision" in caps:
            vision.append(n)
    return vision


def list_vision_models_from_cfg(cfg, timeout=3):
    """按配置解析 Ollama 地址并列出可用视觉模型（界面下拉框用）。"""
    llm = cfg.llm
    root = llm.get("ollama_base_url") or llm.get("base_url") or ""
    return list_ollama_vision_models(root, timeout)


def _find_ollama_vision_model(base_url, timeout=5):
    """在 Ollama 中查找可用的视觉(多模态)模型，返回模型名或 None。"""
    names = list_ollama_vision_models(base_url, timeout)
    prefer = ("qwen2.5vl", "qwen2-vl", "llama3.2-vision", "minicpm-v",
              "llava", "gemma3", "moondream")
    for kw in prefer:
        for n in names:
            if kw in n.lower():
                return n
    return names[0] if names else None


class LlmExtractor:
    """大模型结构化抽取器统一接口。"""

    def extract(self, sheet_text, columns):
        raise NotImplementedError

    def resolve_vision_model(self):
        """返回可用的视觉(多模态)模型名；不可用时返回 None。"""
        return None

    def extract_vision(self, image_path, columns):
        """视觉模型直接看图转写表格（手写记录表用）。"""
        raise NotImplementedError

    def classify_project(self, ocr_text, candidates):
        """根据 OCR 文本从候选检测项目中 AI 判定所属项目。

        返回 (检测项目名, 置信度0~1)；无法判定时抛 RecognitionError。
        """
        raise NotImplementedError

    def classify_project_vision(self, image_path, candidates):
        """视觉模型看图判定检测项目（OCR 文本不可用时的降级路径）。"""
        raise NotImplementedError


def _build_classify_prompt(ocr_text, candidates, max_chars=2000):
    lines = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates, 1))
    return (
        f"候选检测项目：\n{lines}\n"
        "请判断下面的 OCR 文本属于哪个候选检测项目，输出格式：\n"
        '{"detection_item": "<候选名称>", "confidence": 0~1}\n'
        "规则：\n"
        "1. 优先按表头字段名判断；\n"
        "2. detection_item 必须与候选名称逐字一致，禁止编造或改写；\n"
        "3. 都不吻合时输出 {\"detection_item\": \"\", \"confidence\": 0}；\n"
        "4. 只输出 JSON。\n\n"
        f"OCR 文本（可能不完整/有识别错误）：\n{ocr_text[:max_chars]}"
    )


# 各 provider 的专属默认端点/模型（用户在配置 JSON 中显式填写时优先）
_PROVIDER_DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen3.6:35b"},
}

# 用户未显式改模型时视为沿用旧默认，按 provider 自动落到对应模型
_LEGACY_MODEL = "Qwen3.6-35B-A3B"


class QwenDashScopeExtractor(LlmExtractor):
    """基于通义千问 Qwen(OpenAI 兼容 /v1) 的结构化抽取器。

    同时兼容 DashScope 云端、本地 vLLM 与本地 Ollama 部署
    （均为 OpenAI 兼容端点，按 provider 区分默认端点与请求差异）。
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        llm = cfg.llm
        self.provider = (llm.get("provider") or "dashscope").lower()
        p_default = _PROVIDER_DEFAULTS.get(self.provider, {})
        self.base_url = (llm.get("base_url") or ""
                         or p_default.get("base_url", "http://172.16.51.69:8000/v1"))
        self.api_key = llm.get("api_key", "")          # 本地部署通常无需鉴权
        self.model = (llm.get("model") or "").strip()
        if not self.model or (
                self.provider in _PROVIDER_DEFAULTS
                and self.model == _LEGACY_MODEL):
            self.model = p_default.get("model", _LEGACY_MODEL)
        self.temperature = llm.get("temperature", 0.0)
        self.timeout = llm.get("timeout", 120)
        self.max_tokens = llm.get("max_tokens", 4096)
        self.classify_max_chars = llm.get("classify_max_chars", 2000)
        # Qwen 推理模型默认开启思考(reasoning)，content 会为空或带 <think>。
        # vLLM/DashScope：chat_template_kwargs 关闭思考；
        # Ollama：OpenAI 兼容端点不识别该参数，改为 system 追加 /no_think 软开关，
        # 并在解析时剥离 <think> 标签兜底。
        self.disable_thinking = llm.get("disable_thinking", True)
        # 视觉(多模态)识别：手写记录表用 VLM 直接看图转写，绕过 OCR
        self.use_vision = (llm.get("use_vision") or "auto").lower()
        self.vision_model = (llm.get("vision_model") or "").strip()
        # Ollama 原生服务专用地址（视觉转写/provider=ollama 结构化用），
        # 留空则沿用 base_url 推导，兼容旧配置
        self.ollama_base_url = (llm.get("ollama_base_url") or "").strip()
        self._vision_cache = None

    def _ollama_root(self):
        """Ollama 原生服务根地址（http://host:11434）。"""
        root = (self.ollama_base_url or self.base_url).rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        return root

    def _system_prompt(self, base_prompt):
        if self.provider == "ollama" and self.disable_thinking:
            return base_prompt + " /no_think"
        return base_prompt

    def _chat(self, user_prompt, system_prompt=None):
        if self.provider == "ollama":
            return self._chat_ollama(user_prompt, system_prompt)
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = [
            {"role": "system",
             "content": self._system_prompt(system_prompt or _SYSTEM_PROMPT)},
            {"role": "user", "content": user_prompt},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.disable_thinking and self.provider in ("vllm", "dashscope", "openai"):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        # 部分 vLLM 启动参数不支持 response_format，先探测后降级
        payload.setdefault("response_format", {"type": "json_object"})
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            # 若 4xx 因 response_format 不被支持，去掉该字段重试一次
            if payload.get("response_format"):
                payload.pop("response_format", None)
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
            else:
                raise
        except requests.ConnectionError:
            raise RecognitionError(
                f"无法连接大模型服务({self.base_url})。"
                f"provider={self.provider}：请确认服务已启动并已拉取模型 {self.model}。")
        data = resp.json()
        try:
            msg = data["choices"][0]["message"]
            content = msg.get("content")
            # Qwen 推理模型(vLLM)会把正文放在 reasoning 字段，content 为 null
            if not content:
                content = msg.get("reasoning") or msg.get("reasoning_content")
            return content
        except Exception:
            raise RecognitionError(f"大模型返回格式异常: {data}")

    def _chat_ollama(self, user_prompt, system_prompt=None, images=None,
                     model=None, think=None):
        """Ollama 原生 /api/chat。

        OpenAI 兼容端点不支持关闭思考（think），Qwen 思考模型会把推理
        过程当正文输出、耗尽 max_tokens 而拿不到 JSON；改用原生接口：
        - ``think: false`` 强制关闭思考；
        - ``format: "json"`` 强制只输出合法 JSON；
        - ``images``：base64 图片列表（视觉模型看图转写用）。
        """
        root = self._ollama_root()
        url = root + "/api/chat"
        user_msg = {"role": "user", "content": user_prompt}
        if images:
            user_msg["images"] = images
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
                user_msg,
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        # think 参数语义：False=强制关闭思考（payload 带 think:false）；
        # True=允许思考（不带字段，模型默认开启）；None=按配置 disable_thinking。
        # 实测（Ollama 0.32.15 + qwen3.6:35b）：不带 think 字段时默认开启
        # 思考，思考文本耗尽 num_predict 导致拿不到 JSON；显式 think:false
        # 时 format:"json" 完全生效。
        allow_think = ((not self.disable_thinking) if think is None
                       else bool(think))
        if not allow_think:
            payload["think"] = False
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            # 旧版 Ollama 不识别 think 参数：去掉后重试一次
            if "think" in payload:
                payload.pop("think", None)
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
            else:
                raise
        except requests.ConnectionError:
            raise RecognitionError(
                f"无法连接 Ollama({root})。"
                f"请确认已运行 ollama serve 并已 pull 模型 {self.model}。")
        data = resp.json()
        msg = data.get("message") or {}
        # 思考型模型即使关不掉思考，正文/thinking 也会分开返回
        content = msg.get("content") or msg.get("thinking") or ""
        if not content:
            raise RecognitionError(
                f"Ollama 返回内容为空（done_reason={data.get('done_reason')}），"
                f"请检查模型 {self.model} 是否可用。")
        return content

    @staticmethod
    def _clean_json(text):
        text = _strip_think(text or "")
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if fence:
            text = fence.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
        return text

    def _vision_json_call(self, prompt, images,
                          system_prompt=_SYSTEM_PROMPT, retries=None):
        """视觉模型 JSON 调用 + 思考溢出自动重试。

        思考模型带图请求时 Ollama 不保证尊重 think/format 约束，思考
        文本可能占满输出导致解析不出合法 JSON（偶发）。解析失败自动
        重试（llm.vision_retries，默认 1 次），重试时在提示词前追加
        "直接输出 JSON"强指令降低再次触发思考的概率。

        返回 (JSON 对象或 None, 最后一次原始回复文本)。
        """
        if retries is None:
            retries = max(0, int(self.cfg.llm.get("vision_retries", 1)))
        model = self.resolve_vision_model()
        content = ""
        for attempt in range(retries + 1):
            ask = prompt if attempt == 0 else (
                "直接输出 JSON，禁止任何分析、思考或解释文字。\n" + prompt)
            content = self._chat_ollama(
                ask, system_prompt=system_prompt,
                images=images, model=model, think=False)
            try:
                return json.loads(self._clean_json(content)), content
            except Exception:
                # 思考溢出/截断/夹带推理文字等，重试
                continue
        return None, content

    def extract(self, sheet_text, columns):
        content = self._chat(_build_user_prompt(sheet_text, columns))
        try:
            obj = json.loads(self._clean_json(content))
        except Exception:
            raise RecognitionError(f"无法解析大模型输出为 JSON：{content[:500]}")
        records = obj.get("records") or obj.get("data") or obj
        if isinstance(records, dict):
            records = [records]
        return records or []

    def resolve_vision_model(self):
        """视觉模型解析：off 关闭；显式配置优先；Ollama 自动探测。

        探测地址取 llm.ollama_base_url（未配置时回退 base_url 推导），
        不再要求 provider 必须为 ollama——结构化抽取可走 vLLM/DashScope，
        视觉转写仍可指向另一台机器上的 Ollama。
        """
        if self.use_vision == "off":
            return None
        if self.vision_model:
            return self.vision_model
        if self._vision_cache is None:
            self._vision_cache = _find_ollama_vision_model(self._ollama_root())
        if self._vision_cache is None and self.use_vision == "on":
            raise RecognitionError(
                f"未在 Ollama({self._ollama_root()}) 找到可用视觉模型，"
                "请 pull qwen2.5vl 等多模态模型，或将 use_vision 设为 auto/off。")
        return self._vision_cache

    def extract_vision(self, image_path, columns, hints=""):
        """视觉模型直接看图转写表格（绕过 OCR，手写记录表用）。

        hints 为历史校正经验文本（长期记忆召回），注入提示词供模型
        对照参考（明确要求仍以图片实际内容为准）。
        思考模型带图偶发思考文本占满输出导致 JSON 解析失败，
        ``_vision_json_call`` 内自动重试（llm.vision_retries，默认 1 次）。
        """
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        prompt = _build_vision_prompt(columns)
        if hints:
            prompt += "\n" + hints + "\n"
        obj, content = self._vision_json_call(prompt, [b64])
        if obj is None:
            raise RecognitionError(f"无法解析大模型输出为 JSON：{content[:500]}")
        records = obj.get("records") or obj.get("data") or obj
        if isinstance(records, dict):
            records = [records]
        return records or []

    def _parse_classify_reply(self, content, candidates):
        """解析判定回复：返回 (候选名, 置信度)，无法匹配抛 RecognitionError。"""
        self._last_classify_raw = content or ""
        obj = None
        try:
            obj = json.loads(self._clean_json(content))
            if not isinstance(obj, dict):
                # 思考模型常把推理包成 JSON 字符串——视为解析失败走兜底
                obj = None
        except Exception:
            obj = None
        if obj is None:
            # 兜底：从原文提取 detection_item（取最后一次出现，防推理复述）
            import re
            ms = re.findall(r'"detection_item"\s*:\s*"([^"]+)"', content or "")
            if ms:
                obj = {"detection_item": ms[-1]}
                mc = re.findall(r'"confidence"\s*:\s*([0-9.]+)', content or "")
                if mc:
                    obj["confidence"] = mc[-1]
        if obj is None:
            raise RecognitionError(
                f"AI 判定检测项目失败，无法解析输出：{(content or '')[:200]}")
        name = ""
        for key in ("detection_item", "item", "sub_item", "name"):
            if isinstance(obj, dict) and obj.get(key):
                name = str(obj[key]).strip()
                break
        confidence = 0.0
        try:
            confidence = float(obj.get("confidence", 0))
        except Exception:
            pass
        matched = self._match_candidate(name, candidates)
        if not matched:
            raise RecognitionError(
                f"AI 无法判定检测项目（原始输出：{(content or '')[:200]}）。"
                f"候选：{candidates}，请手动选择。")
        return matched, max(0.0, min(1.0, confidence))

    def classify_project(self, ocr_text, candidates):
        content = self._chat(
            _build_classify_prompt(ocr_text, candidates, self.classify_max_chars),
            system_prompt=_CLASSIFY_SYSTEM_PROMPT,
        )
        return self._parse_classify_reply(content, candidates)

    def classify_project_vision(self, image_path, candidates):
        """视觉模型判定检测项目（OCR 文本不可用时的降级路径）。

        思考模型带图调用时 format/think 约束不生效、推理会占满正文，
        因此分两步：先让视觉模型转写表格标题/表头（转写是其强项、
        实测可靠），再用文本通道按候选判定（format json 可靠）。
        """
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        obj, content = self._vision_json_call(
            "转写图片中记录表格的标题和表头字段名。直接输出 JSON 对象："
            '{"title": "<标题原文>", "headers": ["<字段1>", "<字段2>"]}，'
            "不要输出任何思考过程或解释文字。图中没有标题时 title 输出空串。",
            [b64], system_prompt="你是检测记录表格识别助手，只输出 JSON。")
        # 容错解析：优先 JSON，兜底正则（思考模型可能夹带推理文字）
        title, headers = "", []
        if isinstance(obj, dict):
            title = str(obj.get("title") or "")
            headers = [str(h) for h in (obj.get("headers") or []) if h]
        if not title:
            import re
            mt = re.search(r'"title"\s*:\s*"([^"]*)"', content or "")
            if mt:
                title = mt.group(1)
            if not headers:
                hs = re.findall(r'"([^"]{2,20})"', content or "")
                headers = [h for h in hs
                           if h not in ("title", "headers", "检测记录识别助手")][:10]
        hint = (title + "\n" + " ".join(headers)).strip()
        if not hint:
            raise RecognitionError(
                "视觉模型未能转写出表格标题/表头，无法判定检测项目，请手动选择。")
        self._vision_transcribed_header = hint
        return self.classify_project(hint, candidates)

    @staticmethod
    def _match_candidate(name, candidates):
        """候选名匹配：先精确，再做去空白/全角括号归一匹配。"""
        if not name:
            return None
        for c in candidates:
            if name == c:
                return c
        def _norm(s):
            return (str(s).replace("（", "(").replace("）", ")")
                    .replace(" ", "").replace("\t", ""))
        n = _norm(name)
        for c in candidates:
            if _norm(c) == n:
                return c
        return None


class MockLLMExtractor(LlmExtractor):
    """离线模拟：根据目标列名生成一条示例结构化记录。"""

    def extract(self, sheet_text, columns):
        record = {}
        # 用最简单直观的列名生成便于匹配的演示数据
        lookup = {
            "楼栋": "2号楼",
            "批次": "1",
            "构件编号": "1",
            "构件位置及名称": "2层FL-3",
            "轴线编号": "1/A",
            "轴线": "1/A",
            "序号": "1",
            "芯样直径(mm)": "100",
            "测试荷载(kN)": "320",
            "设计等级": "C30",
            "设计强度等级": "C30",
            "构件类型": "梁",
            "楼层": "2",
        }
        for col in columns:
            if col in lookup:
                record[col] = lookup[col]
            else:
                record[col] = ""
        return [record]

    def classify_project(self, ocr_text, candidates):
        """离线确定性规则：按关键词命中候选（与 MockOcrBackend 配套）。"""
        self._last_classify_raw = "mock：关键词规则判定"
        if not candidates:
            raise RecognitionError("未获取到候选检测项目，无法 AI 判定。")
        keywords = (
            ("芯样", "钻芯"), ("回弹", "回弹"), ("碳化", "回弹"),
            ("砂浆", "砂浆"), ("砖", "砖"), ("焊", "焊"),
            ("螺栓", "螺栓"), ("锚栓", "锚"), ("锚固", "锚"),
            ("含水率", "含水"), ("挠度", "挠度"), ("涂层", "涂层"),
            ("硬度", "硬度"), ("保护层", "保护层"), ("植筋", "植筋"),
            ("钢筋", "钢筋"),
        )
        text = ocr_text or ""
        for kw, hint in keywords:
            if kw in text:
                for c in candidates:
                    if hint in c or kw in c:
                        return c, 0.9
        return candidates[0], 0.5


# 兼容别名：OpenAI 兼容端点抽取器（DashScope/vLLM/Ollama 通用）
OpenAICompatExtractor = QwenDashScopeExtractor


def build_llm_extractor(cfg: Config):
    provider = (cfg.llm.get("provider") or "dashscope").lower()
    if provider == "mock":
        return MockLLMExtractor()
    if provider in ("dashscope", "vllm", "openai", "ollama"):
        return QwenDashScopeExtractor(cfg)
    raise ValueError(f"未知 LLM provider: {provider}")