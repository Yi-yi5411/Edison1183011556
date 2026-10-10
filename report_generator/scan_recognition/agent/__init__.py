# -*- coding: utf-8 -*-
"""扫描识别自修复智能体（LangGraph 状态图编排）。

模块化结构：
- ``state``    修复状态图的状态定义（RepairState）；
- ``nodes``    节点实现：视觉重转写（reextract）/ 规则治理（govern）；
- ``graph``    状态图编排与主入口 ``run_repair_agent``。

主流程：结构化识别后，对字段治理发现的可疑值带原图与可疑清单重问
视觉模型重新转写，再经 Normalizer 校验，最多 ``max_rounds`` 轮、
按“可疑值最少”择优采纳，未改善保留原值。

注意：LangGraph/langchain 依赖只在 ``graph``/``nodes`` 内部惰性导入，
本包 ``__init__`` 不引入任何第三方依赖，保证旧环境（如 Python 3.8
未装 langgraph）导入本包不报错，流水线可整体降级运行。
"""
