---
name: structural-beam-section
description: "混凝土构件 · 混凝土梁结构尺寸检测：数据采集、按规范评定、生成报告与原始记录。"
whenToUse: "用户要采集、导入、评定或核对「混凝土梁结构尺寸检测」数据时。"
---

# 混凝土构件 · 混凝土梁结构尺寸检测

混凝土构件 · 混凝土梁结构尺寸检测：录入或导入检测数据，按规范评定并生成报告与原始记录。

## 构件维度

- 无构件维度
- 工作表键：混凝土梁结构尺寸检测

## 采集参数

- 无参数：直接录入或在采集页导入表格

- 表格形态：records

## 表格列

- 1. 楼栋（string）
- 2. 构件位置及名称（string）
- 3. 轴线编号（string）
- 4. 设计宽度B(mm)（string）
- 5. 设计高度H(mm)（string）
- 6. 实测宽度B1（string）
- 7. 实测宽度B2（string）
- 8. 实测宽度B3（string）
- 9. 实测高度H1（string）
- 10. 实测高度H2（float）
- 11. 实测高度H3（float）
- 12. 宽度平均值(mm)（float）
- 13. 高度平均值(mm)（float）
- 14. 宽度偏差(mm)（float）
- 15. 高度偏差(mm)（float）
- 16. 楼层（string）

## 导入

- excel
- word_table

## 评定

- 规则：section_beam（family=section），结论由评定引擎生成
- 输入形态：sheet_rows
- 必须调用 run_assessment，不要自行计算或编造结论

## 报告与原始记录

- 报告章节：四、检测内容
- 原始记录模板：builtin_member_size
- 报告设备：检测设备

## 工具

- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
