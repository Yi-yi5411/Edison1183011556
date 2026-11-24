# 变更记录

## 报告表格格式统一（2026-11-13）

- 结果表按“连续相同值”自动纵向合并：批次、构件编号、构件名称/轴号、设计值、设计等级、钢筋牌号等；
- 所有结果表单元格水平、垂直居中；表头跨页重复、行不跨页；
- 字体取模板中出现最多的中文字体与字号，全表统一，表头加粗；
- 表头多段合并为一段，数据行去掉换行和空段落，单元格里不再出现一串换行符；
- 报告落盘前统一清理所有表格空段落；26 套件通过。

## 报告预览稿（2026-11-13）

- 新增 scripts/generate_preview.py：跳过正式预检直接渲染预览稿，不占设备、不写报告历史；
- 预览稿页眉标红“预览稿 · 非正式报告（未通过报告预检）”；
- 输出 data/previews/current/检测报告_预览稿.docx|pdf。

## 会话记录移入工作区（2026-11-13）

- 左侧栏移除会话列表，只保留工程切换、新建会话和导航；
- 主区「对话」默认进入会话记录工作区：按工程分组**连续排列**（非卡片网格），
  每行显示标题、会话 ID 与相对时间；点击进入对话，顶部「← 会话」返回；
- 支持搜索会话标题/ID、全部工程过滤；空白会话默认隐藏，只保留当前“新会话”；
- 行内保留重命名/删除；新建会话直接进入对话；
- 截图：docs/assets/chat-sessions-workspace.png。

## 报告结果表模板修复（2026-11-13）

- 31 个结果表统一收敛到 15.4cm，补表题 keep-with-next、表头跨页重复、行不跨页；
- 锚固表 5.7/通用模板拆除“构件名称”纵向合并，重分配列宽，HRB400 不再拆行；
- 数据中的重复单位（7.3 kN 在“检验荷载(kN)”列）改为 7.3；
- 已完成全局修复与锚固表单表修复；剩余结构性问题（保护层 6/10 点、回弹钻芯修正法列映射、
  钢筋数量表头映射、厚度表缺合格点率、截面尺寸表映射）记录在 docs/报告表格缺陷清单.md；
- 全量 26 套件通过。

## 锚固承载力评定规则（2026-11-13）

- 新增 `anchor_bearing` 评定规则（`family=anchor`）：逐根检查检测荷载 ≥6.0kN、
  持荷2min荷载降低率 ≤5%、试验现象无裂缝/无滑移，或逐行结论；
- `化学植筋锚固承载力检测` manifest 增加 assessment 关联，报告可使用类型一/类型二结论；
- 当前工程 75 根实测全部合格（类型一）；单测新增合格/不合格两例，规则总数 18；
- 新增 `record_check` 覆盖砌体尺寸、砌筑砂浆、高强螺栓、防腐/防火涂层、钢材、焊缝、木结构 4 项：
  8 项按逐行结论汇总，3 项无判定列时仅记录（类型三）；
- 规范库只有 2 本示例（11 条条文），未伪造条文级阈值；严格规则需先导入对应规范。

## 本地模型 qwen3.8:27b-64k（2026-11-13）

- 创建派生模型 `qwen3.8:27b-64k`（`num_ctx=65536`），避免 262144 上下文的 KV cache 把模型挤到 CPU；
- `ollama ps` 验证：100% GPU、CONTEXT 65536；ACP 短 prompt 约 14 秒完成；
- `web` / `acp` profile 均加入 `qwen3.8:27b-64k`（`contextWindow: 65536`），默认模型切换到该模型；
- ACP `session/new` configOptions 已确认包含 qwen3.8:27b-64k；
- 262144 上下文实测 33% CPU / 67% GPU、约 1.9 tokens/s，不再作为默认。

## 报告检测项目名称统一（2026-11-13）

- 新增 `report_items.py`：报告“四、检测内容”按父级分类分组（1.1/1.2 子项），
  首页“检测项目”、结果章节标题、结果表标题统一使用标准项目名；
- 表格/结论按“分类 → 子项”重排，结论编号与内容分组一致；
- 例：`钻芯法检测（梁）` → `钻芯法检测构件混凝土抗压强度（梁）`；
  `混凝土板保护层厚度检测` → `混凝土板构件保护层厚度检测`；
  `化学植筋锚固承载力检测` → `填充砌体墙锚固承载力检测`；
- 未收录的砖强度等项目作为独立项保留原名；分类顺序用于内容、表格和结论编号；
- 新增 `tests/test_report_item_names.py`，全量 **25 套件**通过。

## 报告预检与结论兜底（2026-11-13）

- 新增 `report_preflight.py`：生成/渲染前校验报告抬头、每个勾选项目的数据/评定/结果表模板、
  占位符与日期；不通过返回 400，不占用仪器、不写生成记录；
- 兜底结论不再默认“满足”：没有可比数值、也没有逐行合格结论时，统一输出“未提供足够数据，无法判定”；
- 空数据项目写入 `skipped`/`warnings`，不再从报告和生成记录里静默消失；
- 修复自动纵向合并把锚固表“构件名称”清空的问题（关闭合并可复现，已加回归）；
- 首页“检测依据”自动回填；新增建设单位/施工单位等字段，施工单位使用独立的 `contractor` 字段；
- 新增 `tests/test_report_preflight.py`，全量 24 套件通过。

> 当前工程 5 个检测项中 2 项已评定、砖强度无数据、报告信息仍有占位符，预检会阻止生成；
> 补全信息并完成评定后即可重新生成。

## 后端后台运行（2026-11-12）

- `start-backend.ps1` 新增 `-Detach`：用 `Start-Process` 独立启动 uvicorn，
  不再随 DSH 的终端/后台任务结束而退出；日志写 `data/logs/backend.out.log`、`backend.err.log`；
- 已后台启动并验证：PID 5360，`/api/health` 正常，跨工具调用后仍存活。

## 项目更名：工程检测harness（2026-11-12）

- 产品显示名统一为「工程检测harness」：Web 标题/登录页/侧栏、桌面登录与主窗口、
  FastAPI/MCP 描述、README、EXE/安装包名；
- 桌面端已重新打包：`dist\工程检测harness\工程检测harness.exe`（14.96 MB，2026-11-12 16:54），
  启动进入“系统登录”窗口；
- 内部目录 `structural_inspection`、Python 包名、MCP serverName、数据库文件名保持不变，
  避免 DSH 配置、快捷方式与已有工程路径失效。

## 设备选取修正（2026-11-12）

- 钻芯法 / 回弹钻芯修正法的设备由「钻芯机」改为「微控电液伺服压力试验机」；
  本机设备库没有钻芯机，旧映射会让所有含钻芯法的报告报“没有可用仪器”；
- 锚杆拉拔仪匹配改为 `拉拔/拉力计`，优先 `数显 / 锚杆 / 一体式`；植筋拉拔优先选数显锚杆拉拔仪；
- 游标卡尺规则收紧，排除砖用卡尺、消防卡尺、深度尺、千分尺等；
- 实测当前 5 项工程：压力试验机、游标卡尺、钢筋扫描仪、板厚仪、数显锚杆拉拔仪、砖回弹仪全部匹配。

## 对话布局对齐 DSH（2026-11-12）

- 左侧：工程下拉切换 + 会话按工程分组；导航改为 对话 / 工作区 / 插件 / 自动化任务；
- 顶部：**对话 / 轨迹** 切换，右侧“文件”抽屉；
- 右侧：工作区文件树（目录/文件、大小），文本与图片可直接预览；
- 底部：上传文件、当前工作区、模型选择与输入框；上传落到 `data/uploads/` 并插入对话路径；
- 会话元数据增加 `project`，会话列表按当前工程过滤（可切“全部工程”）；
- 「插件」面板：只读列出 web/acp profile 的 bundle、版本与 `structural_inspection` MCP（109 工具）；
- 「自动化任务」面板：展示当前工程勾选/录入/评定进度，并可跳流程总览；
- 工程下拉支持「＋新建工程」；切换工程弹确认框，确认后新建会话，避免旧会话挂到新工程。
- 修复切换工程覆盖 autosave：自动保存改为写回当前项目文件，不再把目标工程写进 autosave.json；
- 实测往返切换：原工程 5 项/5 表/2 评定 → 目标 1 项/1 表 → 切回 5/5/2，结构化哈希一致。

## 自研 Web 对话界面（2026-11-12）

- `/harness` 不再内嵌 DSH 页面，改为**本产品自研对话界面**（`ChatView.vue`）：
  左侧产品导航/会话，右侧消息流、工具轨迹、计划、输入框；
- 新增后端 ACP 桥 `webapp/backend/routers/chat.py`：WebSocket `/api/chat/ws`
  ↔ `dsh --profile acp`（stdio JSON-RPC），自动挂载 `structural_inspection` MCP；
- 登录态校验：WebSocket 复用 `structural_session` Cookie，未登录拒绝；
- ACP profile 默认模型改为本地 `ollama / qwen3.6:35b`；页面右上角可切换
  DeepSeek / 本地模型（`session/set_config_option`）；
- 本地 35B 首次响应很慢（实测数分钟），日常可先切 DeepSeek；
- 会话侧栏：`session/list` 列出持久会话，点击 `session/resume` 恢复（本地保留消息记录）；
- 工具权限改为页面确认（允许一次 / 拒绝），不再静默放行；
- prompt 改为后台任务，`session/cancel` 可中断当前回合；
- 会话重命名 / 删除（软隐藏，不动 DSH 磁盘会话）；首条消息自动作为标题；
- 助手消息支持 Markdown（标题/列表/粗体/代码块/链接/表格/图片），工具轨迹可展开原始入参/结果；
- 对话里检测到 `/api/report/preview|download` 链接时，底部出现「检测报告已生成」卡片，可直接预览/下载；
- 权限弹窗已做端到端验证：shell 工具触发确认，点「允许一次」后执行；
- 原 DSH 整页保留在 `/dsh` 作为排障/回退入口。

## Web 登录与产品化（2026-11-12）

- 新 Web 端登录：复用桌面端账号库（`desktop/auth.db`，admin/admin123 或手机号），
  新增 `POST /api/auth/login`、`GET /api/auth/me`、`POST /api/auth/logout`；
- 新增登录页 [LoginView.vue](webapp/frontend/src/views/LoginView.vue)：品牌分栏 + 账号表单；
  路由守卫未登录跳 `/login`，已登录访问 `/login` 回 `/harness`；
- 顶栏与对话状态条增加“退出登录”；
- 产品边界：Web 端独立成新产品，桌面端与旧 DSH 作为另一个产品，不再混用品牌与入口。

## 本地模型接入（2026-11-12）

- DSH web profile 接入本机 Ollama（OpenAI 兼容 `http://127.0.0.1:11434/v1`）：
  `qwen3.6:35b`（默认，262144 上下文）与 `qwen2.5vl:7b`（128000，视觉）。
- `agent-default-model` 改为 `provider: ollama / model: qwen3.6:35b`；模型选择器已显示该模型。
- 配置备份：`~/.dsh/profiles/web/cordis.patch.yml.bak3_<时间戳>`。

## 项目品牌 + 对话工作流（2026-11-12）

- **品牌**：新增项目 logo（深蓝楼体 + 琥珀色对勾）并替换
  Web favicon、侧栏品牌图标、桌面登录 logo、桌面 EXE 图标；
  旧资源备份为 `logo.jpg.bak_20261112_123242`、`app.ico.bak_20261112_123242`。
- **对话工作流**：新增技能 `.dsh/skills/structural-workflow`，把
  “加载采集 / 录入数据 / 执行评定 / 生成报告 / 预览报告 / 修改报告 / 查规范”映射到本项目 MCP 工具。
- DSH 的 `ui-structural` dock / 启动页选项扩展为上述全流程按钮；
  `generate_report` 返回值新增 `preview_url`、`download_url`（指向 `/api/report/preview`、`/api/report/download`）。
- 安装到 DSH `web` profile：`ui-structural` 插件 + `structural_inspection` MCP（109 工具），
  workspace 设为项目目录（30 个技能可加载）；`/harness` 默认指向 `http://127.0.0.1:3660`。

## 对话入口 DSH 原生化（2026-11-12）

- `/harness` 改为**整屏 DSH**：去掉左侧工程卡片与自定义对话面板，只保留 40px 状态条
  （工程名 / 勾选·录入·评定 / 刷新 / 采集 / 报告 / 新窗口），启动页交互与 DSH 一致。
- DSH 插件新增 `conversation.hero.options` 注册：DSH 空白会话启动页出现
  「工程体检 / 录入数据 / 生成报告」快捷选项；与输入框 dock 共用 Session 原生 `prompt`。
- 工程上下文不再由 Vue 外层卡片承担，全部下沉到 DSH 插件内部。

## DSH 源码改造（2026-11-12）

- 在 `deepseek-harness/packages/client/ui-structural` 新增客户端插件 `@deepseek-ai/dsh-client-ui-structural`：
  DSH 输入框上方出现「结构检测」dock，左侧工程名与勾选/录入/评定计数（读本项目后端），
  右侧五个项目化预设按钮，点击通过 **Session 原生 `prompt`** 发进当前会话，保留 DSH 全部能力。
- 已登记到 `packages/bundle/web-app/cordis.patch.yml` 的浏览器 roster 与 `package.json` 依赖；
  构建 `pnpm --filter @deepseek-ai/dsh-client-ui-structural bundle`。
- 本项目新增 `scripts/start-dsh-source.ps1`（默认 3654 端口）与 [docs/DSH源码改造.md](docs/DSH源码改造.md)。
- 后端 CORS 放开本机任意端口（`allow_origin_regex`），供 DSH 页面读取工程上下文；不放开公网。

## 对话入口恢复（2026-11-12）

- `/harness` 恢复为**对话入口**并作为默认首页：页面直接嵌入**原生 DSH Web GUI**
  （`config/structural.toml [dsh].gui_url`，默认 `http://127.0.0.1:3642`），
  保留 DSH 的会话、计划、子智能体、审批、技能、工具与交付物全部能力。
- 页面只做本项目特有的三件事：工程上下文（工程名/勾选/录入/评定/模板）、
  项目化快捷指令（一键复制话术）、DSH 可达性与登录提示。
- 新增 `GET /api/system/dsh` → `{url, reachable, status, auth_required}`，供嵌入前探测。
- 嵌入依赖浏览器里 DSH 的 `dsh-auth-*` Cookie（SameSite=Strict），请用 `127.0.0.1:8765` 访问；
  首次或失效时点「在新窗口打开 DSH」登录一次。

## 桌面端独立（2026-11-12）

- 新建 `desktop/` 包：`login.py` / `login_launcher.py` / `home_menu.py` / `auth_db.py`
  + `auth.db` / 种子 SQL / `app.ico` 全部迁入，附 `desktop/README.md`。
- 根目录只保留**外部入口**：`run.py`（薄壳）、`run_app.bat`、`build.bat` / `compress.bat`、
  `report_generator.spec`。
- `run.py` 与 `report_generator/main.py` 改为 `from desktop.login_launcher import main`；
  `login_launcher` 按 frozen/源码两种模式定位 `auth.db` 与种子 SQL。
- PyInstaller spec：收集 `desktop` 包，`auth.db`/`user_mobile_1029.sql` 放 `_MEIPASS` 根，
  图标改到 `desktop/app.ico`。

## 项目整理（2026-11-12）

- 测试统一到 `tests/`（23 个套件），新增共用骨架 `tests/_harness.py`：
  路径引导、UTF-8 输出、`check/skip/finish` 汇总；16 个脚本去掉重复样板代码。
- 删除过期/重复用例：`test_mcp_smoke.py`（会重置真实工程）、
  `test_mcp_import_formats.py` 的 Word/CSV 解析段（与 ingest/excel 套件重复）→ 只保留
  MCP 上传白名单，改名 `test_mcp_upload.py`。
- 工具总数只由 `test_mcp_tool_surface` 断言（109），各功能套件不再各写一个 `>=` 下限。
- 根目录瘦身：调试产物 → `_archive/`，官方资料 → `docs/references/`，
  用户手册 → `docs/manual/`，示例输入 → `data/samples/`，业务文档 → `docs/`。
- 新增 `docs/项目结构.md`；README 项目结构树与 `webapp/README.md` 页面/架构说明同步更新。

## P8 — 工程化（2026-11-12）

- 版本单一来源 `[app].version`：`/api/health`、`/api/system/info`、FastAPI 同源。
- `scripts/check.ps1`：23 套件 × 3.8/3.14 + manifest 校验 + 工具面计数 + 目录卫生（约 1 分钟）。
- `scripts/release.ps1`：改版本 → 写 CHANGELOG → 自检 → 打 zip（支持 `-DryRun`）。
- 结构化访问日志 `data/logs/backend.jsonl` + `X-Request-ID` 透传（`STRUCTURAL_ACCESS_LOG=off` 可关）。
- `requirements-web.txt` / `requirements-dev.txt` 锁定 Web 依赖与测试依赖。
- 测试卫生：清理临时目录泄漏（27 个），统一 UTF-8 输出（cp936 下 Python 3.8 输出会崩）。

## P7 — CAD / 结构计算集成（2026-11-12）

- **CAD**：`cad_agent/` 从“自带中文 NLU 的独立智能体”改为**结构化绘图库 + MCP 服务**：
  - 删除 `nlu.py`、`agent.py`（应用内 NLU 与“只用 DSH”冲突）；
  - 新增 `drawing.py`（在线 COM / 离线 DXF 统一接口、参数校验、计划执行）；
  - 新增 `mcp_server.py`（serverName `autocad`，12 个工具，写操作需 confirm）；
  - `config.py` 改读 `config/structural.toml` 的 `[cad]`，pywin32 延迟导入；
  - `cli.py` 改为 `status` / `open` / `draw --spec`。
- **YJK**：新增 `integrations/yjk/`：
  - `model.py` 按官方示例（案例1/案例6）生成 YJKAPI 建模与读取脚本；
  - `bridge.py` 用盈建科自带 Python 3.10 执行脚本并解析 JSON；
  - `mcp_server.py`（serverName `yjk`，4 个工具，`yjk_run_script` 为危险操作）。
- 新增 `docs/CAD与结构计算集成.md`、两个 `dsh-patch.yml`；`install.ps1` 增加
  AutoCAD / 探索者 / pywin32 / 盈建科 Python / YJKAPI 检查。
- 测试：`test_cad_agent.py`（25）、`test_yjk_integration.py`（21），均不依赖 CAD/YJK 安装。

## P6 — 人机协同与安全门（2026-11-12）

- 工具三级：只读 58 / 普通写 38 / 危险写 13；危险工具需 `confirm_delete=true`。
- 安全门集中在 `mcp_server._call_tool`；写操作审计 `data/audit/mcp_writes.jsonl`（脱敏、轮转）。
- 新增 `get_audit_log`、`list_project_backups`、`restore_project`；工程恢复前自动另存。
- 工具总数 109。

## P5 — 报告事实与措辞分离（2026-11-12）

- 新增 `report_facts.py`（`report.facts/1`）与 `report_render.py`；`generate_report(narrative=...)`。
- 删除 `report_agent.py`、`report_tools.py`、`use_agent` 与桌面端 Agent 模式。
- 新增 `GET /api/report/facts`、`POST /api/report/render` 与 MCP `report_facts` / `render_report`。

## P4 — 四个库（2026-11-11 ~ 11-12）

- 规范库：语料重建、bm25、术语扩展、按检测项目过滤、覆盖度。
- 报告模板：结果表覆盖 0.6 + 章节完整 0.4 打分、切换建议。
- 设备库：真实仪器名 29/29 覆盖、16 条匹配规则、逐项目推荐理由。
- 记录库：相似检索、快照列对齐复用、数据往返验证。

## P3 — 检测项目插件化（2026-11-11）

- `structural.item/1` manifest：16 个插件 / 29 个检测项 / 29 个技能。
- `/plugins/summary`、`get_item_contract`、manifest 参数校验。

## P2 — 采集入口与扫描作业（2026-11-11）

- `recognize_file`、`import_file`；`scan_submit/scan_job/scan_jobs` 异步作业。

## P1 — 工具面补齐（2026-11-11）

- `webapp/mcp_tools_extra.py`：模板库/人员/Wiki/规范/记录库/表格结构/项目/设备/配置/扫描。

## P0 — 运行时收敛（2026-11-12）

- 删除 DSH sidecar（`dsh_bridge/dsh_worker/.mjs/权限补丁`）、`structural_cli`、`agent_service`。
- 删除应用内编排层（`harness/` 10 个模块）、`/api/harness/*`、`/api/agent/*`。
- 配置外置 `config/structural.toml` + `webapp/structural_config.py`；`/api/system/info`。
- Vue `/harness` 改为只读 AI 状态页；默认首页 `/project`；未命中 `/api/*` 返回 404。
- 新增 `install.ps1` / `start-backend.ps1` / `scripts/check.ps1`。
