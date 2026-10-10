# -*- coding: utf-8 -*-
"""钻芯法检测 - GUI 处理逻辑（Mixin）

从 gui_qt.py 提取的钻芯法检测特有逻辑，通过混入 ReportGeneratorApp 复用。
依赖主类提供：self._to_float, self._reset_spans, self._parse_sheet_key,
self.table, self.sheet_data, self._merges, self._merge_formats,
self._cd_params, self.current_item, self._loading, self._displayed_merges
"""

import math
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTableWidgetItem, QMessageBox, QDialog

from framework.models import ITEM_COLUMNS
from .batch_assessment import batch_assess
from .dialogs import BatchAssessmentResultDialog

# 测试荷载(kN) → 测试强度(MPa) 的单位换算因子：强度 = 荷载×1000 / 截面积
LOAD_TO_STRENGTH_FACTOR = 1000.0
REBOUND_FLOOR_COUNT = 100
REBOUND_NEGATIVE_FLOORS = [-6, -5, -4, -3, -2, -1]


class CoreDrillingMixin:
    """钻芯法检测特有 GUI 逻辑混入类。

    包含：工作表构建、测试强度/推定值自动计算、批推定计算、合并单元格应用、
    构件位置列楼层标签（FL/FZ/FB/FQ）校验与下拉、右键菜单贡献。

    通过注册式钩子与主窗口协作（主窗口不感知具体检测项目）：
    - ``_core_drilling_cell_changed``  单元格编辑联动（含位置列校验）
    - ``_core_drilling_sheet_loaded``  工作表加载联动（位置列下拉 + 全表重算）
    - ``_core_drilling_context_menu``  右键菜单贡献项

    依赖宿主（主窗口）属性/方法：table、win、current_item、sheet_data、
    _cd_params、_loading、_merges、_floor_delegate、_floor_delegate_column、
    _get_columns、_parse_sheet_key、_get_position_column、_sync_table_to_data 等。
    """

    # 钻芯法检测列索引
    _CD_COL_BUILDING   = 0   # 楼栋
    _CD_COL_BATCH      = 1   # 批次
    _CD_COL_COMP_NO    = 2   # 构件编号
    _CD_COL_COMP_NAME  = 3   # 构件位置及名称
    _CD_COL_AXIS       = 4   # 轴号
    _CD_COL_SAMPLE_NO  = 5   # 序号
    _CD_COL_DIAMETER   = 6   # 直径(mm)
    _CD_COL_AREA       = 7   # 截面积(mm²)
    _CD_COL_LOAD       = 8   # 测试荷载(kN)
    _CD_COL_STRENGTH   = 9   # 测试强度(MPa)
    _CD_COL_INFERRED   = 10  # 推定值(MPa)
    _CD_COL_CRITIC     = 11  # 批评定值(MPa)
    _CD_COL_GRADE      = 12  # 设计等级
    _CD_COL_COUNT      = 13  # 总列数
    # 回弹钻芯修正法检测列索引
    _RCD_COL_BUILDING   = 0   # 楼栋
    _RCD_COL_BATCH      = 1   # 批次
    _RCD_COL_COMP_NO    = 2   # 构件编号
    _RCD_COL_COMP_NAME  = 3   # 构件位置及名称
    _RCD_COL_AXIS       = 4   # 构件轴号
    _RCD_COL_ZONE       = 5   # 钻芯测区
    _RCD_COL_DIAMETER   = 6   # 芯样直径(mm)
    _RCD_COL_AREA       = 7   # 截面积(mm²)
    _RCD_COL_LOAD       = 8   # 测试荷载(kN)
    _RCD_COL_STRENGTH   = 9   # 测试强度(MPa)
    _RCD_COL_GRADE      = 10  # 设计强度等级
    _RCD_COL_MEAN       = 11  # 芯样强度均值(MPa)
    _RCD_COL_COUNT      = 12  # 总列数


    def _build_core_drilling_sheet(self, sheet_key, params):
        """根据对话框参数构建钻芯法检测工作表。

        表格结构参考 image：每构件 2 个芯样，楼栋/构件编号/构件名称/轴号/
        直径/截面积/推定值/设计等级 按规则合并。
        """
        building = params["building"]
        n_components = params["components"]
        samples_per = params["samples_per_component"]
        sample_start = params["sample_start"]
        grade = params["grade"]
        diameter = params["diameter"]
        method = params.get("method", "batch")
        batches = int(params.get("batches", 1) or 1)
        if batches < 1:
            batches = 1

        batch_size = math.ceil(n_components / batches) if n_components else 1

        total_rows = n_components * samples_per
        cols = ITEM_COLUMNS.get("钻芯法检测", [])

        # 构建空数据
        data = [["" for _ in range(len(cols))] for _ in range(total_rows)]

        # 截面积: π × (d/2)²
        area = math.pi * (diameter / 2) ** 2

        # 填充数据
        for comp_idx in range(n_components):
            comp_row_start = comp_idx * samples_per
            if method == "batch":
                comp_no = str(comp_idx % batch_size + 1)
            else:
                comp_no = str(comp_idx + 1)
            if method == "batch" and comp_idx % batch_size == 0:
                batch_no = min(batches, comp_idx // batch_size + 1)
                data[comp_row_start][self._CD_COL_BATCH] = str(batch_no)
            else:
                data[comp_row_start][self._CD_COL_BATCH] = ""
            for s in range(samples_per):
                row = comp_row_start + s
                sample_no = str(sample_start + s)
                data[row][self._CD_COL_BUILDING] = building
                data[row][self._CD_COL_COMP_NO] = comp_no
                data[row][self._CD_COL_COMP_NAME] = ""
                data[row][self._CD_COL_AXIS] = ""
                data[row][self._CD_COL_SAMPLE_NO] = sample_no
                data[row][self._CD_COL_DIAMETER] = f"{diameter:.1f}"
                data[row][self._CD_COL_AREA] = f"{area:.0f}"
                data[row][self._CD_COL_LOAD] = ""
                data[row][self._CD_COL_STRENGTH] = ""
                data[row][self._CD_COL_INFERRED] = ""
                data[row][self._CD_COL_GRADE] = grade

        self.sheet_data[sheet_key] = data

        # 构建合并信息
        merges = []
        # 楼栋合并（跨所有行）
        if total_rows > 1:
            merges.append((0, self._CD_COL_BUILDING, total_rows, 1))
        # 设计等级合并（跨所有行）
        if total_rows > 1:
            merges.append((0, self._CD_COL_GRADE, total_rows, 1))
        # 每构件内部的合并
        for comp_idx in range(n_components):
            rs = samples_per
            r_start = comp_idx * samples_per
            # 构件编号
            if rs > 1:
                merges.append((r_start, self._CD_COL_COMP_NO, rs, 1))
            # 构件名称
            if rs > 1:
                merges.append((r_start, self._CD_COL_COMP_NAME, rs, 1))
            # 轴号
            if rs > 1:
                merges.append((r_start, self._CD_COL_AXIS, rs, 1))
            # 直径
            if rs > 1:
                merges.append((r_start, self._CD_COL_DIAMETER, rs, 1))
            # 截面积
            if rs > 1:
                merges.append((r_start, self._CD_COL_AREA, rs, 1))
            # 推定值
            if rs > 1:
                merges.append((r_start, self._CD_COL_INFERRED, rs, 1))


        # Merge the batch input column by configured batch groups.
        if method == "batch":
            for batch_idx in range(batches):
                start_comp = batch_idx * batch_size
                end_comp = min(n_components, (batch_idx + 1) * batch_size)
                if end_comp <= start_comp:
                    continue
                r_start = start_comp * samples_per
                row_span = (end_comp - start_comp) * samples_per
                if row_span > 1:
                    merges.append((r_start, self._CD_COL_BATCH, row_span, 1))
        self._merges[sheet_key] = merges

        # 构建合并格式信息
        merge_formats = {}
        # 楼栋
        merge_formats[(0, self._CD_COL_BUILDING)] = {"align": "center"}
        # 设计等级
        merge_formats[(0, self._CD_COL_GRADE)] = {"align": "center", "bold": True}
        # 每构件合并单元格
        for comp_idx in range(n_components):
            r_start = comp_idx * samples_per
            for c in [self._CD_COL_COMP_NO, self._CD_COL_COMP_NAME, self._CD_COL_AXIS,
                      self._CD_COL_DIAMETER, self._CD_COL_AREA, self._CD_COL_INFERRED]:
                merge_formats[(r_start, c)] = {"align": "center"}
        if method == "batch":
            for batch_idx in range(batches):
                start_comp = batch_idx * batch_size
                end_comp = min(n_components, (batch_idx + 1) * batch_size)
                if end_comp <= start_comp:
                    continue
                r_start = start_comp * samples_per
                merge_formats[(r_start, self._CD_COL_BATCH)] = {"align": "center"}
        self._merge_formats[sheet_key] = merge_formats
        # 保存钻芯法参数供后续计算使用
        self._cd_params[sheet_key] = {
            "samples_per": samples_per,
            "diameter": diameter,
            "grade": grade,
            "method": method,
            "batches": batches,
        }

    def _get_cd_samples_per(self):
        """获取当前钻芯法检测工作表的每构件芯样数量"""
        if not self.current_item:
            return 2
        params = self._cd_params.get(self.current_item, {})
        return params.get("samples_per", 2)

    def _is_core_drilling_sheet(self, sheet_key=None):
        """判断当前工作表是否为钻芯法检测类型"""
        if sheet_key is None:
            sheet_key = self.current_item
        if not sheet_key:
            return False
        base, _comp = self._parse_sheet_key(sheet_key)
        return base == "钻芯法检测"

    def _recalc_core_drilling_row(self, row):
        """重新计算钻芯法检测表格指定行的测试强度和推定值。

        测试强度(MPa) = 测试荷载(kN) × 1000 / 截面积(mm²)
        推定值(MPa)：
          - 单构件检测时，取同一构件所有芯样测试强度的最小值（保守推定）
          - 批推定（批评定）时，不计算推定值，统一输出“/”，仅计算批评定值
        """
        if not self._is_core_drilling_sheet():
            return

        samples_per = self._get_cd_samples_per()
        sheet_key = self.current_item
        params = self._cd_params.get(sheet_key, {})
        data = self.sheet_data.get(sheet_key, [])
        if row >= len(data):
            return

        # 计算当前行的测试强度
        area_val = self._to_float(self.table.item(row, self._CD_COL_AREA))
        load_val = self._to_float(self.table.item(row, self._CD_COL_LOAD))

        strength_item = self.table.item(row, self._CD_COL_STRENGTH)
        if strength_item is None:
            strength_item = QTableWidgetItem()
            self.table.setItem(row, self._CD_COL_STRENGTH, strength_item)

        if area_val and area_val > 0 and load_val:
            strength = load_val / area_val * LOAD_TO_STRENGTH_FACTOR
            strength_item.setText(f"{strength:.1f}")
        else:
            strength_item.setText("")

        # 找到所在构件的所有行，收集芯样强度（批推定模式推定值输出“/”，单构件模式取最小值）
        comp_row_start = (row // samples_per) * samples_per
        strength_values = []
        for r in range(comp_row_start, min(comp_row_start + samples_per, self.table.rowCount())):
            it = self.table.item(r, self._CD_COL_STRENGTH)
            v = self._to_float(it)
            if v and v > 0:
                strength_values.append(v)

        inferred = None
        if strength_values:
            inferred = min(strength_values)

        # 更新推定值列（合并区域只更新 anchor 单元格）
        inferred_item = self.table.item(comp_row_start, self._CD_COL_INFERRED)
        if inferred_item is None:
            inferred_item = QTableWidgetItem()
            self.table.setItem(comp_row_start, self._CD_COL_INFERRED, inferred_item)
        if params.get("method", "batch") == "batch":
            inferred_item.setText("/")
        elif inferred:
            inferred_item.setText(f"{inferred:.1f}")
        else:
            inferred_item.setText("")

    def _recalc_core_drilling_all(self):
        """Recalculate all core drilling rows and the batch assessment value."""
        if not self._is_core_drilling_sheet():
            return
        self._loading = True
        try:
            for r in range(self.table.rowCount()):
                self._recalc_core_drilling_row(r)
            self._recalc_core_drilling_batch_value()
        finally:
            self._loading = False

    def _get_cd_batch_raw(self, row):
        """Return the visible batch text for a row, resolving merged anchors."""
        if hasattr(self, "_resolve_anchor"):
            ar, ac = self._resolve_anchor(row, self._CD_COL_BATCH)
        else:
            ar, ac = row, self._CD_COL_BATCH
        item = self.table.item(ar, ac)
        return item.text().strip() if item is not None else ""

    def _get_cd_batch_token(self, row):
        """Return canonical numeric batch token for a merged batch cell, or None."""
        text = self._get_cd_batch_raw(row)
        value = self._to_float(text)
        if value is None or not math.isfinite(value) or value <= 0:
            return None
        if value == int(value):
            return str(int(value))
        return text

    def _get_cd_batch_groups(self):
        """Return contiguous batch groups for display and calculation.

        Numeric groups participate in critic assessment; "/" groups are merged
        but excluded from calculation. Empty batch cells are skipped.
        """
        groups = []
        row_count = self.table.rowCount()
        if row_count == 0:
            return groups

        samples_per = max(1, self._get_cd_samples_per())
        comp_start = 0
        while comp_start < row_count:
            raw = self._get_cd_batch_raw(comp_start)
            if raw == "":
                comp_start += samples_per
                continue

            value = self._to_float(raw)
            numeric = value is not None and math.isfinite(value) and value > 0
            if numeric:
                token = str(int(value)) if value == int(value) else raw
            else:
                token = raw

            run_start = comp_start
            run_end = min(comp_start + samples_per - 1, row_count - 1)
            values = self._collect_cd_component_strengths(comp_start)
            comp_start += samples_per

            while comp_start < row_count and self._get_cd_batch_raw(comp_start) == raw:
                values.extend(self._collect_cd_component_strengths(comp_start))
                run_end = min(comp_start + samples_per - 1, row_count - 1)
                comp_start += samples_per

            groups.append({
                "token": token,
                "start": run_start,
                "end": run_end,
                "values": values,
                "numeric": numeric,
            })
        return groups

    def _collect_cd_component_strengths(self, comp_start):
        """Collect valid test strength values for one component."""
        samples_per = self._get_cd_samples_per()
        values = []
        for r in range(comp_start, min(comp_start + samples_per, self.table.rowCount())):
            v = self._to_float(self.table.item(r, self._CD_COL_STRENGTH))
            if v is not None and v > 0:
                values.append(v)
        return values

    def _get_cd_batch_runs(self):
        """Return contiguous numeric-batch runs with collected strength samples."""
        runs = []
        row_count = self.table.rowCount()
        if row_count == 0:
            return runs

        samples_per = max(1, self._get_cd_samples_per())
        comp_start = 0
        while comp_start < row_count:
            token = self._get_cd_batch_token(comp_start)
            if token is None:
                comp_start += samples_per
                continue

            run_start = comp_start
            run_end = min(comp_start + samples_per - 1, row_count - 1)
            values = self._collect_cd_component_strengths(comp_start)
            comp_start += samples_per

            while comp_start < row_count and self._get_cd_batch_token(comp_start) == token:
                values.extend(self._collect_cd_component_strengths(comp_start))
                run_end = min(comp_start + samples_per - 1, row_count - 1)
                comp_start += samples_per

            runs.append({
                "token": token,
                "start": run_start,
                "end": run_end,
                "values": values,
            })
        return runs

    def _get_cd_run_for_row(self, row):
        """Return the batch run containing the given row, or None."""
        for run in self._get_cd_batch_runs():
            if run["start"] <= row <= run["end"]:
                return run
        return None

    def _refresh_core_drilling_batch_merges(self, groups):
        """Recreate batch-column merges according to current batch groups."""
        if not self.current_item:
            return
        sheet_key = self.current_item
        merges = [m for m in self._merges.get(sheet_key, [])
                  if m[1] != self._CD_COL_BATCH]
        formats = self._merge_formats.setdefault(sheet_key, {})
        for key in [k for k in formats if k[1] == self._CD_COL_BATCH]:
            formats.pop(key, None)

        for group in groups:
            start = group["start"]
            end = group["end"]
            if end - start + 1 > 1:
                merges.append((start, self._CD_COL_BATCH, end - start + 1, 1))
            formats[(start, self._CD_COL_BATCH)] = {"align": "center"}

        self._merges[sheet_key] = merges
        self._apply_merges_to_table()

    def _refresh_core_drilling_critic_merges(self, runs):
        """Recreate critic-column merges according to current numeric batch runs."""
        if not self.current_item:
            return
        sheet_key = self.current_item
        merges = [m for m in self._merges.get(sheet_key, [])
                  if m[1] != self._CD_COL_CRITIC]
        formats = self._merge_formats.setdefault(sheet_key, {})
        for key in [k for k in formats if k[1] == self._CD_COL_CRITIC]:
            formats.pop(key, None)

        for run in runs:
            start = run["start"]
            end = run["end"]
            if end - start + 1 > 1:
                merges.append((start, self._CD_COL_CRITIC, end - start + 1, 1))
            formats[(start, self._CD_COL_CRITIC)] = {"align": "center", "bold": True}

        self._merges[sheet_key] = merges
        self._apply_merges_to_table()

    def _recalc_core_drilling_batch_value(self):
        """根据检测方法计算批评定值并写回表格。

        检测方法为“批推定（批评定）”时，按“批次”列分组计算；
        批次单元格输入数字时参与批评定，输入“/”或留空时不参与。
        检测方法为“单构件检测”时，仅保留每构件推定值，不生成批评定值。
        """
        if not self._is_core_drilling_sheet():
            return
        if self.table.rowCount() == 0:
            return

        sheet_key = self.current_item
        params = self._cd_params.get(sheet_key, {})

        # 先清空全部批评定值，避免批次变化或模式切换后残留旧值
        for r in range(self.table.rowCount()):
            critic_item = self.table.item(r, self._CD_COL_CRITIC)
            if critic_item is not None:
                critic_item.setText("")
                critic_item.setForeground(Qt.black)

        if params.get("method", "batch") != "batch":
            self._refresh_core_drilling_batch_merges([])
            self._refresh_core_drilling_critic_merges([])
            return

        groups = self._get_cd_batch_groups()
        if not groups:
            self._refresh_core_drilling_batch_merges([])
            self._refresh_core_drilling_critic_merges([])
            return
        self._refresh_core_drilling_batch_merges(groups)

        runs = [g for g in groups if g.get("numeric")]
        if not runs:
            self._refresh_core_drilling_critic_merges(groups)
            return

        D = self._to_float(self.table.item(0, self._CD_COL_DIAMETER))
        if D is None or D <= 0:
            D = params.get("diameter")
        if D is None or D <= 0:
            self._refresh_core_drilling_critic_merges(groups)
            return

        grade_text = None
        first_grade_item = self.table.item(0, self._CD_COL_GRADE)
        if first_grade_item is not None:
            grade_text = first_grade_item.text().strip()
        if not grade_text:
            grade_text = params.get("grade")
        design_value = self._parse_design_value(grade_text)

        for run in runs:
            critic_item = self.table.item(run["start"], self._CD_COL_CRITIC)
            if critic_item is None:
                critic_item = QTableWidgetItem()
                self.table.setItem(run["start"], self._CD_COL_CRITIC, critic_item)

            Xi = run["values"]
            if not Xi:
                critic_item.setText("")
                critic_item.setForeground(Qt.black)
                continue

            try:
                result = batch_assess(D, Xi, design_value, mode="batch")
            except Exception:
                result = {"error": "计算失败"}

            f_cu_e = result.get("f_cu_e")
            if result.get("error") or f_cu_e is None:
                critic_item.setText("")
                critic_item.setForeground(Qt.black)
                continue

            if result.get("valid") is False or result.get("insufficient"):
                critic_item.setText(f"{f_cu_e:.1f} \u26a0")
                critic_item.setForeground(Qt.red)
            else:
                critic_item.setText(f"{f_cu_e:.1f}")
                critic_item.setForeground(Qt.black)

        self._refresh_core_drilling_critic_merges(groups)

    @staticmethod
    def _parse_design_value(grade_text):
        """解析设计强度等级字符串为数值 (MPa)。

        "C40" → 40.0；"C35" → 35.0；"40" → 40.0；空或无法解析 → None
        """
        if not grade_text:
            return None
        s = str(grade_text).strip()
        if not s:
            return None
        # 去除前导字母（如 C、c、C30 中的 C）
        digits = ""
        for ch in s:
            if ch.isdigit() or ch == ".":
                digits += ch
            elif digits:
                break
        if not digits:
            return None
        try:
            return float(digits)
        except ValueError:
            return None

    def _run_batch_assessment(self):
        """钻芯法批量推定计算（批评定）。

        根据当前选中行所在批次执行计算；批次列为“/”或空时提示并返回。
        """
        if not self._is_core_drilling_sheet():
            QMessageBox.information(
                self.win, "提示", "请在钻芯法检测工作表上执行批推定计算。"
            )
            return

        sheet_key = self.current_item
        params = self._cd_params.get(sheet_key, {})
        if params.get("method", "batch") != "batch":
            QMessageBox.information(
                self.win, "提示", "当前检测方法为“单构件检测”，无需批推定计算。"
            )
            return

        row = self.table.currentRow()
        if row < 0:
            row = 0
        run = self._get_cd_run_for_row(row)
        if run is None:
            QMessageBox.warning(
                self.win, "无法计算",
                "当前构件未设置批号。请先在“批次”列输入数字（如 1、2）；"
                "不参与批评定的批次请输入“/”。"
            )
            return

        Xi = run["values"]
        if not Xi:
            QMessageBox.warning(
                self.win, "无法计算",
                "当前批次未收集到有效的测试强度数据，请先填写测试荷载。"
            )
            return

        # ── 获取芯样直径 D（优先取当前批次首行，回退到对话框参数）──
        D = self._to_float(self.table.item(run["start"], self._CD_COL_DIAMETER))
        if D is None or D <= 0:
            D = params.get("diameter")
        if D is None or D <= 0:
            QMessageBox.warning(self.win, "无法计算", "未能获取有效的芯样直径。")
            return

        # ── 获取设计强度等级 design_value ──
        grade_text = None
        first_grade_item = self.table.item(0, self._CD_COL_GRADE)
        if first_grade_item is not None:
            grade_text = first_grade_item.text().strip()
        if not grade_text:
            grade_text = params.get("grade")
        design_value = self._parse_design_value(grade_text)

        # ── 执行当前批次的批推定计算 ──
        try:
            result = batch_assess(D, Xi, design_value, mode="batch")
        except Exception as e:
            QMessageBox.critical(self.win, "计算错误", f"批推定计算失败：{e}")
            return

        # ── 展示结果 ──
        dlg = BatchAssessmentResultDialog(result, self.win)
        dlg.exec_()

        # ── 同步所有批次的批评定值与合并显示 ──
        self._recalc_core_drilling_batch_value()
        self._sync_table_to_data()

        f_cu_e = result.get("f_cu_e")
        if result.get("error") or f_cu_e is None:
            self._status("批评定值未生成")
        else:
            reason = ""
            if result.get("valid") is False:
                reason = "，推定区间过宽，仅供参考"
            elif result.get("insufficient"):
                reason = "，芯样数量不足，仅供参考"
            self._status(f"批评定值已更新: {f_cu_e:.1f} MPa{reason}")


    def _build_rebound_core_drilling_sheet(self, sheet_key, params):
        """根据回弹钻芯修正法初始参数构建工作表。
        """
        building = params.get("building", "")
        batch_count = params.get("batches", 1)
        comps_per_batch = params.get("components_per_batch", 5)
        zones_per_component = params.get("zones_per_component", 3)
        grade = params.get("grade", "C40")
        diameter = params.get("diameter", 100.0)

        total_rows = batch_count * comps_per_batch * zones_per_component
        cols = ITEM_COLUMNS.get("回弹钻芯修正法检测", [])
        area = math.pi * (diameter / 2) ** 2
        rows_per_batch = comps_per_batch * zones_per_component

        data = [["" for _ in range(len(cols))] for _ in range(total_rows)]
        for b in range(batch_count):
            batch_no = str(b + 1)
            batch_start = b * rows_per_batch
            for comp_idx in range(comps_per_batch):
                comp_start = batch_start + comp_idx * zones_per_component
                comp_no = str(comp_idx + 1)
                for z in range(zones_per_component):
                    row = comp_start + z
                    data[row][self._RCD_COL_BUILDING] = building
                    data[row][self._RCD_COL_BATCH] = batch_no
                    data[row][self._RCD_COL_COMP_NO] = comp_no
                    data[row][self._RCD_COL_COMP_NAME] = ""
                    data[row][self._RCD_COL_AXIS] = ""
                    data[row][self._RCD_COL_ZONE] = str(z + 1)
                    data[row][self._RCD_COL_DIAMETER] = f"{diameter:.1f}"
                    data[row][self._RCD_COL_AREA] = f"{area:.3f}"
                    data[row][self._RCD_COL_LOAD] = ""
                    data[row][self._RCD_COL_STRENGTH] = ""
                    data[row][self._RCD_COL_GRADE] = grade
                    data[row][self._RCD_COL_MEAN] = ""

        self.sheet_data[sheet_key] = data

        merges = []
        if total_rows > 1:
            merges.append((0, self._RCD_COL_BUILDING, total_rows, 1))
        for b in range(batch_count):
            batch_start = b * rows_per_batch
            if rows_per_batch > 1:
                merges.append((batch_start, self._RCD_COL_BATCH, rows_per_batch, 1))
                merges.append((batch_start, self._RCD_COL_GRADE, rows_per_batch, 1))
                merges.append((batch_start, self._RCD_COL_MEAN, rows_per_batch, 1))
            for comp_idx in range(comps_per_batch):
                comp_start = batch_start + comp_idx * zones_per_component
                if zones_per_component > 1:
                    merges.append((comp_start, self._RCD_COL_COMP_NO, zones_per_component, 1))
                    merges.append((comp_start, self._RCD_COL_COMP_NAME, zones_per_component, 1))
                    merges.append((comp_start, self._RCD_COL_AXIS, zones_per_component, 1))
        self._merges[sheet_key] = merges

        merge_formats = {(0, self._RCD_COL_BUILDING): {"align": "center"}}
        for b in range(batch_count):
            batch_start = b * rows_per_batch
            merge_formats[(batch_start, self._RCD_COL_BATCH)] = {"align": "center"}
            merge_formats[(batch_start, self._RCD_COL_GRADE)] = {"align": "center", "bold": True}
            merge_formats[(batch_start, self._RCD_COL_MEAN)] = {"align": "center", "bold": True}
            for comp_idx in range(comps_per_batch):
                comp_start = batch_start + comp_idx * zones_per_component
                for c in [self._RCD_COL_COMP_NO, self._RCD_COL_COMP_NAME, self._RCD_COL_AXIS]:
                    merge_formats[(comp_start, c)] = {"align": "center"}
        self._merge_formats[sheet_key] = merge_formats
        self._cd_params[sheet_key] = {
            "building": building,
            "batches": batch_count,
            "components_per_batch": comps_per_batch,
            "zones_per_component": zones_per_component,
            "grade": grade,
            "diameter": diameter,
        }

    @staticmethod
    def _get_floor_labels(component):
        """返回回弹钻芯修正法检测构件位置及名称的允许值列表。"""
        config = {
            "梁": ("FL", "WML"),
            "柱": ("FZ", None),
            "板": ("FB", "WMB"),
            "墙": ("FQ", None),
            "剪力墙": ("FQ", None),
        }
        item = config.get(component)
        if not item:
            return []
        suffix, roof_label = item
        labels = [f"{f}{suffix}" for f in REBOUND_NEGATIVE_FLOORS]
        labels += [f"{i}{suffix}" for i in range(1, REBOUND_FLOOR_COUNT + 1)]
        if roof_label:
            labels.append(roof_label)
        return labels

    @staticmethod
    def _infer_component_type(base, comp):
        """根据工作表名称和树节点构件名推断构件类型。"""
        if comp in ("梁", "柱", "板", "墙", "剪力墙", "基础"):
            return comp
        if not base:
            return None
        if "梁" in base:
            return "梁"
        if "柱" in base:
            return "柱"
        if "板" in base:
            return "板"
        if "墙" in base:
            return "墙"
        return None

    def _get_rcd_zones_per(self):
        """获取当前回弹钻芯修正法工作表的每构件钻芯测区数量"""
        if not self.current_item:
            return 3
        params = self._cd_params.get(self.current_item, {})
        return params.get("zones_per_component", 3)

    def _is_rebound_core_drilling_sheet(self, sheet_key=None):
        """判断当前工作表是否为回弹钻芯修正法检测类型"""
        if sheet_key is None:
            sheet_key = self.current_item
        if not sheet_key:
            return False
        base, _comp = self._parse_sheet_key(sheet_key)
        return base == "回弹钻芯修正法检测"

    def _recalc_rebound_core_drilling_row(self, row):
        """计算回弹钻芯修正法表格指定行的测试强度。

        测试强度(MPa) = 测试荷载(kN) × 1000 / 截面积(mm²)
        """
        if not self._is_rebound_core_drilling_sheet():
            return
        area_val = self._to_float(self.table.item(row, self._RCD_COL_AREA))
        load_val = self._to_float(self.table.item(row, self._RCD_COL_LOAD))
        strength_item = self.table.item(row, self._RCD_COL_STRENGTH)
        if strength_item is None:
            strength_item = QTableWidgetItem()
            self.table.setItem(row, self._RCD_COL_STRENGTH, strength_item)
        if area_val and area_val > 0 and load_val:
            strength = load_val / area_val * LOAD_TO_STRENGTH_FACTOR
            strength_item.setText(f"{strength:.1f}")
        else:
            strength_item.setText("")

    def _recalc_rebound_core_drilling_batch_mean(self):
        """重算每个批次的芯样强度均值，写入对应合并单元格。"""
        if not self._is_rebound_core_drilling_sheet():
            return
        if self.table.rowCount() == 0:
            return
        sheet_key = self.current_item
        params = self._cd_params.get(sheet_key, {})
        batch_count = params.get("batches", 1)
        comps_per_batch = params.get("components_per_batch", 5)
        zones_per_component = params.get("zones_per_component", 3)
        rows_per_batch = comps_per_batch * zones_per_component
        for b in range(batch_count):
            batch_start = b * rows_per_batch
            batch_end = min(batch_start + rows_per_batch, self.table.rowCount())
            values = []
            for r in range(batch_start, batch_end):
                v = self._to_float(self.table.item(r, self._RCD_COL_STRENGTH))
                if v is not None and v > 0:
                    values.append(v)
            mean_item = self.table.item(batch_start, self._RCD_COL_MEAN)
            if mean_item is None:
                mean_item = QTableWidgetItem()
                self.table.setItem(batch_start, self._RCD_COL_MEAN, mean_item)
            if values:
                mean_item.setText(f"{sum(values) / len(values):.1f}")
            else:
                mean_item.setText("")

    def _recalc_rebound_core_drilling_all(self):
        """Recalculate all rebound-core drilling rows and batch mean values."""
        if not self._is_rebound_core_drilling_sheet():
            return
        self._loading = True
        try:
            for r in range(self.table.rowCount()):
                self._recalc_rebound_core_drilling_row(r)
            self._recalc_rebound_core_drilling_batch_mean()
        finally:
            self._loading = False

    def _core_drilling_cell_changed(self, row, col, item):
        """单元格编辑联动钩子：位置列楼层校验 + 钻芯法/回弹钻芯修正法重算。

        由主窗口在单元格编辑后调用：
        1. 构件位置列（构件位置及名称等）输入校验——楼层标签
           （FL/FZ/FB/FQ）不对时警告并清空，对所有含位置列的工作表生效；
        2. 钻芯法/回弹钻芯修正法：测试荷载列变化时重算该行测试强度，
           直径列变化时重算截面积并联动整组构件，批次列变化时重算批评定值；
        返回 True 表示当前工作表命中本模块的钻芯法业务并已处理。
        """
        # ── 构件位置列输入校验（楼层标签 FL/FZ/FB/FQ）──
        # 注：早期版本会对不在下拉候选列表中的值弹窗警告并清空，导致用户
        # 手动输入的自定义位置名（如 "12层WKL-5"）无法保存，出现"选择后
        # 仍无法显示"的现象。现改为：下拉仅作为快捷候选项，允许自由输入
        # 任意位置及名称文本，不再做强校验清空。
        pos_col = self._get_position_column(self._get_columns(self.current_item))
        _ = pos_col  # 保留语义占位，避免未使用告警

        if self._is_core_drilling_sheet():
            if col == self._CD_COL_LOAD:
                self._recalc_core_drilling_row(row)
                self._recalc_core_drilling_batch_value()
                self._sync_table_to_data()
            elif col == self._CD_COL_DIAMETER:
                sp = self._get_cd_samples_per()
                comp_start = (row // sp) * sp
                d_val = self._to_float(item)
                if d_val and d_val > 0:
                    new_area = math.pi * (d_val / 2) ** 2
                    for r in range(comp_start, min(comp_start + sp, self.table.rowCount())):
                        area_it = self.table.item(r, self._CD_COL_AREA)
                        if area_it is None:
                            area_it = QTableWidgetItem()
                            self.table.setItem(r, self._CD_COL_AREA, area_it)
                        area_it.setText(f"{new_area:.0f}")
                        d_item = self.table.item(r, self._CD_COL_DIAMETER)
                        if d_item is None:
                            d_item = QTableWidgetItem()
                            self.table.setItem(r, self._CD_COL_DIAMETER, d_item)
                        d_item.setText(f"{d_val:.1f}")
                for r in range(comp_start, min(comp_start + sp, self.table.rowCount())):
                    self._recalc_core_drilling_row(r)
                self._recalc_core_drilling_batch_value()
                self._sync_table_to_data()
            elif col == self._CD_COL_BATCH:
                self._recalc_core_drilling_batch_value()
                self._sync_table_to_data()
            return True

        if self._is_rebound_core_drilling_sheet():
            if col == self._RCD_COL_LOAD:
                self._recalc_rebound_core_drilling_row(row)
                self._recalc_rebound_core_drilling_batch_mean()
                self._sync_table_to_data()
            elif col == self._RCD_COL_DIAMETER:
                d_val = self._to_float(item)
                if d_val and d_val > 0:
                    area_val = math.pi * (d_val / 2) ** 2
                    area_item = self.table.item(row, self._RCD_COL_AREA)
                    if area_item is None:
                        area_item = QTableWidgetItem()
                        self.table.setItem(row, self._RCD_COL_AREA, area_item)
                    area_item.setText(f"{area_val:.3f}")
                self._recalc_rebound_core_drilling_row(row)
                self._recalc_rebound_core_drilling_batch_mean()
                self._sync_table_to_data()
            return True

        return False

    def _core_drilling_sheet_loaded(self, sheet_key, cols):
        """工作表加载钩子：位置列楼层下拉设置 + 钻芯法/回弹钻芯修正法全表重算。

        由主窗口在加载工作表完成后调用：
        1. 构件位置列（构件位置及名称等）挂接楼层标签下拉
           （FL/FZ/FB/FQ，由构件类型推断），无位置列时移除已有下拉；
        2. 钻芯法/回弹钻芯修正法工作表加载时重算所有测试强度和推定值。
        """
        # ── 构件位置列楼层标签下拉 ──
        pos_col = self._get_position_column(cols)
        if pos_col is not None:
            base, comp = self._parse_sheet_key(sheet_key)
            comp_type = self._infer_component_type(base, comp)
            allowed = self._get_floor_labels(comp_type)
            if allowed:
                if self._floor_delegate_column is not None and self._floor_delegate_column != pos_col:
                    self.table.setItemDelegateForColumn(self._floor_delegate_column, None)
                self._floor_delegate.set_items(allowed)
                self.table.setItemDelegateForColumn(pos_col, self._floor_delegate)
                self._floor_delegate_column = pos_col
            else:
                if self._floor_delegate_column is not None:
                    self.table.setItemDelegateForColumn(self._floor_delegate_column, None)
                self._floor_delegate_column = None
        else:
            if self._floor_delegate_column is not None:
                self.table.setItemDelegateForColumn(self._floor_delegate_column, None)
            self._floor_delegate_column = None

        # ── 钻芯法/回弹钻芯修正法：加载时重算所有测试强度和推定值 ──
        if self._is_core_drilling_sheet(sheet_key):
            self._recalc_core_drilling_all()
        elif self._is_rebound_core_drilling_sheet(sheet_key):
            self._recalc_rebound_core_drilling_all()

    def _core_drilling_context_menu(self):
        """右键菜单贡献项钩子（注册式分派）。

        返回 [(显示文本, 处理函数), ...]；仅钻芯法工作表返回专属动作，
        其余工作表返回空列表。
        """
        if self._is_core_drilling_sheet():
            return [
                ("批量录入构件信息", self._batch_input_core_drilling_components),
                ("批推定计算", self._run_batch_assessment),
                ("删除当前构件", self._delete_core_drilling_component),
            ]
        return []

    def _batch_input_core_drilling_components(self):
        """批量录入钻芯法构件的构件位置及名称与轴线编号。

        钻芯法表格中“构件位置及名称 / 轴线编号”按构件合并，逐个锚点行
        录入较繁琐；此对话框把每个构件集中到一张可编辑列表中，名称列仍
        保留楼层标签下拉候选（可自由输入），确定后一次写回工作表。
        """
        if not self._is_core_drilling_sheet():
            QMessageBox.information(self.win, "提示", "请在钻芯法检测工作表上执行此操作。")
            return

        sheet_key = self.current_item
        data = self.sheet_data.get(sheet_key, [])
        samples_per = self._get_cd_samples_per()
        if not data:
            QMessageBox.information(self.win, "提示", "当前没有构件数据。")
            return

        components = []
        for comp_idx in range(0, len(data), samples_per):
            row = data[comp_idx]
            components.append({
                "no": str(row[self._CD_COL_COMP_NO]).strip() if len(row) > self._CD_COL_COMP_NO else "",
                "name": str(row[self._CD_COL_COMP_NAME]).strip() if len(row) > self._CD_COL_COMP_NAME else "",
                "axis": str(row[self._CD_COL_AXIS]).strip() if len(row) > self._CD_COL_AXIS else "",
            })

        base, comp = self._parse_sheet_key(sheet_key)
        comp_type = self._infer_component_type(base, comp)
        floor_labels = self._get_floor_labels(comp_type)

        from .dialogs import CoreDrillingComponentInputDialog
        dlg = CoreDrillingComponentInputDialog(components, floor_labels, self.win)
        if dlg.exec_() != QDialog.Accepted:
            return

        updated = dlg.get_components()
        self._sync_table_to_data()
        data = self.sheet_data.get(sheet_key, [])
        for idx, info in enumerate(updated):
            start = idx * samples_per
            for r in range(start, min(start + samples_per, len(data))):
                data[r][self._CD_COL_COMP_NAME] = info.get("name", "")
                data[r][self._CD_COL_AXIS] = info.get("axis", "")
        self.sheet_data[sheet_key] = data
        self._load_item(sheet_key)
        self._status("已批量录入构件信息")

    def _delete_core_drilling_component(self):
        """删除选中行所在的整个构件（含其全部芯样行）。

        钻芯法表格按构件分组，每构件占 ``samples_per`` 行；删除时整组移除，
        避免破坏合并结构。楼栋/设计等级等全表合并由 _adjust_merges_for_delete_row
        自动缩减行高。

        当全部构件被删除后，自动移除整个工作表并取消树节点勾选；
        再次勾选时重新弹出参数对话框创建新表。
        """
        if not self._is_core_drilling_sheet():
            QMessageBox.information(self.win, "提示", "请在钻芯法检测工作表上执行此操作。")
            return

        sheet_key = self.current_item
        data = self.sheet_data.get(sheet_key, [])

        # 检查是否还有实际构件数据（构件编号列是否有非空值）
        has_components = any(
            len(row) > self._CD_COL_COMP_NO
            and row[self._CD_COL_COMP_NO]
            and str(row[self._CD_COL_COMP_NO]).strip()
            for row in data
        )

        if not has_components:
            # 数据已全部删除 → 移除整个工作表，再次勾选时重新弹出对话框
            self._remove_sheet_data(sheet_key)
            self._status(f"已删除工作表: {sheet_key}")
            return

        samples_per = self._get_cd_samples_per()
        total_rows = len(data)

        # 确定当前选中行所在的构件行范围
        rng = self._get_selected_range()
        if not rng:
            # 无选中时默认取第一行作为当前构件
            current_row = 0
        else:
            current_row = rng[0]
        if current_row >= total_rows:
            current_row = total_rows - 1

        comp_row_start = (current_row // samples_per) * samples_per
        comp_row_end = min(comp_row_start + samples_per - 1, total_rows - 1)
        comp_idx = comp_row_start // samples_per + 1

        reply = QMessageBox.question(
            self.win, "确认删除构件",
            f"确定删除第 {comp_row_start + 1}~{comp_row_end + 1} 行"
            f"（构件 {comp_idx}，{comp_row_end - comp_row_start + 1} 个芯样）？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 从下往上逐行删除，复用现有合并调整逻辑
        self._reset_spans()
        self._loading = True
        try:
            for r in range(comp_row_end, comp_row_start - 1, -1):
                self.table.removeRow(r)
                self._adjust_merges_for_delete_row(r)
        finally:
            self._loading = False
        self._apply_merges_to_table()
        self._update_row_headers(self.table.rowCount())
        self._sync_table_to_data()

        # 删除后检查是否还有构件数据，若全部删光则移除整个工作表
        remaining = self.sheet_data.get(sheet_key, [])
        has_remaining = any(
            len(row) > self._CD_COL_COMP_NO
            and row[self._CD_COL_COMP_NO]
            and str(row[self._CD_COL_COMP_NO]).strip()
            for row in remaining
        )
        if not has_remaining:
            self._remove_sheet_data(sheet_key)
            self._status(f"已删除工作表: {sheet_key}")
            return

        # 重算剩余构件的推定值（行号映射未变，全表重算保险）
        self._recalc_core_drilling_all()
        self._status(f"已删除构件 {comp_idx}（第 {comp_row_start + 1}~{comp_row_end + 1} 行）")

    def _apply_core_drilling_merges(self):
        """在钻芯法检测表格生成后，应用合并单元格"""
        if not self._is_core_drilling_sheet():
            return
        sheet_key = self.current_item
        merges = self._merges.get(sheet_key, [])
        self._reset_spans()
        for (r, c, rs, cs) in merges:
            if rs <= 1 and cs <= 1:
                continue
            try:
                self.table.setSpan(r, c, rs, cs)
                # 恢复合并格式
                fmt = self._merge_formats.get(sheet_key, {}).get((r, c), {})
                anchor = self.table.item(r, c)
                if anchor and fmt:
                    align = fmt.get("align", "center")
                    flag = {"left": Qt.AlignLeft, "center": Qt.AlignCenter,
                            "right": Qt.AlignRight}.get(align, Qt.AlignCenter)
                    anchor.setTextAlignment(flag | Qt.AlignVCenter)
                    if fmt.get("bold"):
                        f = anchor.font()
                        f.setBold(True)
                        anchor.setFont(f)
            except Exception:
                pass
        self._displayed_merges = list(merges)
