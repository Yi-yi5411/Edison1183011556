# -*- coding: utf-8 -*-
"""项目管理路由：新建/打开/保存/勾选检测项目。

复用 AppController 的持久化与序列化方法；requires_setup 项目（钻芯法等）
的表格构建使用 sheet_logic 中剥离 Qt 后的等价纯数据逻辑。
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Optional
import os
import re
import time

from deps import (ROOT, clean_template_selection, get_controller,
                  get_plugin_manager, get_state, get_template_library,
                  ok, ApiError, ITEM_COLUMNS)
try:  # manifest 是可选的：老部署没有 structural_items 时退回原有逻辑
    from structural_items import normalize_params as _normalize_params
    from structural_items import param_specs as _param_specs
except ImportError:  # noqa: BLE001
    _normalize_params = None
    _param_specs = None


def _manifest_param_specs(base):
    """取 manifest 声明的采集参数；没有 manifest 时返回空列表。"""
    if _param_specs is None:
        return []
    try:
        return list(_param_specs(base) or [])
    except Exception:  # noqa: BLE001 - manifest 损坏不应阻断勾选
        return []
import sheet_logic

router = APIRouter(tags=["project"])


class NewBody(BaseModel):
    project_name: str = "新建项目"


class OpenBody(BaseModel):
    filepath: str


class SaveBody(BaseModel):
    filepath: Optional[str] = None


class RenameBody(BaseModel):
    project_name: str = ""


@router.put("/project/name")
def rename_project(body: RenameBody):
    """修改工程名称，同时同步报告抬头中的工程名称。"""
    try:
        name = str(body.project_name or "").strip()
        if not name:
            raise ApiError("工程名称不能为空")
        state = get_state()
        state.project_name = name
        state.report_info = dict(state.report_info or {})
        state.report_info["project_name"] = name
        return ok(state.snapshot(), f"工程名称已修改：{name}")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"修改工程名称失败：{e}"}


class CheckItemBody(BaseModel):
    sheet_key: str
    checked: bool = True
    params: Optional[dict] = None


class TemplateSelectionBody(BaseModel):
    report_template_id: str = ""
    original_template_map: Dict[str, str] = {}


DEFAULT_EMPTY_ROWS = 15  # 新勾选普通检测项时的默认空行数


@router.get("/project")
def get_project():
    """当前项目快照：项目名/勾选项/各工作表数据/报告抬头。"""
    try:
        return ok(get_state().snapshot())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取项目失败：{e}"}


@router.post("/project/new")
def new_project(body: NewBody):
    """新建项目；已有数据时先自动备份，避免误清空。"""
    try:
        state = get_state()
        backup_path = None
        has_data = bool(state.checked_items or state.sheet_data or state.report_info)
        if has_data:
            backup_dir = os.path.join(ROOT, "data", "projects", "backups")
            os.makedirs(backup_dir, exist_ok=True)
            safe_name = re.sub(r'[\\/:*?"<>|]', "_",
                               state.project_name or "未命名工程").strip()[:60] or "未命名工程"
            stamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(
                backup_dir, "%s_%s.json" % (safe_name, stamp))
            state.save(backup_path)
        state.reset(body.project_name or "新建项目")
        data = state.snapshot()
        data["backup_path"] = backup_path
        message = "已新建项目"
        if backup_path:
            message += "；原工程已备份到 %s" % backup_path
        return ok(data, message)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"新建项目失败：{e}"}


@router.get("/project/history")
def project_history():
    """历史工程项目：自动备份、会话工程快照和旧版导出的项目文件。"""
    try:
        import json
        from datetime import datetime
        candidates = []
        scan_dirs = [
            (os.path.join(ROOT, "data", "projects", "backups"), "自动备份"),
            (os.path.join(ROOT, "data", "projects", "sessions"), "会话工程"),
            (os.path.join(ROOT, "report_generator", "exports"), "历史保存"),
            (os.path.join(ROOT, "data", "projects"), "项目文件"),
        ]
        seen = set()
        for folder, source in scan_dirs:
            if not os.path.isdir(folder):
                continue
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                if not name.lower().endswith(".json"):
                    continue
                path = os.path.join(folder, name)
                if not os.path.isfile(path):
                    continue
                real = os.path.realpath(path)
                if real in seen:
                    continue
                seen.add(real)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                if "data" not in data and "project_name" not in data:
                    continue
                sheets = data.get("data") if isinstance(data.get("data"), dict) else {}
                checked = data.get("checked_items")
                if not isinstance(checked, list):
                    checked = list(sheets.keys())
                stat = os.stat(path)
                candidates.append({
                    "filepath": path,
                    "name": str(data.get("project_name") or "").strip()
                            or os.path.splitext(name)[0],
                    "source": source,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": stat.st_mtime,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "checked_count": len(checked),
                    "sheet_count": len(sheets),
                })
        candidates.sort(key=lambda item: item.get("mtime", 0), reverse=True)
        for item in candidates:
            item.pop("mtime", None)
        return ok({"items": candidates[:200], "total": len(candidates)},
                  "历史工程读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取历史工程失败：{e}"}


@router.post("/project/open")
def open_project(body: OpenBody):
    """加载项目文件（与桌面版项目 JSON 互通）。"""
    try:
        import os
        path = body.filepath
        if not path or not os.path.isfile(path):
            raise ApiError(f"项目文件不存在：{path}")
        state = get_state()
        state.load(path)
        return ok(state.snapshot(), f"已打开项目：{os.path.basename(path)}")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"打开项目失败：{e}"}


@router.post("/project/save")
def save_project(body: SaveBody):
    """保存当前项目（缺省当前路径，再缺省落到 exports 目录）。"""
    try:
        state = get_state()
        target = state.save(body.filepath)
        return ok({"filepath": target}, f"项目已保存：{target}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存项目失败：{e}"}


def _build_setup_sheet(base, params):
    """构建 requires_setup 项目的工作表（剥离 Qt 的纯数据构建）。

    返回 (rows, merges, merge_formats, cd_params) 或 None（未支持的构建类型）。
    """
    if base == "钻芯法检测":
        return sheet_logic.build_core_drilling(params or {})
    if base == "回弹钻芯修正法检测":
        return sheet_logic.build_rebound_core_drilling(params or {})
    if base == "砖强度检测":
        return sheet_logic.build_brick_rebound(params or {})
    return None


@router.get("/project/structured")
def get_structured_project():
    """结构化项目数据：列头 + 行数据 + 按列展开的记录 dict（供导出/核对）。"""
    try:
        return ok(get_state().structured(), "结构化数据读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取结构化数据失败：{e}"}


@router.put("/project/template_selection")
def put_template_selection(body: TemplateSelectionBody):
    """保存当前项目的报告模板 / 原始记录模板选择。"""
    try:
        lib = get_template_library()
        report_id = str(body.report_template_id or "").strip()
        if report_id and not lib.get_report_template(report_id):
            raise ApiError(f"报告模板不存在：{report_id}")
        mapping = {}
        for key, template_id in (body.original_template_map or {}).items():
            key = str(key or "").strip()
            template_id = str(template_id or "").strip()
            if not key or not template_id:
                continue
            view = lib.get_original_template(template_id)
            if not view:
                raise ApiError(f"原始记录模板不存在：{template_id}")
            if not view.get("fillable"):
                raise ApiError(f"“{view.get('name') or template_id}”为存档模板，不能用于自动填充")
            mapping[key] = template_id
        state = get_state()
        state.template_selection = clean_template_selection({
            "report_template_id": report_id,
            "original_template_map": mapping,
        })
        return ok(state.template_selection, "模板选择已保存")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存模板选择失败：{e}"}


@router.post("/project/check_item")
def check_item(body: CheckItemBody):
    """勾选/取消检测项目；requires_setup 项目勾选时需传 params。

    params 为钻芯法对话框等参数（楼栋/构件数/芯样数/起始编号/设计等级/直径）。
    """
    try:
        state = get_state()
        controller = get_controller()
        key = body.sheet_key
        if not key:
            raise ApiError("缺少 sheet_key")

        if not body.checked:
            state.remove_sheet(key)
            return ok(state.snapshot(), f"已取消勾选：{key}")

        if key in state.sheet_data:
            if key not in state.checked_items:
                state.checked_items.append(key)
            return ok(state.snapshot(), f"检测项目已勾选并纳入报告：{key}")

        base, _comp = controller.parse_sheet_key(key)
        # 列定义（带说明后缀的项目名规范化到插件注册键名）
        columns = controller.get_columns(key)

        setup_specs = _manifest_param_specs(base)
        needs_setup = bool(setup_specs)
        if not needs_setup and controller.requires_setup_dialog(base):
            # manifest 未覆盖的老插件：沿用「按名字判断」的兼容分支
            needs_setup = True
            if not body.params:
                setup_specs = [
                    {"key": "building", "label": "楼栋", "type": "string"},
                    {"key": "components", "label": "构件数", "type": "int"},
                    {"key": "samples_per_component", "label": "每构件芯样数",
                     "type": "int"},
                    {"key": "sample_start", "label": "芯样起始编号", "type": "int"},
                    {"key": "grade", "label": "设计强度等级", "type": "string"},
                    {"key": "diameter", "label": "芯样直径(mm)", "type": "float"},
                ]

        if needs_setup:
            if not body.params:
                fields = [spec.get("key") for spec in setup_specs]
                labels = "、".join(spec.get("label") or spec.get("key")
                                  for spec in setup_specs)
                return ok({"requires_setup": True, "sheet_key": key,
                           "fields": fields, "field_specs": setup_specs,
                           "source": "manifest" if _manifest_param_specs(base)
                           else "plugin"},
                          "“%s”需要设置参数（%s）" % (base, labels))
            if _normalize_params is not None and _manifest_param_specs(base):
                normalized = _normalize_params(base, body.params)
                if normalized.get("errors"):
                    raise ApiError("参数不正确：" + "；".join(normalized["errors"]))
                body.params = normalized.get("params") or body.params
            built = _build_setup_sheet(base, body.params)
            if built is None:
                raise ApiError(f"暂不支持“{base}”的参数化构建，请联系后端补充")
            rows, merges, merge_formats, cd_params = built
            state.sheet_data[key] = rows
            state.merges[key] = list(merges)
            state.merge_formats[key] = dict(merge_formats)
            state.cd_params[key] = cd_params
        else:
            rows = [["" for _ in range(len(columns))]
                    for _ in range(DEFAULT_EMPTY_ROWS)]
            state.sheet_data[key] = rows
            state.merges.setdefault(key, [])
            state.merge_formats.setdefault(key, {})

        if key not in state.checked_items:
            state.checked_items.append(key)
        return ok(state.sheet_snapshot(key), f"已勾选检测项目：{key}")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"勾选检测项目失败：{e}"}


@router.get("/project/current")
def current_project():
    """当前工程的显式身份：名称、文件路径、勾选项与表数。"""
    try:
        state = get_state()
        return ok({
            "project_name": state.project_name or "",
            "filepath": state.filepath or "",
            "autosave_path": getattr(state, "autosave_path", "") or "",
            "checked_items": list(state.checked_items or []),
            "sheet_count": len(state.sheet_data or {}),
            "assessed_count": sum(
                1 for key in (state.checked_items or [])
                if (state.assessment_results or {}).get(key, {}).get("ok")),
        }, "当前工程读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取当前工程失败：{e}"}


@router.get("/project/list")
def list_projects():
    """历史工程清单（与 /project/history 同一份扫描结果，名称更直白）。"""
    return project_history()


@router.post("/project/activate")
def activate_project(body: OpenBody):
    """把指定工程文件切换为当前工程（与 /project/open 等价）。"""
    return open_project(body)


BACKUP_DIR = os.path.join(ROOT, "data", "projects", "backups")


@router.get("/project/backups")
def project_backups(limit: int = 50):
    """列出自动备份与恢复前快照（人工回退用）。"""
    try:
        items = []
        if os.path.isdir(BACKUP_DIR):
            for name in os.listdir(BACKUP_DIR):
                if not name.lower().endswith(".json"):
                    continue
                path = os.path.join(BACKUP_DIR, name)
                if not os.path.isfile(path):
                    continue
                stat = os.stat(path)
                items.append({
                    "filepath": path,
                    "name": name,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "mtime": stat.st_mtime,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(stat.st_mtime)),
                })
        items.sort(key=lambda item: item["mtime"], reverse=True)
        for item in items:
            item.pop("mtime", None)
        try:
            limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit = 50
        return ok({"items": items[:limit], "total": len(items),
                   "dir": BACKUP_DIR}, "工程备份读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取工程备份失败：{e}"}


@router.post("/project/restore")
def restore_project(body: OpenBody):
    """从备份恢复工程：先把当前工程另存到 backups/restore_<时间戳>.json，再加载。"""
    try:
        path = body.filepath
        if not path or not os.path.isfile(path):
            raise ApiError(f"备份文件不存在：{path}")
        state = get_state()
        os.makedirs(BACKUP_DIR, exist_ok=True)
        safety = os.path.join(BACKUP_DIR, "restore_%s.json"
                              % time.strftime("%Y%m%d_%H%M%S"))
        try:
            state.save(safety)
        except Exception:  # noqa: BLE001 - 当前工程保存失败不应阻止恢复
            safety = ""
        state.load(path)
        return ok({
            "restored": path,
            "safety_backup": safety,
            "project_name": state.project_name or "",
            "sheet_count": len(state.sheet_data or {}),
        }, "已从备份恢复工程")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"恢复工程失败：{e}"}


@router.get("/project/items")
def project_items():
    """左侧勾选树数据（按结构类型分组，复用插件聚合）。"""
    try:
        pm = get_plugin_manager()
        return ok(pm.aggregated_detection_data(), "检测项目树加载成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"加载检测项目树失败：{e}"}


@router.get("/project/columns/{sheet_key}")
def sheet_columns(sheet_key: str):
    """查询单个工作表的列头（含说明后缀的键名自动规范化）。"""
    try:
        controller = get_controller()
        return ok({"sheet_key": sheet_key,
                   "columns": controller.get_columns(sheet_key)})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"查询列头失败：{e}"}


@router.get("/project/item_contract")
def item_contract(item: str = ""):
    """只读：读取检测项目的 manifest 契约（采集参数/评定/设备/技能/模板）。

    数据来自 report_generator/structural_items（modules/<id>/plugin.json）。
    """
    try:
        from structural_items import describe_item
        data = describe_item(item)
        if data is None:
            raise ApiError("未找到检测项目：%s（可先调用 list_detection_items）" % item)
        return ok(data, "检测项目契约读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取检测项目契约失败：{e}"}


@router.get("/project/suggest")
def suggest_detection_items(text: str = ""):
    """只读：把一句话需求识别成检测项目/构件/工作表键与建议页面。

    复用 item_intent 的规则别名（30 条），不调用模型、不修改项目。
    """
    try:
        from item_intent import detect as _detect_intent
        pm = get_plugin_manager()
        items = []
        for plugin in pm.all_plugins():
            for item, comps in (plugin.tree_entries() or {}).items():
                keys = ([(item + "（%s）" % c) if c else item for c in comps]
                        if comps else [item])
                items.append({
                    "item": item,
                    "structure_type": plugin.structure_type,
                    "components": comps,
                    "sheet_keys": keys,
                })
        return ok(_detect_intent(text, items=items), "检测项目建议已生成")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"识别检测项目失败：{e}"}


# 供其他模块复用的列宽缺省（未使用可忽略）
_ = ITEM_COLUMNS
