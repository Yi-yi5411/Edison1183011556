# -*- coding: utf-8 -*-
"""自修复智能体的节点实现（LangGraph 节点函数 + Ollama 传输封装）。

- ``reextract_node``：带原图 + 可疑清单重问视觉模型，重新转写整表；
- ``govern_node``：Normalizer 规范化 + validate_records 校验，按
  “可疑值最少”与历史最优比较、择优暂存；
- 条件边逻辑 ``should_continue`` 见 graph.py（定稿/再修一轮）。

传输层用 langchain_ollama.ChatOllama（走 Ollama 原生 /api/chat，
format=json 强制 JSON 输出）。langchain_ollama 在函数内部惰性导入，
未安装时抛 ImportError 由上层捕获降级。

提示词复用 llm.py 的视觉转写模板（与首轮识别同一规则体系），
修复轮追加可疑清单与修正指令。
"""
import base64
import inspect
import json
import os

from report_generator.scan_recognition.llm import (
    _SYSTEM_PROMPT,
    QwenDashScopeExtractor,
    _build_vision_prompt,
    _ollama_root_from_base,
)
from report_generator.scan_recognition.normalizer import Normalizer


def resolve_model(cfg):
    """解析可用的视觉模型名（复用抽取器的探测逻辑），不可用返回 None。"""
    return QwenDashScopeExtractor(cfg).resolve_vision_model()


class AgentCtx:
    """一次智能体运行共享的上下文：配置 / 模型名 / 客户端 / 规范化器。"""

    def __init__(self, cfg, model, normalizer: Normalizer):
        self.cfg = cfg
        self.model = model
        self.normalizer = normalizer
        self._client = None

    def system_prompt(self):
        """系统提示词：与首轮视觉转写一致；思考模型追加 /no_think。"""
        base = _SYSTEM_PROMPT
        if self.cfg.llm.get("disable_thinking", True):
            base += " /no_think"
        return base

    def client(self):
        """懒创建 ChatOllama 客户端（线程内单次运行复用）。

        - base_url 用 Ollama 原生根地址（去掉 /v1 后缀）；
        - format="json" 强制只输出合法 JSON；
        - langchain-ollama 1.x 用 reasoning=False 关闭思考（对应 Ollama
          原生 think:false）；旧版本无该参数时靠 /no_think 软开关 +
          <think> 剥离兜底。
        """
        if self._client is None:
            from langchain_ollama import ChatOllama
            llm = self.cfg.llm
            root = _ollama_root_from_base(
                llm.get("ollama_base_url") or llm.get("base_url") or "")
            kwargs = {
                "base_url": root,
                "model": self.model,
                "temperature": float(llm.get("temperature", 0.0)),
                "num_predict": int(llm.get("max_tokens", 4096)),
                "format": "json",
            }
            if llm.get("disable_thinking", True) and \
                    "reasoning" in inspect.signature(ChatOllama).parameters:
                kwargs["reasoning"] = False
            self._client = ChatOllama(**kwargs)
        return self._client


def build_repair_prompt(columns, hints, memory_hints=""):
    """视觉转写提示词 + 识别记忆 + 修复轮追加指令（可疑清单）。

    hints 为空时即首轮转写提示词（含全部转写规则），保证修复轮
    与首轮识别遵循同一套转写规则，避免规则漂移。
    memory_hints 为识别记忆召回文本（历史校正经验/上轮留痕），
    置于修复指令之前供模型对照参考。
    """
    prompt = _build_vision_prompt(columns)
    if memory_hints:
        prompt += "\n" + str(memory_hints) + "\n"
    if not hints:
        return prompt
    lines = []
    for w in hints[:20]:
        lines.append(f"- 第{w.get('行')}行 字段「{w.get('字段')}」当前值"
                     f"「{w.get('值')}」：{w.get('问题')}")
    return (
        prompt
        + "\n上一轮机器转写结果经规则校验发现以下可疑之处，"
          "请对照图片重新逐格核对这些位置及其所在整行：\n"
        + "\n".join(lines) + "\n"
        + "修正要求：图中该格确为斜杠“/”或空白时输出空字符串；"
          "确为手写数字时逐字符如实转写；其余内容保持原样。"
          "按上述同一格式重新输出全部数据行，只输出 JSON。\n"
    )


def _parse_records(content):
    """解析视觉模型回复为记录列表（复用抽取器的 JSON 清洗兜底）。"""
    text = QwenDashScopeExtractor._clean_json(content)
    obj = json.loads(text)
    records = obj.get("records") if isinstance(obj, dict) else None
    if records is None and isinstance(obj, dict):
        records = obj.get("data")
    if records is None and isinstance(obj, list):
        records = obj
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ValueError("修复轮未解析出有效记录")
    if not all(isinstance(r, dict) for r in records):
        raise ValueError("修复轮记录格式异常（含非对象项）")
    return records


def reextract_node(state, ctx: AgentCtx):
    """重转写节点：看图重新转写整表（带可疑清单）。失败只置 error 不中断。"""
    try:
        image_path = state["image_path"]
        if not (image_path and os.path.exists(image_path)):
            raise FileNotFoundError(f"原图不存在：{image_path}")
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        prompt = build_repair_prompt(
            state["columns"], state.get("hints") or [],
            state.get("memory_hints") or "")
        # 图片块用 langchain v1 base64 内容块（langchain-ollama 原生支持）
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "base64": b64, "mime_type": "image/png"},
            ],
        }
        resp = ctx.client().invoke([
            {"role": "system", "content": ctx.system_prompt()},
            message,
        ])
        content = resp.content
        if isinstance(content, list):  # 多模态分块响应：拼接文本块
            content = "".join(
                b.get("text", "") for b in content if isinstance(b, dict))
        records = _parse_records(content)
        state["raw_records"] = records
        state["error"] = ""
        state["log"].append(
            f"第{state.get('rounds', 0) + 1}轮重转写完成：得到 {len(records)} 条记录")
    except Exception as e:  # noqa: BLE001 —— 任何失败都降级，不打断流水线
        state["error"] = f"重转写失败：{type(e).__name__}: {e}"
        state["log"].append(state["error"])
    return state


def govern_node(state, ctx: AgentCtx):
    """治理节点：规范化 + 校验，与历史最优比可疑值数量，更少则择优暂存。"""
    if state.get("error") or not state.get("raw_records"):
        return state
    normalized = ctx.normalizer.normalize_records(state["raw_records"])
    warnings = ctx.normalizer.validate_records(normalized)
    # 量程治理留痕（与流水线 NormalizeStep 同一规则）
    for w in ctx.normalizer.take_auto_cleared():
        warnings.insert(0, {
            "行": w["行"], "字段": w["字段"], "值": w["值"],
            "问题": "小于合理量程，已按未测（/）自动清空，请确认"})
    state["normalized"] = normalized
    state["warnings"] = warnings
    state["rounds"] = state.get("rounds", 0) + 1
    best_n = len(state.get("best_warnings") or [])
    state["log"].append(
        f"第{state['rounds']}轮校验：可疑值 {len(warnings)} 条"
        f"（此前最优 {best_n} 条）")
    if len(warnings) < best_n:
        state["best_raw"] = state["raw_records"]
        state["best_normalized"] = normalized
        state["best_warnings"] = warnings
        state["log"].append(f"第{state['rounds']}轮结果更优，暂存为最优")
    return state


def should_continue(state):
    """条件边：有改善且仍有可疑、未超轮数上限 → 再修一轮；否则定稿。"""
    if state.get("error"):
        return "end"
    if state.get("rounds", 0) >= state.get("max_rounds", 0):
        return "end"
    if not state.get("warnings"):
        return "end"
    # 相比初始无可改善，说明同样提示重问无益，定稿保留最优
    if len(state["warnings"]) >= state.get("initial_warnings", 0):
        return "end"
    return "reextract"
