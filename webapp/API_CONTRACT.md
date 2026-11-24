# Web 版 API 契约（webapp/backend ↔ webapp/frontend）

> 全量改造：PyQt5 桌面版功能 1:1 迁移为 Web 版，桌面版并行保留。
> 后端 FastAPI 复用 report_generator 现有 Python 业务层，不重写业务逻辑。

## 全局约定

- 后端：`webapp/backend/main.py`，uvicorn 端口 **8765**，前缀 `/api`
- CORS 允许 http://localhost:5173（vite dev）；生产托管 `frontend/dist` 静态文件
- 所有响应 `{"ok": true/false, "data": ..., "message": "中文消息"}`；错误 400/500 带中文 message
- 后端 Python 与 report_generator 同级：`sys.path` 加入 `<ROOT>/report_generator` 与 `<ROOT>/report_generator/libs`（内置 openpyxl 等）
- 数据目录沿用 report_generator 现有约定（项目文件/规范库/识别历史同桌面版，两版互通）

## 1. 检测项目（插件）

`GET /api/plugins`
→ `{ok, data: [{id, name, structure_type, requires_setup, columns: [{key, label, type, width, editable, calc}], calc_rules, source, external}]}`
复用：`core.plugin_manager.PluginManager.discover()/all_plugins()`；列定义取 plugin 的 columns 配置（含 repeat 动态列语义，如钻芯法每个芯样重复）。`source` 为 builtin/external，外部插件由 `plugins/external` 或配置目录加载。

`GET /api/plugins/summary`
→ `{items: [{structure_type, plugin_name, plugin_id, item, components, sheet_keys, column_count, param_count, param_keys, param_fields, requires_setup, assessment_spec, skill, original_template, equipment}], count, manifest}`
逐检测项目合并 manifest 摘要（见 `docs/检测项目MANIFEST.md`），给智能体「一次调用看懂全部项目」用；没有 manifest 时相应字段为空，树结构不受影响。

`GET /api/plugins/external`
→ `{roots, records: [{id,name,source,status,root,path,errors,warnings}], loaded, errors}`
外部插件目录、加载状态与错误。

`POST /api/plugins/external/reload`
→ 重新发现内置+外部插件，返回同 `GET /api/plugins/external` 的结构；无需重启后端。

`PUT /api/plugins/external/sources` `{roots: [路径]}`
→ 保存外部插件根目录（不存在时创建）、重新加载，返回状态。

`GET /api/plugins/dsh`
→ DSH Profile、bundle、能力清单与市场入口。

`GET/PUT /api/plugins/dsh/host`
→ 读取/保存 DSH Host API 连接（base_url + launch token；token 不回传）。连接后通过 DSH Host 的 Typert RPC 调用：

- `GET /api/plugins/dsh/host/indexes` / `PUT` `{urls}`：插件市场索引源
- `GET /api/plugins/dsh/host/bundles`：已安装/官方 bundle 与启用状态
- `POST /api/plugins/dsh/host/search` `{url,text,limit}`
- `POST /api/plugins/dsh/host/inspect` `{spec}`
- `POST /api/plugins/dsh/host/install` `{spec,name?,version?,confirm}`
- `POST /api/plugins/dsh/host/toggle` `{name,enabled,confirm}`
- `POST /api/plugins/dsh/host/remove` `{name,confirm,confirm_delete}`

安装/删除等写操作必须传确认字段。

## 2. 项目管理

- `GET /api/project` → `{ok, data: {project_name, checked_items, sheets: {sheet_key: {columns, base_item, component, rows, merges, params, assessment}}, report_info, template_selection, assessment, autosave: {enabled, autosaved_at, restored}}}`
- `GET /api/project/history` → 历史工程列表（自动备份、会话工程、旧版导出项目文件）
- `POST /api/project/new` `{project_name}` → 清空当前项目
- `POST /api/project/open` `{filepath}` → 加载项目文件
- `POST /api/project/save` `{filepath?}` → 保存（缺省当前路径）
- `POST /api/project/check_item` `{sheet_key, checked, params?}` → 勾选/取消检测项目；requires_setup 的项目勾选时 params 传钻芯法对话框等参数（楼栋/构件数/芯样数/起始编号/设计等级/直径）
  - 工作表已有数据但尚未勾选时，勾选会把该键补入 `checked_items`，不再提前返回“已勾选”；不会重建或清空已有数据。
- `GET /api/project/structured` → 结构化数据 `{project_name, checked_items, report_info, template_selection, sheets: {sheet_key: {base_item, component, columns, rows, records: [{列头: 值}]}}}`
- `PUT /api/project/template_selection` `{report_template_id, original_template_map}` → 保存报告/原始记录模板选择；空字符串表示使用模板库默认；非法模板返回 400
- `GET /api/project/suggest?text=` → 只读：用规则别名把一句话识别成 `{category, items, components, sheet_keys, next_page, confidence, reason, summary}`（复用 `harness.intent`，不调模型、不改项目）
- `GET /api/project/item_contract?item=` → 只读：检测项目 manifest 契约（采集参数/列/导入别名/评定/设备/原始记录模板/技能），数据来自 `report_generator/modules/<id>/plugin.json`，见 `docs/检测项目MANIFEST.md`
复用：`core.app_controller.AppController.save_project_file/load_project_file/serialize/deserialize`；`get_columns(sheet_key)` 取列；`build_sheet(item_name, params, app)` 的 app 参数传 None 评估可否复用，不可复用则在 router 内提取其纯数据逻辑（不 import PyQt5）。

## 3. 表格数据（类 Excel）

- `PUT /api/sheet/{sheet_key}/rows` `{rows: [[cell...], ...]}` → 覆盖保存该表数据并**立即重算计算列**；返回 `{sheet_key, rows, marks, merges, recalc_error}`（保存失败仍保留原始行）
- `POST /api/sheet/{sheet_key}/calc` `{rows}` → 跑 `framework.engine.CalcEngine` 返回自动计算列的新 rows 与最新 `merges`（截面积/测试强度/推定值/平均强度/标准差等）
- `POST /api/sheet/{sheet_key}/merge` `{merges: [{start_row, end_row, start_col, end_col}], append?}` → 校验列范围后保存合并；`append=true` 追加，缺省整体替换（取消合并时传剩余列表）；校验复用现有 MergeOps 逻辑纯数据部分；越界报 400
- `POST /api/sheet/{sheet_key}/smart_merge` `{columns?: number[]}` → 智能合并分组列；`columns` 为 0-based 全量列下标，给定时**只处理这些列**，并清除这些候选列上的旧自动合并；省略则兼容旧行为（全部候选列）
- `POST /api/sheet/{sheet_key}/fill_down` `{col_keys, row_from, row_to}` → 批量填充（Ctrl+D 语义）
- `GET /api/sheet/{sheet_key}/export` → 导出 Excel 下载（复用 `utils.excel_exporter.export_workbook`，StreamingResponse）
- `POST /api/sheet/{sheet_key}/import_excel`（multipart `file=*.xlsx/.xlsm/.csv/.docx`，`append=false`，可选 `sheet_name`）→ Excel/CSV/Word 表格按表头自动匹配当前列导入；多表工作簿优先同名表；默认覆盖，参数化工作表同结构回导时保留合并；导入后立即重算；返回 `{sheet_key, rows, imported, matched_columns, warnings, merges, recalc_error}`
  - 检测项目列末尾统一增加 `楼层` 列（不影响既有计算列索引；旧行数据缺该列时按空值处理）。

## 3.5 统一采集入口（P2）

一份原始记录文件进来，先认检测项目、再决定怎么落库；后端直接读本机路径，不需要上传。

- `GET /api/ingest/recognize?filepath=&sheet_name=` → 只读识别：
  - `kind`：`table`（表格）/ `knowledge`（.md/.txt）/ `scan`（.pdf/图片）
  - 表格文件返回 `table{rows,columns,sheet_name}`、`header`、`preview`、`candidates`（按命中列数排序）、`suggested_sheet_key`、`assessment_family`（`rebound`/`rebound_core`/空）。
  - candidate 字段：`item/structure_type/sheet_key/component/component_guess/matched/total_columns/score/header_index/missing_columns/requires_setup/param_specs/components/sheet_keys`；`components` 是该检测项目全部构件，`sheet_keys` 是全部候选工作表，供前端确认/校正；`requires_setup=true` 时 `param_specs` 给出必填采集参数（键、标签、类型、默认值、选项）。
  - 文件中通常没有构件维度，`component_guess` 由数据前 20 行关键词推断；推断命中时 `sheet_key` 直接带构件
  - `.doc` 先转 `.docx`（Word/WPS COM，失败再试 LibreOffice），转换产物放 `data/tmp/ingest/`，24 小时后自动清理
- `POST /api/ingest/import` `{filepath, sheet_key, sheet_name?, append?, auto_assess=true, params?}` → 复用 `utils.excel_import.import_sheet_rows` 按表头匹配，写入走 `sheet_apply.apply_rows_to_sheet`（与 `import_excel` 同一份实现：覆盖/追加、钻芯法同结构保留合并、立即重算、自动勾选）。
  - `params`：参数化检测项目（钻芯法、回弹钻芯修正法、砖强度等）的采集参数；`requires_setup` 的项目若目标工作表尚未建表，未传 `params` 返回 400「需要先设置采集参数」。
  - `auto_assess=true`（默认）在导入成功后立即评定并写回 `assessment_results/options`，失败不阻断导入；返回 `{sheet_key, imported, matched_columns, rows, merges, recalc_error, warnings, requires_setup, assessment, ready}`，`ready=assessment.ok`。
- 不支持的类型返回 400 与支持列表；无表格的 `.doc` 返回「Word 中没有可导入的表格」而不是异常栈

## 3.6 对话、长期记忆、异步任务与并行任务

- `GET /api/chat/memory` → 当前工程长期记忆：`{project, snapshot:{checked_count, filled_count, assessed_count, rows}, facts, summaries, reports, count}`；只读。
- `WS /api/chat/ws?resume=1&session=<id>` → 自研对话桥（浏览器 ↔ 本机 DSH ACP stdio）。`session` 省略时按当前工程自动恢复最近有本地 transcript 的会话；带 `session` 时订阅/恢复指定会话。切换会话只解除旧 runtime 的订阅，不取消其正在执行的回合；目标会话已有 runtime 则直接 attach，没有才新建 ACP。
  - 客户端帧：`prompt`、`resume`（`sessionId`）、`new_session`、`set_model`（`value` 为 JSON 字符串）、`cancel`、`permission`、`delete_session`。
  - 服务端帧：`ready/resumed`（含 `history{messages,tools,plan,title}`、`memoryCount`、`busy`、`queue`、`assistantId`）、`sessions`（`items:[{sessionId,title,project,updatedAt,busy,queue}]`，全局会话列表）、`queued`（`jobId,queue`）、`queue`（`queue,busy?,cancelled?`）、`prompt_start`（`jobId,queue`）、`update`（ACP 流式更新）、`cancel_notice`（`jobId,messageId,text`）、`prompt_end`（含 `stopReason`、`queue`、`memoryCount`）、`permission_request`、`session_title`、`error`（带 `jobId` 为任务失败，不带为操作错误）、`closed`。`sessions` 在任意会话开始/结束/取消时刷新，左侧运行点不依赖当前订阅的会话。
  - 新会话首轮自动注入工程长期记忆；恢复会话不重复注入。transcript 存 `data/chat_transcripts/<sessionId>.json`，长期记忆存 `data/chat_memory/*.json`。
  - 对话任务由后端常驻 `ChatSessionRuntime` 执行：WebSocket 断开不取消当前回合；同一会话严格串行，队列上限 20；不同会话是不同 runtime，可并行，各自持有一个 ACP 进程；无订阅者且无任务时空闲 120 秒关闭 ACP；后端重启后 queued/running 任务标记 `interrupted`。执行中可切到其他会话，原回合继续后台执行，完成/取消通过全局 `sessions` 帧更新运行点。
- `GET /api/chat/jobs?limit=12` → 最近对话任务，limit 1..50；runtime 存在时补 `live=true`、实时 `queue`，当前任务状态覆盖为 running。任务字段：`id/session_id/project/title/prompt/status/message/assistant/queue/pid/created_at/started_at/finished_at`；状态 `queued/running/done/failed/cancelled/interrupted`，最多保留 80 条，存 `data/chat_jobs.json`。
- `POST /api/chat/jobs/{job_id}/cancel` → 停止一个对话任务：排队项立即取消并广播 `cancel_notice`，执行项发 DSH `session/cancel`；任务不存在返回 404。
- `GET /api/tasks?limit=12` → 最近并行评定任务列表；`GET /api/tasks/{id}` 单任务。
- `POST /api/tasks/assess` `{sheet_keys?: string[], title?: string}` → 启动并行评定；空 `sheet_keys` 表示全部已勾选项。已有任务运行时返回 409。
- `POST /api/tasks/{id}/cancel` → 协作式停止：已开始的项跑完，未开始的不再执行；已完成结果仍写回。
- 任务先对工程做只读快照，多 worker 计算，全部结束后一次性写回 `assessment_results/options/inputs`；详见 `docs/会话持久化与并行任务.md`。

## 3.7 工程工作区

- 目标：/harness 右侧“工作区”只呈现当前检测工程相关的产物，不再把项目源码目录当作工作区根。实现见 webapp/backend/routers/workspace.py，前端见 webapp/frontend/src/views/ChatView.vue。
- GET /api/workspace/overview?q=&limit=60&include_missing=false
  - q：同时模糊搜索检测报告与原始记录；
  - limit：每类最多返回条数，默认 60，范围 1..200；
  - include_missing：默认 false，只返回文件仍存在的条目；true 时同时返回文件已缺失的历史记录。
  - 返回：{project:{name,checked_count,filled_count,assessed_count,total_rows,snapshot_name,snapshot_at}, query, limit, counts:{reports,originals,uploads,snapshots}, total, missing:{reports,originals}, missing_total, sections:[{key,title,items,total}], message}。
  - item 字段：id/kind/name/path/filepath/size/at/exists/preview/downloadable/meta/detail/where；kind 为 report|original|upload|snapshot，preview 为 docx|pdf|image|text|none。
  - counts 只统计文件存在的条目；missing_total 表示被默认隐藏的缺失记录数。
- GET /api/workspace/download?path=<项目内相对路径>：以附件下载；路径必须位于项目根内。
- GET /api/workspace/file?path=<项目内相对路径>：图片返回原文件，文本返回 {kind:"text",content,truncated}（上限 200KB），其它返回 {kind:"binary",size}。
- POST /api/workspace/upload {name, data}：data 为 dataURL；保存到 data/uploads/YYYYmmdd_HHMMSS_<安全文件名>，返回 {path}。
- GET /api/workspace/tree?path= 仅保留兼容旧调用；/harness 工作区已改为调用 overview，不再遍历源码目录。

## 4. 报告生成

- `POST /api/report/generate`：同步生成，兼容旧调用。
- `POST /api/report/generate/stream`：SSE 流式生成，事件 `log`（实时日志）、`result`（报告结果）、`error`、`done`；前端报告页默认使用此接口。
- `GET /api/workflow/status`：流程总览（项目/采集/评定/设备/模板/报告状态），供首页流程看板使用。


- `GET /api/report/info` → 报告信息字段当前值：基础抬头 + 工程概况（建设单位/设计单位/监理单位/结构类型/面积/层数/高度/开工竣工日期/检测目的/概况描述）
- `POST /api/report/auto_info` → 自动识别并整理报告信息，自动匹配模板，返回二~五章（主要检测依据/设备/内容/结果）及可编辑的 `overview_template`；工程概况为空时自动填入
- `GET /api/report/match_template` → 只读：模板库打分与切换建议
  - `effective{id,name,source}`：生成时实际会用的模板（项目选择 → 库默认 → 内置）
  - `best_fit{id,name,score,reasons}`：按「有数据的已勾选检测项」算出的最佳匹配
  - `recommend_switch` / `switch_reason`：差距 <0.05 不建议切换，否则给出中文理由（含当前模板缺哪些结果表）
  - `templates[]`：逐份模板的 `score`（结果表覆盖 0.6 + 章节完整 0.4）、`covered_items` / `missing_items` / `missing_chapters` / `reasons`
  - 口径与报告生成一致：只统计**有数据**的已勾选工作表，基础项目名经 `resolve_sheet_key` 归一化后再查结果表模板
  - 兼容旧字段：`recommended` / `recommended_name` / `source` / `missing_chapters` 仍返回
- `GET /api/report/preview?filepath=` → docx 转 PDF 在线内嵌预览（报告与原始记录通用）
- `GET /api/report/download?filepath=` → 下载已生成 docx
- 报告页已移除人工模板设置步骤；生成时按模板库自动匹配，原始记录按检测项目默认模板自动匹配
- `PUT /api/report/info` `{report_info: {字段}}` → 保存报告信息（随项目持久化）
- `POST /api/report/generate` `{output_path?, template_id?, narrative?, draft?}` → 同步生成《检测报告》.docx；template_id 省略时按“项目选择 → 模板库默认 → 内置”解析；**已评定的检测项优先使用评定引擎的结论表述**；返回 `{ok, data: {filepath, engine, tables, skipped, warnings, skipped_items, draft, template_id, template_name, applied_narrative?, assessed_count, record_id}}`
  - 报告纳入范围：优先 `checked_items` 中有有效数据的项；未勾选但 `sheet_data` 有有效数据的项也会自动纳入，因此“只上传数据、未勾选”也能出报告。
  - `draft=true`：草稿模式，只生成“有数据 + 有结果表模板 + 已评定通过”的就绪项，其余写入 `skipped_items[{sheet_key,reason}]`；无任何就绪项返回 400。前端报告页有“草稿：仅生成已就绪项”复选框。
- `GET /api/report/facts` → **只读事实包**（`report.facts/1`）：项目抬头、逐项列/行/参数、压缩后的评定结果、规范清单、设备、模板，以及确定性措辞底稿 `narrative{overview,basis,conclusions}`；不占设备、不写记录库
- `POST /api/report/render` `{narrative?, template_id?, output_path?}` → 按当前工程事实 + 措辞覆盖渲染（不调用模型）；`narrative` 只接受 `overview`（字符串）/ `basis`（字符串数组）/ `conclusions`（**带编号前缀**的结论句数组），其它键忽略
- 事实/措辞分离：事实 `utils.report_facts.build_facts`，渲染 `utils.report_render.render_from_facts`；**已删除** `utils/report_agent.py` 与 `use_agent`，报告生成恒为确定性渲染
复用：`utils.word_report.generate_report`（新增 `narrative` 参数）。output_path 缺省 `report_generator/exports/<时间戳>/检测报告.docx`。

## 5. 规范问答

- `GET /api/normqa/status` → `{total, codes}`（复用 `utils.norm_qa.store.db_status`）
- `POST /api/normqa/import`（multipart 文件多选, mode=append|rebuild）→ `{total, imported, files}`
- `POST /api/normqa/query` `{question, detection_items?}` → `{type: exact|search|candidates|empty, clauses, candidates, codes, filter_codes, filter_applied, filtered_out}`
  - 传 `detection_items` 时只在该项目的依据规范里检索（映射见 `utils/norm_qa/catalog.py`），检索不到自动放开范围并置 `filtered_out=true`
  - 每条命中带 `score`、`matched_terms`、`rank`（FTS5 bm25 名次）
- `GET /api/normqa/coverage` → `{db_path, total_clauses, codes, items:[{item, codes, covered_codes, clause_count, covered}], covered_items, uncovered_items}`（读 manifest 的 29 个检测项目逐项算覆盖）
- `POST /api/normqa/explain` `{question, clauses}` → `{answer}`（复用 explain_clauses，**QThread 不可用**——llm.py 是纯 urllib 已兼容）

## 6. 批量审查

- `POST /api/review/run`（multipart 文件多选 docx/pdf/txt）→ `{candidates, chunks, files, model}`（复用 run_batch_review；SSE 可选，先同步）
- `POST /api/review/export` `{candidates, project_name}` → 生成审查意见表 docx 返回下载（复用 export_review_docx）

## 7. 扫描识别

- `POST /api/scan/run`（multipart: 图片多选 + detection_item 可选）→ 同步跑 `scan_recognition` 管线（pipeline 类已与 GUI 解耦），返回识别结果+field_warnings
- `POST /api/scan/submit` `{filepath, detection_item?}` → **异步作业**：直接传本机图片/PDF 路径，秒回 `{id, status}`；OCR 在后台线程跑，作业写入 `data/scan_jobs.json`，重启后仍可查询；重启时仍在 `running` 的作业标记为 `interrupted`
- `POST /api/scan/ocr-text` `{filepath, max_chars?}` → 对单张图片/PDF 直接跑项目 PaddleOCR（GPU 优先、CPU 回退），返回 `{filepath, text, truncated, n_cells, n_rows, low_confidence, suspect_numbers}`；`max_chars` 默认 20000、范围 1000..40000；路径必须在项目根内。扫描识别失败时，前端可点“仅作为附件”，用它把文字放进输入框，纯文本模型也能读图
- `GET /api/scan/job/{job_id}` → 作业状态；`done` 时带 `result{rows, columns, field_warnings, classification, ocr_stats}`，可直接喂给 `scan_fill`；未知/过期 id 返回 404，文案提示作业不存在或已过期
- `GET /api/scan/jobs?limit=20` → 最近作业（不含识别结果）；内存与 `data/scan_jobs.json` 合计最多保留 50 个
- `POST /api/scan/fill` `{sheet_key, records}` → 回填到目标表（等价 _fill_into_sheet 纯数据逻辑；只追加、不评定）
- `GET /api/scan/targets?detection_item=` → 按识别出的检测项目返回可选采集表：`{detection_item, components, requires_setup, param_specs, columns, candidates, targets, suggested_sheet_key}`；`targets[]` 含 `{sheet_key, component, columns, exists, rows, checked}`，无构件项目只有一张表，有构件项目按构件列出；`candidates` 用于弹窗内改选检测项目
- `POST /api/scan/commit` `{job_id, sheet_key, append?, params?, auto_assess?}` → 把已完成的扫描作业写入指定采集表：按列头归一化对齐、覆盖或追加、重算、仅把该表加入 `checked_items`、默认立即评定；参数化项目未建表时用 `params` 先建结构化空表。返回 `{sheet_key, imported, rows, matched_columns, target_columns, merges, recalc_error, warnings, requires_setup, assessment, ready, checked_items}`
- 扫描相关 `filepath` 均支持相对项目根；越界或不存在返回 400/404
- `GET /api/scan/history` → 识别记录（storage.scan_memory/识别历史库）
- 模型列表：`GET /api/scan/vision_models`（复用 llm.list_ollama_vision_models）

## 7.5 登录（Web 新品）

- `POST /api/auth/login` `{login_id, password}` → 校验 `desktop/auth.db`，下发 HttpOnly Cookie `structural_session`（12 小时）
- `GET /api/auth/me` → 当前用户（未登录 401）
- `POST /api/auth/logout` → 删除 Cookie
- 前端：未登录访问任意页面跳 `/login`；登录成功回 `redirect` 或 `/harness`

## 8. 配置

- `GET /api/config` → llm/ocr/matcher/ui 等配置节（`report_agent` 段已随报告 Agent 删除）；`ocr.det_model_dir/rec_model_dir/cls_model_dir` 指向项目内 `data/models/paddleocr`，`use_gpu` 默认 false（主程序为 CPU 版 paddle）；GPU 优先走独立服务：`ocr.gpu_service_url` 默认 `http://127.0.0.1:8770`，`gpu_service_autostart` 自动拉起 `.venv-ocr-gpu`，`gpu_det_model/gpu_rec_model` 默认 `PP-OCRv5_mobile_det/rec`，服务不可用时自动回退 CPU
- `PUT /api/config` `{section, values}` → 保存（复用 scan_recognition.config.Config）

## 9. 模板库

### 9.1 报告模板库

报告模板 = 一个目录 + `manifest.json`（8 个章节 + 若干结果一览表）。

```json
{
  "schema": "report_template_v1",
  "name": "标准检测报告模板",
  "description": "内置报告模板",
  "chapters": {
    "cover_main": "封面-项目名称.docx",
    "cover_home": "封面-首页.docx",
    "overview": "一、工程概况-概况.docx",
    "basis": "二、主要检测依据-依据.docx",
    "equipment": "三、主要检测设备-设备.docx",
    "content": "四、检测内容-内容概述.docx",
    "result_intro": "五、检测结果-概述.docx",
    "conclusion": "六、检测结论-结论.docx"
  },
  "result_tables": [
    {"base": "回弹法检测", "component": "墙", "file": "五、实际检测内容模板/....docx", "header_rows": 1, "aliases": {}}
  ]
}
```

- `GET /api/templates/report` → 模板列表（含 `available`、`is_default`、章节/结果表数）
- `POST /api/templates/report/upload`（multipart `file=*.zip`）→ 导入模板包，返回 `{template, warnings}`
- `GET /api/templates/report/{id}` → 模板详情（含 manifest）
- `POST /api/templates/report/{id}/default` → 设默认
- `DELETE /api/templates/report/{id}` → 删除导入模板（内置/默认模板不可删）
- `GET /api/templates/report/{id}/export` → 导出模板包 ZIP

### 9.2 原始记录库

- `GET /api/templates/original` → `{templates, defaults}`；模板含 `engine`（native_docx/docx_import/doc_archive）、`detection_items`、`default_for`、`fillable`
- `GET /api/templates/original/defaults` → `{检测项目基础名: 模板ID}`
- `POST /api/templates/original/upload`（multipart：`file`、`name`、`code`、`detection_items`(JSON 数组字符串)、`set_default`）→ 导入 .docx/.doc
- `POST /api/templates/original/{id}/default` `{items: [检测项目基础名]}` → 设置默认适用项目
- `DELETE /api/templates/original/{id}`
- `GET /api/templates/original/{id}/download` → 下载空白/原始模板
- `GET /api/templates/original/{id}/preview` → 预览（native 定义 / docx 段落表格 / archive 提示）
- `GET /api/templates/original/{id}/reference` → 下载官方 .doc 参考模板

导入 .docx 原始记录约定：
1. 占位符：`{{project_name}}`、`{{report_no}}`、`{{test_date}}`、`{{client}}`、`{{witness}}`、`{{project_location}}`、`{{tester}}` 等，也支持 `{{工程名称}}`、`{{检测编号}}`；
2. 表头信息按标签（工程名称/委托单位/检测日期/检测编号……）写入右侧单元格；
3. 数据表按表头自动匹配检测项列并扩展数据行；
4. .doc 仅存档，不能设为默认或自动填充，请先另存为 .docx。

## 10. 原始记录生成

- `POST /api/original-record/generate` `{sheet_keys: [...], template_map: {sheet_key: template_id}}` → 逐检测项生成 .docx：
  `{files: [{sheet_key, template_id, template_name, filepath, warnings}], warnings}`
- `GET /api/original-record/history` → 最近 50 条生成历史（附文件存在性）
- `POST /api/original-record/history/clear` → 清空历史

## 11. 报告修改

- `GET /api/report/document?filepath=` → 文档块 `{filepath, filename, size, modified_at, paragraphs: [{index,text,style,heading}], tables: [{index, rows: [[{row,col,text,colspan,merged}]]}], blocks}`
- `POST /api/report/document/save` `{filepath, paragraphs?, cells?, output_path?, overwrite?}` → 默认另存新文件；overwrite 先备份 .bak.docx
- `POST /api/report/document/replace` `{filepath, find, replace, output_path?, overwrite?}` → 正文+表格查找替换
- `GET /api/report/document/download?filepath=` → 下载 .docx

路径限制：只允许项目根内 .docx；`report_template/`、`data/templates/` 受保护；只支持 .docx（.doc 请先另存）。

## 12. 检测评定

规则来源：`prompt/01~13`，机器可读定义在 `report_generator/utils/assessment_specs.py`，评定引擎在 `report_generator/utils/assessment_engine.py`。

- `GET /api/assessment/specs` → 16 条规则摘要（含 `implemented`、`needs_raw_input`、`required_fields`）
- `GET /api/assessment/{sheet_key}` → 当前工作表规则/已保存输入/选项/结果/列定义
- `PUT /api/assessment/{sheet_key}/input` `{input?, options?}` → 保存原始数据与选项（不执行）
- `POST /api/assessment/{sheet_key}/run` `{input?, options?}` → 执行评定并保存结果；返回
  `{ok, conclusion_type, conclusion, template, data, summary, details, warnings, errors, points?, components?}`
- `GET /api/assessment/{sheet_key}/result` → 最近一次评定结果
- `POST /api/assessment/run_all` `{sheet_keys?}` → 批量评定，返回 `{results, warnings}`
- `POST /api/assessment/{sheet_key}/import_excel`（multipart `file=*.xlsx/.xlsm/.csv/.docx`，可选 `sheet_name`）→ 导入回弹法/回弹钻芯修正法原始数据；返回 `{input, components, warnings}`，需再调用 run 执行评定
  - 回弹法表头：楼层/构件类型/构件编号/轴线/设计强度等级 + 测区1..n（或测区换算值）
  - 回弹钻芯：另需芯样直径、成对“芯样实测强度N + 对应测区值N”列

`options`：`{no_drawing, table_no, include_component_stats}`。
- `no_drawing=true` 强制类型三；
- `table_no` 用于“详见表xxx”，报告生成时自动替换为实际表号 5.x；
- `include_component_stats=true` 对应截面尺寸/厚度/间距提示词中的“模板2”，不默认启用。

回弹法 `input` 结构：
```json
{"components": [
  {"floor": "1F", "component_type": "墙", "component_code": "Q1",
   "axis": "1/A", "grade": "C30", "zones": [35.2, 34.8, 36.1]}
]}
```

已实现全部 13 份提示词对应的评定族：回弹法、回弹钻芯修正法、钻芯法、截面尺寸（梁/柱）、厚度（墙/板）、钢筋间距（板/墙）、受力钢筋数量（梁/柱/墙）、保护层（梁/柱/墙/板）。

回弹钻芯修正法的 `input` 需要 `components[].zones` 与 `components[].cores`（`[{actual, zone}]`），并可用 `method=修正系数法|修正量法` 指定修正方式。

## 12.5 设备库（设备管理系统）

设备数据来自设备管理系统，后端负责验证码登录、token 缓存、远程分页查询和本地库同步；
密码不返回前端，token 仅保存在后端进程内（重启后需重新登录）。

- `GET /api/equipment/status` → `{base_url, username, logged_in, expires_at, local_count}`
- `GET /api/equipment/captcha` → `{key, image}`（image 为 data:image/jpg;base64,...）
- `POST /api/equipment/login` `{username, password, captcha, check_key}` → 登录状态
- `POST /api/equipment/logout` → 清除 token
- `GET /api/equipment/remote?page_no=1&page_size=20&keyword=&status=` → `{records,total,page_no,page_size}`
  - keyword 按设备名称包含匹配（后端自动补 `*` 通配）
  - status 可为“在用/停用”
- `POST /api/equipment/sync` `{ids: [], all: false}` → `{synced, local_count}`
- `GET /api/equipment/library?keyword=&selected_only=false` → 本地设备库
- `POST /api/equipment/library/select` `{ids, selected}` → 报告选用状态
- `POST /api/equipment/library/delete` `{ids}` → 删除本地设备
- `GET /api/equipment/recommend?limit=20` → 只读：按已勾选检测项目推荐在用设备，**不占用当日使用额度**
  - `equipment[]`：扁平设备行（与报告第三章同口径：在用 + 当天 <10 次 + 已选用优先）
  - `items[]`：逐检测项目明细 `{item, required:[仪器名], candidates:[{required,name,usage,daily_limit,selected,available,reason}], missing, covered}`，`reason` 形如「推荐：在用、当日报用 0/10 次、可选用」或「不可用：…今日已达上限」
  - `covered_items`：有可用仪器的项目数；仪器名来自 manifest 的 `equipment`（见 `docs/检测项目MANIFEST.md`），没有专用仪器的项目显式返回空列表而不是兜底「检测设备」

本地库保存在 `data/equipment/equipment.db`；报告第三章“主要检测设备”按检测项目自动选择：
必须是 `status=在用`，且该仪器当天 `equipment_usage` 次数 < 10；每份生成成功的报告对每台选用仪器记 1 次。
字段映射：设备名称→`equipmentName`、设备分类编号→`equipmentId1`、最近检定日期→`codetwo`、检定证书编号→`code`。

## 13. MCP 工具桥

- 启动：`python webapp/mcp_server.py`（stdio JSON-RPC，后端需先运行）
- 环境变量：`STRUCTURAL_API_BASE`（默认 `http://127.0.0.1:8765/api`）
- 工具：健康检查/项目/检测项/工作表/评定/模板库/报告生成/原始记录/报告修改/Excel·CSV·Word 导入/规范问答/Wiki/记录库/设备，共 40 个基础工具
- 扩展工具（P1+P2，见 `webapp/mcp_tools_extra.py`）：模板库 8（读取/上传 zip/设默认/删除/原始记录模板上传与绑定）、人员库 6、Wiki 4（写入/删除/导入/上下文）、规范库 4（检索/解释/导入/覆盖度）、记录库 8（统计/详情/快照/删除/相似检索/快照表/复用）、表格结构 7（合并/智能合并/插删行/向下填充/重算/列头）、项目 8（改名/历史/项目树/检测项建议/项目契约/当前工程/工程清单/切换工程）、设备 4（状态/删除/远程同步/推荐）、配置 2、报告信息 5（自动整理/读写抬头/报告编号/模板匹配）、扫描 6（识别历史/视觉模型/回填 + `scan_submit`/`scan_job`/`scan_jobs` 异步作业）、采集入口 2（`recognize_file` 识别文件 / `import_file` 直接导入）、报告事实 2（`report_facts` / `render_report`）、工程回退 2（`list_project_backups` / `restore_project`）、审计 1（`get_audit_log`）；**合计 109 个（写 51 / 读 58，其中危险 13）**
- 导入类工具接受 `.xlsx/.xlsm/.csv/.docx`（工作表/评定/人员）或 `.md/.markdown/.txt/.docx`（Wiki/规范，支持多文件 `filepaths`），按扩展名选择 MIME；Word 取第一张表格，CSV 自动识别分隔符
- 原有补充工具：`get_workflow_status`、`get_library_status`、`search_wiki`、`get_wiki_page`、`list_wiki_pages`、`list_report_records`、`list_original_records`、`list_equipment`、`select_equipment`、`create_data_sheet`
- 资源：`assessment://specs` + `prompt/01~13` 的 13 个 skill 资源
- 写操作（新建/勾选/保存/评定/生成/修改/设备选用）必须在参数中传 `confirm=true`；未确认时返回 `isError=true` 和中文提示
- **危险操作二次确认**：删除/覆盖类 13 个工具（`delete_*`、`reuse_original_record`、`import_file`、`import_sheet_excel`、`import_assessment_excel`、`import_norms`、`restore_project`）额外要求 `confirm_delete=true`，否则返回「危险操作需要二次确认」；工具注解 `destructiveHint` 仅在危险工具为 true
- **写操作审计**：写工具每次调用（含被安全门拦下的）追加到 `data/audit/mcp_writes.jsonl`：时间、工具、危险标记、耗时、结果、错误、脱敏后的参数（密钥类字段置 `***`，长文本截断）；超过 5MB 轮转为 `.1`
- 安全门在 `_call_tool` 集中执行，不依赖各 handler 自觉；读工具不写审计
- 示例配置：`webapp/mcp_server.example.json`（通用 MCP 客户端）、`webapp/mcp_server.dsh-patch.yml`（DSH profile 片段）
- 自检：`scripts/check.ps1`（23 套件 × 3.8/3.14 + manifest + 工具面 + 目录卫生；不修改真实工程）

## 13.5 智能体入口（P0 后：DSH + MCP）

> **P0 已完成**：官方 DSH runtime sidecar、本地 `.mjs` 工具插件、
> `/api/harness/*`（会话/对话/上传/测试）、`/api/agent/*`、`structural_cli`、
> `agent_service`、`harness/` 编排层（planner/team/llm_client/task_state/session_store/
> project_binding）均已删除。智能体入口统一为 **DSH GUI + MCP**。

- 页面：`/harness` 是**对话入口**，内嵌原生 DSH Web GUI（`[dsh].gui_url`），左侧展示工程上下文与快捷指令；默认首页为 `/harness`。
- `GET /api/system/dsh` → `{url, reachable, status, auth_required}`：后端探测 DSH 是否可达、是否返回 401（需登录）。
  嵌入窗口依赖浏览器里 DSH 的 `dsh-auth-*` Cookie；请用 `http://127.0.0.1:8765` 访问，首次在新窗口打开 DSH 登录一次。
- `GET /api/system/info` → `{backend, version, agent_surface: "dsh", dsh_gui_url, mcp_server_name, architecture_doc}`
  （值来自 `config/structural.toml` 的 `[dsh]` 段）
- 工程作用域显式化：`GET /api/project/current`（名称/路径/勾选项/表数/已评定数）、
  `GET /api/project/list`（历史工程清单）、`POST /api/project/activate` `{filepath}`（切换工程）
- 人工回退：`GET /api/project/backups?limit=`（`data/projects/backups/` 的自动备份与恢复前快照）、
  `POST /api/project/restore` `{filepath}`（先把当前工程另存为 `restore_<时间戳>.json` 再加载备份，返回 `{restored, safety_backup, project_name, sheet_count}`）
- 顶栏“新建工程”走 `POST /api/project/new`（旧工程自动备份），“历史工程”走
  `GET /api/project/history` + `POST /api/project/open`；不再有会话级工程快照。
- 未命中的 `/api/*` 统一返回 **404 JSON**（此前会回退成 `index.html`，删除的端点看起来仍存在）。
- 前端构建产物 `webapp/frontend/dist` 已重建，bundle 中不再含任何 `/api/harness` 调用。

## 13.6 LLM Wiki 知识库

- 数据：`data/wiki/wiki.db`（wiki_pages / wiki_revisions / FTS5），可用 `STRUCTURAL_WIKI_DB` 覆盖。
- 内置种子：`prompt/01~13`、`操作步骤说明与菜单优化方案.md` 的操作小节、`core_drilling_logic.md`、规范示例、Harness 使用说明。
- `GET /api/wiki/status`、`GET /api/wiki/categories`、`GET /api/wiki/pages`、`GET /api/wiki/pages/{id}`
- `POST /api/wiki/pages`（新建/保存，写修订）、`DELETE /api/wiki/pages/{id}`
- `POST /api/wiki/import`（md/markdown/txt/docx，指定分类/检测项目）
- `POST /api/wiki/search` `{question, top_k?, detection_items?}` → 页面命中与 snippet
- `POST /api/wiki/context` `{question...}` → 供 Harness 注入的 Wiki + 规范引用文本
- 页面：`/wiki`（浏览/搜索/编辑/导入）。

## 13.7 记录库与数据库状态

- 数据：`data/records/records.db`（report_records / original_records），可用 `STRUCTURAL_RECORDS_DB` 覆盖。
- 首次初始化自动把旧 JSON 历史（`report_generator/report_history.json`、`data/original_record_history.json`）幂等导入，并备份到 `data/backup/records_<时间戳>/`。
- 原始记录保存生成时的数据快照（超过 1MB 时标记 truncated）。
- `GET /api/records/stats`、`GET /api/records/report`、`GET /api/records/original`（q/project/limit/offset）
- `GET /api/records/report/{id}`、`GET /api/records/original/{id}`、`GET /api/records/original/{id}/snapshot`
- `GET /api/records/similar?q=&kind=both|report|original&project=&limit=` → 历史检索：按项目名/检测项/模板/报告编号/结论多字段加权，返回 `{items:[{kind,id,score,matched_fields,conclusion_type,conclusion,...}], count}`；结论取自快照（只解析前 100 条且 ≤256KB 的快照，避免全量解压）
- `GET /api/records/original/{id}/sheets` → 该原始记录快照里可复用的表：`{sheets:[{sheet_key, columns, rows, conclusion_type, params, current_columns, compatibility:{compatible,missing_columns,extra_columns,needs_reorder}}]}`
- `POST /api/records/original/{id}/reuse` `{sheet_key?, append?}` → 把快照里的表复制到当前工程：按当前列名对齐（同名列重排、新列补空、历史独有列丢弃并告警），恢复当时的钻芯参数与评定原始输入，走 `sheet_apply.apply_rows_to_sheet` 立即重算；返回行数/重排标记/告警
- `DELETE /api/records/report/{id}`、`DELETE /api/records/original/{id}`（只删记录，不删磁盘文件）
- `GET /api/libraries/status` → 报告模板/原始记录模板/设备/人员/记录库/Wiki/规范/项目统一状态
- 人员库：`data/personnel/personnel.db`；`GET /api/personnel?q=&role=&active_only=&limit=&offset=`、`POST /api/personnel`、`PUT /api/personnel/{id}`、`DELETE /api/personnel/{id}`、`GET /api/personnel/status`
- `POST /api/personnel/import`（multipart `file=*.xlsx/.xlsm/.csv/.docx`）→ 按表头识别姓名、岗位、证书编号、电话、所属单位、备注、状态；同名且证书/电话相同则更新，返回 `{created, updated, skipped, total, warnings}`
- 页面：`/records`；旧接口 `GET /api/report/history`、`GET /api/original-record/history` 继续兼容（内部读记录库）。

## 14. 自动保存

- 任何写请求（POST/PUT/PATCH/DELETE）成功后，后端自动把当前项目原子写入
  `data/projects/autosave.json`（临时文件 + os.replace）。
- 后端启动时若该文件存在且可读，自动恢复上次项目；项目快照中的
  `autosave.restored` 标记是否为恢复项目。
- 手动保存（`POST /api/project/save`）仍然可用，不受自动保存影响。
- 前端底部状态栏显示最近自动保存时间。

## 15. 旧版智能助手

- `GET /api/agent/status` → 后端/模型/工具数状态
- `GET /api/agent/tools` → 40 个工具的 function schema
- `POST /api/agent/chat` `{messages: [{role,content}], allow_write, max_rounds?}` → `{reply, tool_calls, model, rounds, error}`
  - 工具执行复用 MCP Server 的工具表；
  - `allow_write=false` 时写工具返回 `requires_confirmation`，不会修改系统；
  - `allow_write=true` 时写工具自动注入 `confirm=true`；
  - 通过 Ollama 原生 `/api/chat` 工具调用循环执行，最多 12 轮。
- 前端 `/assistant` 已重定向到 `/harness`；新功能统一使用 Harness 会话。

## 前端约定

- 技术栈：Vite + Vue3 `<script setup>` + TypeScript + Element Plus + Pinia + Axios + **vxe-table**（数据表格用，原生支持单元格编辑/合并/撤销/Ctrl+C/V/键盘导航——类 Excel 交互核心）
- 路由页：`/harness`（默认入口）、`/project`（数据采集，含 AI 采集栏）、`/report`（AI 自动识别+生成+在线预览）、`/wiki`（知识库）、`/records`（记录库）、`/library`（资料与工具统一入口：模板/设备/人员/知识/记录 + 流程工具 + 设置）
- 顶栏主导航只保留：Harness、数据采集、报告生成、知识库、记录库、内部功能；智能问答/扫描/审查归入 `/internal`。
- 布局：顶栏（项目名/打开/保存/导出Excel/生成报告按钮）+ 左侧检测项目树（el-tree 勾选，按结构类型分组）+ 主区 el-tabs（勾选项目→vxe-table 工作表）+ 底部状态栏；非 Harness 页面右下角常驻 Harness 执行抽屉
- 主题：Element Plus dark CSS 变量切换（`html.dark` class），偏好存 localStorage
- 全部界面文案中文；请求失败 ElMessage.error 展示后端中文 message
- vite proxy：`/api` → `http://localhost:8765`

## 实施约束

- 后端禁止 import PyQt5（纯数据逻辑抽取时剥离 GUI 参数）
- 长任务（扫描识别/批量审查）本期同步阻塞 + 前端 loading；超时 300s
- 不新建 *.md 文档（本契约除外）
