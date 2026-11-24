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
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

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
    from report_generator.utils.report_docx import (
        _fill_page_count_via_com,
        adopt_template_footer,
        fill_home_conclusion,
        normalize_table_paragraphs,
        set_home_page_start,
        split_section_before_home,
    )
    from report_generator.utils.report_format import apply_report_format
    from report_generator.utils.report_templates import ReportTemplateSet
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
    from utils.report_docx import (
        _fill_page_count_via_com,
        adopt_template_footer,
        fill_home_conclusion,
        normalize_table_paragraphs,
        set_home_page_start,
        split_section_before_home,
    )
    from utils.report_format import apply_report_format
    from utils.report_templates import ReportTemplateSet


def _set_results_section_landscape(doc):
    """把“五、检测结果”所在节改为 A4 纵向（保留模板节结构）。"""
    body = doc.element.body
    started = False
    for el in body:
        if el.tag != qn("w:p"):
            continue
        text = "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()
        # 只认正文短标题，跳过目录里的“五、检测结果………”长条目
        if (text.startswith("五、检测结果") and len(text) <= 20
                and text.endswith(("：", ":"))):
            started = True
        if started and text.startswith("六、检测结论") and len(text) <= 20:
            break
        if not started:
            continue
        p_pr = el.find(qn("w:pPr"))
        sect = p_pr.find(qn("w:sectPr")) if p_pr is not None else None
        if sect is None:
            continue
        pg_sz = sect.find(qn("w:pgSz"))
        if pg_sz is None:
            pg_sz = OxmlElement("w:pgSz")
            sect.append(pg_sz)
        pg_sz.set(qn("w:w"), "11906")
        pg_sz.set(qn("w:h"), "16838")
        pg_sz.set(qn("w:orient"), "portrait")
        return True
    return False


def _remove_blank_section_break_before_results(doc):
    """删除“五、检测结果”前的空节符，改为普通分页，避免空白页。"""
    body = doc.element.body
    children = list(body)
    for index, el in enumerate(children):
        if el.tag != qn("w:p"):
            continue
        text = "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()
        if not (text.startswith("五、检测结果") and len(text) <= 20):
            continue
        prev = children[index - 1] if index > 0 else None
        if prev is None or prev.tag != qn("w:p"):
            return False
        prev_text = "".join(t.text or "" for t in prev.iter(qn("w:t"))).strip()
        p_pr = prev.find(qn("w:pPr"))
        sect = p_pr.find(qn("w:sectPr")) if p_pr is not None else None
        if prev_text or sect is None:
            return False
        body.remove(prev)
        p_pr = el.find(qn("w:pPr"))
        if p_pr is None:
            p_pr = OxmlElement("w:pPr")
            el.insert(0, p_pr)
        if p_pr.find(qn("w:pageBreakBefore")) is None:
            p_pr.insert(0, OxmlElement("w:pageBreakBefore"))
        return True
    return False


def generate_report(project_name, report_info, sheet_data, columns_map,
                    checked_order, output_path, on_log=None,
                    format_options=None, template_set=None,
                    assessment_results=None, equipment=None,
                    narrative=None):
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
    :param template_set: 可选 ReportTemplateSet；None 时使用内置模板集合
    :param narrative: 可选措辞覆盖 {"overview", "basis", "conclusions"}；
        只改文字不改数值（见 utils/report_render.py）
    :return: {"tables": n, "skipped": [...], "warnings": [...],
              "template_id": ..., "template_name": ...}
    """
    log = on_log or (lambda msg: None)
    ts = template_set or ReportTemplateSet.builtin()
    try:
        from report_generator.utils.report_narrative import standards_for
        from report_generator.utils.report_items import report_order
    except ImportError:  # 以 report_generator/ 为工作目录导入时
        from utils.report_narrative import standards_for
        from utils.report_items import report_order
    checked_order = report_order(checked_order)
    info = dict(report_info or {})
    if not str(info.get("project_name") or "").strip():
        info["project_name"] = project_name
    narrative = narrative or {}
    if narrative.get("overview"):
        info["project_overview"] = narrative["overview"]

    log("以封面为基准组装章节…")
    doc = Document(str(ts.chapter_path("cover_main")))

    # 封面 → 首页 → 一~四章（各章节独立构建，见 report_chapters.py）
    build_cover(doc, info)
    basis_texts = list(narrative.get("basis") or []) or standards_for(checked_order)
    build_home(doc, info, template_set=ts, basis=basis_texts)
    build_overview(doc, info, template_set=ts)
    build_basis(doc, checked_order, template_set=ts,
                standards=narrative.get("basis"))
    build_equipment(doc, checked_order, template_set=ts,
                    equipment=equipment)
    build_content(doc, checked_order, template_set=ts)

    # 去掉第四章末尾的分页符，避免与横向节符叠加出空白页
    body = doc.element.body
    for para in reversed([c for c in body if c.tag == qn("w:p")]):
        text = "".join(t.text or "" for t in para.iter(qn("w:t"))).strip()
        if text:
            break
        p_pr = para.find(qn("w:pPr"))
        if p_pr is not None:
            pb = p_pr.find(qn("w:pageBreakBefore"))
            if pb is not None:
                p_pr.remove(pb)
        for br in list(para.iter(qn("w:br"))):
            if br.get(qn("w:type")) == "page":
                br.getparent().remove(br)

    # 模板本身已经是 A4 纵向；直接沿用模板的节、页眉页脚和页码，
    # 不再额外插入结果页/返回页节，避免出现空白页和前后页眉页脚断裂。
    results = build_results(doc, info, checked_order, sheet_data,
                            columns_map, on_log=log, template_set=ts,
                            assessment_results=assessment_results)
    if narrative.get("conclusions"):
        # 只替换结论句文字，编号前缀由调用方保留（见 report_facts）
        results["sentences"] = list(narrative["conclusions"])

    fill_home_conclusion(doc, results["sentences"])
    # 首页单独成节并从第1页开始，后续目录/正文延续编号。
    split_section_before_home(doc, 1)
    for index in range(1, len(doc.sections)):
        adopt_template_footer(doc, index, ts.chapter_path("overview"))

    # 六、检测结论（插入结论句）→ 目录清单与残留占位符 → 统一排版
    inserted = build_conclusion(doc, results["sentences"], template_set=ts)
    if results["sentences"] and inserted < len(results["sentences"]):
        results["warnings"].append(
            "检测结论句未全部插入：模板中未找到“六、检测结论”正文标题")
    build_toc(doc, checked_order, info)
    if format_options:
        for msg in apply_report_format(doc, **format_options):
            log("排版：%s" % msg)

    normalize_table_paragraphs(doc)
    doc.save(str(output_path))
    _fill_page_count_via_com(output_path)
    log("报告生成完成。")
    return {"tables": results["tables"], "skipped": results["skipped"],
            "warnings": results["warnings"],
            "template_id": ts.template_id, "template_name": ts.name}
