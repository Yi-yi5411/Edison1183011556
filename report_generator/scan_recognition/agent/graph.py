# -*- coding: utf-8 -*-
"""自修复智能体的状态图编排与主入口。

图结构（LangGraph StateGraph）::

    START → reextract（视觉重转写） → govern（规则治理+择优）
          → should_continue 条件边 ─┬→ reextract（再修一轮）
                                    └→ END（定稿）

主入口 ``run_repair_agent``：任何异常（langgraph 未安装、Ollama 不可达、
模型输出不可解析等）都不抛出，返回 ``fallback_reason`` 并携带原记录，
调用方据此降级保留原识别结果，保证识别流水线不中断。
"""
import os

from .nodes import AgentCtx, govern_node, reextract_node, resolve_model, \
    should_continue
from .state import RepairState
from report_generator.scan_recognition.normalizer import Normalizer


def build_repair_graph(ctx: AgentCtx):
    """构建自修复状态图（依赖 langgraph，惰性导入便于降级）。"""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(RepairState)
    graph.add_node("reextract", lambda s: reextract_node(s, ctx))
    graph.add_node("govern", lambda s: govern_node(s, ctx))
    graph.add_edge(START, "reextract")
    graph.add_edge("reextract", "govern")
    graph.add_conditional_edges(
        "govern", should_continue,
        {"reextract": "reextract", "end": END})
    return graph.compile()


def run_repair_agent(image_path, columns, structured, warnings, cfg,
                     max_rounds=2, model=None, memory_hints=""):
    """AI 智能体自修复主入口（LangGraph 状态图驱动）。

    参数：
        image_path: 扫描原图路径（视觉模型看图用）；
        columns:    目标表头字段列表；
        structured: 流水线首轮识别的原始结构化记录；
        warnings:   规范化校验发现的可疑清单（修复提示）；
        cfg:        扫描识别配置（Config）；
        max_rounds: 最大修复轮数（默认 2）；
        model:      指定视觉模型名，空则自动探测；
        memory_hints: 识别记忆提示词（历史校正经验/上轮留痕），空则不注入。

    返回 dict：
        records         择优后的原始记录（未改善=原记录）；
        normalized      择优后的规范化结果（未改善=None，调用方保留原值）；
        warnings        择优后对应的可疑清单；
        log             过程日志（界面展示）；
        model           实际使用的视觉模型名；
        rounds          实际执行的修复轮数；
        fallback_reason 回退原因（空串=正常完成智能修复）。
    """
    log = []
    fallback = {
        "records": list(structured or []),
        "normalized": None,
        "warnings": list(warnings or []),
        "log": log,
        "model": model or "",
        "rounds": 0,
        "fallback_reason": "",
    }
    try:
        normalizer = Normalizer(cfg)
        model = model or resolve_model(cfg)
        if not model:
            fallback["fallback_reason"] = "未找到可用视觉模型，跳过智能修复。"
            return fallback
        if not (image_path and os.path.exists(str(image_path))):
            fallback["fallback_reason"] = f"原图不存在：{image_path}"
            return fallback
        ctx = AgentCtx(cfg, model, normalizer)
        state = {
            "image_path": str(image_path),
            "columns": list(columns or []),
            "hints": list(warnings or []),
            "memory_hints": str(memory_hints or ""),
            "max_rounds": int(max_rounds),
            "rounds": 0,
            "raw_records": [],
            "normalized": [],
            "warnings": [],
            "error": "",
            "best_raw": list(structured or []),
            "best_normalized": None,
            "best_warnings": list(warnings or []),
            "initial_warnings": len(list(warnings or [])),
            "model": model,
            "log": log,
        }
        graph = build_repair_graph(ctx)
        final = graph.invoke(
            state, config={"recursion_limit": 2 * int(max_rounds) + 8})
        log = final.get("log") or log
        # 择优产物按“是否改善过”判定（空列表也是有效结果，不能用 or 兜底）
        best_raw = final.get("best_raw")
        best_norm = final.get("best_normalized")
        best_warn = final.get("best_warnings")
        improved = best_norm is not None
        err = final.get("error") or ""
        return {
            "records": best_raw if best_raw is not None
            else list(structured or []),
            "normalized": best_norm,
            "warnings": best_warn if best_warn is not None
            else list(warnings or []),
            "log": log,
            "model": model,
            "rounds": final.get("rounds", 0),
            # 全程无改善且有节点错误时，把错误作为回退原因透传
            "fallback_reason": err if (err and not improved) else "",
        }
    except Exception as e:  # noqa: BLE001 —— 兜底降级，保证识别不中断
        fallback["fallback_reason"] = f"{type(e).__name__}: {e}"
        return fallback
