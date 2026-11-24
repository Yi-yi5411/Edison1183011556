# -*- coding: utf-8 -*-
"""报告“检测内容”标准项目名称回归。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)

from utils.report_items import (  # noqa: E402
    canonical_name, category_of, content_groups, content_names, display_name,
)

results = []


def check(desc, ok, got=None):
    results.append((desc, ok))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


CASES = [
    ("钻芯法检测（梁）", "钻芯法检测构件混凝土抗压强度（梁）"),
    ("钻芯法检测（板）", "钻芯法检测构件混凝土抗压强度（板）"),
    ("回弹法检测（墙）", "回弹法检测构件混凝土抗压强度（墙）"),
    ("回弹钻芯修正法检测（梁）", "回弹钻芯修正法检测构件混凝土抗压强度（梁）"),
    ("混凝土板保护层厚度检测", "混凝土板构件保护层厚度检测"),
    ("混凝土梁保护层厚度检测", "混凝土梁构件保护层厚度检测"),
    ("剪力墙保护层厚度检测", "混凝土剪力墙构件保护层厚度检测"),
    ("化学植筋锚固承载力检测", "填充砌体墙锚固承载力检测"),
    ("剪力墙钢筋根数检测", "剪力墙主要受力钢筋根数检测"),
    ("楼板构件厚度检测", "混凝土板构件结构厚度检测"),
    ("剪力墙厚度检测", "混凝土剪力墙构件结构厚度检测"),
    ("混凝土梁结构尺寸检测", "混凝土梁构件结构尺寸检测"),
    ("混凝土柱结构尺寸检测", "混凝土柱构件结构尺寸检测"),
    ("梁构件底排受力钢筋根数检测", "梁构件底排受力钢筋根数检测"),
    ("柱构件主要受力钢筋根数检测", "柱构件主要受力钢筋根数检测"),
    ("现浇板钢筋间距检测", "现浇板钢筋间距检测"),
    ("剪力墙构件钢筋间距检测", "剪力墙构件钢筋间距检测"),
]

for key, expected in CASES:
    got = display_name(key)
    check("标准名称 %s" % key, got == expected, got)

check("分类：钻芯法", category_of("钻芯法检测（梁）") == "混凝土抗压强度检测",
      category_of("钻芯法检测（梁）"))
check("分类：保护层", category_of("混凝土板保护层厚度检测") == "混凝土构件保护层厚度检测",
      category_of("混凝土板保护层厚度检测"))
check("分类：锚固", category_of("化学植筋锚固承载力检测") == "填充砌体墙锚固承载力检测",
      category_of("化学植筋锚固承载力检测"))

names = content_names(["钻芯法检测（梁）", "混凝土板保护层厚度检测",
                       "化学植筋锚固承载力检测", "钻芯法检测（板）"])
check("内容名称顺序", names == [
    "钻芯法检测构件混凝土抗压强度（梁）",
    "混凝土板构件保护层厚度检测",
    "填充砌体墙锚固承载力检测",
    "钻芯法检测构件混凝土抗压强度（板）",
], names)
check("内容名称去重", content_names(["钻芯法检测（梁）", "钻芯法检测（梁）"]) ==
      ["钻芯法检测构件混凝土抗压强度（梁）"], content_names(["钻芯法检测（梁）", "钻芯法检测（梁）"]))

groups = content_groups(["钻芯法检测（梁）", "混凝土板保护层厚度检测",
                         "化学植筋锚固承载力检测", "钻芯法检测（板）"])
check("内容分组：抗压强度", groups[0]["category"] == "混凝土抗压强度检测"
      and groups[0]["items"] == [
          "钻芯法检测构件混凝土抗压强度（梁）",
          "钻芯法检测构件混凝土抗压强度（板）",
      ], groups[0])
check("内容分组：保护层", groups[1]["category"] == "混凝土构件保护层厚度检测"
      and groups[1]["items"] == ["混凝土板构件保护层厚度检测"], groups[1])
check("内容分组：锚固叶级", groups[2]["category"] == "填充砌体墙锚固承载力检测"
      and groups[2]["items"] == [], groups[2])

failed = [desc for desc, ok in results if not ok]
print("=" * 50)
print("%d/%d PASS" % (len(results) - len(failed), len(results)))
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
