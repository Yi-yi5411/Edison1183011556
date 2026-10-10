# -*- coding: utf-8 -*-
"""自修复智能体的状态定义（LangGraph StateGraph 的 State TypedDict）。

字段分为三组：
- 输入：原图路径、目标表头、上一轮可疑清单；
- 轮内产物：本轮重转写记录 / 规范化结果 / 校验警告，以及轮数计数；
- 择优：历史最优（可疑值最少的轮次产物），初始即流水线原结果。

log 为全程可读日志（界面快照展示用），error 标记最近一次节点失败
（出现后条件边直接定稿，保留历史最优）。
"""
from typing import List, Optional, TypedDict


class RepairState(TypedDict, total=False):
    # ── 输入 ──
    image_path: str            # 扫描原图路径（视觉模型看图用）
    columns: List[str]         # 目标表头字段
    hints: List[dict]          # 可疑清单（修复轮提示词用）
    max_rounds: int            # 最大修复轮数

    # ── 轮内产物 ──
    rounds: int                # 已完成的修复轮数
    raw_records: List[dict]    # 本轮视觉模型重转写的原始记录
    normalized: List[dict]     # 本轮规范化结果
    warnings: List[dict]       # 本轮校验出的可疑值
    error: str                 # 最近一次节点错误（空串=无）

    # ── 择优（历史最优，初始为流水线原结果） ──
    best_raw: List[dict]       # 最优原始记录
    best_normalized: Optional[List[dict]]  # 最优规范化结果（未改善时为 None）
    best_warnings: List[dict]  # 最优结果对应的可疑清单
    initial_warnings: int      # 初始可疑值数量（判断是否有改善的基准）

    # ── 全程信息 ──
    model: str                 # 视觉模型名
    log: List[str]             # 过程日志（界面展示）
