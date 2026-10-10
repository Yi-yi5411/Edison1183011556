# -*- coding: utf-8 -*-
"""保护层厚度检测 GUI 逻辑（mixin）。

保护层厚度汇总（合格点率/结论列）的配置与重算逻辑从主窗口下沉到此，
与保护层列头、CALC_RULES 同处一模块，主窗口仅负责调度。
"""

# 保护层厚度（已删除平均值列）：偏差值测点列 deviation_cols / 合格点率列 / 结论列 / 允许偏差
THICKNESS_SUMMARY_CONFIG = {
    '混凝土梁保护层厚度检测': {'deviation_cols': list(range(15, 25)), 'pass_rate_col': 25, 'conclusion_col': 26, 'lower': -7.0, 'upper': 10.0},
    '混凝土柱保护层厚度检测': {'deviation_cols': list(range(15, 25)), 'pass_rate_col': 25, 'conclusion_col': 26, 'lower': -7.0, 'upper': 10.0},
    '剪力墙保护层厚度检测': {'deviation_cols': list(range(15, 25)), 'pass_rate_col': 25, 'conclusion_col': 26, 'lower': -5.0, 'upper': 8.0},
    '混凝土板保护层厚度检测': {'deviation_cols': list(range(15, 25)), 'pass_rate_col': 25, 'conclusion_col': 26, 'lower': -5.0, 'upper': 8.0},
}


class CoverThicknessMixin:
    """保护层厚度检测的合格点率汇总重算。"""

    def _recalc_cover_thickness_totals(self):
        """按参考 Excel 公式语义重算保护层厚度合格点率并合并单元格。

        各类型合格点率与以下 Excel 公式等价（仅允许偏差区间不同）：
            梁/柱  [-7, +10]：1-(COUNTIF(P:Y,"<-7")+COUNTIF(P:Y,">10"))/SUMPRODUCT(--ISNUMBER(P:Y))
            剪力墙/板 [-5, +8]：1-(COUNTIF(P:Y,"<-5")+COUNTIF(P:Y,">8"))/SUMPRODUCT(--ISNUMBER(P:Y))
        - 分母仅统计“真正的数值”单元格：空白与非数值文本（如“/”）不计，
          对应 SUMPRODUCT(--ISNUMBER(偏差区))；
        - 分子统计低于下限或高于上限的偏差点，边界值（-7/-5、+8/+10）判合格，
          对应 COUNTIF("<下限") + COUNTIF(">上限")；
        - 合格点率 ≥90% 判“合格”、≥80% 判“再抽检”、否则“不合格”。
        结论列存在（列数大于 conclusion_col）时才写入，并与合格点率列一同纵向合并。
        """
        if not self.current_item:
            return
        base, _comp = self._parse_sheet_key(self.current_item)
        cfg = THICKNESS_SUMMARY_CONFIG.get(base)
        if not cfg:
            return

        pass_rate_col = cfg['pass_rate_col']
        conclusion_col = cfg['conclusion_col']
        lower = cfg['lower']
        upper = cfg['upper']
        deviation_cols = cfg['deviation_cols']
        column_count = self.table.columnCount()

        for r in range(self.table.rowCount()):
            self._calc_set_cell(r, pass_rate_col, "")
            self._calc_set_cell(r, conclusion_col, "")

        total = 0
        fail = 0
        first = None
        last = -1
        for r in range(self.table.rowCount()):
            for c in deviation_cols:
                v = self._to_float(self.table.item(r, c))
                if v is None:
                    # 空白 / 非数值文本不参与统计，对应 SUMPRODUCT(--ISNUMBER(偏差区))
                    continue
                if first is None:
                    first = r
                last = r
                total += 1
                if v < lower or v > upper:
                    fail += 1

        merges = self._merges.setdefault(self.current_item, [])
        merges[:] = [m for m in merges if m[1] not in (pass_rate_col, conclusion_col)]

        if total == 0:
            self._apply_merges_to_table()
            return

        rate = (1 - fail / total) * 100
        self._calc_set_cell(first, pass_rate_col, f"{rate:.2f}%")
        merge = (first, pass_rate_col, last - first + 1, 1)
        if merge not in merges:
            merges.append(merge)

        # 当前列布局无“合格/不合格”列（conclusion_col 越界）时跳过，避免无效合并
        if conclusion_col < column_count:
            if rate >= 90:
                conclusion = '合格'
            elif rate >= 80:
                conclusion = '再抽检'
            else:
                conclusion = '不合格'
            self._calc_set_cell(first, conclusion_col, conclusion)
            cmerge = (first, conclusion_col, last - first + 1, 1)
            if cmerge not in merges:
                merges.append(cmerge)

        self._apply_merges_to_table()

    # ── 测点录入（原始记录辅助录入）──
    def _open_cover_point_entry(self):
        """测点录入（保护层原始记录）：每根主筋在两端部和跨中各测2次，
        平均值作为系统实测值。

        流程：独立对话框批量录入多构件测点 → 生成 HBJG/JJ 0226014
        原始记录 Word（WPS/Word COM 填充模板）→ 按项目类型定位并跳转
        对应保护层工作表回填平均值（偏差值/合格点率走自动计算）。
        """
        from PyQt5.QtWidgets import QDialog, QMessageBox
        from framework.models import PROJECT_NAME
        from framework.resources import get_asset
        from modules.cover_thickness.point_dialog import CoverPointEntryDialog
        from modules.cover_thickness.word_record import (
            fill_cover_original_record, TEMPLATE_ASSET)

        defaults = {'工程名称': PROJECT_NAME, '楼栋': '1#'}
        dlg = CoverPointEntryDialog(
            list(THICKNESS_SUMMARY_CONFIG.keys()), parent=self.win,
            defaults=defaults)
        if dlg.exec_() != QDialog.Accepted:
            return
        records = dlg.get_records()
        header = dlg.get_header()

        # 1) 跳转回填：按构件所属项目定位工作表（未勾选时自动勾选建表）
        filled = 0
        for comp in records:
            key = self._resolve_fill_target(comp['project'])
            if key is None:
                QMessageBox.warning(
                    self.win, "未找到检测项目",
                    "「%s」未匹配到检测项目工作表，该构件未回填。"
                    % comp['project'])
                continue
            averages = [float(a) for a in comp['averages']][:10]
            row = ([comp['building'], comp['position'], comp['axis'],
                    comp['design'], comp['n_rebars']]
                   + averages + [''] * (10 - len(averages))
                   + [''] * 11)   # 偏差值1~10 + 合格点率，交由自动计算
            self._sync_table_to_data()
            existing = self._trim_empty_tail_rows(
                self.sheet_data.get(key, []))
            existing.append(row)
            self.sheet_data[key] = existing
            self._load_item(key)
            self._run_current_calc()
            filled += 1

        # 2) 生成原始记录 Word
        out_path = None
        warnings = []
        try:
            template = get_asset(*TEMPLATE_ASSET, must_exist=True)
            out_path, warnings = fill_cover_original_record(
                str(template), records, header=header)
        except Exception as e:  # noqa: BLE001 - 生成失败不阻断回填结果提示
            QMessageBox.warning(self.win, "原始记录生成失败", str(e))

        self._status("测点录入：回填 %d 个构件%s"
                     % (filled, "，原始记录已生成" if out_path else ""))
        msg = "已回填 %d 个构件的测点平均值到检测工作表。" % filled
        if out_path:
            msg += "\n\n原始记录已生成：\n%s" % out_path
        if warnings:
            msg += "\n\n生成提示：\n" + "\n".join("· " + w for w in warnings[:10])
        QMessageBox.information(self.win, "测点录入完成", msg)

