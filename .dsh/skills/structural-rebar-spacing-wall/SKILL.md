---
name: structural-rebar-spacing-wall
description: "钢筋配置 · 剪力墙构件钢筋间距检测：数据采集、按规范评定、生成报告与原始记录。"
whenToUse: "用户要采集、导入、评定或核对「剪力墙构件钢筋间距检测」数据时。"
---

# 钢筋配置 · 剪力墙构件钢筋间距检测

钢筋配置 · 剪力墙构件钢筋间距检测：录入或导入检测数据，按规范评定并生成报告与原始记录。

## 构件维度

- 无构件维度
- 工作表键：剪力墙构件钢筋间距检测

## 采集参数

- 无参数：直接录入或在采集页导入表格

- 表格形态：records

## 表格列

- 1. 楼栋（string）
- 2. 构件位置及名称（string）
- 3. 轴线编号（string）
- 4. 方向（string）
- 5. 设计值（float）
- 6. 实测值1（float）
- 7. 实测值2（float）
- 8. 实测值3（float）
- 9. 实测值4（float）
- 10. 实测值5（float）
- 11. 实测值6（float）
- 12. 实测值平均值（float）
- 13. 偏差值1（float）
- 14. 偏差值2（float）
- 15. 偏差值3（float）
- 16. 偏差值4（float）
- 17. 偏差值5（float）
- 18. 偏差值6（float）
- 19. 偏差值平均值（float）
- 20. 合格点率（string）
- 21. 合格/不合格（string）
- 22. 楼层（string）

## 导入

- excel
- word_table

## 评定

- 规则：spacing_wall（family=spacing），结论由评定引擎生成
- 输入形态：sheet_rows
- 必须调用 run_assessment，不要自行计算或编造结论

## 报告与原始记录

- 报告章节：四、检测内容
- 原始记录模板：builtin_rebar_spacing
- 报告设备：一体式钢筋扫描仪

## 工具

- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
