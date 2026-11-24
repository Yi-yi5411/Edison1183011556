# -*- coding: utf-8 -*-
"""报告模板匹配打分：解释「为什么推荐这个模板」。

只看模板集合的公开结构（chapters / result_entry / missing_chapters），
不读写项目状态，便于单测；实际生效顺序（项目选择 → 默认 → 内置）仍由路由决定。

用法：
    entries = [{"base": "钻芯法检测", "component": "梁", "key": "钻芯法检测（梁）"}]
    scored = rank_templates(candidates, entries, selected_id, default_id)
    recommend_switch, reason = explain_switch(scored, effective_id)
"""
try:  # utils 包内与扁平导入两种环境
    from .report_templates import REQUIRED_CHAPTERS
except ImportError:  # pragma: no cover
    from utils.report_templates import REQUIRED_CHAPTERS

# 结果表覆盖比章节完整度更能说明「这份模板适不适合当前项目」
RESULT_WEIGHT = 0.6
CHAPTER_WEIGHT = 0.4
# 分数差距小于该阈值时不建议切换，避免无意义打扰
SWITCH_EPSILON = 0.05


def _coverage(template_set, entries):
    """返回 (章节覆盖率, 覆盖的检测项, 未覆盖的检测项, 缺失章节列表)。"""
    total = len(REQUIRED_CHAPTERS)
    missing_chapters = list(template_set.missing_chapters())
    present = max(0, total - len(missing_chapters))
    chapter_cov = (present / float(total)) if total else 1.0

    covered, missing_items = [], []
    for entry in entries or []:
        base = entry.get("base") or ""
        component = entry.get("component") or None
        key = entry.get("key") or base
        found = None
        try:
            found = template_set.result_entry(base, component)
        except Exception:  # noqa: BLE001
            found = None
        if found:
            covered.append(key)
        else:
            missing_items.append(key)
    result_cov = (len(covered) / float(len(entries))) if entries else 1.0
    return chapter_cov, covered, missing_items, missing_chapters


def score_template(template_set, entries, template_id="", name="", builtin=False,
                   selected=False, is_default=False):
    """给一份模板打分并给出可读依据。"""
    chapter_cov, covered, missing_items, missing_chapters = _coverage(
        template_set, entries)
    result_cov = (len(covered) / float(len(entries))) if entries else 1.0
    score = round(RESULT_WEIGHT * result_cov + CHAPTER_WEIGHT * chapter_cov, 4)

    reasons = []
    if entries:
        reasons.append("结果表覆盖 %d/%d 个检测项（%s）"
                       % (len(covered), len(entries),
                          "、".join(covered[:3]) if covered else "无"))
    else:
        reasons.append("当前项目还没有已录入的检测项，按章节完整度打分")
    if missing_chapters:
        reasons.append("缺 %d 个章节：%s"
                       % (len(missing_chapters),
                          "；".join(missing_chapters[:2])))
    else:
        reasons.append("章节齐全")
    if selected:
        reasons.append("当前项目已选")
    if is_default:
        reasons.append("模板库默认")
    if builtin:
        reasons.append("内置模板")

    return {
        "id": str(template_id or template_set.template_id or ""),
        "name": str(name or template_set.name or ""),
        "score": score,
        "chapter_coverage": round(chapter_cov, 4),
        "result_coverage": round(
            (len(covered) / float(len(entries))) if entries else 1.0, 4),
        "covered_items": covered,
        "missing_items": missing_items,
        "missing_chapters": missing_chapters,
        "builtin": bool(builtin),
        "selected": bool(selected),
        "is_selected": bool(selected),
        "is_default": bool(is_default),
        "reasons": reasons,
    }


def rank_templates(candidates, entries, selected_id="", default_id=""):
    """给候选模板逐份打分并排序（分数 → 结果表覆盖 → 非内置 → 名称）。"""
    scored = []
    for cand in candidates or []:
        template_set = cand.get("template_set")
        if template_set is None:
            continue
        template_id = str(cand.get("id") or "")
        scored.append(score_template(
            template_set, entries,
            template_id=template_id,
            name=cand.get("name") or "",
            builtin=bool(cand.get("builtin")),
            selected=bool(template_id) and template_id == str(selected_id or ""),
            is_default=bool(template_id) and template_id == str(default_id or "")))
    scored.sort(key=lambda row: (-row["score"], -row["result_coverage"],
                                 row["builtin"], row["name"]))
    return scored


def explain_switch(scored, effective_id):
    """比较最佳匹配与实际生效模板，返回 (是否建议切换, 中文理由)。"""
    if not scored:
        return False, "模板库为空，无法比较"
    best = scored[0]
    effective = next((row for row in scored
                      if row["id"] == str(effective_id or "")), None)
    if effective is None:
        return False, "当前模板不在模板库（使用内置或文件缺失），不做切换建议"
    if best["id"] == effective["id"]:
        return False, "当前模板已是最佳匹配"
    gap = round(best["score"] - effective["score"], 4)
    if gap < SWITCH_EPSILON:
        return False, "最佳匹配与当前模板差距很小（%.3f），可不切换" % gap
    reason = "建议改用「%s」：%s" % (best["name"], "；".join(best["reasons"][:2]))
    if effective["missing_items"]:
        reason += "；当前模板缺结果表：%s" % "、".join(effective["missing_items"][:3])
    return True, reason
