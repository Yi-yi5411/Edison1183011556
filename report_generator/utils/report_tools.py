# -*- coding: utf-8 -*-
"""《检测报告》处理过程函数 → 大模型工具封装（无第三方依赖，py3.8 安全）。

把 report_chapters / report_format / word_report 的过程函数包装成
LLM 工具（OpenAI/Ollama tools 格式的 JSON Schema + 会话分发器），
大模型按工作流逐步调用即可生成完整报告；工具结果为结构化中文
摘要，供模型推理下一步。

三件套：
  - TOOL_DEFINITIONS    工具清单（直接传入 Ollama /api/chat 的 tools）
  - ReportToolSession   会话：持有工作文档与数据，逐步执行并校验顺序
  - execute_tool        分发器：execute_tool(session, name, args)

标准工作流（build_system_prompt() 可直接作为系统提示词）::

    start_report → append_home_page → append_chapter(overview/basis/
    equipment/content) → append_results → append_conclusion →
    fill_toc → format_report(可选) → save_report

接入 LangGraph/LangChain 时可用 ``as_langchain_tools(session)``
（内部延迟导入，未安装 langchain-core 时返回 None，可回退到
execute_tool 分发）。
"""
import json

try:
    from report_generator.utils import report_chapters as chapters
    from report_generator.utils.report_docx import _fill_page_count_via_com
    from report_generator.utils.report_format import (apply_report_format,
                                                      describe_format)
    from report_generator.utils.word_report import generate_report
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils import report_chapters as chapters
    from utils.report_docx import _fill_page_count_via_com
    from utils.report_format import apply_report_format, describe_format
    from utils.word_report import generate_report


# ═══════════════════════════════════════════════════════════
#  工具清单（OpenAI / Ollama tools 格式）
# ═══════════════════════════════════════════════════════════
_INFO_FIELDS_DESC = (
    "抬头信息对象，键：report_no(报告编号)、project_name(工程名称)、"
    "project_location(工程地点)、client(委托单位)、witness(见证单位)、"
    "tester(检测人)、writer(报告编写人)、checker(复核人)、"
    "reviewer(审核人)、approver(批准人)、test_date(检测日期区间)、"
    "report_date(报告日期，默认今天)；缺省键留空处理")

_TOOL_SPECS = [
    ("start_report", "开始生成《检测报告》：加载封面基准文档并填充封面（工程名称、报告日期、人员信息）。此后才能调用其余报告工具。",
     {"project_name": {"type": "string", "description": "工程名称（抬头缺省值，必填）"},
      "report_info": {"type": "object", "description": _INFO_FIELDS_DESC},
      "checked_order": {"type": "array", "items": {"type": "string"},
                        "description": "参与报告的工作表键顺序（建表顺序），如 [\"回弹法检测（墙）\"]"},
      "sheet_data": {"type": "object", "description": "检测数据 {工作表键: [[值,...],...]}"},
      "columns_map": {"type": "object", "description": "列头 {工作表键: [列头,...]}"}},
     ["project_name"]),

    ("append_home_page", "拼装首页（含目录页模板）：回填工程名称/地点/委托单位/见证单位信息表。须在 start_report 之后调用。",
     {}, []),

    ("append_chapter", "拼装正文章节。须按 overview → basis → equipment → content 顺序逐个调用；content 会自动追加检测项目清单。",
     {"chapter_name": {"type": "string", "enum": ["overview", "basis", "equipment", "content"],
                       "description": "overview=一、工程概况；basis=二、主要检测依据；equipment=三、主要检测设备；content=四、检测内容"}},
     ["chapter_name"]),

    ("append_results", "拼装五、检测结果：概述（含检测日期区间）+ 按勾选顺序逐项目填充结果一览表，并按规则推理收集各项目结论句（推定值与设计等级比对）。须在四、检测内容之后调用。",
     {}, []),

    ("append_conclusion", "拼装六、检测结论：把 append_results 收集的结论句插入正文真标题之后（自动跳过目录条目）。须在 append_results 之后调用。",
     {}, []),

    ("fill_toc", "目录收口：回填目录中的检测项目清单，并统一替换全文残留占位符（工程名称/清单/报告日期）。须在 append_conclusion 之后调用。",
     {}, []),

    ("format_report", "可选统一排版：页脚页码域、页面设置、正文字体字号、表格字体。各开关默认关闭（保持模板自带排版）。须在 fill_toc 之后、save_report 之前调用；可整体跳过。",
     {"page_number_footer": {"type": "boolean", "description": "给无页脚的节添加\"第 X 页 共 Y 页\"页码域"},
      "page_setup": {"type": "boolean", "description": "统一 A4 页面与标准页边距"},
      "fonts": {"type": "boolean", "description": "统一正文字体（章标题黑体三号加粗）"},
      "table_fonts": {"type": "boolean", "description": "统一表格字体（五号宋体）"}},
     []),

    ("describe_report", "查看当前报告进度：已完成步骤、表格总数、结论句数、各节页面/页脚概览。任何时刻可调用，用于推理下一步。",
     {}, []),

    ("save_report", "保存 .docx 并做 COM 页数回填（{page} 占位符），返回最终摘要。须在 fill_toc 之后调用。",
     {"output_path": {"type": "string", "description": "输出 .docx 完整路径（必填）"}},
     ["output_path"]),

    ("generate_report_once", "一次性生成完整报告（不走逐步编排）：等价于以上全部步骤按标准顺序执行。适合无需模型介入编排的场景。",
     {"project_name": {"type": "string", "description": "工程名称（必填）"},
      "report_info": {"type": "object", "description": _INFO_FIELDS_DESC},
      "sheet_data": {"type": "object", "description": "检测数据 {工作表键: [[值,...],...]}（必填）"},
      "columns_map": {"type": "object", "description": "列头 {工作表键: [列头,...]}（必填）"},
      "checked_order": {"type": "array", "items": {"type": "string"}, "description": "工作表键顺序（必填）"},
      "output_path": {"type": "string", "description": "输出 .docx 路径（必填）"},
      "format_options": {"type": "object", "description": "可选排版参数，键同 format_report 参数"}},
     ["project_name", "sheet_data", "columns_map", "checked_order", "output_path"]),
]

TOOL_DEFINITIONS = [
    {"type": "function",
     "function": {"name": name, "description": desc,
                  "parameters": {"type": "object",
                                 "properties": props,
                                 "required": required}}}
    for name, desc, props, required in _TOOL_SPECS
]

_SYSTEM_PROMPT = (
    "你是检测报告生成助手，通过调用工具逐步生成《检测报告》.docx。\n"
    "必须严格按以下顺序调用（不可跳步、不可重复）：\n"
    "1. start_report（封面）→ 2. append_home_page（首页）→ "
    "3. append_chapter：依次 overview、basis、equipment、content → "
    "4. append_results（结果一览表+结论句）→ 5. append_conclusion → "
    "6. fill_toc（目录收口）→ 7. format_report（可选）→ 8. save_report。\n"
    "不确定下一步时先调用 describe_report 查看进度。乱序或重复调用会被拒绝，"
    "请根据返回 message 中的 next_step 修正后再调用。")


def build_system_prompt():
    """返回描述工具工作流的系统提示词片段。"""
    return _SYSTEM_PROMPT


def tool_schemas(names=None):
    """按名称筛选工具 Schema（缺省返回全部）。"""
    if names is None:
        return list(TOOL_DEFINITIONS)
    keep = set(names)
    return [t for t in TOOL_DEFINITIONS if t["function"]["name"] in keep]


# ═══════════════════════════════════════════════════════════
#  会话：持有工作文档与数据，逐步执行
# ═══════════════════════════════════════════════════════════
# 章节固定顺序（append_chapter 的 chapter_name 依次校验）
_CHAPTER_ORDER = ["overview", "basis", "equipment", "content"]


class ReportToolSession(object):
    """一次报告生成的工具会话：持有基准文档与数据，供 LLM 逐步调用。"""

    def __init__(self):
        self.doc = None               # 基准 Document（start 后非空）
        self.info = {}
        self.checked_order = []
        self.sheet_data = {}
        self.columns_map = {}
        self.sentences = []           # append_results 收集的结论句
        self.result_tables = 0        # 结果一览表数量
        self.result_warnings = []
        self.result_skipped = []
        self.done_steps = []          # 已完成步骤（有序、唯一）
        self.chapter_cursor = 0       # append_chapter 进度（0~4）
        self.logs = []

    # ── 内部工具 ──
    def _log(self, msg):
        self.logs.append(str(msg))

    def _result(self, ok, message, **data):
        payload = {"ok": bool(ok), "message": message,
                   "done_steps": list(self.done_steps)}
        payload.update(data)
        return payload

    def next_step(self):
        """按标准工作流推荐下一步（供模型推理）。"""
        if self.doc is None or "start_report" not in self.done_steps:
            return "start_report"
        if "append_home_page" not in self.done_steps:
            return "append_home_page"
        if self.chapter_cursor < len(_CHAPTER_ORDER):
            return "append_chapter(%s)" % _CHAPTER_ORDER[self.chapter_cursor]
        if "append_results" not in self.done_steps:
            return "append_results"
        if "append_conclusion" not in self.done_steps:
            return "append_conclusion"
        if "fill_toc" not in self.done_steps:
            return "fill_toc"
        if "format_report" not in self.done_steps:
            return "format_report(可选)"
        if "save_report" not in self.done_steps:
            return "save_report"
        return "（全部完成）"

    def _check_prereq(self, name):
        """步骤前置校验；不满足时返回拒绝结果（供模型推理修正）。"""
        done = self.done_steps
        need = []
        if name == "append_home_page":
            if "start_report" not in done:
                need = ["start_report"]
        elif name == "append_chapter":
            if "start_report" not in done:
                need = ["start_report"]
            elif self.chapter_cursor >= len(_CHAPTER_ORDER):
                return self._result(
                    False, "调用被拒绝：四个章节已全部拼装完成，请勿重复调用。",
                    next_step=self.next_step())
        elif name == "append_results":
            if "start_report" not in done:
                need = ["start_report"]
            elif self.chapter_cursor < len(_CHAPTER_ORDER):
                need = ["append_chapter(content)"]
        elif name == "append_conclusion":
            if "append_results" not in done:
                need = ["append_results"]
        elif name == "fill_toc":
            if "append_conclusion" not in done:
                need = ["append_conclusion"]
        elif name == "format_report":
            if "fill_toc" not in done:
                need = ["fill_toc"]
        elif name == "save_report":
            if "fill_toc" not in done:
                need = ["fill_toc"]
        if need:
            return self._result(
                False, "调用被拒绝：须先完成 %s。" % "、".join(need),
                next_step=self.next_step())
        if name in done and name != "append_chapter":  # 章节重复由 cursor 校验
            return self._result(
                False, "调用被拒绝：%s 已完成，请勿重复调用。" % name,
                next_step=self.next_step())
        return None

    # ── 工具实现（方法名 = 工具名）──
    def start_report(self, project_name, report_info=None, checked_order=None,
                     sheet_data=None, columns_map=None, **_):
        self.info = dict(report_info or {})
        if not str(self.info.get("project_name") or "").strip():
            self.info["project_name"] = project_name
        self.checked_order = list(checked_order or [])
        self.sheet_data = dict(sheet_data or {})
        self.columns_map = dict(columns_map or {})
        self.doc = chapters.Document(str(chapters.chapter_path("cover_main")))
        chapters.build_cover(self.doc, self.info)
        self.done_steps.append("start_report")
        self._log("封面已填充")
        return self._result(
            True, "封面完成：工程名称《%s》，报告日期 %s。" % (
                self.info.get("project_name") or "",
                self.info.get("report_date") or "（空，待目录收口）"),
            next_step=self.next_step())

    def append_home_page(self, **_):
        chapters.build_home(self.doc, self.info)
        self.done_steps.append("append_home_page")
        return self._result(True, "首页完成：信息表已回填。",
                            next_step=self.next_step())

    def append_chapter(self, chapter_name, **_):
        if chapter_name not in _CHAPTER_ORDER:
            return self._result(False, "未知章节 %r，可选：%s。" % (
                chapter_name, "、".join(_CHAPTER_ORDER)),
                next_step=self.next_step())
        expect = _CHAPTER_ORDER[self.chapter_cursor]
        if chapter_name != expect:
            return self._result(
                False, "章节须按序拼装：当前应调用 append_chapter(%s)。" % expect,
                next_step=self.next_step())
        if chapter_name == "overview":
            chapters.build_overview(self.doc, self.info)
        elif chapter_name == "basis":
            chapters.build_basis(self.doc)
        elif chapter_name == "equipment":
            chapters.build_equipment(self.doc)
        else:
            chapters.build_content(self.doc, self.checked_order)
        self.chapter_cursor += 1
        if "append_chapter" not in self.done_steps:
            self.done_steps.append("append_chapter")
        label = {"overview": "一、工程概况", "basis": "二、主要检测依据",
                 "equipment": "三、主要检测设备",
                 "content": "四、检测内容"}[chapter_name]
        return self._result(True, "%s 已拼装。" % label,
                            next_step=self.next_step())

    def append_results(self, **_):
        res = chapters.build_results(
            self.doc, self.info, self.checked_order,
            self.sheet_data, self.columns_map, on_log=self._log)
        self.sentences = res["sentences"]
        self.result_tables = res["tables"]
        self.result_warnings = res["warnings"]
        self.result_skipped = res["skipped"]
        self.done_steps.append("append_results")
        return self._result(
            True, "五、检测结果完成：生成 %d 张一览表，收集 %d 条结论句。" % (
                res["tables"], len(self.sentences)),
            tables=res["tables"], skipped=res["skipped"],
            warnings=res["warnings"], sentences=self.sentences,
            next_step=self.next_step())

    def append_conclusion(self, **_):
        chapters.build_conclusion(self.doc, self.sentences)
        self.done_steps.append("append_conclusion")
        return self._result(
            True, "六、检测结论完成：插入 %d 条结论句。" % len(self.sentences),
            next_step=self.next_step())

    def fill_toc(self, **_):
        chapters.build_toc(self.doc, self.checked_order, self.info)
        self.done_steps.append("fill_toc")
        return self._result(True, "目录收口完成：清单与残留占位符已替换。",
                            next_step=self.next_step())

    def format_report(self, page_number_footer=False, page_setup=False,
                      fonts=False, table_fonts=False, **_):
        applied = apply_report_format(
            self.doc, page_setup=page_setup,
            page_number_footer=page_number_footer,
            fonts=fonts, table_fonts=table_fonts)
        self.done_steps.append("format_report")
        msg = "；".join(applied) if applied else "未启用任何排版开关（保持模板排版）。"
        return self._result(True, "统一排版：%s" % msg, applied=applied,
                            next_step=self.next_step())

    def describe_report(self, **_):
        lines = describe_format(self.doc) if self.doc is not None else []
        return self._result(
            True, "进度：%s；推荐下一步：%s。" % (
                "、".join(self.done_steps) or "（未开始）",
                self.next_step()),
            done_steps=list(self.done_steps),
            chapter_cursor=self.chapter_cursor,
            total_tables=len(self.doc.tables) if self.doc is not None else 0,
            result_tables=self.result_tables,
            sentences=len(self.sentences), format_overview=lines,
            next_step=self.next_step())

    def save_report(self, output_path, **_):
        self.doc.save(str(output_path))
        _fill_page_count_via_com(output_path)
        self.done_steps.append("save_report")
        return self._result(
            True, "报告已保存：%s（结果一览表 %d 张）。" % (
                output_path, self.result_tables),
            output_path=str(output_path), tables=self.result_tables)


# ═══════════════════════════════════════════════════════════
#  分发器
# ═══════════════════════════════════════════════════════════
def execute_tool(session, name, arguments=None):
    """LLM 工具调用统一入口：execute_tool(session, name, args)。

    返回结构化 dict（ok/message/...）；异常捕获为 ok=False 的结果，
    模型可依据 message 自行修正。顺序违规会被拒绝并附 next_step。
    """
    arguments = dict(arguments or {})
    if name == "generate_report_once":
        try:
            res = generate_report(
                arguments.get("project_name", ""),
                arguments.get("report_info") or {},
                arguments.get("sheet_data") or {},
                arguments.get("columns_map") or {},
                checked_order=arguments.get("checked_order") or [],
                output_path=arguments.get("output_path"),
                format_options=arguments.get("format_options"))
            return {"ok": True, "message": "报告已生成：%s（%d 张一览表）。" % (
                arguments.get("output_path"), res["tables"]), **res}
        except Exception as e:
            return {"ok": False, "message": "生成失败：%s" % e}
    fn = getattr(session, name, None)
    if not callable(fn):
        return {"ok": False, "message": "未知工具 %r。" % name}
    if name != "describe_report":
        refused = session._check_prereq(name)
        if refused is not None:
            return refused
    try:
        return fn(**arguments)
    except Exception as e:
        return {"ok": False, "message": "工具 %s 执行失败：%s" % (name, e)}


def as_langchain_tools(session):
    """可选：转换为 LangChain StructuredTool 列表（延迟导入）。

    供 LangGraph ToolNode 等框架使用；未安装 langchain-core/pydantic
    时返回 None（调用方回退到 execute_tool 分发）。
    """
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return None

    tools = []
    for spec in TOOL_DEFINITIONS:
        fname = spec["function"]["name"]
        model = _json_schema_to_pydantic(fname, spec["function"]["parameters"])
        if model is None:
            continue

        def _call(_name=fname, _session=session, **kw):
            return json.dumps(execute_tool(_session, _name, kw),
                              ensure_ascii=False)

        tools.append(StructuredTool.from_function(
            func=_call, name=fname,
            description=spec["function"]["description"], args_schema=model))
    return tools


def _json_schema_to_pydantic(name, schema):
    """极简 JSON Schema → pydantic 模型（失败返回 None）。"""
    try:
        from pydantic import Field, create_model
    except ImportError:
        return None
    type_map = {"string": str, "boolean": bool, "number": float,
                "integer": int, "array": list, "object": dict}
    fields = {}
    for prop, meta in (schema.get("properties") or {}).items():
        typ = type_map.get(meta.get("type", "string"), str)
        required = prop in (schema.get("required") or [])
        desc = meta.get("description", "")
        if required:
            fields[prop] = (typ, Field(..., description=desc))
        else:
            fields[prop] = ((typ, None), Field(None, description=desc))
    try:
        return create_model("Args_" + name, **fields)
    except Exception:
        return None
