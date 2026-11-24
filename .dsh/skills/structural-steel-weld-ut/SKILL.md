---
name: structural-steel-weld-ut
description: "钢结构焊缝质量检测 · 焊缝超声波探伤检测：数据采集、按规范评定、生成报告与原始记录。"
whenToUse: "用户要采集、导入、评定或核对「焊缝超声波探伤检测」数据时。"
---

# 钢结构焊缝质量检测 · 焊缝超声波探伤检测

钢结构焊缝质量检测 · 焊缝超声波探伤检测：录入或导入检测数据，按规范评定并生成报告与原始记录。

## 构件维度

- 无构件维度
- 工作表键：焊缝超声波探伤检测

## 采集参数

- 无参数：直接录入或在采集页导入表格

- 表格形态：records

## 表格列

- 1. 楼栋（string）
- 2. 焊缝编号（string）
- 3. 焊缝位置及名称（string）
- 4. 焊缝形式（string）
- 5. 母材厚度(mm)（float）
- 6. 探伤等级（string）
- 7. 缺陷指示长度(mm)（string）
- 8. 等级评定（string）
- 9. 结论（string）
- 10. 备注（string）

## 导入

- excel
- word_table

## 评定

- 该项目暂未配置评定规则
- 必须调用 run_assessment，不要自行计算或编造结论

## 报告与原始记录

- 报告章节：四、检测内容
- 原始记录模板：builtin_generic
- 报告设备：检测设备

## 工具

- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
