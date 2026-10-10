# -*- coding: utf-8 -*-
"""《检测报告》Word 生成主入口（编排器，纯函数，无 Qt 依赖）。

章节逻辑已按"各章节独立、互不耦合"拆分：
  - report_chapters.py  封面/首页/目录/一~六章 独立构建函数
  - report_format.py    页面/页脚/字体/字号 统一排版函数
  - report_docx.py      底层 docx 操作原语（拼装、占位符、列匹配等）

本模块只负责编排调用顺序与结果汇总，对外保持
``generate_report(...)`` 接口不变（见 main_window.py 与冒烟测试）。

流程：以"封面-项目名称.docx"为基准文档，依次构建各章节
（章节间分页），逐个检测项目填充"结果一览表"模板，最后按需
统一排版、整体替换残留占位符并保存。
"""
from docx import Document

try:
    from report_generator.utils.report_chapters import (
        build_basis,
        build_conclusion,
        build_content,
        build_cover,
        build_equipment,
        build_home,
        build_overview,
        build_results,
        build_toc,
        chapter_path,
    )
    from report_generator.utils.report_docx import _fill_page_count_via_com
    from report_generator.utils.report_format import apply_report_format
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_chapters import (
        build_basis,
        build_conclusion,
        build_content,
        build_cover,
        build_equipment,
        build_home,
        build_overview,
        build_results,
        build_toc,
        chapter_path,
    )
    from utils.report_docx import _fill_page_count_via_com
    from utils.report_format import apply_report_format


def generate_report(project_name, report_info, sheet_data, columns_map,
                    checked_order, output_path, on_log=None,
                    format_options=None):
    """生成完整《检测报告》.docx。

    :param project_name: 当前项目名（工程名称缺省值）
    :param report_info: 抬头信息 dict（见 REPORT_INFO_FIELDS）
    :param sheet_data: {sheet_key: [[值, ...], ...]}
    :param columns_map: {sheet_key: [列头, ...]}
    :param checked_order: 参与报告的工作表键顺序（建表顺序）
    :param output_path: 输出 .docx 路径
    :param on_log: 可选进度回调 on_log(str)
    :param format_options: 可选统一排版参数 dict，原样透传给
        ``report_format.apply_report_format``（如
        ``{"page_number_footer": True, "fonts": True}``）；
        None 时保持模板自带排版不改动
    :return: {"tables": n, "skipped": [...], "warnings": [...]}
    """
    log = on_log or (lambda msg: None)
    info = dict(report_info or {})
    if not str(info.get("project_name") or "").strip():
        info["project_name"] = project_name

    log("以封面为基准组装章节…")
    doc = Document(str(chapter_path("cover_main")))

    # 封面 → 首页 → 一~四章（各章节独立构建，见 report_chapters.py）
    build_cover(doc, info)
    build_home(doc, info)
    build_overview(doc, info)
    build_basis(doc)
    build_equipment(doc)
    build_content(doc, checked_order)

    # 五、检测结果概述 + 逐项目一览表（收集结论句）
    results = build_results(doc, info, checked_order, sheet_data,
                            columns_map, on_log=log)

    # 六、检测结论（插入结论句）→ 目录清单与残留占位符 → 统一排版
    build_conclusion(doc, results["sentences"])
    build_toc(doc, checked_order, info)
    if format_options:
        for msg in apply_report_format(doc, **format_options):
            log("排版：%s" % msg)

    doc.save(str(output_path))
    _fill_page_count_via_com(output_path)
    log("报告生成完成。")
    return {"tables": results["tables"], "skipped": results["skipped"],
            "warnings": results["warnings"]}
