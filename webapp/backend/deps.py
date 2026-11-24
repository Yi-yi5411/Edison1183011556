# -*- coding: utf-8 -*-
"""Web 后端公共依赖：sys.path 引导、业务层导入、项目状态、响应包装。

所有复用 report_generator 业务层（插件/引擎/工具）的入口都在这里统一导入，
路由模块只从本模块取业务对象，保证业务层与 FastAPI 解耦。
"""

import os
import sys
import threading
from datetime import datetime

# ── sys.path 引导（参考 report_generator/main.py 的写法）──────────────
# ROOT = 项目根（structural_inspection）；webapp/backend 与 report_generator 同级两级
_BACKEND = os.path.dirname(os.path.abspath(__file__))
_WEBAPP = os.path.dirname(_BACKEND)
ROOT = os.path.dirname(_WEBAPP)
_REPORT_GEN = os.path.join(ROOT, "report_generator")
_LIBS = os.path.join(_REPORT_GEN, "libs")
for _p in (_LIBS, _REPORT_GEN, _WEBAPP, ROOT):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# ── 业务层导入（纯 Python，无 Qt 依赖）──────────────────────────────
from core.app_controller import AppController          # noqa: E402
from core.plugin_manager import get_plugin_manager as _discover_plugins  # noqa: E402
from framework.engine import CalcEngine, batch_assess  # noqa: E402
from framework.models import ITEM_COLUMNS, CALC_RULES  # noqa: E402
from utils.excel_exporter import export_workbook       # noqa: E402
from utils.word_report import generate_report          # noqa: E402
from utils.report_template_map import REPORT_INFO_FIELDS  # noqa: E402
from utils.report_templates import ReportTemplateSet     # noqa: E402
from utils.template_library import TemplateLibrary        # noqa: E402
from utils.original_record import generate_native_record  # noqa: E402
from utils.original_record_fill import (                  # noqa: E402
    fill_imported_record, inspect_docx,
)
from utils.report_edit import (                           # noqa: E402
    load_report_document, replace_report_text, save_report_document,
)
from utils.assessment_engine import (                     # noqa: E402
    assess, format_conclusion,
)
from utils.assessment_specs import get_spec, list_specs  # noqa: E402
from utils.norm_qa import (                            # noqa: E402
    NormQueryEngine, db_status, import_files, explain_clauses,
    run_batch_review, export_review_docx,
)
from scan_recognition.config import Config             # noqa: E402
from scan_recognition.storage import ScanDatabase      # noqa: E402
from scan_recognition import llm as scan_llm           # noqa: E402
from scan_recognition.matcher import available_sub_items  # noqa: E402

# ── 异常与响应包装 ────────────────────────────────────────────────


class ApiError(Exception):
    """业务异常：携带 HTTP 状态码与中文消息，由全局异常处理器输出。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def ok(data=None, message="操作成功"):
    """统一成功响应包装。"""
    return {"ok": True, "data": data, "message": message}


def fail(message, status_code=400):
    """统一失败响应（直接抛 ApiError，由全局处理器输出）。"""
    raise ApiError(message, status_code)


# ── 项目状态（全局单例，桌面版内存态的 Web 等价物）──────────────────


def clean_template_selection(raw):
    """规整模板选择结构（旧项目/脏数据容错）。"""
    raw = raw if isinstance(raw, dict) else {}
    report_id = str(raw.get("report_template_id") or "").strip()
    mapping = raw.get("original_template_map")
    clean_map = {}
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            key = str(key or "").strip()
            value = str(value or "").strip()
            if key and value:
                clean_map[key] = value
    return {
        "report_template_id": report_id,
        "original_template_map": clean_map,
    }


class ProjectState:
    """当前项目内存状态：表格数据 / 合并 / 格式 / 参数 / 抬头信息。

    与桌面版 AppController.serialize/deserialize 的字典结构一一对应，
    保存/加载直接复用业务层方法，项目文件与桌面版互通。
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.autosave_path = (
            os.environ.get("STRUCTURAL_AUTOSAVE_PATH")
            or os.path.join(ROOT, "data", "projects", "autosave.json"))
        self.autosave_enabled = True
        self.autosaved_at = None
        self._restored_autosave = False
        self.reset()
        self._restore_autosave()

    def reset(self, project_name="新建项目"):
        """清空当前项目（新建项目）。"""
        self.project_name = project_name
        self.sheet_data = {}      # {sheet_key: [[单元格,...], ...]}
        self.merges = {}          # {sheet_key: [(r, c, row_span, col_span), ...]}
        self.merge_formats = {}   # {sheet_key: {(r, c): {"align":..., "bold":...}}}
        self.cell_formats = {}    # {sheet_key: {(r, c): fmt}}
        self.cd_params = {}       # {sheet_key: 钻芯法参数}
        self.operation_notes = {}
        self.checked_items = []   # 勾选（建表）顺序的 sheet_key 列表
        self.report_info = {}     # 报告抬头字段
        self.template_selection = {  # 报告/原始记录模板选择
            "report_template_id": "",
            "original_template_map": {},
        }
        self.assessment_inputs = {}   # {sheet_key: 原始数据}
        self.assessment_options = {}  # {sheet_key: {no_drawing, table_no, ...}}
        self.assessment_results = {}  # {sheet_key: 评定结果}
        self._restored_autosave = False
        self.filepath = None      # 当前项目文件路径（缺省保存用）

    def _restore_autosave(self):
        """启动时恢复上次自动保存的项目（存在且可读时）。"""
        try:
            if not os.path.isfile(self.autosave_path):
                return
            self.load(self.autosave_path)
            self.filepath = None
            self._restored_autosave = True
            try:
                self.autosaved_at = datetime.fromtimestamp(
                    os.path.getmtime(self.autosave_path)).strftime(
                        "%Y-%m-%d %H:%M:%S")
            except Exception:  # noqa: BLE001
                self.autosaved_at = None
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("[autosave] 恢复失败，已新建空项目：%s\n" % e)
            self.reset()

    def autosave(self):
        """把当前项目原子写回：已加载项目文件写自身，否则写 autosave.json。

        切换工程时不能把目标工程写进 autosave.json，否则原工程会被覆盖。
        """
        if not self.autosave_enabled:
            return None
        target = self.autosave_path
        filepath = getattr(self, "filepath", None)
        if filepath and os.path.abspath(filepath) != os.path.abspath(self.autosave_path):
            target = filepath
        with self._lock:
            state = AppController.serialize(
                self.project_name, self.sheet_data, self.merges,
                self.merge_formats, self.cell_formats, self.cd_params,
                operation_notes=self.operation_notes,
                checked_items=self.checked_items,
                report_info=self.report_info,
                template_selection=self.template_selection,
                assessment={
                    "inputs": self.assessment_inputs,
                    "options": self.assessment_options,
                    "results": self.assessment_results,
                })
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            tmp = target + ".tmp"
            AppController.save_project_file(tmp, state)
            os.replace(tmp, target)
            self.autosaved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return target

    # ── 序列化 / 反序列化（复用 AppController）────────────────────
    def load(self, filepath):
        """从项目 JSON 文件加载。"""
        saved = AppController.load_project_file(filepath)
        (project_name, sheet_data, merges, merge_formats, cell_formats,
         cd_params, operation_notes, checked_items, report_info) = \
            AppController.deserialize(saved)
        with self._lock:
            self.project_name = project_name or "未命名项目"
            self.sheet_data = sheet_data
            self.merges = merges
            self.merge_formats = merge_formats
            self.cell_formats = cell_formats
            self.cd_params = cd_params
            self.operation_notes = operation_notes
            self.checked_items = list(checked_items or [])
            self.report_info = dict(report_info or {})
            self._restored_autosave = False
            self.template_selection = clean_template_selection(
                saved.get("template_selection"))
            assessment = saved.get("assessment")
            assessment = assessment if isinstance(assessment, dict) else {}
            self.assessment_inputs = assessment.get("inputs") or {}
            self.assessment_options = assessment.get("options") or {}
            self.assessment_results = assessment.get("results") or {}
            self.filepath = filepath

    def save(self, filepath=None):
        """保存当前项目；filepath 缺省用当前路径，再缺省落到 exports 目录。"""
        target = filepath or self.filepath
        if not target:
            from datetime import datetime
            export_dir = os.path.join(_REPORT_GEN, "exports")
            os.makedirs(export_dir, exist_ok=True)
            target = os.path.join(
                export_dir, "project_%s.json"
                % datetime.now().strftime("%Y%m%d_%H%M%S"))
        state = AppController.serialize(
            self.project_name, self.sheet_data, self.merges,
            self.merge_formats, self.cell_formats, self.cd_params,
            operation_notes=self.operation_notes,
            checked_items=self.checked_items, report_info=self.report_info,
            template_selection=self.template_selection,
            assessment={
                "inputs": self.assessment_inputs,
                "options": self.assessment_options,
                "results": self.assessment_results,
            })
        AppController.save_project_file(target, state)
        with self._lock:
            self.filepath = target
        return target

    # ── 快照输出 ─────────────────────────────────────────────────
    def sheet_snapshot(self, key):
        """单个工作表快照：columns/rows/merges/params/base_item。"""
        controller = get_controller()
        merges = self.merges.get(key, [])
        base, comp = controller.parse_sheet_key(key)
        return {
            "columns": controller.get_columns(key),
            "base_item": base,
            "component": comp,
            "rows": self.sheet_data.get(key, []),
            "merges": [list(m) for m in merges],
            "params": self.cd_params.get(key, {}),
            "assessment": {
                "options": self.assessment_options.get(key, {}),
                "result": self.assessment_results.get(key),
            },
        }

    def snapshot(self):
        """整个项目快照（GET /api/project）。"""
        sheets = {key: self.sheet_snapshot(key) for key in self.sheet_data}
        return {
            "project_name": self.project_name,
            "checked_items": list(self.checked_items),
            "sheets": sheets,
            "report_info": dict(self.report_info),
            "template_selection": clean_template_selection(
                self.template_selection),
            "assessment": {
                "options": dict(self.assessment_options),
                "results": dict(self.assessment_results),
            },
            "autosave": {
                "enabled": bool(self.autosave_enabled),
                "autosaved_at": self.autosaved_at,
                "restored": bool(self._restored_autosave),
            },
            "filepath": self.filepath,
        }

    def structured(self):
        """结构化数据导出：列头 + 二维行 + 按列头展开的记录 dict。"""
        controller = get_controller()
        sheets = {}
        for key, rows in self.sheet_data.items():
            columns = controller.get_columns(key)
            base, comp = controller.parse_sheet_key(key)
            records = []
            for row in rows or []:
                record = {}
                for i, label in enumerate(columns):
                    record[str(label)] = row[i] if i < len(row) else ""
                for j in range(len(columns), len(row)):
                    record["col%d" % (j + 1)] = row[j]
                if any(str(v).strip() for v in record.values()):
                    records.append(record)
            sheets[key] = {
                "base_item": base,
                "component": comp,
                "columns": list(columns),
                "rows": rows,
                "records": records,
                "assessment_result": self.assessment_results.get(key),
            }
        return {
            "project_name": self.project_name,
            "checked_items": list(self.checked_items),
            "report_info": dict(self.report_info),
            "template_selection": clean_template_selection(
                self.template_selection),
            "sheets": sheets,
        }

    def remove_sheet(self, key):
        """取消勾选：移除工作表全部相关状态。"""
        with self._lock:
            self.sheet_data.pop(key, None)
            self.merges.pop(key, None)
            self.merge_formats.pop(key, None)
            self.cell_formats.pop(key, None)
            self.cd_params.pop(key, None)
            self.operation_notes.pop(key, None)
            self.assessment_inputs.pop(key, None)
            self.assessment_options.pop(key, None)
            self.assessment_results.pop(key, None)
            if key in self.checked_items:
                self.checked_items.remove(key)


# ── 全局单例访问 ──────────────────────────────────────────────────

_project_state = None
_controller = None
_plugin_manager = None
_template_library = None
_template_library_lock = threading.Lock()
_record_store = None
_wiki_store = None
_store_lock = threading.Lock()


def get_state():
    """当前项目状态单例。"""
    global _project_state
    if _project_state is None:
        _project_state = ProjectState()
    return _project_state


def get_controller():
    """AppController 单例（承载业务层查询与序列化）。"""
    global _controller
    if _controller is None:
        _controller = AppController()
    return _controller


def get_plugin_manager():
    """插件管理器单例（启动时自动发现 modules 下全部检测项目插件）。"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = _discover_plugins()
    return _plugin_manager


def get_report_gen_dir():
    """report_generator 目录绝对路径（导出缺省位置等）。"""
    return _REPORT_GEN


def get_template_library():
    """模板库单例（报告模板 + 原始记录模板）。"""
    global _template_library
    if _template_library is None:
        with _template_library_lock:
            if _template_library is None:
                _template_library = TemplateLibrary()
    return _template_library


def get_original_record_dir():
    """原始记录缺省输出目录（original_record/word/generated）。"""
    out = os.path.join(ROOT, "original_record", "word", "generated")
    os.makedirs(out, exist_ok=True)
    return out


def get_record_store():
    """报告记录库 / 原始记录库单例（首次访问时建表并迁移旧 JSON）。"""
    global _record_store
    if _record_store is None:
        with _store_lock:
            if _record_store is None:
                from utils import record_store as _rs
                _rs.ensure_schema()
                _record_store = _rs
    return _record_store


def get_wiki_store():
    """LLM Wiki 知识库单例（首次访问时建表并写入内置种子）。"""
    global _wiki_store
    if _wiki_store is None:
        with _store_lock:
            if _wiki_store is None:
                from utils import wiki_store as _ws
                _ws.ensure_schema()
                _wiki_store = _ws
    return _wiki_store


# ── 列定义转换（插件列配置 → API 契约结构）────────────────────────


def _col_width(label):
    """根据列头文字长度估算列宽（像素）。"""
    text = str(label or "")
    width = 14 * (len(text) + 4) + 20
    return max(70, min(240, width))


def plugin_payload(plugin, source="builtin"):
    """把插件对象转换为 /api/plugins 契约结构。

    columns 为该插件全部子检测项列定义的扁平列表（含 sub_item 分组标记），
    calc 标记该列是否为自动计算目标列（CalcEngine 计算列）。
    """
    subs = plugin.columns()
    types = plugin.column_types()
    rules = plugin.calc_rules()
    calc_targets = {}
    for sub, rule_map in rules.items():
        calc_targets[sub] = set()
        for k in (rule_map or {}):
            try:
                calc_targets[sub].add(int(k))
            except (TypeError, ValueError):
                continue
    # 桌面版 _get_computed_columns 中由模块汇总逻辑写入、但不在
    # CALC_RULES 里的列；Web 端同样锁定，避免手工覆盖计算结果。
    summary_columns = {
        "剪力墙构件钢筋间距检测": {19, 20},
        "现浇板钢筋间距检测": {19, 20},
        "楼板构件厚度检测": {13, 14},
        "剪力墙厚度检测": {12, 13},
        "混凝土梁保护层厚度检测": {25},
        "混凝土柱保护层厚度检测": {25},
        "剪力墙保护层厚度检测": {25},
        "混凝土板保护层厚度检测": {25},
        "钻芯法检测": {7, 9, 10, 11},
        "回弹钻芯修正法检测": {7, 9, 11},
    }

    columns = []
    sub_items = []
    for sub, headers in subs.items():
        tlist = types.get(sub, [])
        sub_calc = set(calc_targets.get(sub, set())) | summary_columns.get(sub, set())
        for i, header in enumerate(headers):
            is_calc = i in sub_calc
            columns.append({
                "key": str(header),
                "label": str(header),
                "type": tlist[i] if i < len(tlist) else "string",
                "width": _col_width(header),
                "editable": not is_calc,
                "calc": is_calc,
                "sub_item": sub,
                "index": i,
            })
        sub_items.append({"name": sub, "columns": [str(h) for h in headers]})

    setup_items = [s for s in subs if plugin.requires_setup_dialog(s)]
    # 砖回弹表的构件/测区布局由前端参数对话框生成；桌面插件未声明
    # requires_setup_dialog 时，Web 端仍需把它标记为需要设置参数。
    if plugin.plugin_id == "brick_strength" and "砖强度检测" not in setup_items:
        setup_items.append("砖强度检测")
    return {
        "id": plugin.plugin_id,
        "name": plugin.display_name,
        "structure_type": plugin.structure_type,
        "tree_order": int(getattr(plugin, "tree_order", 0) or 0),
        "requires_setup": bool(setup_items),
        "setup_items": setup_items,
        "columns": columns,
        "sub_items": sub_items,
        "tree": plugin.tree_entries(),
        "calc_rules": rules,
        "source": source,
        "external": source == "external",
    }
