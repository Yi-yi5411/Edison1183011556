# Harness 智能体架构（P0 后）

本项目以 DeepSeek Harness（DSH）为唯一智能体底座；DSH 直接以 **MCP stdio** 方式挂载
本项目的工具服务，业务数据与确定性计算仍由 Python 后端提供。

## 运行拓扑

```text
浏览器（127.0.0.1:8765）
  ├─ /harness 对话入口：iframe 内嵌 DSH Web GUI（127.0.0.1:3642，保留原生全部能力）
  │     └─ 外层加工程上下文 / 快捷指令 / 可达性兜底（Vue HarnessView）
  └─ /project、/report、/wiki、/records、/library … 编辑与浏览页

DSH（被嵌入的原生运行时）
  ├─ 会话 / 计划 / 目标 / 子智能体 / 审批 / 技能 / 交付物
  ├─ MCP stdio: structural_inspection  → webapp/mcp_server.py（109 个工具）
  │        │ HTTP
  │        ▼
  │   FastAPI 后端（127.0.0.1:8765）→ report_generator 业务层 + SQLite 库
  └─ 技能：<项目>/.dsh/skills/structural-*（由检测项目 manifest 生成）
```

- 配置：`config/structural.toml`（`webapp/structural_config.py` 读取，环境变量覆盖）。
- MCP 配置片段：`webapp/mcp_server.dsh-patch.yml`（`dsh-mcp-client`，serverName=structural_inspection）。
- 智能体入口：Vue `/harness`（默认首页）**整屏内嵌原生 DSH Web GUI**（`[dsh].gui_url`，默认 http://127.0.0.1:3642），
  只保留 40px 状态条；会话、输入、计划、子智能体、审批全部是 DSH 自己的交互，不重写对话逻辑。
- **DSH 源码改造**：`deepseek-harness/packages/client/ui-structural` 是新增的 DSH 客户端插件，
  在 DSH 输入框上方挂「结构检测」dock（工程/进度摘要 + 项目化预设），点预设通过 Session 原生
  `prompt` 发进当前会话；已在 `packages/bundle/web-app/cordis.patch.yml` 登记。
  构建 `pnpm --filter @deepseek-ai/dsh-client-ui-structural bundle`，用
  `scripts/start-dsh-source.ps1` 启动源码版；详见 [DSH源码改造.md](DSH源码改造.md)。

## P0 已删除的东西

| 已删除 | 原因 |
|---|---|
| `harness/dsh_bridge.py`、`harness/dsh_worker.py` | 通过 Python SDK sidecar 另起一套 `dsh --profile sdk`，与 MCP 路线重复 |
| `harness/dsh_structural_plugin.mjs`、`dsh_permission.patch.yml` | 直接 import DSH 内部构建路径（`packages/core/tools/lib/index.js`），版本一升即断；且把工具压成两个元工具，模型看不到真实 schema |
| `webapp/structural_cli.py` | 第三套派发面（shell → CLI → MCP 表） |
| `webapp/backend/agent_service.py`、`routers/agent.py` | 第二套独立工具循环（Ollama-only、不持久化） |
| `/api/harness/agent_tools`、`/api/harness/agent_tool` | 只服务于已删除的 .mjs 插件 |
| 编排器里的 DSH 分支（`_run_dsh_chat` 等 159 行） | sidecar 删除后成为死代码 |

所有绝对路径（`C:\\Users\\...\\deepseek-harness\\...`、`.venv` 3.14、`dsh.CMD`）随上述文件一并消失，
改由 `config/structural.toml` 提供。

## P0-b 已完成（应用内编排层已删除）

| 已删除 | 说明 |
|---|---|
| `harness/orchestrator.py`、`planner.py`、`team.py`、`llm_client.py`、`task_state.py`、`session_store.py`、`project_binding.py`、`tool_registry.py`、`file_parser.py`、`prompts.py` | 应用内智能体循环、规划/复核/委派、会话库与工程绑定；共 10 个模块 |
| `routers/harness.py`（10 个端点） | 会话/对话/上传/取消/测试/事件；未命中路径现在返回 404 |
| `/api/agent/*`（此前已随 agent_service 删除） | — |
| Vue 自研对话实现：`stores/harness.ts`、`components/harness/*`（5 个组件）、`HarnessDock` 全局抽屉、`api/index.ts` 的 harness 封装 | 改为**嵌入原生 DSH**；`HarnessView.vue` 重写为「工程上下文 + iframe + 兜底」 |
| `api/index.ts` 的 harness 封装（146 行） | 前端 bundle 中已无 `/api/harness` 调用 |
| `test_harness_smoke.py`、`backend/test_agent_state.py` | 随功能删除 |

替代实现：

- `harness/intent.py` → `webapp/backend/item_intent.py`（规则意图，`/api/project/suggest` 仍在用）；
- `GET /api/system/info` → 返回 `agent_surface=dsh`、`dsh_gui_url`、`mcp_server_name`；
- 工程作用域：`/api/project/current|list|activate`（MCP：`current_project` / `list_projects` / `activate_project`）；
- 顶栏“新建工程”走 `/api/project/new`（自动备份），“历史工程”走文件列表，不再有会话级工程快照；
- 默认首页 `/` → `/harness`（对话入口）；页面内嵌原生 DSH，不再自研对话 UI。

## 与 DSH 的对应关系

| DSH 能力 | 本项目用法 |
|---|---|
| 会话 / 计划 / 目标 / 审批 / 子智能体 | 原生提供，项目不再自研 |
| MCP 工具 | `webapp/mcp_server.py`（109 个，读写分离，写操作要求 confirm，删除/覆盖类需二次确认并留审计） |
| 技能 | `.dsh/skills/structural-*`（29 个检测项目技能，由 manifest 生成） |
| 会话内交付物 | `generate_report` 等工具返回文件路径，可直接 `present` |
| 外部能力（CAD/结构计算） | 以 MCP 服务器形式挂载（SolidWorks 已是现成样例） |

## 前端事件

Vue 端仅保留业务事件（表格修改、导入、评定、生成）；智能体的工具轨迹与审批在 DSH 里看。

## 启动

```bat
.\install.ps1          :: 首次：写入配置、检查解释器与依赖、打印 MCP 片段
.\start-backend.ps1    :: 起后端（127.0.0.1:8765）
```
