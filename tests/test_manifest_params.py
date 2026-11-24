# -*- coding: utf-8 -*-
"""manifest 采集参数校验冒烟（P3 收尾）：normalize_params + check_item 接线。

运行：python test_manifest_params.py
后端路由部分在没有 fastapi 的解释器上自动 SKIP。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

import structural_items.params as params_mod  # noqa: E402
from structural_items import normalize_params, param_specs, requires_params  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


skip = _R.skip


def test_specs():
    specs = param_specs("钻芯法检测（梁）")
    keys = [s.get("key") for s in specs]
    check("钻芯法 8 个参数", len(specs) == 8, keys)
    check("钻芯参数含 building/components/diameter",
          {"building", "components", "diameter"} <= set(keys), keys)
    check("回弹法无参数", param_specs("回弹法检测（梁）") == [], param_specs("回弹法检测"))
    check("回弹法 requires_params=False", not requires_params("回弹法检测"))
    check("钻芯法 requires_params=True", requires_params("钻芯法检测（板）"))


def test_normalize():
    result = normalize_params("钻芯法检测", {})
    check("空参数补默认值且无错误",
          not result["errors"]
          and result["params"].get("building") == "1#"
          and result["params"].get("components") == 10
          and result["params"].get("diameter") == 100,
          result["params"])

    result = normalize_params("钻芯法检测", {"components": "12",
                                          "diameter": "70",
                                          "method": "single"})
    check("字符串数字被转成 int/float",
          result["params"]["components"] == 12
          and result["params"]["diameter"] == 70.0
          and isinstance(result["params"]["components"], int),
          [result["params"]["components"], result["params"]["diameter"]])
    check("枚举合法值通过", result["params"]["method"] == "single",
          result["params"].get("method"))

    result = normalize_params("钻芯法检测", {"diameter": "abc"})
    check("非数字 diameter 报错",
          any("芯样直径" in e for e in result["errors"]), result["errors"])

    result = normalize_params("钻芯法检测", {"method": "xx"})
    check("非法枚举报错",
          any("batch" in e and "single" in e for e in result["errors"]),
          result["errors"])

    result = normalize_params("钻芯法检测", {"components": 999})
    check("超出上限报错",
          any("不能大于" in e for e in result["errors"]), result["errors"])

    result = normalize_params("钻芯法检测", {"components": 0})
    check("低于下限报错",
          any("不能小于" in e for e in result["errors"]), result["errors"])

    result = normalize_params("钻芯法检测", {"foo": 1})
    check("未知参数告警但保留",
          result["warnings"] and result["params"].get("foo") == 1,
          [result["warnings"], result["params"].get("foo")])

    # 必填无默认值的分支：用临时契约替换 describe_item
    original = params_mod.describe_item
    params_mod.describe_item = lambda name: {"collect": {"params": [
        {"key": "must", "label": "必填项", "type": "string", "required": True},
    ]}}
    try:
        result = normalize_params("任意项目", {})
        check("必填缺失报错",
              any("必填项" in e for e in result["errors"]), result["errors"])
        result = normalize_params("任意项目", {"must": "x"})
        check("必填提供后通过", not result["errors"], result["errors"])
    finally:
        params_mod.describe_item = original


def test_check_item():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("check_item 接线验证", "当前解释器没有 fastapi")
        return
    try:
        from routers.project import CheckItemBody, check_item
    except Exception as e:  # noqa: BLE001
        check("导入 project 路由", False, str(e)[:160])
        return

    from deps import get_state

    state = get_state()
    key = "钻芯法检测（梁）"
    created = []

    def _cleanup():
        for item in created:
            try:
                check_item(CheckItemBody(sheet_key=item, checked=False))
            except Exception:  # noqa: BLE001
                pass

    try:
        state.remove_sheet(key) if key in state.sheet_data else None

        resp = check_item(CheckItemBody(sheet_key=key))
        body = resp.get("data") or {}
        check("缺参数时返回 requires_setup", body.get("requires_setup") is True, body.keys())
        check("返回 manifest 字段定义",
              body.get("source") == "manifest"
              and len(body.get("field_specs") or []) == 8,
              [body.get("source"), len(body.get("field_specs") or [])])

        try:
            check_item(CheckItemBody(sheet_key=key, params={"diameter": "abc"}))
            check("非法参数被拒", False, "未抛错")
        except Exception as e:  # noqa: BLE001
            check("非法参数被拒", "参数不正确" in str(e), str(e)[:100])

        resp = check_item(CheckItemBody(
            sheet_key=key,
            params={"building": "2#", "components": "3",
                    "samples_per_component": "2", "grade": "C30",
                    "diameter": "100"}))
        created.append(key)
        rows = state.sheet_data.get(key) or []
        check("合法参数建表成功", len(rows) > 0, len(rows))
        check("参数已规范化落到 cd_params",
              str(state.cd_params.get(key, {}).get("building")) == "2#"
              and int(state.cd_params.get(key, {}).get("components") or 0) == 3,
              state.cd_params.get(key))
        check("勾选列表包含该项目", key in (state.checked_items or []),
              state.checked_items)

        plain_key = "回弹法检测（梁）"
        resp = check_item(CheckItemBody(sheet_key=plain_key))
        created.append(plain_key)
        check("无参数项目不走 requires_setup",
              (resp.get("data") or {}).get("requires_setup") is None,
              type(resp.get("data")))
        check("无参数项目建了空表",
              len(state.sheet_data.get(plain_key) or []) > 0,
              len(state.sheet_data.get(plain_key) or []))
    finally:
        _cleanup()


def main():
    test_specs()
    test_normalize()
    test_check_item()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
