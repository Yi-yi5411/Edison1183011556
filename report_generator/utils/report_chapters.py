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
        _fill_test_date,
        _replace_in_paragraph,
        _replace_placeholders,
        _trim_base_tail,
    )
    from report_generator.utils.report_template_map import (
        CHAPTER_TEMPLATES,
        SHEET_TEMPLATE_MAP,
        TEMPLATE_DIR,
        build_conclusion as build_conclusion_sentence,
        resolve_sheet_key,
    )
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
        _fill_test_date,
        _replace_in_paragraph,
        _replace_placeholders,
        _trim_base_tail,
    )
    from utils.report_template_map import (
        CHAPTER_TEMPLATES,
        SHEET_TEMPLATE_MAP,
        TEMPLATE_DIR,
        build_conclusion as build_conclusion_sentence,
        resolve_sheet_key,
    )


def chapter_path(name):
    """按章节名取模板文件路径（见 CHAPTER_TEMPLATES）。"""
    return TEMPLATE_DIR / CHAPTER_TEMPLATES[name]


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


def build_home(base_doc, info):
    """首页（含目录页模板）：回填信息表后拼装。

    注意先填充再拼装：_append_chapter 是 deepcopy，拼装后再改
    源文档不生效。{page} 页数留待 COM 后处理回填。
    """
    home_src = Document(str(chapter_path("cover_home")))
    if home_src.tables:
        _fill_home_info_table(home_src.tables[0], info)
    _append_chapter(base_doc, home_src)


def build_toc(base_doc, checked_order, info):
    """目录 + 全文残留占位符统一收口（须在全部章节拼装后调用）。

    覆盖：目录条目中的检测项目清单（{{main_testing_items}}）、
    工程名称（{{project_name}}，含概况/首页等章节）、报告日期
    （{{report_date}}，含结论章节）。各章节函数只填自己的数据，
    残留 {{占位符}} 一律在此处一次替换，编排链路干净可查。
    """
    _replace_placeholders(base_doc, {
        "project_name": _s(info.get("project_name")),
        "main_testing_items": "、".join(checked_order),
        "report_date": _s(info.get("report_date")),
    })


# ═══════════════════════════════════════════════════════════
#  一 ~ 四 章
# ═══════════════════════════════════════════════════════════
def build_overview(base_doc, info):
    """一、工程概况（工程名称占位符由 build_toc 统一收口替换）。"""
    _append_chapter(base_doc, chapter_path("overview"))


def build_basis(base_doc):
    """二、主要检测依据（模板正文自带，无动态填充）。"""
    _append_chapter(base_doc, chapter_path("basis"))


def build_equipment(base_doc):
    """三、主要检测设备（模板正文自带，无动态填充）。"""
    _append_chapter(base_doc, chapter_path("equipment"))


def build_content(base_doc, checked_order):
    """四、检测内容：拼装概述并在末尾追加检测项目清单。"""
    _append_chapter(base_doc, chapter_path("content"))
    _append_content_list(base_doc, checked_order)


# ═══════════════════════════════════════════════════════════
#  五、检测结果 / 六、检测结论
# ═══════════════════════════════════════════════════════════
def build_results(base_doc, info, checked_order, sheet_data, columns_map,
                  on_log=None):
    """五、检测结果：概述（检测日期区间）+ 逐检测项目结果一览表。

    :param info: 抬头信息（取 test_date；留空则保留日期占位符手填）
    :param checked_order: 参与报告的工作表键顺序（建表顺序）
    :param sheet_data: {sheet_key: [[值, ...], ...]}
    :param columns_map: {sheet_key: [列头, ...]}
    :return: {"tables": n, "skipped": [...], "warnings": [...],
              "sentences": [...]}（结论句按表顺序收集）
    """
    log = on_log or (lambda msg: None)
    skipped, warnings, sentences = [], [], []
    table_count = 0

    # 五、检测结果概述
    intro_src = Document(str(chapter_path("result_intro")))
    _fill_test_date(intro_src, info.get("test_date"))
    _append_chapter(base_doc, intro_src)

    # 逐检测项目一览表（无数据/无模板的自动跳过）
    for sheet_key in checked_order:
        rows = _clean_rows(sheet_data.get(sheet_key, []))
        if not rows:
            continue
        gui_cols = columns_map.get(sheet_key, [])
        base, comp = resolve_sheet_key(sheet_key)
        entry = SHEET_TEMPLATE_MAP.get((base, comp))
        if entry is None:
            skipped.append(f"{sheet_key}（无对应报告模板，未生成一览表）")
            continue
        rel_name, header_rows, aliases = entry
        tpl_path = TEMPLATE_DIR / rel_name
        if not tpl_path.exists():
            skipped.append(f"{sheet_key}（模板文件缺失：{rel_name}）")
            continue
        table_no = "5.%d" % (table_count + 1)
        log(f"填充 {sheet_key} → 表{table_no}")
        src = Document(str(tpl_path))
        # 标题 {{table_no}} 替换（标题在表格之前或之后均可能）
        for para in src.paragraphs:
            _replace_in_paragraph(para, {"{{table_no}}": table_no})
        if not src.tables:
            skipped.append(f"{sheet_key}（模板中未找到表格）")
            continue
        _fill_result_table(src.tables[0], rows, gui_cols, header_rows,
                           aliases, warnings, sheet_key)
        _append_chapter(base_doc, src, page_break=False)
        table_count += 1
        sentences.append(build_conclusion_sentence(base, comp, rows, gui_cols))

    return {"tables": table_count, "skipped": skipped,
            "warnings": warnings, "sentences": sentences}


def build_conclusion(base_doc, sentences):
    """六、检测结论：拼装结论章节并把结论句插入真标题之后。

    结论句定位跳过首页目录条目（"六、检测结论………"长文本），
    只匹配正文短标题。
    """
    _append_chapter(base_doc, chapter_path("conclusion"))
    _append_conclusions(base_doc, sentences)
