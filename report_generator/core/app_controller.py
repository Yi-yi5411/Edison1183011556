# -*- coding: utf-8 -*-
"""应用控制器：承载业务逻辑，解耦 UI 与数据/插件/引擎。

职责：
  - 工作表键解析与列定义查询
  - 项目状态序列化 / 反序列化（保存 / 加载 JSON）
  - 导出列映射构建
  - 检测项目插件查询与能力判定

UI 层（gui_qt）仅负责展示与交互，通过本控制器访问业务能力；
控制器通过事件总线对外发布状态变更，供 UI 或其他订阅方响应。
"""

import json

from core.plugin_manager import get_plugin_manager
from core.event_bus import get_event_bus
from framework.models import DETECTION_DATA, ITEM_COLUMNS


_REBAR_LEGACY_KEYS = {
    '剪力墙构件钢筋间距': '剪力墙构件钢筋间距检测',
    '现浇板钢筋间距': '现浇板钢筋间距检测',
    '剪力墙钢筋根数': '剪力墙钢筋根数检测',
}


def _normalize_legacy_key(key):
    """将旧版钢筋配置键名迁移到带“检测”的规范名。"""
    return _REBAR_LEGACY_KEYS.get(key, key)


def _make_sheet_key(item_name, component):
    """构造工作表键：'项目名（构件名）'，无构件时为 '项目名'。"""
    return f"{item_name}（{component}）" if component else item_name


class AppController:
    """MVC 中的控制器：协调插件、引擎与数据，不依赖任何 GUI 框架。"""

    def __init__(self):
        self._pm = get_plugin_manager()
        self.bus = get_event_bus()

    # ── 插件查询 ──
    @property
    def plugin_manager(self):
        return self._pm

    def get_plugin_for_item(self, item_name):
        return self._pm.get_plugin_for_item(item_name)

    # ── 工作表键解析 ──
    @staticmethod
    def make_sheet_key(item_name, component):
        return _make_sheet_key(item_name, component)

    @staticmethod
    def parse_sheet_key(key):
        """解析工作表键，返回 (基础项目名, 构件名或None)。"""
        for _cat, items in DETECTION_DATA.items():
            for iname, comps in items.items():
                if not comps and key == iname:
                    return iname, None
                if comps:
                    for comp in comps:
                        if _make_sheet_key(iname, comp) == key:
                            return iname, comp
        return key, None

    def get_columns(self, sheet_key):
        """获取工作表对应的列头列表。"""
        base, _comp = self.parse_sheet_key(sheet_key)
        base = self.resolve_item_name(base)
        return ITEM_COLUMNS.get(base, ITEM_COLUMNS.get(sheet_key, ["数据"]))

    @staticmethod
    def resolve_item_name(base):
        """将带说明后缀的项目名规范化为插件注册的列/规则键名。

        例如“回弹法检测(主要来源为仪器数据，可选用)”规范化为“回弹法检测”，
        以便正确命中 ITEM_COLUMNS / CALC_RULES 中的检测项目。
        """
        if not base:
            return base
        if base in ITEM_COLUMNS:
            return base
        for key in ITEM_COLUMNS:
            if base.startswith(key):
                return key
        return base

    def build_export_columns(self, sheet_data):
        """构建导出用的 {sheet_key: [列头]} 映射。"""
        return {key: self.get_columns(key) for key in sheet_data}

    # ── 项目能力查询（替代散落在 UI 中的字符串判断）──
    def requires_setup_dialog(self, item_name):
        """该检测项勾选时是否需要弹出参数设置对话框（如钻芯法）。"""
        plugin = self.get_plugin_for_item(item_name)
        if plugin is None:
            return False
        base, _ = self.parse_sheet_key(item_name)
        return plugin.requires_setup_dialog(base)

    def create_setup_dialog(self, item_name, parent, sheet_key=""):
        """创建参数设置对话框实例，由插件决定具体类型（框架层不感知）。

        返回 QDialog 实例或 None（无需对话框时）。
        """
        plugin = self.get_plugin_for_item(item_name)
        if plugin is None:
            return None
        base, _ = self.parse_sheet_key(item_name)
        return plugin.create_setup_dialog(parent, base, sheet_key)

    def build_sheet(self, item_name, params, app):
        """根据参数对话框结果构建工作表，由插件决定具体构建方式。

        与 create_setup_dialog 配对：框架层不感知任何具体构建方法，
        返回 True 表示已构建。
        """
        plugin = self.get_plugin_for_item(item_name)
        if plugin is None:
            return False
        base, _ = self.parse_sheet_key(item_name)
        return plugin.build_sheet(app, base, item_name, params)

    # ── 序列化 / 反序列化 ──
    @staticmethod
    def save_project_file(filepath, state):
        """将项目状态字典写入 JSON 文件（UTF-8，缩进 2）。"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_project_file(filepath):
        """从 JSON 文件读取项目状态字典。"""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def serialize(project_name, sheet_data, merges, merge_formats,
                  cell_formats, cd_params, operation_notes=None,
                  checked_items=None, report_info=None,
                  template_selection=None, assessment=None):
        """将项目状态序列化为可 JSON 化的字典。

        template_selection 为 Web 版新增的可选项（报告/原始记录模板选择），
        旧调用方不传时写空对象，不影响桌面版反序列化。
        """
        return {
            "project_name": project_name,
            "data": sheet_data,
            "merges": {k: [list(m) for m in v] for k, v in merges.items()},
            "merge_formats": {
                k: {f"{r},{c}": fmt for (r, c), fmt in v.items()}
                for k, v in merge_formats.items()
            },
            "cell_formats": {
                k: {f"{r},{c}": fmt for (r, c), fmt in v.items()}
                for k, v in cell_formats.items()
            },
            "cd_params": cd_params,
            "operation_notes": operation_notes or {},
            "checked_items": checked_items or [],
            "report_info": report_info or {},
            "template_selection": template_selection or {},
            "assessment": assessment or {},
        }

    @staticmethod
    def deserialize(saved):
        """从字典反序列化项目状态。

        返回 (project_name, sheet_data, merges, merge_formats, cell_formats,
        cd_params, operation_notes, checked_items, report_info)。
        """
        saved = AppController._migrate_core_drilling_legacy(saved)
        sheet_data = {
            _normalize_legacy_key(k): v
            for k, v in saved.get("data", {}).items()
        }
        merges = {
            _normalize_legacy_key(k): [tuple(m) for m in v]
            for k, v in saved.get("merges", {}).items()
        }

        def _restore_formats(src):
            out = {}
            for k, v in src.items():
                k = _normalize_legacy_key(k)
                out[k] = {}
                for rc_str, fmt in v.items():
                    r, c = map(int, rc_str.split(","))
                    out[k][(r, c)] = fmt
            return out

        merge_formats = _restore_formats(saved.get("merge_formats", {}))
        cell_formats = _restore_formats(saved.get("cell_formats", {}))
        cd_params = saved.get("cd_params", {})
        operation_notes = {
            _normalize_legacy_key(k): v
            for k, v in saved.get("operation_notes", {}).items()
        }
        checked_items = saved.get("checked_items", None)
        if checked_items is not None:
            checked_items = [_normalize_legacy_key(item) for item in checked_items]
        report_info = saved.get("report_info", {})
        return (saved.get("project_name"), sheet_data, merges,
                merge_formats, cell_formats, cd_params, operation_notes,
                checked_items, report_info)

    @staticmethod
    def _is_core_drilling_key(key):
        """判断工作表键是否属于钻芯法检测。"""
        base, _ = AppController.parse_sheet_key(key)
        return base == "钻芯法检测"

    @staticmethod
    def _migrate_core_drilling_legacy(saved):
        """将旧版 12 列钻芯法工作表数据迁移为 13 列（加入“批次”列）。

        旧数据列序为：楼栋、构件编号、构件位置及名称、轴线编号、序号、
        芯样直径、截面积、测试荷载、测试强度、推定值、批评定值、设计等级；
        新版在“楼栋”后新增“批次”列。这里同时迁移数据、合并信息与格式坐标。
        """
        data = saved.get("data", {})
        merges = saved.get("merges", {})
        merge_formats = saved.get("merge_formats", {})
        cell_formats = saved.get("cell_formats", {})
        cd_params = saved.get("cd_params", {})

        for key in list(cd_params.keys()):
            if (AppController._is_core_drilling_key(key)
                    and isinstance(cd_params.get(key), dict)):
                cd_params[key].setdefault("method", "batch")
                cd_params[key].setdefault("batches", 1)

        for key in list(data.keys()):
            if not AppController._is_core_drilling_key(key):
                continue
            rows = data.get(key, [])
            if not rows:
                continue
            width = max((len(row) for row in rows), default=0)
            if width >= 13:
                continue

            samples_per = cd_params.get(key, {}).get("samples_per", 2) or 2
            new_rows = []
            for r_idx, row in enumerate(rows):
                row = list(row)
                if len(row) < 12:
                    row += [""] * (12 - len(row))
                # 旧版没有批次列；为保持旧的“整表参与批评定”行为，锚点行填 1
                batch = "1" if (r_idx % samples_per == 0) else ""
                new_rows.append(row[:1] + [batch] + row[1:])
            data[key] = new_rows

            new_merges = []
            for merge in merges.get(key, []):
                merge = list(merge)
                r, c, rs, cs = merge[0], merge[1], merge[2], merge[3]
                if c >= 1:
                    c += 1
                new_merges.append((r, c, rs, cs))
            for r_idx in range(0, len(new_rows), samples_per):
                if samples_per > 1:
                    new_merges.append((r_idx, 1, samples_per, 1))
            merges[key] = new_merges

            def _shift_formats(src):
                out = {}
                for rc_str, fmt in src.items():
                    try:
                        r_str, c_str = rc_str.split(",")
                        r = int(r_str)
                        c = int(c_str)
                    except ValueError:
                        out[rc_str] = fmt
                        continue
                    if c >= 1:
                        c += 1
                    out[f"{r},{c}"] = fmt
                return out

            if key in merge_formats:
                merge_formats[key] = _shift_formats(merge_formats[key])
            if key in cell_formats:
                cell_formats[key] = _shift_formats(cell_formats[key])

        saved["data"] = data
        saved["merges"] = merges
        saved["merge_formats"] = merge_formats
        saved["cell_formats"] = cell_formats
        return saved
