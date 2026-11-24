# DSH 源码改造：结构检测工程 dock

本项目不再只是“外挂一个 DSH 页面”，而是给 **DSH 源码**加了一个客户端插件，
把本项目的对话操作方式直接嵌进 DSH 原生界面（输入框上方的 dock），
同时保留 DSH 的会话 / 计划 / 子智能体 / 审批 / 技能 / 工具全部能力。

## 1. 插件位置

```text
deepseek-harness/
└── packages/client/ui-structural/        # 新增客户端插件
    ├── package.json                     # dsh.client（浏览器 half + 平台）
    ├── tsdown.config.ts                 # 复用 clientBundle 预设
    ├── src/index.ts                     # Host half（空壳，占 Loader 行）
    ├── src/client/index.ts              # 注册 conversation.input.dock
    ├── src/client/StructuralDock.tsx    # 工程摘要 + 预设按钮
    └── README.zh.md
```

注册点：

- `packages/bundle/web-app/cordis.patch.yml` 的浏览器 roster 增加
  `ui-structural` 行；
- `packages/bundle/web-app/package.json` 增加 workspace 依赖。

## 2. 交互

| 元素 | 行为 |
|---|---|
| 工程名 / 勾选 / 录入 / 评定 | 从本项目后端 `/api/project/current`、`/api/workflow/status` 只读拉取 |
| 工程体检 / 录入原始记录 / 执行评定 / 生成报告 / 查规范 | 点击后通过 **Session 原生 prompt**（`session.prompt([{type:'text',text}], 'queue')`）发进当前会话 |

预设文本只是“话术”，真正的执行仍由 DSH 智能体调用本项目 MCP 工具完成；
插件不绕过审批、计划或会话持久化。

## 3. 构建与启动

```powershell
# 在 deepseek-harness 仓库
pnpm --filter @deepseek-ai/dsh-client-ui-structural bundle
node apps/cli/lib/bin.js --profile web --port 3654
```

或在本项目根目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dsh-source.ps1 -Port 3654
```

启动后终端会打印 `http://127.0.0.1:3654/?token=...`，浏览器打开即可；
输入框上方出现「结构检测」dock。

## 4. 与本项目 Web 的关系

- 本项目 `/harness` 仍内嵌 DSH Web GUI（默认 `[dsh].gui_url`）；
- 若使用源码版 DSH（带 dock），把 `config/structural.toml` 的
  `[dsh].gui_url` 指到源码实例（如 `http://127.0.0.1:3654`），
  这样 Vue 对话页里看到的就是**带 dock 的 DSH**。

## 5. 跨域

DSH 页面（`127.0.0.1:3654`）要读本项目后端（`127.0.0.1:8765`），
后端已允许本机任意端口：

```python
allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+"
```

只放开本机来源，不放开公网。

## 6. 启动页与 DSH 交互对齐

- 本项目 `/harness`（默认首页）改为**整屏 DSH**：只保留 40px 状态条
  （工程名、勾选/录入/评定、刷新/采集/报告/新窗口），其余区域全部是原生 DSH Web GUI，
  不再套左侧卡片或自定义对话面板；启动页的交互就是 DSH 的交互。
- 工程上下文与预设已下沉到 DSH 内部：
  - `conversation.input.dock`：输入框上方的「结构检测」dock；
  - `conversation.hero.options`：DSH 空白会话启动页的「工程体检 / 录入数据 / 生成报告」快捷选项；
- 预设发送走 Session 原生 `prompt`，与用户在输入框输入完全同一条链路。

## 7. 已安装到 web profile（2026-11-12）

```text
~/.dsh/profiles/web/
  package.json   dependencies: dsh-worktable 0.5.1, @deepseek-ai/dsh-client-ui-structural 0.2.2-rc.1
                 bundles: base, web-app, dsh-worktable, ui-structural
  cordis.patch.yml  structural_inspection MCP（stdio）+ agent-default-model
```

- 稳定 tgz：`~/.dsh/plugins/dsh-worktable-0.5.1.tgz`、`~/.dsh/plugins/dsh-client-ui-structural-0.2.2-rc.1.tgz`；
- 启动：`dsh web --port 3660 --no-open`（工作目录 = 项目根，技能从 `.dsh/skills` 加载）；
- 日志会打印 `[structural-mcp] ... tools=109`，页面输入框上方出现结构检测 dock；
- 本项目 `config/structural.toml [dsh].gui_url` 默认指向 `http://127.0.0.1:3660`。

## 8. 本地模型（Ollama）

web profile 已把本机 Ollama 作为 OpenAI 兼容提供方接入：

```yaml
- id: llm-pi-ai
  name: "@deepseek-ai/dsh-llm-pi-ai"
  config:
    providers:
      ollama:
        displayName: 本地 Ollama
        api: openai-completions
        baseURL: http://127.0.0.1:11434/v1
        models:
          - id: qwen3.6:35b
            contextWindow: 262144
          - id: qwen2.5vl:7b
            contextWindow: 128000
          - id: qwen3.8:27b-64k
            name: qwen3.8:27B-64k
            contextWindow: 65536
- id: agent-default-model
  config:
    provider: ollama
    model: qwen3.8:27b-64k
    reasoningEffort: off
```

- qwen3.8 使用派生模型 `qwen3.8:27b-64k`（65536 上下文）；262144 上下文会把
  KV cache 挤到 CPU（实测 33% CPU / 67% GPU，约 1.9 tokens/s），64k 时 100% GPU；
- 派生方法：

  ```powershell
  @"
  FROM qwen3.8:27b
  PARAMETER num_ctx 65536
  "@ | Set-Content "$env:USERPROFILE\qwen3.8-64k.Modelfile" -Encoding ASCII
  ollama create qwen3.8:27b-64k -f "$env:USERPROFILE\qwen3.8-64k.Modelfile"
  ```

- 实测 64k：`ollama ps` 显示 100% GPU、CONTEXT 65536；短 prompt 经 ACP 约 14 秒（含模型加载/工具初始化）；
- 建议保持 Ollama 常驻或设置 `OLLAMA_KEEP_ALIVE`；
- 要换回云端：把 `agent-default-model` 的 provider/model 改回
  `deepseek-official / deepseek-flash`，或还原 `cordis.patch.yml.bak3_*`。

## 9. 自研 Web 对话（ACP 桥）

Web 端不再内嵌 DSH 页面，改为本产品自己的对话界面：

```text
Vue ChatView (/harness)
  │ WebSocket /api/chat/ws（structural_session Cookie）
  ▼
FastAPI routers/chat.py
  │ stdio JSON-RPC (ACP)
  ▼
dsh --profile acp
  ├─ session/new：cwd=项目根，mcpServers=[structural_inspection]
  ├─ session/prompt：流式 session/update（text / tool_call / plan）
  └─ session/request_permission：本机模式自动 allow-once
```

- ACP profile 默认模型：`ollama / qwen3.8:27b-64k`（`~/.dsh/profiles/acp/cordis.patch.yml`）；
  页面右上角模型下拉通过 `session/set_config_option` 切换 DeepSeek / 本地模型；
- ACP `session/new` 的 configOptions 已确认包含 `qwen3.6:35b`、`qwen2.5vl:7b`、`qwen3.8:27b-64k`；
- qwen3.8-64k 加载后 `ollama ps` 为 100% GPU；如果选 qwen3.6 的 262k 配置仍可能掉到 CPU；
- 会话侧栏：`session/list` 列出该 cwd 下的持久会话，点击 `session/resume` 恢复；
  ACP 不回放旧更新，历史消息由前端 `localStorage` 按 sessionId 保存；
- 权限：`session/request_permission` 转发到页面，允许一次 / 拒绝后再回 ACP；
- 取消：prompt 在后台任务里执行，`session/cancel` 可以中断当前回合；
- 命名：标题存 `data/chat_sessions.json`，首条消息自动作标题，可重命名；
  “删除”只把会话标记为隐藏，不删除 DSH 磁盘会话；
- 渲染：助手消息走轻量 Markdown（标题/列表/粗体/代码块/链接/表格/图片），工具轨迹可展开原始数据；
- 报告卡片：消息或工具结果里出现 `/api/report/preview|download?filepath=...` 时，
  输入框上方出现「检测报告已生成」卡片，可直接打开预览或下载；
- 权限弹窗已验证：shell 工具触发 `session/request_permission`，点「允许一次」后继续执行。

## 10. 布局与工作区

对话页按 DSH 工作台布局组织：

- 左侧：工程下拉（`/api/project/list|activate`）+ 导航（对话/工作区/插件/自动化任务），不再堆会话列表；
- 主区：进入「对话」先显示**会话记录工作区**，按工程分组连续排列会话行（标题/会话 ID/相对时间），
  点击行进入对话，顶部「← 会话」返回；支持搜索、「全部工程」过滤，空白会话默认隐藏；
- 对话顶部：对话 / 轨迹切换，右侧「文件」抽屉；
- 右侧：`/api/workspace/tree|file` 的工作区文件树，文本/图片预览；
- 底部：上传（`/api/workspace/upload`，保存到 `data/uploads/`）、当前工作区、模型选择、输入框；
- 会话元数据 `project` 记录创建时工程名，默认只看当前工程，可切「全部工程」；
- 「插件」抽屉：`/api/chat/plugins` 只读列出 web/acp profile 的 bundle、版本与 MCP 工具数；
- 「自动化任务」抽屉：读取 `/api/workflow/status` 展示勾选/录入/评定进度（ACP 不暴露 DSH 定时任务）；
- 工程下拉「＋」调用 `/api/project/new`；切换工程先确认，成功后自动 `session/new`，会话按新工程归档；
- 自动保存写回当前项目文件（`state.filepath`），只有未加载文件时才写 `autosave.json`；
  已回归：原工程 5/5/2 → 目标 1/1 → 切回 5/5/2，结构化哈希 `00f1c7a9487d` 一致。

## 11. 升级注意

- 插件依赖 DSH 的 `conversation.input.dock` 槽位与 Session `prompt` 命令；
  DSH 大版本升级后先跑 `pnpm --filter @deepseek-ai/dsh-client-ui-structural bundle`，
  再手动确认 dock 是否仍挂载；
- `pnpm-lock.yaml` 会因新增 workspace 包更新，属正常变更。
