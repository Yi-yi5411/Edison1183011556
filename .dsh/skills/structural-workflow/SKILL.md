---
name: structural-workflow
description: "工程检测harness 全流程：识别意图 → 加载/录入数据 → 评定 → 生成报告 → 预览 → 修改报告。"
whenToUse: "用户说“录入数据/导入原始记录/开始采集/生成报告/预览报告/修改报告/改一下结论”等，需要把一句话意图落到本项目工具链时。"
---

# 结构检测对话工作流

把用户的一句话意图映射到本项目的 MCP 工具；**数值、结论、规范条文一律来自工具返回**，不臆造。

## 意图 → 动作

| 用户意图 | 先做 | 再调用 |
|---|---|---|
| 加载采集 / 看看有哪些表 | `current_project`、`list_detection_items` | 汇报已勾选项目、工作表键、行数、评定状态 |
| 录入 / 传入数据（粘贴表格） | `get_item_contract`（取列与参数） | `create_data_sheet`（自动建表+填数+重算+勾选） |
| 上传 Excel / Word / CSV | `recognize_file`（可选） | `import_file`（按表头匹配并重算） |
| 扫描件 / 图片 | `scan_submit` → 轮询 `scan_job` | `scan_fill` 回填 |
| 执行评定 | 确认数据已录入 | `run_assessment`，逐项给结论与依据 |
| 生成报告 | 确认已评定 | `generate_report`；返回值含 `filepath`、`preview_url` |
| 预览报告 | 已有 `filepath` | 给用户打开 `http://127.0.0.1:8765{preview_url}`（浏览器内嵌 PDF） |
| 修改报告 | `generate_report` 的 `filepath` | `load_report_document` → `replace_report_text` / `save_report_document`（默认另存新文件） |
| 查规范 | 问题里的检测项目 | `query_norms` / `search_norms`，只引用返回条文 |

## 规则

1. **先读后写**：录入前用 `get_item_contract` 确认列名与参数；报告改写前先 `report_facts` 取事实包。
2. **报告数值不手改**：结论、强度、统计值来自评定结果；需要改措辞时只改 overview / basis / conclusions。
3. **预览链接**：`generate_report` 返回的 `preview_url` 是相对路径，前面拼 `http://127.0.0.1:8765` 即可在浏览器打开。
4. **修改留痕**：`save_report_document` 默认另存新文件，把新路径告诉用户，不覆盖原报告，除非用户明确要求。
5. **不伪造**：缺数据就说缺哪个工作表/哪些列；规范库没有的条文不要编造。

## 典型对话

- “把这份回弹法记录导进来” → `recognize_file` → `import_file` → 汇报行数与重算结果。
- “生成报告并给我预览” → `generate_report` → 拼 `preview_url` → 给出可点击链接。
- “结论里加上‘局部剔凿复检’” → `report_facts` → `replace_report_text` → `save_report_document`（另存）。
