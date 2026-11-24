# Web 版运行说明

## 启动

首次可双击 `安装.bat`（检查依赖、写入 `config/structural.toml`、打印 MCP 片段）；
之后双击 `启动Web版.bat` 或 `启动后端.bat`（读配置里的端口）。手动等价命令：

```bat
cd /d C:\Users\Administrator\Desktop\structural_inspection\webapp\backend
"C:\Program Files\python\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8765
```

> 端口与 API 地址统一在 `config/structural.toml` 的 `[server]` 段；环境变量
> `STRUCTURAL_PORT` / `STRUCTURAL_API_BASE` 可覆盖。

浏览器打开 <http://127.0.0.1:8765/>，使用项目账号登录（管理员默认 **admin / admin123**，也支持手机号）。

> 后端直接托管 `frontend/dist`，不需要再启动 5173 开发服务器。
> 修改前端后需在 `webapp/frontend` 执行 `pnpm build` 重新生成 dist。

## 主要页面

| 页面 | 地址 |
|------|------|
| 对话（默认首页，自研界面） | `/harness` |
| DSH 整页（排障/回退） | `/dsh` |
| 数据采集 | `/project` |
| 报告生成 | `/report` |
| 知识库（LLM Wiki） | `/wiki` |
| 记录库（报告 + 原始记录） | `/records` |
| **资料与工具**（知识/模板/设备/人员/记录 + 流程工具 + 设置） | `/library` |
| 插件管理（内置 + 外部插件） | `/plugins` |
| DSH 插件市场 / Host API | `/plugins/dsh` |
| MCP 工具说明 | `API_CONTRACT.md` 第 13 节 |

## 智能体与工作台

> 智能体架构、DSH 对应关系和扩展边界见
> [docs/HARNESS_AGENT_ARCHITECTURE.md](../docs/HARNESS_AGENT_ARCHITECTURE.md)。

1. 打开根地址进入 `/harness`：自研 Vue 对话页，布局参考 DeepSeek Harness——左侧工程/最近会话，
   中间对话与轨迹，右侧工作区按当前检测工程聚合报告/原始记录/附件/快照，不遍历项目源码；
   窄屏自动收起侧栏。`/dsh` 保留原生 DSH 整页作为排障/回退入口。
2. 对话后端是 `webapp/backend/routers/chat.py`：浏览器 WebSocket ↔ 本机 DSH ACP（stdio JSON-RPC），
   流式消息、工具轨迹、计划、权限确认、取消都由该桥转发；**DSH 以 MCP stdio 挂载
   `webapp/mcp_server.py`（109 个工具）**，评定与结论由后端确定性引擎计算。
3. 采集入口：`recognize_file` 认一份原始记录属于哪个检测项目，`import_file` 按表头直接导入并重算；
   页面上的 Excel/CSV/Word 上传走同一套 `/sheet/{key}/import_*`。对话页上传表格文件会先弹出确认框：
   识别出的检测项目/构件、目标工作表、表头与样例、参数化项目的采集参数都可校正；确认后导入并自动评定。
4. 对话页/工作区上传图片或 PDF 后走 OCR → 识别表格 → 确认检测项目：弹窗里可改选项目/构件、目标采集表和参数，
   确认后只勾选本次识别出的采集表、写入并自动评定，也可直接生成报告草稿；不确认不会写工程。“仅作为附件”可回退为 OCR 文本或纯附件。
5. 报告纳入范围不再要求先勾选：有有效数据的检测项会进入报告；数据不全时可在报告页勾选“草稿：仅生成已就绪项”，
   未就绪项连同原因一起返回（有数据但未评定、缺结果表模板等）。见
   [docs/上传导入与草稿报告.md](../docs/上传导入与草稿报告.md)。
6. 会话 transcript 与工程长期记忆落本机 JSON；刷新/重启后自动恢复当前工程最近会话，新会话首轮注入
   工程快照、最近报告与最近工作。对话回合由后端常驻 runtime 执行：刷新/断线不取消当前回合，执行中可继续
   发送排队，可切到其他会话让原回合后台继续，可停止；后端进程重启会中断未完成回合。存储位置见下方“数据保存”。
7. “自动化任务”面板可把已勾选检测项拆成并行评定任务：先快照、多 worker 计算、全部完成后一次性写回，
   任务状态可在面板观察/停止。设计见
   [docs/会话持久化与并行任务.md](../docs/会话持久化与并行任务.md)。
8. 工程按文件保存：编辑时自动保存到 `data/projects/autosave.json`；顶栏“新建工程”会先把旧工程
   备份到历史工程再清空，“历史工程”按文件/自动备份/历史保存列出，点击切换。
9. 报告与原始记录生成后写入记录库（`data/records/records.db`），支持历史检索与快照复用。

数据保存：

- LLM Wiki：`data/wiki/wiki.db`（内置 30+ 页种子，可从 `/wiki` 编辑/导入）
- 报告/原始记录库：`data/records/records.db`（旧 JSON 历史首次启动自动迁移）
- 报告模板/原始记录模板：`data/template_library.db`
- 设备库：`data/equipment/equipment.db`
- 人员库：`data/personnel/personnel.db`；支持在人员库对话框上传 Excel/CSV/Word 表格批量导入。
- 规范库：`report_generator/data/norm_qa/norm_codes.db`
- 项目自动保存：`data/projects/autosave.json`
- 会话 transcript：`data/chat_transcripts/<sessionId>.json`；工程长期记忆：`data/chat_memory/*.json`
- 对话任务：`data/chat_jobs.json`（最多 80 条）
- 扫描识别作业：`data/scan_jobs.json`（最多 50 条，重启时运行中作业标记 interrupted）
- 并行评定任务历史：`data/tasks.json`（最多 30 条）

## 数据采集

- 左侧检测项目树：**结构类型 → 检测类别 → 检测项目 → 构件**，共 16 个检测类别（17 个插件中“碳化深度”按原设计隐藏），混凝土结构默认展开到构件层。
- 工作表工具栏支持 **导入文件**：一次可选择多个 Excel（.xlsx/.xlsm）、CSV、Word 表格（.docx），按文件类型逐个解析；多文件默认第一个覆盖、后续追加，也可勾选“追加到现有数据”；表头自动匹配，可自动识别多工作表。
- 数据表支持 **Excel 式选区与剪贴板**：单击选中单元格，`Shift+单击` 扩展矩形选区；
  `Ctrl+C / Ctrl+X / Ctrl+V` 复制、剪切、粘贴 TSV 数据，可直接从 Excel 粘贴多行多列。
  双击或 `F2` 进入编辑，选中后直接键入可覆盖单元格；粘贴会跳过只读计算列并自动扩展行。
- 编辑、粘贴、Excel 导入保存后由后端自动重算计算列（平均值/偏差/合格率/钻芯法强度等）；
  计算列在表格中锁定，不允许手工覆盖，等价于桌面版“编辑即计算”。
- 回弹法/回弹钻芯修正法在“评定 / 结论”弹窗中支持 **导入原始数据文件**：可多选 Excel / CSV / Word 表格，逐个解析后合并为评定输入。
- 所有写请求成功后自动保存到 `data/projects/autosave.json`，重启自动恢复。

## 设备库

- “设备库”页面连接检测设备管理系统：账号密码 + 验证码登录，token 仅保存在后端内存。
- “远程设备”按设备名称搜索、分页浏览，可勾选同步到本地库；“本地设备库”可标记“报告选用”、删除。
- 报告第三章“主要检测设备”按检测项目自动从本地库选仪器：必须是“在用”状态，且该仪器当天已被选用少于 10 次；每份报告对每台仪器记 1 次使用。
- 仪器名来自检测项目 manifest 的 `equipment`（如砖强度→砖回弹仪、砂浆→贯入式砂浆强度检测仪、焊缝→超声波探伤仪），没有专用仪器的项目显式留空，不再用「检测设备」占位；`GET /api/equipment/recommend` 会返回逐项目候选与推荐理由。
- 设备库：`data/equipment/equipment.db`，含 `equipment` 与每日 `equipment_usage` 记录；接口说明见 `API_CONTRACT.md` 第 12.5 节。

## 报告

1. 勾选检测项目并录入/导入数据；
2. （可选）在“评定 / 结论”中运行评定；
3. 进入“报告”页面，系统自动识别报告信息、自动匹配模板，并自动整理二~五章（依据/设备/内容/结果）；报告信息输入框保留，可人工修改后保存；工程概况框会自动填入可编辑模板，也可点“套用模板”重新生成；
4. 点击“生成报告”或“生成原始记录”；
5. 生成完成后在线预览（docx 转 PDF 内嵌）或下载，不需要人工选择模板。

生成文件位于 `report_generator/exports/<时间戳>/检测报告.docx`。

## 外部插件

- 默认目录：`plugins/external/<plugin_id>/`，每个插件一个 `plugin.json`，可选 `plugin.py`。
- `source=manifest` 的纯 JSON 插件不执行代码；`source=python` 会加载插件类。
- “插件管理”页可添加外部目录、重新加载全部插件，无需重启后端。
- 额外目录保存在 `data/plugins/sources.json`，也支持 `STRUCTURAL_PLUGIN_DIRS` 环境变量。
- 外部插件 id 与内置插件冲突时不会覆盖，状态页会显示错误。
- DSH Host API 页可保存 launch token，直接调用 DSH 的 `pluginManager` / `pluginMarket`：
  索引源、已安装 bundle、外部安装、启停和删除；token 只保存在 `data/dsh_host.json`。

## 新增检测项目

普通项目只需在 `report_generator/modules/_configs/` 放一个 JSON（列头、列类型、计算规则），重启后端自动注册，不改框架代码。

完整字段说明：[docs/新增检测项目配置.md](../docs/新增检测项目配置.md)。需要参数对话框、专属评定或特殊建表时，才使用 `modules/<name>/plugin.py` Python 插件。

## MCP / Harness

- MCP Server：`webapp/mcp_server.py`（109 个工具 = 40 基础 + 69 扩展，含模板库/人员库/知识库/规范库/记录库（检索/复用）/工程回退/审计/表格结构/设备推荐/配置/扫描作业/采集入口/检测项契约；扩展定义见 `webapp/mcp_tools_extra.py`）
- 采集入口：`recognize_file` 认一份原始记录属于哪个检测项目（Excel/CSV/Word/.doc），`import_file` 直接按表头导入并重算；后端读本机路径，不需要上传
- DSH 配置片段：`webapp/mcp_server.dsh-patch.yml`
- 写操作工具要求 `confirm=true`；
- 删除/覆盖类工具还需 `confirm_delete=true`，并写入 `data/audit/mcp_writes.jsonl`（见 `docs/人机协同与安全门.md`）；
- 自检：`scripts/check.ps1`（23 套件 + manifest + 工具面 + 目录卫生）。

## 依赖

- Python 3.8（系统解释器 `C:\Program Files\python\python.exe`）
- 后端依赖已随项目提供（`report_generator/libs`）
- 前端已构建到 `webapp/frontend/dist`
