---
name: structural-brick-strength
description: "砖强度检测（回弹法） · 砖强度检测：数据采集、按规范评定、生成报告与原始记录。"
whenToUse: "用户要采集、导入、评定或核对「砖强度检测」数据时。"
---

# 砖强度检测（回弹法） · 砖强度检测

砖强度检测（回弹法） · 砖强度检测：录入或导入检测数据，按规范评定并生成报告与原始记录。

## 构件维度

- 无构件维度
- 工作表键：砖强度检测

## 采集参数

- batch（批次，string，默认 1）
- components（构件数，int，必填，默认 10）
- zones_per_component（每构件测区数，int，必填，默认 10）

- 表格形态：records

## 表格列

- 1. 批次（string）
- 2. 构件编号（string）
- 3. 构件位置及类型（string）
- 4. 轴号编号（string）
- 5. 测区号（float）
- 6. 回弹值1（float）
- 7. 回弹值2（float）
- 8. 回弹值3（float）
- 9. 回弹值4（float）
- 10. 回弹值5（float）
- 11. 测区平均回弹值（float）
- 12. 强度换算值(MPa)（float）
- 13. 构件平均强度(MPa)（float）
- 14. 批次平均值(MPa)（float）
- 15. 方差(MPa²)（float）
- 16. 标准差(MPa)（float）
- 17. 变异系数（float）
- 18. 强度标准值(MPa)（float）
- 19. 评定等级（string）
- 20. 备注（string）

## 导入

- excel
- word_table

## 评定

- 规则：brick（family=brick），结论由评定引擎生成
- 输入形态：sheet_rows
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
