# -*- coding: utf-8 -*-
"""规范条文 AI 解释：本地 Ollama 生成中文回答。

复用项目 Ollama 配置（llm.ollama_base_url 推导），urllib 实现，无第三方依赖。
输出遵循用户约定：全部中文、不带 markdown 符号、句子以句号结尾。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Dict, List, Optional

# 解释提示词（充当约束：只依据给出的条文原文作答）
SYSTEM_PROMPT = (
    "你是建筑工程检测规范助手。"
    "只依据给出的规范条文原文回答问题，"
    "回答全部使用中文，"
    "不要使用任何markdown符号（如星号、井号、反引号），"
    "每个句子结尾用句号，"
    "引用条文时写明规范代号和条号，"
    "条文原文没有涉及的内容明确说明条文未涉及，"
    "回答简洁控制在三百字以内。"
)


def _resolve_base_url() -> str:
    """Ollama 根地址：scan_recognition 配置 llm.ollama_base_url 推导。"""
    root = ""
    try:
        from scan_recognition.config import Config
    except ImportError:
        try:
            from report_generator.scan_recognition.config import Config
        except ImportError:
            Config = None  # noqa
    if Config is not None:
        try:
            llm = (Config.load().data or {}).get("llm") or {}
            root = (llm.get("ollama_base_url") or "").strip()
        except Exception:
            root = ""
    if not root:
        root = "http://127.0.0.1:11434"
    root = root.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def _pick_model(base_url: str, timeout: float = 5.0) -> str:
    """选对话模型：取 /api/tags 第一个模型（qwen 优先）。"""
    try:
        with urllib.request.urlopen(
                base_url + "/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name") or "" for m in data.get("models") or []]
        names = [n for n in names if n]
        for n in names:
            if "qwen" in n.lower():
                return n
        return names[0] if names else ""
    except Exception:
        return ""


def explain_clauses(question: str, clauses: List[Dict],
                    model: str = "", timeout: float = 120.0) -> str:
    """基于命中的条文原文生成中文解释；Ollama 不可达时返回空串。"""
    if not clauses:
        return ""
    base_url = _resolve_base_url()
    if not model:
        model = _pick_model(base_url)
    if not model:
        return ""

    context_parts = []
    for c in clauses[:8]:
        head = "%s %s" % (c.get("code") or "", c.get("chapter") or "")
        if c.get("code_name"):
            head += "（%s）" % c["code_name"]
        body = (c.get("body") or "").strip()
        if c.get("title"):
            body = ("%s\n%s" % (c["title"], body)).strip()
        context_parts.append("【%s】\n%s" % (head, body or "（无正文）"))

    prompt = (
        "用户问题：%s\n\n"
        "检索到的规范条文原文如下：\n\n%s\n\n"
        "请依据以上条文原文回答用户问题。"
        % (question.strip(), "\n\n".join(context_parts))
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
    }
    try:
        req = urllib.request.Request(
            base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = ((data.get("message") or {}).get("content") or "").strip()
        if not content and data.get("response"):
            content = str(data["response"]).strip()
        return content
    except Exception:
        return ""
