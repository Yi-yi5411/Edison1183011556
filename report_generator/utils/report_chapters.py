# -*- coding: utf-8 -*-
"""《检测报告》各章节独立处理函数（纯函数，无 Qt 依赖）。

每个章节一个 ``build_xxx`` 函数，彼此独立、互不引用：
模板加载 → 内容填充 → 拼装进基准文档，全部在函数内部闭环。
章节间不共享任何可变状态，只依赖入参数据：

  - build_cover      封面（基准文档就地填充）
  - build_home       首页（信息表回填）
  - build_toc        目录（检测项目清单 + 残留占位符，最后调用）
  - build_overview   一、工程概况
  - build_basis      二、主要检测依据
  - build_equipment  三、主要检测设备
  - build_content    四、检测内容
  - build_results    五、检测结果（概述 + 逐项目一览表）
  - build_conclusion 六、检测结论（结论句插入）

通用 docx 操作来自 report_docx，模板映射来自 report_template_map。
"""
from docx import Document

try:
    from report_generator.utils.report_docx import (
        _append_chapter,
        _append_conclusions,
        _append_content_list,
        _clean_rows,
        _clean_template_notes,
        _fill_cover_personnel,
        _fill_home_info_table,
        _fill_result_table,
        _set_cell_text,
        _strip_empty_paragraphs,
        add_toc_page_fields,
        append_body_paragraph,
        fit_result_table_width,
        _fill_test_date,
        _replace_in_paragraph,
        _replace_placeholders,
        _trim_base_tail,
    )
    from report_generator.utils.assessment_engine import format_conclusion
    from report_generator.utils.report_narrative import (
        equipment_for,
        item_narrative,
        overview_text,
        standards_for,
    )
    from report_generator.utils.report_template_map import (
        build_conclusion as build_conclusion_sentence,
        resolve_sheet_key,
    )
    from report_generator.utils.report_templates import ReportTemplateSet
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_docx import (
        _append_chapter,
        _append_conclusions,
        _append_content_list,
        _clean_rows,
        _clean_template_notes,
        _fill_cover_personnel,
        _fill_home_info_table,
        _fill_result_table,
        _set_cell_text,
        _strip_empty_paragraphs,
        add_toc_page_fields,
        append_body_paragraph,
        fit_result_table_width,
        _fill_test_date,
        _replace_in_paragraph,
        _replace_placeholders,
        _trim_base_tail,
    )
    from utils.assessment_engine import format_conclusion
    from utils.report_narrative import (
        equipment_for,
        item_narrative,
        overview_text,
        standards_for,
    )
    from utils.report_template_map import (
        build_conclusion as build_conclusion_sentence,
        resolve_sheet_key,
    )
    from utils.report_templates import ReportTemplateSet


def chapter_path(name, template_set=None):
    """按章节名取模板文件路径（模板集合缺省为内置集合）。"""
    ts = template_set or ReportTemplateSet.builtin()
    return ts.chapter_path(name)


def _s(value):
    """抬头信息空值归一为空串。"""
    return str(value or "")


# ═══════════════════════════════════════════════════════════
#  封面 / 首页 / 目录
# ═══════════════════════════════════════════════════════════
def build_cover(base_doc, info):
    """封面：基准文档即封面模板，就地填充后修剪尾部空段。

    处理内容：{{project_name}}/{{report_date}} 占位符、"报告编号："
    等人员信息行追加值、删除模板填写提示行、清理尾部连续空段。
    """
    _replace_placeholders(base_doc, {
        "project_name": _s(info.get("project_name")),
        "report_date": _s(info.get("report_date")),
    })
    _fill_cover_personnel(base_doc, info)
    _clean_template_notes(base_doc)
    _trim_base_tail(base_doc)


def build_home(base_doc, info, template_set=None, basis=None):
    """首页（含目录页模板）：回填信息表后拼装。

    注意先填充再拼装：_append_chapter 是 deepcopy，拼装后再改
    源文档不生效。{page} 页数留待 COM 后处理回填。
    """
    home_src = Document(str(chapter_path("cover_home", template_set)))
    if home_src.tables:
        table = home_src.tables[0]
        _fill_home_info_table(table, info)
        # 首页“检测依据”行不在 info 字段里，用第二章同一份规范清单回填
        if basis:
            basis_text = "；".join(str(item).strip() for item in basis if str(item).strip())
            for row in table.rows:
                cells = row.cells
                if len(cells) >= 2 and "检测依据" in (cells[0].text or ""):
                    _set_cell_text(cells[1], basis_text, size=10.5)
                    break
    _append_chapter(base_doc, home_src, keep_section_break=True)


def build_toc(base_doc, checked_order, info):
    """目录 + 全文残留占位符统一收口（须在全部章节拼装后调用）。

    覆盖：目录条目中的检测项目清单（{{main_testing_items}}）、
    工程名称（{{project_name}}，含概况/首页等章节）、报告日期
    （{{report_date}}，含结论章节）。各章节函数只填自己的数据，
    残留 {{占位符}} 一律在此处一次替换，编排链路干净可查。
    """
    add_toc_page_fields(base_doc)
    try:
        from report_generator.utils.report_items import content_names
    except ImportError:  # 以 report_generator/ 为工作目录导入时
        from utils.report_items import content_names
    _replace_placeholders(base_doc, {
        "project_name": _s(info.get("project_name")),
        "main_testing_items": "、".join(content_names(checked_order)),
        "report_date": _s(info.get("report_date")),
    })


# ═══════════════════════════════════════════════════════════
#  一 ~ 四 章
# ═══════════════════════════════════════════════════════════
_REPORT_FILL_LABELS = (
    "楼栋", "楼层", "批次", "设计等级", "设计强度等级",
    "构件位置及名称", "构件名称", "构件位置",
    "构件轴号", "构件轴线编号", "轴线编号",
    "合格点率", "标准要求", "设计值", "钢筋牌号",
    "批评定值", "批混凝土强度推定值",
)
_REPORT_AXIS_LABELS = ("构件轴号", "构件轴线编号", "轴线编号")


def _normalize_report_rows(rows, columns):
    """报告表格专用：把分组列的空白续行补成有效值。

    只影响报告渲染，不改工程数据。批次/设计等级/位置等跨构件下填；
    轴线类在构件编号变化时重置，避免把上一个构件的轴线带到新构件。
    """
    labels = [str(c or "").strip() for c in (columns or [])]
    fill_cols = [i for i, label in enumerate(labels)
                 if any(k in label for k in _REPORT_FILL_LABELS)]
    axis_cols = {i for i, label in enumerate(labels)
                 if any(k in label for k in _REPORT_AXIS_LABELS)}
    code_col = next((i for i, label in enumerate(labels)
                     if "构件编号" in label), None)
    if not fill_cols:
        return [list(row) for row in (rows or [])]
    out = []
    last = {}
    last_code = ""
    for row in rows or []:
        item = list(row)
        raw_code = ""
        if code_col is not None and code_col < len(item):
            raw_code = str(item[code_col] or "").strip()
        code_changed = bool(raw_code and last_code and raw_code != last_code)
        if raw_code:
            last_code = raw_code
        for ci in fill_cols:
            if ci >= len(item):
                continue
            raw = str(item[ci] or "").strip()
            if raw:
                last[ci] = raw
            elif code_changed and ci in axis_cols:
                last[ci] = ""
            item[ci] = last.get(ci, "")
        out.append(item)
    return out


def _chunk_report_rows(rows, columns, max_rows=15):
    """按构件边界切分报告表，避免把同一构件的两个芯样拆到两张表。"""
    labels = [str(c or "").strip() for c in (columns or [])]
    code_col = next((i for i, label in enumerate(labels)
                     if "构件编号" in label), None)
    if code_col is None:
        return [rows[i:i + max_rows] for i in range(0, len(rows), max_rows)]
    groups = []
    current = []
    current_code = ""
    for row in rows or []:
        code = ""
        if code_col < len(row):
            code = str(row[code_col] or "").strip()
        if current and code and current_code and code != current_code:
            groups.append(current)
            current = []
        if code:
            current_code = code
        current.append(row)
    if current:
        groups.append(current)
    chunks = []
    chunk = []
    for group in groups:
        if len(chunk) + len(group) > max_rows and chunk:
            chunks.append(chunk)
            chunk = []
        if len(group) > max_rows:
            for i in range(0, len(group), max_rows):
                chunks.append(group[i:i + max_rows])
            continue
        chunk.extend(group)
    if chunk:
        chunks.append(chunk)
    return chunks or [list(rows or [])]


def build_overview(base_doc, info, template_set=None):
    """一、工程概况：在标题后追加项目概况。"""
    src = Document(str(chapter_path("overview", template_set)))
    append_body_paragraph(src, overview_text(info))
    _strip_empty_paragraphs(src)
    _append_chapter(base_doc, src)


def build_basis(base_doc, checked_order=None, template_set=None,
                standards=None):
    """二、主要检测依据：按检测项目生成规范清单（可被措辞层覆盖）。"""
    src = Document(str(chapter_path("basis", template_set)))
    texts = list(standards) if standards else standards_for(checked_order or [])
    for index, text in enumerate(texts, 1):
        append_body_paragraph(src, "%d、%s；" % (index, text), indent=False)
    _strip_empty_paragraphs(src)
    _append_chapter(base_doc, src)


def build_equipment(base_doc, checked_order=None, template_set=None,
                    equipment=None):
    """三、主要检测设备：优先使用设备库，没有设备库时按检测项目兜底。"""
    src = Document(str(chapter_path("equipment", template_set)))
    if src.tables:
        table = src.tables[0]
        rows = equipment if equipment else equipment_for(checked_order or [])
        keys = ("设备名称", "设备分类编号", "最近检定日期", "检定证书编号")
        en_keys = ("name", "category_code", "last_check_date", "cert_no")
        for i, item in enumerate(rows or []):
            if i >= len(table.rows) - 1:
                table.add_row()
            row = table.rows[i + 1]
            for j, key in enumerate(keys):
                if j >= len(row.cells):
                    continue
                value = item.get(key)
                if value is None:
                    value = item.get(en_keys[j], "")
                _set_cell_text(row.cells[j], value or "", size=12)
        fit_result_table_width(table, 15.5)
    _strip_empty_paragraphs(src)
    _append_chapter(base_doc, src)


def build_content(base_doc, checked_order, template_set=None):
    """四、检测内容：拼装概述并在末尾追加检测项目清单。"""
    src = Document(str(chapter_path("content", template_set)))
    _strip_empty_paragraphs(src)
    _append_chapter(base_doc, src)
    _append_content_list(base_doc, checked_order)


# ═══════════════════════════════════════════════════════════
#  五、检测结果 / 六、检测结论
# ═══════════════════════════════════════════════════════════
def _fill_component_number_column(table, header_rows):
    """模板有“构件编号”列但数据未提供时，按行自动编号。"""
    if not table.rows:
        return
    header_text = ""
    for ri in range(min(max(1, header_rows), len(table.rows))):
        header_text += "".join(cell.text or "" for cell in table.rows[ri].cells)
    compact = "".join(str(header_text).split())
    if "构件编号" not in compact:
        return
    # 找到表头中“构件编号”所在列
    target = None
    for ri in range(min(max(1, header_rows), len(table.rows))):
        for ci, cell in enumerate(table.rows[ri].cells):
            if "构件编号" in "".join(str(cell.text or "").split()):
                target = ci
                break
        if target is not None:
            break
    if target is None:
        return
    seq = 0
    for ri in range(header_rows, len(table.rows)):
        cell = table.rows[ri].cells[target]
        if str(cell.text or "").strip():
            continue
        seq += 1
        _set_cell_text(cell, str(seq), size=12)


def conclusion_group(base):
    """结论编号分组：1 强度 / 2 钢筋 / 3 尺寸厚度 / 4 保护层 / 5 锚固 / 6 其它。"""
    if any(k in base for k in ("钻芯", "回弹", "抗压")):
        return 1
    if any(k in base for k in ("钢筋间距", "钢筋根数", "受力钢筋")):
        return 2
    if "保护层" in base:
        return 4
    if any(k in base for k in ("厚度", "结构尺寸")):
        return 3
    if "植筋" in base or "锚固" in base:
        return 5
    return 6


def next_conclusion_no(base, counters, category_no=None):
    """取下一个结论编号（如 1.1、）。

    category_no 由报告内容分组顺序传入；不传时沿用旧的按项目类型分组。
    """
    group = int(category_no) if category_no else conclusion_group(base)
    counters[group] = counters.get(group, 0) + 1
    return "%d.%d、" % (group, counters[group])


def build_results(base_doc, info, checked_order, sheet_data, columns_map,
                  on_log=None, template_set=None, assessment_results=None):
    """五、检测结果：概述（检测日期区间）+ 逐检测项目结果一览表。

    :param info: 抬头信息（取 test_date；留空则保留日期占位符手填）
    :param checked_order: 参与报告的工作表键顺序（建表顺序）
    :param sheet_data: {sheet_key: [[值, ...], ...]}
    :param columns_map: {sheet_key: [列头, ...]}
    :return: {"tables": n, "skipped": [...], "warnings": [...],
              "sentences": [...]}（结论句按表顺序收集）
    """
    log = on_log or (lambda msg: None)
    ts = template_set or ReportTemplateSet.builtin()
    try:
        from report_generator.utils.report_items import (
            category_key, category_number_map)
    except ImportError:  # 以 report_generator/ 为工作目录导入时
        from utils.report_items import category_key, category_number_map
    category_numbers = category_number_map(checked_order)
    skipped, warnings, sentences = [], [], []
    table_count = 0
    item_number = 0
    conclusion_counters = {}



    # 五、检测结果概述
    intro_src = Document(str(chapter_path("result_intro", ts)))
    _fill_test_date(intro_src, info.get("test_date") or info.get("report_date"))
    _strip_empty_paragraphs(intro_src)
    _append_chapter(base_doc, intro_src)

    # 逐检测项目一览表（无数据/无模板的自动跳过）
    for sheet_key in checked_order:
        rows = _clean_rows(sheet_data.get(sheet_key, []))
        if not rows:
            skipped.append(f"{sheet_key}（无有效数据，未生成一览表）")
            warnings.append(f"{sheet_key}: 没有有效数据，未生成结果表")
            continue
        gui_cols = columns_map.get(sheet_key, [])
        base, comp = resolve_sheet_key(sheet_key)
        entry = ts.result_entry(base, comp)
        if entry is None:
            skipped.append(f"{sheet_key}（无对应报告模板，未生成一览表）")
            continue
        rel_name = entry.get("file") or ""
        header_rows = int(entry.get("header_rows", 1) or 1)
        aliases = entry.get("aliases") or {}
        tpl_path = ts.result_path(entry)
        if not tpl_path.exists():
            skipped.append(f"{sheet_key}（模板文件缺失：{rel_name}）")
            continue
        table_no = "5.%d" % (table_count + 1)
        item_number += 1
        log(f"填充 {sheet_key} → 表{table_no}")
        # 参考报告：每个检测项目先写方法/抽样/依据/表号
        for index, text in enumerate(item_narrative(
                base, comp, rows, "", table_no, item_number, checked_order)):
            append_body_paragraph(base_doc, text, bold=(index == 0))
        # 长表拆成约 15 行/张，保证每张表完整落在一页内；每张独立重复
        # 表名/表头并重新智能合并，避免合并单元格跨页后续页只剩空白。
        report_rows = _normalize_report_rows(rows, gui_cols)
        chunks = _chunk_report_rows(report_rows, gui_cols, 15)
        try:
            from report_generator.utils.report_items import display_name
        except ImportError:  # 以 report_generator/ 为工作目录导入时
            from utils.report_items import display_name
        for chunk_index, chunk in enumerate(chunks):
            src = Document(str(tpl_path))
            # 标题 {{table_no}} 替换，并统一为报告标准项目名
            caption_done = False
            for para in src.paragraphs:
                _replace_in_paragraph(para, {"{{table_no}}": table_no})
                text = para.text.strip()
                if caption_done or not text.startswith("表") or table_no not in text:
                    continue
                name = display_name(sheet_key)
                # “...检测”后接“结果”，其余接“检测结果”，避免“（梁）结果”这种断句
                title = name + ("结果" if name.endswith("检测") else "检测结果")
                if "一览表" in text:
                    title += "一览表"
                new_text = "表%s  %s" % (table_no, title)
                if para.runs:
                    para.runs[0].text = new_text
                    for run in para.runs[1:]:
                        run._element.getparent().remove(run._element)
                else:
                    para.add_run(new_text)
                caption_done = True
            if not src.tables:
                skipped.append("%s（模板中未找到表格）" % sheet_key)
                break
            _fill_result_table(src.tables[0], chunk, gui_cols, header_rows,
                               aliases, warnings, sheet_key)
            _fill_component_number_column(src.tables[0], header_rows)
            fit_result_table_width(src.tables[0], 15.5)
            _strip_empty_paragraphs(src)
            _append_chapter(base_doc, src, page_break=True)
        table_count += 1
        assessment = (assessment_results or {}).get(sheet_key)
        if assessment and assessment.get("ok") and assessment.get("conclusion"):
            conclusion = format_conclusion(assessment, table_no)
        else:
            conclusion = build_conclusion_sentence(base, comp, rows, gui_cols)
        append_body_paragraph(base_doc, "检测结果表明：")
        append_body_paragraph(base_doc, conclusion)
        sentences.append(next_conclusion_no(
            base, conclusion_counters,
            category_numbers.get(category_key(sheet_key))) + conclusion)

    return {"tables": table_count, "skipped": skipped,
            "warnings": warnings, "sentences": sentences}


def build_conclusion(base_doc, sentences, template_set=None):
    """六、检测结论：拼装结论章节并把结论句插入真标题之后。

    结论句定位跳过首页目录条目（"六、检测结论………"长文本），
    只匹配正文短标题。返回实际插入的结论句数量。
    """
    src = Document(str(chapter_path("conclusion", template_set)))
    _strip_empty_paragraphs(src)
    _append_chapter(base_doc, src)
    return _append_conclusions(base_doc, sentences)
