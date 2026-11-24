---
name: structural-concrete-rebound-core
description: "混凝土抗压强度（回弹-钻芯修正法）检测：回弹测区与芯样实测值成对修正（修正量法/修正系数法）、批量评定与结论。"
whenToUse: "用户要做回弹钻芯修正法数据录入、修正计算、批量评定或核对修正后结论时。"
---

# 混凝土抗压强度检测 · 回弹钻芯修正法检测

回弹测区值与芯样实测强度成对修正，输出修正后的强度与结论。

## 构件维度

- 梁 / 柱 / 板 / 剪力墙 / 基础
- 工作表键：回弹钻芯修正法检测（梁）、回弹钻芯修正法检测（柱）、回弹钻芯修正法检测（板）、回弹钻芯修正法检测（剪力墙）、回弹钻芯修正法检测（基础）

## 采集参数

- building（楼栋，string，必填，默认 1#）
- batches（批次数量，int，必填，默认 1）
- components_per_batch（每批次构件数，int，必填，默认 5）
- zones_per_component（每构件测区数，int，必填，默认 3）
- grade（设计强度等级，string，必填，默认 C40）
- diameter（芯样直径(mm)，float，必填，默认 100，可选 70 / 100）

- 表格形态：components_x_zones
- 校验：core_pair_required、batch_min_count_6

## 表格列

- 1. 楼栋（string）
- 2. 批次（string）
- 3. 构件编号（string）
- 4. 构件位置及名称（string）
- 5. 构件轴线编号（string）
- 6. 钻芯测区（string）
- 7. 芯样直径(mm)（float）
- 8. 截面积(mm²)（float）
- 9. 测试荷载(kN)（float）
- 10. 测试强度(MPa)（float）
- 11. 设计强度等级（string）
- 12. 芯样强度均值(MPa)（float）
- 13. 楼层（string）

## 导入

- excel：表头别名 构件轴线编号←轴线编号/轴线、芯样直径(mm)←芯样直径/直径、设计强度等级←设计等级/强度等级、芯样强度均值(MPa)←芯样强度均值/芯样均值
- word_table
- scan：扫描目标 rebound_core

## 评定

- 规则：rebound_core（family=rebound_core），结论由评定引擎生成
- 输入形态：raw_components
- 必须调用 run_assessment，不要自行计算或编造结论

## 报告与原始记录

- 报告章节：四、检测内容
- 原始记录模板：rebound_core
- 报告设备：混凝土回弹仪、钻芯机

## 工具

- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
