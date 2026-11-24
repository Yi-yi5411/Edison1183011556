# 检测项目 manifest（structural.item/1）

把原先散落在 6 个位置的「检测项目契约」收敛到一份
`modules/<plugin_id>/plugin.json`，用于工具、技能生成与校验。

> **现状（P3 已完成迁移）**：16 份 manifest 覆盖 29 个检测项目，生成 29 个技能；
> carbonation 按设计在树中隐藏，不生成 manifest。Python 插件仍是运行时权威
> （`source: "python"`），manifest 由 `tools/build_manifests.py` 从插件导出、
> 由 `test_manifests_all.py` 逐字段比对守住；`source: "manifest"` 的项目可完全由
> JSON 驱动（`structural_items.manifest_plugin`，已被 `plugin_manager` 自动发现）。

## 契约从哪来

| 原位置 | manifest 字段 |
|---|---|
| plugin.py（id/name/structure_type/tree_order/tree_entries） | `id` `name` `structure_type` `tree_order` `items[].key/components` |
| columns.py | `items[].columns / column_types`（`columns_key` 对应 `columns()` 的键） |
| calc_rules.py | `items[].calc_rules`（键为目标列序号） |
| dialogs.py（参数对话框） | `items[].collect.params` |
| assessment_specs.py | `items[].assessment.spec / family / input` |
| report_narrative.py | `items[].equipment / report.chapter` |
| prompt/NN-*.md | `items[].skill.slug / description / when_to_use` |

## 最小示例

```json
{
  "schema": "structural.item/1",
  "id": "concrete_strength",
  "name": "混凝土抗压强度检测",
  "structure_type": "混凝土结构",
  "tree_order": 10,
  "source": "python",
  "items": [{
    "key": "钻芯法检测",
    "columns_key": "钻芯法检测",
    "family": "core",
    "components": ["梁", "柱", "板", "剪力墙", "基础"],
    "columns": ["楼栋", "批次", "构件编号"],
    "column_types": ["string", "string", "string"],
    "calc_rules": {},
    "collect": {
      "params": [
        {"key": "building", "label": "楼栋", "type": "string", "required": true, "default": "1#"},
        {"key": "diameter", "label": "芯样直径(mm)", "type": "float", "default": 100, "options": [70, 100]}
      ],
      "layout": "components_x_samples",
      "entry": "setup_dialog",
      "validators": ["core_diameter_positive"],
      "importers": [
        {"kind": "excel", "header_aliases": {"测试荷载(kN)": ["测试荷载", "荷载"]}},
        {"kind": "word_table", "anchor": "钻芯法检测原始记录"},
        {"kind": "scan", "target": "core_drilling"}
      ]
    },
    "assessment": {"spec": "core", "family": "core", "input": "sheet_rows"},
    "equipment": ["微控电液伺服压力试验机", "游标卡尺"],
    "original_record": {"template": "core"},
    "report": {"chapter": "四、检测内容"},
    "skill": {
      "slug": "concrete-core-drilling",
      "description": "混凝土抗压强度（钻芯法）检测……",
      "when_to_use": "用户要建钻芯法采集表、录入芯样直径/荷载时。"
    }
  }]
}
```

字段约束（`structural_items/schema.py` 强校验）：

- `schema` 必须是 `structural.item/1`；`id` 小写字母/数字/下划线；未知顶层字段直接报错；
- `column_types` 长度必须等于 `columns`；`calc_rules` 的键必须是范围内的列序号且含 `type`；
- `collect.params[].type` ∈ string/int/float/bool/enum，enum 必须给 options；
- `skill.slug` 必须 kebab-case 且全局唯一（技能名 = `structural-` + slug）。

## 报告设备（equipment）

`items[].equipment` 是报告第三章「主要检测设备」与设备推荐（`recommend_equipment`）
的唯一来源：

- 名称必须能在 `data/equipment/equipment.db` 里匹配到仪器，匹配规则在
  `utils/equipment_store.py` 的 `_MATCH_RULES`（支持 `include` / `all` / `exclude`）；
- 没有专用仪器的项目**显式写空列表**（目前只有「木材含水率检测」），
  不再用兜底名称「检测设备」占位；
- 生成器 `tools/build_manifests.py` 从 `structural_items/equipment.py` 的
  `ITEM_EQUIPMENT` 取名称，未覆盖的项目回退 `report_narrative.equipment_for`；
- 运行期 `equipment_store._required_instruments` 优先读 manifest，读不到才回退
  插件声明与 `equipment_for`。

当前映射（与真实设备库对齐）：

| 检测项目 | 主要检测设备 |
|---|---|
| 回弹法 / 回弹钻芯修正法 | 混凝土回弹仪、微控电液伺服压力试验机 |
| 钻芯法 | 微控电液伺服压力试验机、游标卡尺 |
| 砖强度 | 砖回弹仪 |
| 砌筑砂浆强度 | 贯入式砂浆强度检测仪 |
| 化学植筋锚固 | 锚杆拉拔仪 |
| 高强度螺栓扭矩系数 | 高强螺栓扭矩系数测定仪 |
| 防腐/防火涂层厚度 | 涂层测厚仪 |
| 钢材强度（硬度法） | 金属硬度计 |
| 焊缝超声波探伤 | 超声波探伤仪 |
| 梁/柱尺寸、砌体/木尺寸 | 钢卷尺 |
| 木构件挠度 | 百分表 |
| 木构件缺陷 | 钢直尺 |
| 木材含水率 | （无专用仪器） |

## 采集参数校验（已接线）

`collect.params` 不再只是文档，已经接到后端：

- `POST /api/project/check_item` 缺参数时返回
  `{requires_setup: true, fields, field_specs, source}`，`source` 为 `manifest` 或 `plugin`；
- 带参数时调用 `structural_items.params.normalize_params`：
  - 补默认值、把 `"12"` 转成 int、`"70"` 转成 float、布尔规范化；
  - 校验必填、枚举可选值、`min`/`max`；失败返回 400「参数不正确：构件数（components）不能大于 200」；
  - 未声明的键原样透传给建表逻辑，并在 warnings 里提示；
- MCP `create_data_sheet` 缺参数时把字段说明写进错误信息
  （`building（楼栋，string，必填，默认 1#）`），模型可带着 params 重试；
- `GET /api/plugins/summary`（MCP `list_detection_items`）逐项目返回
  `param_count / param_keys / param_fields / assessment_spec / skill / original_template`。

校验逻辑只有一份实现：`report_generator/structural_items/params.py`，由
`test_manifest_params.py` 覆盖（23 项）。没有 manifest 的项目退回原有的
`requires_setup_dialog` 逻辑，不会被新规则误伤。

## 命令行

```bat
cd report_generator
python -m structural_items validate            :: 校验所有 manifest
python -m structural_items describe 钻芯法检测  :: 查看某项目的完整契约
python -m structural_items export-skills       :: 生成 .dsh/skills/<name>/SKILL.md
python -m tools.build_manifests --check        :: 比对 manifest 与 Python 插件是否一致
python -m tools.build_manifests                :: 从插件重新导出 manifest（手写的不覆盖）
```

> `build_manifests` 只跳过两类：树中隐藏的插件（carbonation）与已有手写 manifest 的
> 插件（concrete_strength，需 `--force` 才覆盖）。技能 slug 在脚本的 `SLUGS` 表里维护，
> 新增检测项目时必须在表里补一条，否则生成会直接失败。

技能生成位置：`<项目根>/.dsh/skills/<skill-name>/SKILL.md`，DSH 会按项目技能目录
（rank 100）自动发现，无需重启；技能正文含构件维度、采集参数、表格列、导入别名、
评定规则、设备与模板，以及推荐的工具调用顺序。

## 新增检测项目的两条路

1. **纯 manifest**：`modules/<id>/plugin.json` 且 `source: "manifest"`，没有 `plugin.py` 时
   由 `structural_items.manifest_plugin` 提供列/树/计算规则（`_configs/*.json` 的轻量路径
   仍然保留，用于最简单的列头项目）。
2. **manifest + Python 钩子**：需要特殊建表/对话框/评定时，继续写 `plugin.py`，
   manifest 记录契约与技能说明，二者由 `test_manifest_smoke.py` 的逐字段比对守住。

## 相关接口

- `GET /api/project/item_contract?item=` → 契约（MCP 工具 `get_item_contract`）
- `GET /api/project/suggest?text=` → 一句话识别检测项目
