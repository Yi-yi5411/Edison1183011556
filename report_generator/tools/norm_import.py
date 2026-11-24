# -*- coding: utf-8 -*-
"""规范库导入 CLI：把真实规范文件灌进 norm_codes.db。

用法（在 report_generator 目录下执行）：
    python -m tools.norm_import --coverage
    python -m tools.norm_import --dir data/norm_qa/input --mode rebuild
    python -m tools.norm_import "JGJT 23-2011 回弹法检测混凝土抗压强度技术规程.md"
    python -m tools.norm_import --dir 某个目录 --dry-run

文件名约定：`<代号> <名称>.md`，例如
`JGJT 23-2011 回弹法检测混凝土抗压强度技术规程.md`
→ 代号 JGJ/T 23-2011，名称 回弹法检测混凝土抗压强度技术规程。
拆不准时用 --code / --name 覆盖（仅单文件）。

条文格式（md）：`# 章` / `## 节` / `### 条号 标题` + 正文；
也支持 txt/docx（条号行开头约定），解析规则见 utils/norm_qa/parser.py。
"""
import argparse
import os
import sys

if __name__ == "__main__":
    _here = os.path.dirname(os.path.abspath(__file__))
    _report_gen = os.path.dirname(_here)
    for _path in (os.path.join(_report_gen, "libs"), _report_gen,
                  os.path.dirname(_report_gen)):
        if _path not in sys.path:
            sys.path.insert(0, _path)

from utils.norm_qa.catalog import coverage  # noqa: E402
from utils.norm_qa.ingest import import_files, plan_import  # noqa: E402
from utils.norm_qa.store import db_status  # noqa: E402

SUPPORTED_SUFFIX = (".md", ".markdown", ".txt", ".docx")


def _collect(args):
    paths = [os.path.abspath(p) for p in (args.files or [])]
    if args.dir:
        folder = os.path.abspath(args.dir)
        if not os.path.isdir(folder):
            print("目录不存在：%s" % folder)
            return []
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(SUPPORTED_SUFFIX):
                paths.append(os.path.join(folder, name))
    return paths


def _print_coverage():
    data = coverage()
    print("规范库：%s" % data["db_path"])
    print("共 %d 本规范 / %d 条条文" % (data["code_count"], data["total_clauses"]))
    for row in data["codes"]:
        print("  - %s %s：%d 条" % (row["code"], row["code_name"] or "", row["clauses"]))
    print("检测项目覆盖：%d/%d 有规范可依"
          % (data["covered_items"], len(data["items"])))
    missing = data["uncovered_items"]
    if missing:
        print("  暂无规范可依：%s" % "、".join(missing))


def main(argv=None):
    parser = argparse.ArgumentParser(description="导入规范文件到本地规范库")
    parser.add_argument("files", nargs="*", help="规范文件（md/markdown/txt/docx）")
    parser.add_argument("--dir", default="", help="目录：导入其中全部支持的文件")
    parser.add_argument("--mode", choices=("append", "rebuild"), default="append",
                        help="append=增量（默认），rebuild=清空重建")
    parser.add_argument("--code", default="", help="覆盖规范代号（仅单文件）")
    parser.add_argument("--name", default="", help="覆盖规范名称（仅单文件）")
    parser.add_argument("--dry-run", action="store_true", help="只解析不入库")
    parser.add_argument("--coverage", action="store_true", help="只看覆盖度")
    args = parser.parse_args(argv)

    if args.coverage:
        _print_coverage()
        return 0

    paths = _collect(args)
    if not paths:
        print("没有可导入的文件（用 --dir 或直接给文件名）")
        return 2

    overrides = {}
    if args.code or args.name:
        if len(paths) > 1:
            print("--code / --name 只能用于单个文件")
            return 2
        overrides[os.path.basename(paths[0])] = {
            "code": args.code or "", "code_name": args.name or ""}

    if args.dry_run:
        for entry in plan_import(paths, overrides):
            print("%s → %s %s，%d 条%s"
                  % (os.path.basename(entry["file"]), entry["code"],
                     entry["code_name"], entry["count"],
                     ("  错误：" + entry["error"]) if entry["error"] else ""))
        return 0

    before = db_status().get("total", 0)
    result = import_files(paths, mode=args.mode, code_overrides=overrides,
                          on_log=print)
    print("入库 %d 条（导入前 %d 条，现 %d 条）"
          % (result.get("imported", 0), before, result.get("total", 0)))
    _print_coverage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
