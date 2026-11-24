---
name: structural-concrete-rebound
description: "混凝土抗压强度（回弹法）检测：录入测区换算值、单构件推定值、批次统计与结论、生成报告与原始记录。"
whenToUse: "用户要采集或导入回弹法数据、判定强度是否满足设计要求、核对推定值与批量批结论时。"
---

# 混凝土抗压强度检测 · 回弹法检测(主要来源为仪器数据，可选用)

回弹仪测区换算值汇总到构件级，输出单构件推定值或批量批评定值。

## 构件维度

- 梁 / 墙 / 柱 / 基础
- 工作表键：回弹法检测(主要来源为仪器数据，可选用)（梁）、回弹法检测(主要来源为仪器数据，可选用)（墙）、回弹法检测(主要来源为仪器数据，可选用)（柱）、回弹法检测(主要来源为仪器数据，可选用)（基础）

## 采集参数

- 无参数：直接录入或在采集页导入表格

- 表格形态：records
- 校验：zone_count_lt10_use_min、strength_lt10_fail

## 表格列

- 1. 构件名称（string）
- 2. 构件轴号（string）
- 3. 设计强度等级（string）
- 4. 平均强度值(MPa)（float）
- 5. 标准差(MPa)（float）
- 6. 最小测区强度值(MPa)（float）
- 7. 强度推定值(MPa)（float）
- 8. 龄期(d)（float）
- 9. 楼层（string）

## 导入

- excel：表头别名 构件名称←构件位置及名称/构件、构件轴号←轴线编号/轴线、平均强度值(MPa)←平均强度值/平均值、标准差(MPa)←标准差、最小测区强度值(MPa)←最小测区强度值/最小值、强度推定值(MPa)←强度推定值/推定值
- word_table
- scan：扫描目标 rebound_zones

## 评定

- 规则：rebound（family=rebound），结论由评定引擎生成
- 输入形态：raw_components
- 必须调用 run_assessment，不要自行计算或编造结论

## 报告与原始记录

- 报告章节：四、检测内容
- 原始记录模板：rebound
- 报告设备：混凝土回弹仪

## 工具

- recognize_file {filepath}：先认文件属于哪个检测项目、列匹配情况
- import_file {filepath, sheet_key}：按表头导入并自动重算
- create_data_sheet {sheet_key, params, rows}：直接建表填数（参数见上）
- run_assessment {sheet_key}：评定必须走引擎，不要自行计算
- generate_original_record / generate_report：出原始记录与报告
