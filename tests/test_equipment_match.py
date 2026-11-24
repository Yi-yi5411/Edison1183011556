# -*- coding: utf-8 -*-
"""设备匹配冒烟（P4-3）：匹配规则、manifest 设备优先级、真实设备库覆盖、推荐理由。

前三部分只依赖代码与 manifest；「设备库覆盖」「推荐明细」「端点」需要
data/equipment/equipment.db 与 fastapi，缺失时自动 SKIP。

运行：python test_equipment_match.py
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

import utils.equipment_store as es  # noqa: E402
from structural_items import iter_items  # noqa: E402
from tools.build_manifests import main as build_main  # noqa: E402

RESULTS = []
DB_PATH = os.path.join(ROOT, "data", "equipment", "equipment.db")


def check(desc, ok, got=None):
    RESULTS.append((desc, bool(ok)))
    print(("PASS" if ok else "FAIL"), desc, "->", repr(got))


def skip(desc, why=""):
    print("SKIP", desc, "->", why)


def _device_names():
    if not os.path.isfile(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        return [row[0] for row in conn.execute("SELECT name FROM equipment")
                if row[0]]
    finally:
        conn.close()


def test_match_rules():
    cases = [
        ("混凝土回弹仪", "混凝土回弹仪", True),
        ("混凝土回弹仪", "一体式数显回弹仪", True),
        ("混凝土回弹仪", "数显砖回弹仪", False),
        ("混凝土回弹仪", "混凝土回弹仪率定钢砧", False),
        ("砖回弹仪", "数显砖回弹仪", True),
        ("砖回弹仪", "测砖回弹仪", True),
        ("砖回弹仪", "混凝土回弹仪", False),
        ("贯入式砂浆强度检测仪", "贯入式砂浆强度检测仪", True),
        ("贯入式砂浆强度检测仪", "混凝土贯入阻力仪", False),
        ("贯入式砂浆强度检测仪", "标准贯入试验仪贯入器", False),
        ("锚杆拉拔仪", "微型锚杆拉拔仪", True),
        ("锚杆拉拔仪", "便携式拉拔仪", True),
        ("锚杆拉拔仪", "微机控制电液伺服静载锚固试验机", False),
        ("高强螺栓扭矩系数测定仪", "高强螺栓扭矩系数测定仪", True),
        ("高强螺栓扭矩系数测定仪", "高强螺栓扭矩检测仪", True),
        ("高强螺栓扭矩系数测定仪", "数显标准扭矩板子", False),
        ("涂层测厚仪", "高精度涂层测厚仪", True),
        ("涂层测厚仪", "多功能覆层涂镀层测厚仪", True),
        ("涂层测厚仪", "一体式楼板测厚仪", False),
        ("金属硬度计", "洛氏硬度计", True),
        ("金属硬度计", "数显硬度计", True),
        ("金属硬度计", "便携式涂膜铅笔划痕硬度计", False),
        ("超声波探伤仪", "数字式超声波探伤仪", True),
        ("超声波探伤仪", "数字式超声波探伤", True),
        ("超声波探伤仪", "基桩多跨孔超声波自动循测仪", False),
        ("钢卷尺", "钢卷尺", True),
        ("钢卷尺", "皮卷尺", True),
        ("钢直尺", "钢直尺", True),
        ("百分表", "数显百分表", True),
        ("游标卡尺", "数显游标卡尺", True),
        ("游标卡尺", "砖用卡尺", False),
        ("微控电液伺服压力试验机", "微控电液伺服压力试验机", True),
        ("微控电液伺服压力试验机", "微机控制电液伺服压力试验机", True),
        ("微控电液伺服压力试验机", "井盖压力试验机", False),
        ("锚杆拉拔仪", "数显锚杆拉拔仪", True),
        ("锚杆拉拔仪", "锚杆拉力计", True),
    ]
    bad = [(required, name, expect, es._instrument_matches(required, name))
           for required, name, expect in cases
           if es._instrument_matches(required, name) != expect]
    check("匹配规则 %d 例全对" % len(cases), not bad, bad[:3])


def test_required_from_manifest():
    check("砖强度用砖回弹仪",
          es._required_instruments(["砖强度检测"]) == ["砖回弹仪"],
          es._required_instruments(["砖强度检测"]))
    check("砂浆用贯入式检测仪",
          es._required_instruments(["砌筑砂浆强度检测"])
          == ["贯入式砂浆强度检测仪"],
          es._required_instruments(["砌筑砂浆强度检测"]))
    check("无专用仪器时返回空列表",
          es._required_instruments(["木材含水率检测"]) == [],
          es._required_instruments(["木材含水率检测"]))
    check("混凝土回弹法沿用回弹仪",
          es._required_instruments(["回弹法检测(主要来源为仪器数据，可选用)（墙）"])
          == ["混凝土回弹仪"],
          es._required_instruments(["回弹法检测(主要来源为仪器数据，可选用)（墙）"]))
    check("未覆盖项目回退到既有映射",
          es._required_instruments(["不存在的检测项目"]) == ["检测设备"],
          es._required_instruments(["不存在的检测项目"]))
    merged = es._required_instruments(["砖强度检测", "混凝土梁保护层厚度检测"])
    check("多项目去重合并",
          merged == ["砖回弹仪", "一体式钢筋扫描仪", "一体式楼板测厚仪"],
          merged)


def test_manifest_sync():
    items = list(iter_items())
    empty = [item["key"] for _entry, item in items
             if not (item.get("equipment") or [])]
    check("只有木材含水率没有专用仪器",
          empty == ["木材含水率检测"], empty)
    check("manifest 与生成器一致（--check 无差异）",
          build_main(["--check"]) == 0, None)


def test_library_coverage():
    devices = _device_names()
    if not devices:
        skip("设备库覆盖", "缺少 data/equipment/equipment.db")
        return
    items = list(iter_items())
    missing = {}
    covered_items = 0
    for _entry, item in items:
        names = es._required_instruments([item["key"]])
        if not names:
            covered_items += 1
            continue
        gaps = [name for name in names
                if not any(es._instrument_matches(name, device)
                           for device in devices)]
        if gaps:
            missing[item["key"]] = gaps
        else:
            covered_items += 1
    check("多数检测项目能在真实设备库匹配到仪器",
          covered_items >= 26, [covered_items, len(items)])
    print("      未匹配项目：", missing or "无")
    check("关键仪器均已覆盖",
          not any(name in sum(missing.values(), [])
                  for name in ("砖回弹仪", "贯入式砂浆强度检测仪", "锚杆拉拔仪",
                               "高强螺栓扭矩系数测定仪", "涂层测厚仪", "金属硬度计",
                               "超声波探伤仪", "钢卷尺", "百分表", "钢直尺")),
          missing)


def test_detail_and_endpoint():
    devices = _device_names()
    if not devices:
        skip("推荐明细", "缺少设备库")
        return
    detail = es.preview_equipment_detail(["砖强度检测", "木材含水率检测"])
    brick = next((row for row in detail if row["item"] == "砖强度检测"), {})
    check("明细给出需要的仪器", brick.get("required") == ["砖回弹仪"],
          brick.get("required"))
    check("明细给出候选与理由",
          bool(brick.get("candidates"))
          and str(brick["candidates"][0].get("reason", "")).startswith("推荐"),
          (brick.get("candidates") or [{}])[0].get("reason"))
    check("明细标记当天用量",
          isinstance((brick.get("candidates") or [{}])[0].get("usage"), int),
          (brick.get("candidates") or [{}])[0].get("usage"))
    no_device = next((row for row in detail
                      if row["item"] == "木材含水率检测"), {})
    check("无专用仪器的项目不报缺设备",
          no_device.get("required") == [] and no_device.get("covered") is True,
          [no_device.get("required"), no_device.get("covered")])

    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("推荐端点", "当前解释器没有 fastapi")
        return
    from routers.equipment import equipment_recommend
    from deps import get_state

    state = get_state()
    keys = ["砖强度检测", "木材含水率检测"]
    saved_rows = {key: state.sheet_data.get(key) for key in keys}
    saved_checked = list(state.checked_items or [])
    try:
        for key in keys:
            state.sheet_data[key] = [["测试"]]
            if key not in state.checked_items:
                state.checked_items.append(key)
        data = equipment_recommend(limit=5)
        body = data.get("data") or {}
        items = {row["item"]: row for row in (body.get("items") or [])}
        check("端点返回逐项目明细", set(keys) <= set(items), sorted(items))
        brick = items.get("砖强度检测") or {}
        candidates = brick.get("candidates") or []
        check("端点明细含候选与理由",
              bool(candidates)
              and str(candidates[0].get("reason", "")).startswith("推荐"),
              candidates[0].get("reason") if candidates else None)
        check("端点返回覆盖计数",
              int(body.get("covered_items") or 0) >= 2,
              body.get("covered_items"))
    finally:
        for key in keys:
            if saved_rows.get(key) is None:
                state.sheet_data.pop(key, None)
            else:
                state.sheet_data[key] = saved_rows[key]
        state.checked_items = saved_checked


def main():
    test_match_rules()
    test_required_from_manifest()
    test_manifest_sync()
    test_library_coverage()
    test_detail_and_endpoint()
    fails = [d for d, ok in RESULTS if not ok]
    print("=" * 50)
    print("%d/%d PASS" % (len(RESULTS) - len(fails), len(RESULTS)))
    if fails:
        print("FAILED:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
