---
name: structural-concrete-core-drilling
description: "混凝土抗压强度（钻芯法）检测：建表参数、芯样强度换算、构件推定值、批次批评定与结论、生成报告与原始记录。"
whenToUse: "用户要建钻芯法采集表、录入芯样直径/荷载、做批评定或核对钻芯结论时。"
---

# 混凝土抗压强度检测 · 钻芯法检测

按构件钻取芯样，测试荷载换算强度，构件取最小值作推定值，批次按批推定值评定。

## 构件维度

- 梁 / 柱 / 板 / 剪力墙 / 基础
- 工作表键：钻芯法检测（梁）、钻芯法检测（柱）、钻芯法检测（板）、钻芯法检测（剪力墙）、钻芯法检测（基础）

## 采集参数

- building（楼栋，string，必填，默认 1#）
- components（构件数，int，必填，默认 10）
- samples_per_component（每构件芯样数，int，必填，默认 2）
- sample_start（芯样起始编号，int，默认 1）
- grade（设计强度等级，string，必填，默认 C30）：如 C30；缺设计值则按无图纸结论
- diameter（芯样直径(mm)，float，必填，默认 100，可选 70 / 100）：影响 k1/k2 系数查表
- method（评定方式，enum，默认 batch，可选 batch / single）：batch=批评定，single=单构件
- batches（批次数量，int，默认 1）

- 表格形态：components_x_samples
- 校验：core_diameter_positive、batch_min_count_15

## 表格列

- 1. 楼栋（string）
- 2. 批次（string）
- 3. 构件编号（string）
- 4. 构件位置及名称（string）
- 5. 轴线编号（string）
- 6. 序号（string）
- 7. 芯样直径(mm)（float）
- 8. 截面积(mm²)（float）
- 9. 测试荷载(kN)（float）
- 10. 测试强度(MPa)（float）
- 11. 推定值(MPa)（float）
- 12. 批评定值(MPa)（float）
- 13. 设计等级（string）
- 14. 楼层（string）

## 导入

- excel：表头别名 构件位置及名称←构件名称/构件位置、轴线编号←轴线/构件轴号、测试荷载(kN)←测试荷载/荷载、测试强度(MPa)←测试强度/强度、设计等级←设计强度等级/强度等级
- word_table
- scan：扫描目标 core_drilling

## 评定

- 规则：core（family=core），结论由评定引擎生成
- 输入形态：sheet_rows
- 必须调用 run_assessment，不要自行计算或编造结论

## 报告与原始记录

- 报告章节：四、检测内容
- 原始记录模板：core
- 报告设备：钻芯机、游标卡尺

## 工具

- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
