# -*- coding: utf-8 -*-
"""《检测报告》Ollama 工具代理（LLM 编排 report_tools 逐步生成报告）。

方案（与扫描识别 Ollama 约定一致）：
  - 走 Ollama 原生 ``/api/chat``，传 ``tools=TOOL_DEFINITIONS``；
  - ``think: false`` 强制关闭思考（旧版 Ollama 不识别时去掉重试一次）；
  - 模型返回 ``message.tool_calls`` → 逐个经 ``execute_tool`` 执行，
    结果以 ``role=tool`` 消息回传，模型据此推理下一步；
  - ``save_report`` 成功即达成目标，结束循环；
  - 任何异常（Ollama 不可达 / 无 tools 模型 / 轮数耗尽 / 模型不配合）
    由 ``generate_report_via_agent`` 自动回退直接生成，识别链路不受影响。

模型探测：显式配置 report_agent.model 优先；否则在 /api/tags 中找
capabilities 含 "tools" 的模型（qwen 优先，工具调用最稳）。

命令行自检::

    python utils/report_agent.py --demo            # 内置样例数据走完整流程
    python utils/report_agent.py --list-models     # 仅探测可用 tools 模型
"""
import json
import os
import sys

import requests

# 支持命令行直跑（python utils/report_agent.py）：引导包搜索路径
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(os.path.dirname(_HERE), "libs"),  # 内置 openpyxl
           os.path.dirname(_HERE),
           os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from report_generator.utils.report_tools import (
        TOOL_DEFINITIONS,
        ReportToolSession,
        build_system_prompt,
        execute_tool,
    )
    from report_generator.utils.word_report import generate_report
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_tools import (
        TOOL_DEFINITIONS,
        ReportToolSession,
        build_system_prompt,
        execute_tool,
    )
    from utils.word_report import generate_report

# report_agent 配置缺省（与 scan_recognition/config.py 保持一致）
DEFAULT_AGENT_CFG = {
    "enabled": True,
    "base_url": "",
    "model": "",
    "max_rounds": 24,
    "timeout": 180,
    "num_predict": 1024,
    "temperature": 0.2,
}


# ═══════════════════════════════════════════════════════════
#  配置 / 模型探测
# ═══════════════════════════════════════════════════════════
def _ollama_root(base_url):
    """由任意 base_url 推导 Ollama 原生服务根地址（去掉 /v1 后缀）。"""
    root = (base_url or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root or "http://localhost:11434"


def load_agent_cfg():
    """读取 report_agent 配置：scan_recognition Config 为主，缺省兜底。

    utils 层不硬依赖 scan_recognition（导入失败静默回退默认值），
    base_url 缺省时沿用 llm.ollama_base_url / llm.base_url 推导。
    """
    cfg = dict(DEFAULT_AGENT_CFG)
    try:
        from scan_recognition.config import Config
    except ImportError:
        try:
            from report_generator.scan_recognition.config import Config
        except ImportError:
            return cfg
    try:
        data = Config.load().data or {}
        ra = dict(data.get("report_agent") or {})
        for key in cfg:
            if key in ra and ra[key] not in (None, ""):
                cfg[key] = ra[key]
        llm = dict(data.get("llm") or {})
        root = (llm.get("ollama_base_url") or "").strip()
        if not root and llm.get("base_url"):
            root = _ollama_root(llm.get("base_url"))
        if not cfg.get("base_url"):
            cfg["base_url"] = root or cfg["base_url"]
    except Exception:
        pass
    return cfg


def list_ollama_tool_models(base_url, timeout=3):
    """列出 capabilities 含 "tools" 的本地模型（qwen 系优先）。"""
    root = _ollama_root(base_url)
    try:
        resp = requests.get(root + "/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("models") or []
    except Exception:
        return []
    tool_models = []
    for m in models:
        name = m.get("name") or m.get("model") or ""
        if not name:
            continue
        try:
            r = requests.post(root + "/api/show",
                              json={"model": name}, timeout=timeout)
            caps = (r.json() or {}).get("capabilities") or []
        except Exception:
            continue
        if "tools" in caps:
            tool_models.append(name)
    tool_models.sort(key=lambda n: (0 if n.lower().startswith("qwen") else 1, n))
    return tool_models


def resolve_tool_model(base_url, configured="", timeout=5):
    """解析工具调用模型：显式配置优先，否则自动探测。

    返回 (model 或 None, 说明文本)。
    """
    if str(configured or "").strip():
        return configured.strip(), "使用配置模型 %s" % configured
    names = list_ollama_tool_models(base_url, timeout=timeout)
    if not names:
        return None, "未在 Ollama(%s) 中找到支持 tools 的模型" % base_url
    return names[0], "自动探测模型 %s" % names[0]


# ═══════════════════════════════════════════════════════════
#  工具循环代理
# ═══════════════════════════════════════════════════════════
def _normalize_args(raw):
    """Ollama tool_calls 的 arguments 可能是 dict 或 JSON 字符串。"""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            return dict(obj) if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


class ReportToolAgent(object):
    """驱动 ReportToolSession 的 Ollama 工具循环。"""

    def __init__(self, base_url, model, max_rounds=24, timeout=180,
                 num_predict=1024, temperature=0.2, on_log=None):
        self.root = _ollama_root(base_url)
        self.model = model
        self.max_rounds = max(1, int(max_rounds))
        self.timeout = int(timeout)
        self.num_predict = int(num_predict)
        self.temperature = float(temperature)
        self._log = on_log or (lambda msg: None)

    def _chat(self, messages):
        """单次 /api/chat（带 tools）；think:false，旧版 Ollama 兼容重试。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }
        try:
            resp = requests.post(self.root + "/api/chat", json=payload,
                                 timeout=self.timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            if "think" in payload:  # 旧版不识别 think：去掉重试一次
                payload.pop("think", None)
                resp = requests.post(self.root + "/api/chat", json=payload,
                                     timeout=self.timeout)
                resp.raise_for_status()
            else:
                raise
        return (resp.json() or {}).get("message") or {}

    def run(self, task, session=None, messages=None):
        """执行工具循环，返回运行摘要。

        结束条件：save_report 成功 / 模型给出无工具调用的答复 /
        轮数耗尽。返回 {"ok", "rounds", "final_content", "session"}。
        """
        session = session or ReportToolSession()
        if messages is None:
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": task},
            ]
        final_content = ""
        for round_no in range(1, self.max_rounds + 1):
            msg = self._chat(messages)
            tool_calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            if not tool_calls:
                final_content = content or msg.get("thinking") or ""
                messages.append({"role": "assistant",
                                 "content": final_content})
                self._log("模型答复（无工具调用，第%d轮）：%s"
                          % (round_no, final_content[:120]))
                break
            messages.append({"role": "assistant", "content": content,
                             "tool_calls": tool_calls})
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                args = _normalize_args(fn.get("arguments"))
                result = execute_tool(session, name, args)
                self._log("第%d轮 %s → %s" % (round_no, name,
                                              result.get("message", "")))
                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            if "save_report" in session.done_steps:
                final_content = "报告已保存，任务完成。"
                break
        else:
            final_content = "工具循环达到最大轮数 %d。" % self.max_rounds
        saved = "save_report" in session.done_steps
        if not saved:
            self._log("未完成保存；当前进度：%s"
                      % "、".join(session.done_steps))
        return {"ok": saved, "rounds": round_no,
                "final_content": final_content, "session": session}


# ═══════════════════════════════════════════════════════════
#  对外入口：LLM 编排生成（失败自动回退直接生成）
# ═══════════════════════════════════════════════════════════
def _build_task_text(project_name, report_info, sheet_data, columns_map,
                     checked_order, output_path):
    return (
        "请调用工具为本工程生成《检测报告》.docx，全程按标准工作流执行，"
        "完成后务必调用 save_report 保存。\n"
        "输出路径：%s\n"
        "工程名称：%s\n"
        "抬头信息：%s\n"
        "参与报告的工作表（按此顺序）：%s\n"
        "检测数据：%s\n"
        "列头：%s\n" % (
            output_path, project_name,
            json.dumps(report_info or {}, ensure_ascii=False),
            json.dumps(checked_order or [], ensure_ascii=False),
            json.dumps(sheet_data or {}, ensure_ascii=False),
            json.dumps(columns_map or {}, ensure_ascii=False)))


def generate_report_via_agent(project_name, report_info, sheet_data,
                              columns_map, checked_order, output_path,
                              on_log=None, agent_cfg=None):
    """LLM 编排生成报告；任何失败自动回退直接生成（不中断业务）。

    返回直接生成结果 dict，并附加 "engine"（agent/direct）与
    "fallback_reason"（回退原因，直接成功时才有）、"model"、"rounds"。
    """
    log = on_log or (lambda msg: None)
    cfg = dict(DEFAULT_AGENT_CFG)
    cfg.update(agent_cfg or {})
    reason = ""
    if cfg.get("enabled"):
        try:
            model, note = resolve_tool_model(cfg.get("base_url"),
                                             cfg.get("model"))
            log("报告代理：%s" % note)
            if not model:
                raise RuntimeError(note)
            agent = ReportToolAgent(
                cfg.get("base_url"), model,
                max_rounds=cfg.get("max_rounds", 24),
                timeout=cfg.get("timeout", 180),
                num_predict=cfg.get("num_predict", 1024),
                temperature=cfg.get("temperature", 0.2), on_log=log)
            run = agent.run(_build_task_text(
                project_name, report_info, sheet_data, columns_map,
                checked_order, output_path))
            if not run["ok"]:
                raise RuntimeError("LLM 未完成保存（%d 轮）：%s" % (
                    run["rounds"], run["final_content"][:200]))
            session = run["session"]
            log("报告代理完成：%d 轮工具调用。" % run["rounds"])
            return {"tables": session.result_tables,
                    "skipped": session.result_skipped,
                    "warnings": session.result_warnings,
                    "engine": "agent", "model": model,
                    "rounds": run["rounds"]}
        except Exception as e:
            reason = str(e)
            log("报告代理失败，回退直接生成：%s" % reason)
    res = generate_report(project_name, report_info, sheet_data, columns_map,
                          checked_order=checked_order,
                          output_path=output_path, on_log=log)
    res["engine"] = "direct"
    if reason:
        res["fallback_reason"] = reason
    return res


# ═══════════════════════════════════════════════════════════
#  命令行自检
# ═══════════════════════════════════════════════════════════
_DEMO_SHEET = {
    "回弹法检测（墙）": {
        "rows": [["1", "-1FL墙", "2-3/A-C", "C30", "35.2", "1.8", "32.4"],
                 ["2", "-1FL墙", "3-4/A-C", "C30", "34.6", "2.0", "32.8"]],
        "cols": ["序号", "构件名称", "构件轴号", "设计强度等级",
                 "平均强度值(MPa)", "标准差(MPa)", "强度推定值(MPa)"],
    },
}

_DEMO_INFO = {
    "report_no": "HBJG-2026-001",
    "project_location": "武汉市演示区演示路1号",
    "client": "演示委托单位",
    "witness": "演示见证单位",
    "tester": "张三", "writer": "李四", "checker": "王五",
    "reviewer": "赵六", "approver": "钱七",
    "test_date": "2026年09月20日~22日", "report_date": "2026年09月24日",
}


def _demo():
    import os
    import tempfile

    cfg = load_agent_cfg()
    print("report_agent 配置：base_url=%s model=%r max_rounds=%s"
          % (cfg.get("base_url"), cfg.get("model"), cfg.get("max_rounds")))
    out = os.path.join(tempfile.mkdtemp(prefix="agent_demo_"), "代理报告.docx")
    res = generate_report_via_agent(
        "代理演示工程", dict(_DEMO_INFO),
        {"回弹法检测（墙）": _DEMO_SHEET["回弹法检测（墙）"]["rows"]},
        {"回弹法检测（墙）": _DEMO_SHEET["回弹法检测（墙）"]["cols"]},
        checked_order=["回弹法检测（墙）"], output_path=out,
        on_log=lambda m: print("  ", m), agent_cfg=cfg)
    print("引擎：%s" % res.get("engine"))
    print("一览表：%d" % res["tables"])
    if res.get("fallback_reason"):
        print("回退原因：%s" % res["fallback_reason"])
    if res.get("engine") == "agent":
        print("输出：%s" % out)
    return 0 if res["tables"] >= 1 else 1


if __name__ == "__main__":
    import sys
    if "--list-models" in sys.argv:
        base = _ollama_root(load_agent_cfg().get("base_url"))
        names = list_ollama_tool_models(base, timeout=5)
        print("Ollama(%s) 支持 tools 的模型：%s" % (base, names or "（无）"))
        sys.exit(0 if names else 2)
    sys.exit(_demo())
