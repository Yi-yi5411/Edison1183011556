# -*- coding: utf-8 -*-
"""统一采集入口（P2）：一份文件进来，先认检测项目，再决定怎么落库。

职责边界：
- 本模块只做「格式识别 + 表头匹配 + 调用既有导入逻辑」，不重写解析与计算；
- 落库统一走 sheet_apply.apply_rows_to_sheet（与 sheets 路由同一份实现）；
- OCR/扫描件不在这里跑，只识别为 scan 类型并提示走 scan_submit。

入口：
- classify_file(path, sheet_name=None)  → 只读识别，返回候选检测项目与列匹配情况
- import_into_sheet(path, sheet_key, ...) → 直接导入到指定工作表
"""
import os
import re
import shutil
import subprocess
import tempfile
import time

from deps import (ITEM_COLUMNS, ROOT, assess, get_controller, get_plugin_manager,
                  get_spec, get_state)
from framework.models import DETECTION_DATA
import sheet_logic
from sheet_apply import apply_rows_to_sheet
from utils.excel_import import (ExcelImportError, find_header_row,
                                import_sheet_rows, match_headers, read_rows)

TABLE_FORMATS = (".xlsx", ".xlsm", ".csv", ".docx")
KNOWLEDGE_FORMATS = (".md", ".markdown", ".txt")
SCAN_FORMATS = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
DOC_FORMATS = (".doc",)

# 构件关键词：用于从数据里猜构件（文件表头通常不带构件维度）
COMPONENT_WORDS = ("剪力墙", "梁", "柱", "板", "基础", "墙")

try:  # manifest 可选：老部署没有 structural_items 时退回插件判断
    from structural_items import param_specs as _manifest_param_specs
    from structural_items import normalize_params as _normalize_params
except ImportError:  # noqa: BLE001
    _manifest_param_specs = None
    _normalize_params = None

# 老插件没有 manifest 参数定义时，沿用钻芯法对话框的兼容字段
_FALLBACK_SETUP_SPECS = [
    {"key": "building", "label": "楼栋", "type": "string"},
    {"key": "components", "label": "构件数", "type": "int"},
    {"key": "samples_per_component", "label": "每构件芯样数", "type": "int"},
    {"key": "sample_start", "label": "芯样起始编号", "type": "int"},
    {"key": "grade", "label": "设计强度等级", "type": "string"},
    {"key": "diameter", "label": "芯样直径(mm)", "type": "float"},
]


def _resolve_input_path(path):
    """把接口传入的相对路径按项目根解析，避免依赖后端进程 cwd。"""
    text = str(path or "").strip()
    if not text:
        raise IngestError("缺少文件路径")
    if not os.path.isabs(text):
        text = os.path.join(ROOT, text)
    return os.path.abspath(text)


def _setup_specs(base):
    """返回 (是否需要参数, 参数定义)。manifest 优先，插件判断兜底。"""
    specs = []
    if _manifest_param_specs is not None:
        try:
            specs = list(_manifest_param_specs(base) or [])
        except Exception:  # noqa: BLE001 - manifest 损坏不应阻断识别
            specs = []
    if specs:
        return True, specs
    try:
        needs = bool(get_controller().requires_setup_dialog(base))
    except Exception:  # noqa: BLE001
        needs = False
    return (True, list(_FALLBACK_SETUP_SPECS)) if needs else (False, [])


def _clean_assessment_options(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "no_drawing": bool(raw.get("no_drawing")),
        "table_no": str(raw.get("table_no") or "1").strip() or "1",
        "include_component_stats": bool(raw.get("include_component_stats")),
    }


def assess_imported_sheet(sheet_key):
    """导入后立即按当前行数据评定，写回 state；失败不阻断导入。"""
    state = get_state()
    controller = get_controller()
    try:
        base, comp = controller.parse_sheet_key(sheet_key)
        base = controller.resolve_item_name(base) or base
        spec = get_spec(base)
        if spec is None:
            return {"ok": False,
                    "errors": ["未找到“%s”的评定规则" % base]}
        columns = controller.get_columns(sheet_key)
        rows = state.sheet_data.get(sheet_key) or []
        options = _clean_assessment_options(
            state.assessment_options.get(sheet_key) or {})
        result = assess(sheet_key, base, comp, columns, rows,
                        options=options,
                        raw_input=state.assessment_inputs.get(sheet_key))
        state.assessment_options[sheet_key] = options
        state.assessment_results[sheet_key] = result
        return result
    except Exception as e:  # noqa: BLE001 - 评定失败由前端提示，不丢已导入数据
        return {"ok": False, "errors": [str(e)]}


# 转换出来的 .docx 放在项目内的临时目录，便于排查且不污染系统临时区
_TMP_ROOT = os.path.join(ROOT, "data", "tmp", "ingest")


class IngestError(Exception):
    """可读的导入失败原因（路由层转 400）。"""


def _prune_temp(max_age_seconds=24 * 3600):
    """清理一天前的转换临时目录，避免 .doc 转换产物堆积。"""
    try:
        now = time.time()
        for name in os.listdir(_TMP_ROOT):
            path = os.path.join(_TMP_ROOT, name)
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        return


def _temp_dir():
    os.makedirs(_TMP_ROOT, exist_ok=True)
    _prune_temp()
    return tempfile.mkdtemp(prefix="doc_", dir=_TMP_ROOT)


# ── .doc → .docx ──────────────────────────────────────────
def _convert_with_com(source, target):
    """用本机 Word/WPS 转换（后端进程内可用时最快）。"""
    try:
        import pythoncom
        import win32com.client
    except Exception:  # noqa: BLE001
        return False
    com_ready = False
    app = None
    try:
        pythoncom.CoInitialize()
        com_ready = True
        for prog_id in ("Word.Application", "Kwps.Application",
                        "wps.Application"):
            try:
                app = win32com.client.DispatchEx(prog_id)
                break
            except Exception:  # noqa: BLE001
                continue
        if app is None:
            return False
        doc = app.Documents.Open(os.path.abspath(source))
        try:
            doc.SaveAs2(target, FileFormat=16)  # wdFormatDocumentDefault
        finally:
            doc.Close(False)
        return os.path.isfile(target)
    except Exception:  # noqa: BLE001
        return False
    finally:
        try:
            if app is not None:
                app.Quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            if com_ready:
                pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


def _find_soffice():
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for path in (
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if os.path.isfile(path):
            return path
    return ""


def _convert_with_soffice(source, target):
    soffice = _find_soffice()
    if not soffice:
        return False
    out_dir = os.path.dirname(target)
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "docx",
             "--outdir", out_dir, os.path.abspath(source)],
            timeout=120, capture_output=True, check=False)
    except Exception:  # noqa: BLE001
        return False
    return os.path.isfile(target)


def ensure_docx(path):
    """把 .doc 就地转成 .docx（放在临时目录），返回 (可读路径, 警告列表)。"""
    ext = os.path.splitext(str(path))[1].lower()
    if ext not in DOC_FORMATS:
        return path, []
    if not os.path.isfile(path):
        raise IngestError("文件不存在：%s" % path)
    tmp = _temp_dir()
    stem = os.path.splitext(os.path.basename(path))[0]
    target = os.path.join(tmp, stem + ".docx")
    if _convert_with_com(path, target) or _convert_with_soffice(path, target):
        return target, ["已将 .doc 转换为 .docx 后解析（临时文件）"]
    raise IngestError(
        "无法解析 .doc：本机未检测到可用的 Word/WPS/LibreOffice 转换器，"
        "请另存为 .docx 后重试")


# ── 候选工作表 ────────────────────────────────────────────
def candidate_sheets():
    """所有可导入的工作表候选（检测项目 × 构件），带列定义与参数要求。"""
    out = []
    setup_cache = {}
    for plugin in get_plugin_manager().all_plugins():
        columns_by_item = plugin.columns() or {}
        for item, comps in (plugin.tree_entries() or {}).items():
            columns = list(columns_by_item.get(item)
                           or ITEM_COLUMNS.get(item) or [])
            if not columns:
                continue
            if item not in setup_cache:
                setup_cache[item] = _setup_specs(item)
            requires_setup, param_specs = setup_cache[item]
            if comps:
                for comp in comps:
                    out.append({
                        "item": item,
                        "component": comp,
                        "sheet_key": "%s（%s）" % (item, comp),
                        "structure_type": plugin.structure_type,
                        "columns": columns,
                        "requires_setup": requires_setup,
                        "param_specs": list(param_specs),
                    })
            else:
                out.append({
                    "item": item,
                    "component": "",
                    "sheet_key": item,
                    "structure_type": plugin.structure_type,
                    "columns": columns,
                    "requires_setup": requires_setup,
                    "param_specs": list(param_specs),
                })
    return out


def _guess_component(rows, header_index, comps):
    """从数据前若干行里猜构件类型（文件中通常不带构件维度）。"""
    if not comps:
        return ""
    counter = {}
    for row in rows[header_index + 1: header_index + 21]:
        text = " ".join(str(v) for v in row)
        for comp in comps:
            if comp and comp in text:
                counter[comp] = counter.get(comp, 0) + 1
    if not counter:
        return ""
    return max(counter.items(), key=lambda kv: kv[1])[0]


def _match_candidates(rows, limit=5):
    """用统一定价：命中列数优先、命中率次之，同一检测项目只留最佳构件。"""
    best = {}
    all_candidates = candidate_sheets()
    for cand in all_candidates:
        try:
            header_index = find_header_row(rows, cand["columns"])
        except ExcelImportError:
            continue
        mapping = match_headers(rows[header_index], cand["columns"])
        matched = len(mapping)
        if matched < 2:
            continue
        total = len(cand["columns"]) or 1
        score = round(matched / float(total), 3)
        missing = [c for i, c in enumerate(cand["columns"])
                   if i not in mapping]
        entry = {
            "item": cand["item"],
            "structure_type": cand["structure_type"],
            "sheet_key": cand["sheet_key"],
            "component": cand["component"],
            "component_guess": "",
            "matched": matched,
            "total_columns": total,
            "score": score,
            "header_index": header_index,
            "missing_columns": missing[:8],
            "requires_setup": bool(cand.get("requires_setup")),
            "param_specs": list(cand.get("param_specs") or []),
        }
        key = cand["item"]
        current = best.get(key)
        if current is None or (entry["matched"], entry["score"]) > (
                current["matched"], current["score"]):
            best[key] = entry
    result = sorted(best.values(),
                    key=lambda x: (-x["matched"], -x["score"],
                                   x["total_columns"]))
    for entry in result[:limit]:
        item_cands = [c for c in all_candidates if c["item"] == entry["item"]]
        comps = sorted({c["component"] for c in item_cands if c["component"]},
                       key=len, reverse=True)
        entry["components"] = comps
        entry["sheet_keys"] = [c["sheet_key"] for c in item_cands]
        if entry["component"]:
            guess = _guess_component(rows, entry["header_index"], comps)
            if guess:
                entry["component_guess"] = guess
                entry["sheet_key"] = "%s（%s）" % (entry["item"], guess)
    return result[:limit]


def detect_assessment_family(headers):
    """回弹原始记录类文件的判定：含「测区」= 回弹；再加「芯样」= 回弹钻芯修正。"""
    text = "".join(str(h) for h in headers)
    if "测区" not in text:
        return ""
    if "芯样" in text:
        return "rebound_core"
    return "rebound"


# ── 对外入口 ──────────────────────────────────────────────
def classify_file(path, sheet_name=None):
    """识别一份文件：类型、检测项目候选、表头与预览。只读，不改工程。"""
    path = _resolve_input_path(path)
    if not os.path.isfile(path):
        raise IngestError("文件不存在：%s" % path)
    ext = os.path.splitext(path)[1].lower()
    warnings = []
    converted_from = ""

    if ext in KNOWLEDGE_FORMATS:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(2000)
        return {
            "filepath": path, "format": ext, "kind": "knowledge",
            "converted_from": "", "warnings": [],
            "preview_text": text[:600],
            "next": {"tool": "import_wiki_files",
                     "hint": "知识/规范文本请用 import_wiki_files 或 import_norms"},
        }

    if ext in SCAN_FORMATS:
        return {
            "filepath": path, "format": ext, "kind": "scan",
            "converted_from": "", "warnings": [],
            "next": {"tool": "scan_submit",
                     "hint": "扫描件/图片需要 OCR 流水线，提交后轮询 scan_job"},
        }

    if ext in DOC_FORMATS:
        converted_from = ".doc"
        path, convert_warnings = ensure_docx(path)
        warnings.extend(convert_warnings)
        ext = ".docx"
    elif ext not in TABLE_FORMATS:
        raise IngestError(
            "不支持的文件类型：%s（支持 %s）"
            % (ext, " / ".join(TABLE_FORMATS + KNOWLEDGE_FORMATS
                               + SCAN_FORMATS + DOC_FORMATS)))

    try:
        rows = read_rows(path, sheet_name or None)
    except ExcelImportError as e:
        raise IngestError(str(e))

    if not rows:
        raise IngestError("文件为空：%s" % os.path.basename(path))
    candidates = _match_candidates(rows)
    header_index = candidates[0]["header_index"] if candidates else 0
    headers = rows[header_index] if header_index < len(rows) else []
    filled = [r for r in rows[header_index + 1:]
              if any(str(v).strip() for v in r)]
    return {
        "filepath": path,
        "format": ext,
        "kind": "table",
        "converted_from": converted_from,
        "warnings": warnings,
        "table": {
            "rows": len(filled),
            "columns": len([h for h in headers if str(h).strip()]),
            "sheet_name": sheet_name or "",
        },
        "header": [str(h) for h in headers],
        "preview": [[str(v) for v in r[:12]] for r in filled[:3]],
        "candidates": candidates,
        "suggested_sheet_key": candidates[0]["sheet_key"] if candidates else "",
        "assessment_family": detect_assessment_family(headers),
    }


def import_into_sheet(path, sheet_key, sheet_name=None, append=False,
                      auto_assess=True, params=None):
    """把文件导入指定工作表：按表头匹配 + 立即重算 + 自动勾选/评定。

    需要采集参数的项目（钻芯法等）必须先由 project/check_item 建好结构化
    空表；这里只校验，不重复构建，避免把参数表覆盖成普通行数据。
    """
    if not str(sheet_key or "").strip():
        raise IngestError("sheet_key 不能为空")
    path = _resolve_input_path(path)
    if not os.path.isfile(path):
        raise IngestError("文件不存在：%s" % path)
    path, warnings = ensure_docx(path)
    controller = get_controller()
    columns = controller.get_columns(sheet_key)
    if not columns:
        raise IngestError("工作表不存在或没有列定义：%s（先 list_detection_items 核对键名）"
                          % sheet_key)
    state = get_state()
    base, _comp = controller.parse_sheet_key(sheet_key)
    base = controller.resolve_item_name(base) or base
    needs_setup, setup_specs = _setup_specs(base)
    if needs_setup and sheet_key not in state.sheet_data:
        labels = "、".join(spec.get("label") or spec.get("key")
                          for spec in setup_specs)
        raise IngestError(
            "“%s”需要先设置采集参数（%s），再导入数据" % (base, labels))
    if params and _normalize_params is not None and \
            _manifest_param_specs is not None:
        try:
            normalized = _normalize_params(base, params)
        except Exception:  # noqa: BLE001 - 未知项目不校验
            normalized = {}
        if normalized.get("errors"):
            raise IngestError("参数不正确：" + "；".join(normalized["errors"]))
    try:
        data = import_sheet_rows(path, columns, sheet_name or None,
                                 preferred_name=sheet_key)
    except ExcelImportError as e:
        raise IngestError(str(e))
    result = apply_rows_to_sheet(state, sheet_key, data.get("rows") or [],
                                 append=append)
    assessment = None
    if auto_assess:
        assessment = assess_imported_sheet(sheet_key)
    return {
        "sheet_key": sheet_key,
        "imported": len(data.get("rows") or []),
        "matched_columns": data.get("matched"),
        "rows": result["total"],
        "merges": result["merges"],
        "recalc_error": result["recalc_error"],
        "warnings": warnings + list(data.get("warnings") or []),
        "requires_setup": bool(needs_setup),
        "assessment": assessment,
        "ready": bool(assessment and assessment.get("ok")),
    }

# ── 扫描识别结果：检测项目 → 目标表 → 结构对齐 → 入库/评定 ─────────────

def _norm_header(text):
    """列头归一化：去单位括号、空白，转小写，用于扫描结果与目标表对齐。"""
    text = str(text or "")
    text = re.sub(r"[（(].*?[)）]", "", text)
    return re.sub(r"\s+", "", text).lower()


def _component_map():
    """返回 {规范化项目名: [构件...]}，兼容带说明后缀的旧项目名。"""
    controller = get_controller()
    mapping = {}
    for _category, items in DETECTION_DATA.items():
        for item_name, components in (items or {}).items():
            base = controller.resolve_item_name(item_name) or item_name
            if components:
                mapping[base] = list(components)
            else:
                mapping.setdefault(base, [])
    return mapping


def _setup_specs_with_params(base, params):
    """校验并规范化参数化项目的采集参数，返回 (needs_setup, specs, params)。"""
    needs_setup, specs = _setup_specs(base)
    if not needs_setup or not params:
        return needs_setup, specs, params
    if _normalize_params is not None and _manifest_param_specs is not None:
        try:
            normalized = _normalize_params(base, params)
        except Exception:  # noqa: BLE001 - 未知项目不阻断
            normalized = {}
        errors = normalized.get("errors") or []
        if errors:
            raise IngestError("参数不正确：" + "；".join(errors))
        params = normalized.get("params") or params
    return needs_setup, specs, params


def _build_setup_rows(base, params):
    """纯数据构建参数化工作表；与 routers/project.py 的构建口径保持一致。"""
    if base == "钻芯法检测":
        return sheet_logic.build_core_drilling(params or {})
    if base == "回弹钻芯修正法检测":
        return sheet_logic.build_rebound_core_drilling(params or {})
    if base == "砖强度检测":
        return sheet_logic.build_brick_rebound(params or {})
    return None


def scan_targets(detection_item):
    """根据识别出的检测项目，查询可写入的采集工作表。

    返回候选检测项、是否需要采集参数、全部构件目标表、已存在/已勾选状态，
    由前端让用户确认“这次只勾选这一个项目”，不会批量勾选其它项目。
    """
    text = str(detection_item or "").strip()
    if not text:
        raise IngestError("识别结果没有检测项目，无法查询采集表")
    controller = get_controller()
    base = controller.resolve_item_name(text) or text
    if base not in ITEM_COLUMNS:
        raise IngestError("未找到检测项目的采集列定义：%s" % text)
    components = _component_map().get(base, [])
    state = get_state()
    keys = []
    if components:
        for comp in components:
            keys.append(controller.make_sheet_key(base, comp))
    else:
        keys.append(base)
    # 兼容用户已经建立、但键名与当前规范略有差异的工作表
    for key in state.sheet_data:
        parsed_base, _comp = controller.parse_sheet_key(key)
        if (controller.resolve_item_name(parsed_base) or parsed_base) == base and key not in keys:
            keys.append(key)
    targets = []
    for key in keys:
        comp = None
        parsed_base, parsed_comp = controller.parse_sheet_key(key)
        if (controller.resolve_item_name(parsed_base) or parsed_base) == base:
            comp = parsed_comp
        targets.append({
            "sheet_key": key,
            "component": comp or "",
            "columns": controller.get_columns(key),
            "exists": key in state.sheet_data,
            "rows": len(state.sheet_data.get(key) or []),
            "checked": key in state.checked_items,
        })
    preferred = ""
    if text in keys:
        preferred = text
    for target in targets:
        if target["checked"] and target["rows"]:
            preferred = target["sheet_key"]
            break
    if not preferred:
        existing = [t for t in targets if t["exists"]]
        preferred = existing[0]["sheet_key"] if existing else targets[0]["sheet_key"]
    needs_setup, specs = _setup_specs(base)
    try:
        from report_generator.scan_recognition.matcher import available_sub_items
        candidates = list(available_sub_items())
    except Exception:  # noqa: BLE001
        candidates = list(ITEM_COLUMNS)
    return {
        "detection_item": base,
        "input_item": text,
        "components": components,
        "requires_setup": bool(needs_setup),
        "param_specs": specs,
        "columns": ITEM_COLUMNS.get(base, []),
        "candidates": candidates,
        "targets": targets,
        "suggested_sheet_key": preferred,
    }


def _align_scan_rows(rows, source_columns, target_columns):
    """按列头把扫描对齐行映射到目标采集表列，避免列顺序不同造成错位。"""
    source = [str(c or "") for c in (source_columns or [])]
    target = [str(c or "") for c in (target_columns or [])]
    if source and [_norm_header(c) for c in source] == [_norm_header(c) for c in target]:
        aligned = []
        for row in rows or []:
            cells = list(row or [])
            cells.extend([""] * max(0, len(target) - len(cells)))
            aligned.append(cells[:len(target)])
        return aligned, len(target)
    index = {}
    for i, col in enumerate(source):
        index.setdefault(_norm_header(col), i)
    mapping = []
    matched = 0
    for col in target:
        key = _norm_header(col)
        src = index.get(key)
        if src is None and key:
            for candidate, pos in index.items():
                if candidate and (key in candidate or candidate in key) and len(key) >= 2:
                    src = pos
                    break
        mapping.append(src)
        if src is not None:
            matched += 1
    if source and matched == 0:
        raise IngestError(
            "识别结果的列头与目标采集表不匹配，请改选检测项目或目标工作表")
    aligned = []
    for row in rows or []:
        cells = list(row or [])
        out = []
        for src in mapping:
            out.append(cells[src] if src is not None and src < len(cells) else "")
        aligned.append(out)
    return aligned, matched


def commit_scan_job(job_id, sheet_key, append=False, params=None,
                    auto_assess=True):
    """把扫描作业的结构化结果写入指定采集表，只勾选该表并立即评定。

    前置：参数化项目（钻芯法等）由前端先调用 project/check_item 建表；
    这里也允许直接传 params 构建，保证 API 单独调用也能工作。
    """
    import scan_jobs
    view = scan_jobs.status(job_id)
    if not view:
        raise IngestError("识别作业不存在或已过期：%s" % job_id)
    if view.get("status") != "done":
        raise IngestError("识别作业尚未完成：%s" % view.get("status"))
    result = view.get("result") or {}
    rows = result.get("rows") or []
    if not rows:
        raise IngestError("识别结果没有可写入的数据行")
    key = str(sheet_key or "").strip()
    if not key:
        raise IngestError("缺少目标采集表")
    controller = get_controller()
    target_columns = controller.get_columns(key)
    if not target_columns:
        raise IngestError("目标采集表没有列定义：%s" % key)
    state = get_state()
    base, _comp = controller.parse_sheet_key(key)
    base = controller.resolve_item_name(base) or base
    needs_setup, specs, params = _setup_specs_with_params(base, params)
    if key not in state.sheet_data:
        if needs_setup:
            if not params:
                labels = "、".join(spec.get("label") or spec.get("key")
                                  for spec in specs)
                raise IngestError(
                    "“%s”需要先设置采集参数（%s），再写入识别数据" % (base, labels))
            built = _build_setup_rows(base, params)
            if built is None:
                raise IngestError("暂不支持“%s”的参数化构建" % base)
            setup_rows, merges, merge_formats, cd_params = built
            state.sheet_data[key] = setup_rows
            state.merges[key] = list(merges)
            state.merge_formats[key] = dict(merge_formats)
            state.cd_params[key] = cd_params
    aligned, matched = _align_scan_rows(
        rows, result.get("columns") or [], target_columns)
    written = apply_rows_to_sheet(state, key, aligned, append=append)
    assessment = None
    if auto_assess:
        assessment = assess_imported_sheet(key)
    return {
        "sheet_key": key,
        "imported": len(aligned),
        "rows": written.get("total", len(state.sheet_data.get(key) or [])),
        "matched_columns": matched,
        "target_columns": target_columns,
        "merges": written.get("merges") or [],
        "recalc_error": written.get("recalc_error", ""),
        "warnings": list(result.get("field_warnings") or []),
        "requires_setup": bool(needs_setup),
        "assessment": assessment,
        "ready": bool(assessment and assessment.get("ok")),
        "checked_items": list(state.checked_items),
    }

