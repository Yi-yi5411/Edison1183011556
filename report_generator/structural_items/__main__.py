# -*- coding: utf-8 -*-
"""manifest CLI：校验、生成技能、查看契约。

    python -m structural_items validate
    python -m structural_items export-skills [--out DIR]
    python -m structural_items describe "钻芯法检测"
"""
import json
import os
import sys

from structural_items import (describe_item, discover, export_skills,
                              validate_manifest)


def cmd_validate(args):
    entries = discover(force=True)
    if not entries:
        print("未发现 manifest（modules/*/plugin.json）")
        return 0
    failed = 0
    for entry in entries:
        name = os.path.basename(os.path.dirname(entry["path"]))
        if entry["errors"]:
            failed += 1
            print("FAIL %s" % name)
            for error in entry["errors"]:
                print("  - %s" % error)
        else:
            print("PASS %s（%d 个检测项目）"
                  % (name, len(entry["data"].get("items") or [])))
        for warning in entry["warnings"]:
            print("  ! %s" % warning)
    print("=" * 50)
    print("%d/%d 通过" % (len(entries) - failed, len(entries)))
    return 1 if failed else 0


def cmd_export(args):
    out_dir = ""
    only = set()
    index = 0
    while index < len(args):
        if args[index] == "--out" and index + 1 < len(args):
            out_dir = args[index + 1]
            index += 2
            continue
        if args[index] == "--only" and index + 1 < len(args):
            only.update(x.strip() for x in args[index + 1].split(",") if x.strip())
            index += 2
            continue
        index += 1
    paths = export_skills(out_dir or None, only)
    for path in paths:
        print(path)
    print("共生成 %d 个技能" % len(paths))
    return 0


def cmd_describe(args):
    if not args:
        print("用法：describe <检测项目名或工作表键>")
        return 2
    data = describe_item(" ".join(args))
    if data is None:
        print("未找到检测项目：%s" % " ".join(args))
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "validate":
        return cmd_validate(rest)
    if command == "export-skills":
        return cmd_export(rest)
    if command == "describe":
        return cmd_describe(rest)
    print("未知命令：%s" % command)
    return 2


if __name__ == "__main__":
    sys.exit(main())
