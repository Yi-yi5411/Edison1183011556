# -*- coding: utf-8 -*-
"""manifest 采集参数的校验与规范化。

供 /api/project/check_item 使用：只在 manifest 声明了 collect.params 的项目上生效，
没有 manifest 的项目仍走原有的 requires_setup_dialog 逻辑。
"""
from structural_items.registry import describe_item

TYPE_NAMES = {"string": "文本", "int": "整数", "float": "数值", "bool": "布尔",
              "enum": "枚举"}


def _label(spec):
    return spec.get("label") or spec.get("key") or ""


def _to_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on", "是"):
        return True
    if text in ("0", "false", "no", "n", "off", "否", ""):
        return False
    raise ValueError("不是布尔值")


def param_specs(item_name):
    """取某个检测项目在 manifest 中声明的采集参数定义（空列表表示无参数）。"""
    contract = describe_item(item_name)
    if not contract:
        return []
    return list((contract.get("collect") or {}).get("params") or [])


def requires_params(item_name):
    return bool(param_specs(item_name))


def normalize_params(item_name, raw):
    """按 manifest 校验并规范化参数。

    :return: {params, errors, warnings, fields, field_specs}
        - params：补全默认值、转好类型的最终参数（未知键原样保留）
        - errors：中文错误列表，非空时调用方应拒绝
    """
    specs = param_specs(item_name)
    raw = dict(raw or {})
    values = {}
    errors = []
    warnings = []
    known = set()

    for spec in specs:
        key = spec.get("key") or ""
        if not key:
            continue
        known.add(key)
        missing = (key not in raw or raw[key] is None
                   or str(raw[key]).strip() == "")
        if missing:
            default = spec.get("default")
            if default not in (None, ""):
                values[key] = default
            elif spec.get("required"):
                errors.append("%s（%s）不能为空" % (_label(spec), key))
            continue

        ptype = spec.get("type") or "string"
        value = raw[key]
        try:
            if ptype == "int":
                value = int(float(value))
            elif ptype == "float":
                value = float(value)
            elif ptype == "bool":
                value = _to_bool(value)
            else:
                value = str(value).strip()
        except (TypeError, ValueError):
            errors.append("%s（%s）必须是%s，当前 %r"
                          % (_label(spec), key,
                             TYPE_NAMES.get(ptype, ptype), raw[key]))
            continue

        options = spec.get("options") or []
        if ptype == "enum" and options:
            matched = [o for o in options if str(o) == str(value)]
            if not matched:
                errors.append("%s（%s）只能是 %s，当前 %r"
                              % (_label(spec), key,
                                 " / ".join(str(o) for o in options), raw[key]))
                continue
            value = matched[0]

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.get("min") is not None and value < spec["min"]:
                errors.append("%s（%s）不能小于 %s，当前 %s"
                              % (_label(spec), key, spec["min"], value))
                continue
            if spec.get("max") is not None and value > spec["max"]:
                errors.append("%s（%s）不能大于 %s，当前 %s"
                              % (_label(spec), key, spec["max"], value))
                continue
        values[key] = value

    for key, value in raw.items():
        if key in known:
            continue
        values[key] = value
        warnings.append("未知参数：%s（原样传给构建逻辑）" % key)

    return {
        "params": values,
        "errors": errors,
        "warnings": warnings,
        "fields": [spec.get("key") for spec in specs],
        "field_specs": specs,
    }
