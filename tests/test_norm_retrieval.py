# -*- coding: utf-8 -*-
"""规范库检索冒烟（P4-1）：代号解析、去重、项目过滤、bm25 排序、覆盖度。

用临时库跑检索用例（示例条文只用于测试检索行为）；另外校验仓库内真实规范库
的代号是否已按新解析器重建。

运行：python test_norm_retrieval.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from utils.norm_qa.catalog import (codes_for_items, coverage,  # noqa: E402
                                   expand_keywords, match_db_codes)
from utils.norm_qa.engine import NormQueryEngine  # noqa: E402
from utils.norm_qa.parser import parse_text_to_clauses, split_file_code  # noqa: E402
from utils.norm_qa.store import (ClauseRecord, build_from_records,  # noqa: E402
                                 db_status, get_db_path)

from _harness import Results

_R = Results()
check = _R.check


FIXTURES = [
    ("JGJ/T 23-2011", "回弹法检测混凝土抗压强度技术规程（测试）", "4.1.1",
     "回弹值测量", "回弹值测量时，回弹仪的轴线应始终垂直于混凝土检测面。"),
    ("JGJ/T 23-2011", "回弹法检测混凝土抗压强度技术规程（测试）", "4.1.2",
     "测区数量", "每一结构或构件测区数不应少于10个。"),
    ("JGJ/T 23-2011", "回弹法检测混凝土抗压强度技术规程（测试）", "5.1.2",
     "强度推定值", "结构或构件的混凝土强度推定值，应按测区强度换算值中的最小值确定。"),
    ("JGJ/T 384-2016", "钻芯法检测混凝土强度技术规程（测试）", "3.1.1",
     "芯样直径", "钻取的混凝土芯样直径不应小于70mm。"),
    ("JGJ/T 384-2016", "钻芯法检测混凝土强度技术规程（测试）", "4.2.1",
     "高径比", "芯样试件的高径比宜为1.00，且不应小于0.95。"),
]


def _build_fixture(tmp):
    db_path = Path(tmp) / "fixture_norms.db"
    records = [ClauseRecord(code=code, code_name=name, chapter=chapter,
                            title=title, body=body, source_file="fixture.md")
               for code, name, chapter, title, body in FIXTURES]
    build_from_records(db_path, records)
    return db_path


def test_parser():
    cases = {
        "JGJT 23-2011 回弹法检测混凝土抗压强度技术规程（示例）.md":
            ("JGJ/T 23-2011", "回弹法检测混凝土抗压强度技术规程（示例）"),
        "GB 50204-2015 混凝土结构工程施工质量验收规范.md":
            ("GB 50204-2015", "混凝土结构工程施工质量验收规范"),
        "GB50204-2015混凝土结构工程施工质量验收规范.docx":
            ("GB 50204-2015", "混凝土结构工程施工质量验收规范"),
        "JGJ/T 384-2016 钻芯法检测混凝土强度技术规程.txt":
            ("JGJ/T 384-2016", "钻芯法检测混凝土强度技术规程"),
    }
    for filename, expected in cases.items():
        got = split_file_code(filename)
        check("代号解析：%s" % filename.split(" ")[0], got == expected, got)
    fallback = split_file_code("没有编号的规范.md")
    check("无编号文件退回整名", fallback == ("没有编号的规范", ""), fallback)

    text = (
        "# 4 回弹检测\n\n## 4.1 一般规定\n\n"
        "### 4.1.1 回弹值测量\n回弹仪应垂直于检测面。\n\n"
        "<!-- tags: 4.1.1, 4.1.2 -->\n\n"
        "### 4.1.2 测区数量\n测区数不应少于10个。\n")
    records = parse_text_to_clauses(text, "JGJ/T 23-2011", "测试", "a.md", "md")
    chapters = [r.chapter for r in records]
    check("tags 注释不会造出重复条号", len(chapters) == len(set(chapters)),
          chapters)
    check("同号保留真实标题",
          [r.title for r in records if r.chapter == "4.1.2"] == ["测区数量"],
          [r.title for r in records if r.chapter == "4.1.2"])


def test_catalog():
    rebound = codes_for_items(["回弹法检测（墙）"])
    check("回弹法映射到 JGJ/T 23", "JGJ/T 23-2011" in rebound, rebound)
    core = codes_for_items(["钻芯法检测（梁）"])
    check("钻芯法映射到 JGJ/T 384", "JGJ/T 384-2016" in core, core)
    rebound_core = codes_for_items(["回弹钻芯修正法检测（梁）"])
    check("回弹钻芯修正法同时映射两本规程",
          "JGJ/T 23-2011" in rebound_core
          and "JGJ/T 384-2016" in rebound_core, rebound_core)

    expanded = expand_keywords(["回弹"])
    check("查询词扩展含规范用词",
          "回弹法" in expanded and "测区" in expanded, expanded[:6])
    check("无映射项目不报错", codes_for_items(["不存在项目"]) != [], None)


def test_engine(tmp):
    db_path = _build_fixture(tmp)
    engine = NormQueryEngine(db_path)

    exact = engine.query("5.1.2 说的是什么")
    check("条号精确命中", exact["type"] == "exact"
          and exact["clauses"][0]["chapter"] == "5.1.2",
          [c["chapter"] for c in exact["clauses"]])
    section = engine.query("4.1 有哪些要求")
    check("节号返回子条", {c["chapter"] for c in section["clauses"]}
          == {"4.1.1", "4.1.2"},
          [c["chapter"] for c in section["clauses"]])

    filtered = engine.query("回弹仪 测区", detection_items=["回弹法检测"])
    codes = {c["code"] for c in filtered["clauses"]}
    check("项目过滤只返回依据规范",
          filtered["filter_applied"] and codes == {"JGJ/T 23-2011"}, codes)
    check("命中带匹配词与名次",
          bool(filtered["clauses"][0].get("matched_terms"))
          and "rank" in filtered["clauses"][0],
          filtered["clauses"][0].get("matched_terms"))

    ranking = engine.query("芯样 高径比")
    check("多词命中排第一", ranking["clauses"][0]["chapter"] == "4.2.1",
          [c["chapter"] for c in ranking["clauses"]])

    # 回弹法项目的依据规范里没有钻芯法规程；问芯样问题应放开范围并标记
    fallback = engine.query("芯样 高径比", detection_items=["回弹法检测"])
    check("过滤内无命中会放开范围",
          fallback["filtered_out"] is True
          and any(c["code"] == "JGJ/T 384-2016" for c in fallback["clauses"]),
          [c["chapter"] for c in fallback["clauses"]])
    check("放开后仍标记原过滤", fallback["filter_applied"] is True,
          fallback["filter_applied"])

    empty = engine.query("")
    check("空查询返回 empty", empty["type"] == "empty", empty["type"])

    matched = match_db_codes(["JGJ/T 23-2011", "GB 50204-2015"], db_path)
    check("只返回库里存在的代号", matched == ["JGJ/T 23-2011"], matched)
    loose = match_db_codes(["JGJ/T 23"], db_path)
    check("代号匹配忽略年份", loose == ["JGJ/T 23-2011"], loose)

    cov = coverage(db_path, items=["回弹法检测", "钻芯法检测", "砖强度检测"])
    check("覆盖度统计有依项目", cov["covered_items"] == 2, cov["covered_items"])
    check("覆盖度标出缺口",
          cov["uncovered_items"] == ["砖强度检测"], cov["uncovered_items"])
    check("覆盖度按项目算条数",
          [row["clause_count"] for row in cov["items"]
           if row["item"] == "钻芯法检测"] == [2],
          [row["clause_count"] for row in cov["items"]])
    check("覆盖度统计条数", cov["total_clauses"] == len(FIXTURES),
          cov["total_clauses"])


def test_real_db():
    path = get_db_path()
    check("仓库规范库存在", os.path.isfile(path), str(path))
    status = db_status()
    check("规范库已按新解析器重建（2 本规范）",
          len(status.get("codes") or []) == 2, status.get("codes"))
    check("条文数 11 条（去掉重复与错拆）", status.get("total") == 11,
          status.get("total"))
    cov = coverage()
    check("真实库覆盖 3 个项目",
          cov["covered_items"] >= 3, cov["covered_items"])
    check("真实库代号正确",
          {c["code"] for c in cov["codes"]}
          == {"JGJ/T 23-2011", "JGJ/T 384-2016"},
          [c["code"] for c in cov["codes"]])


def test_tool_surface():
    sys.path.insert(0, os.path.join(ROOT, "webapp"))
    import mcp_server  # noqa: E402
    tool = mcp_server._TOOL_MAP.get("search_norms")
    check("search_norms 支持 detection_items",
          tool is not None
          and "detection_items" in (tool["inputSchema"]["properties"] or {}),
          tool and sorted(tool["inputSchema"]["properties"]))
    check("norm_coverage 工具存在", "norm_coverage" in mcp_server._TOOL_MAP)
    # 工具总数会随阶段增长，这里只保证规范相关工具都在
    check("工具总数 >= 98", len(mcp_server._TOOL_MAP) >= 98,
          len(mcp_server._TOOL_MAP))


def main():
    tmp = tempfile.mkdtemp(prefix="norm_retrieval_")
    try:
        test_parser()
        test_catalog()
        test_engine(tmp)
        test_real_db()
        test_tool_surface()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
