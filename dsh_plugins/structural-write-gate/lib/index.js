/**
 * 结构检测写操作审批门禁（host 端原生钩子插件）。
 *
 * 机制：在 `tools/pre-execute` waterfall 对 structural_inspection MCP 的
 * 写工具返回 `{ kind: 'ask' }`，由 dsh-tools 管线经 `ctx.approval` 走审批，
 * ACP 桥（dsh-acp）将其转发为 `session/request_permission`，产品对话页
 * （webapp/frontend ChatView.vue）弹出确认框，用户允许后才会执行。
 *
 * 写工具清单与 webapp/mcp_server.py 的 write=True 保持一致
 * （由 AST 解析 _tool(...) 第 5 个位置参数提取）；MCP 层的 confirm=true
 * 参数门禁仍然生效，本插件是额外的 ACP 层弹窗审批。
 */

export const name = 'dsh-structural-write-gate'

const SERVER_PREFIX = 'mcp__structural_inspection__'

const WRITE_TOOLS = new Set([
  'create_project',
  'open_project',
  'save_project',
  'check_item',
  'create_data_sheet',
  'put_rows',
  'import_sheet_excel',
  'import_assessment_excel',
  'save_assessment_input',
  'run_assessment',
  'run_all_assessments',
  'select_templates',
  'generate_report',
  'render_report',
  'generate_original_record',
  'save_report_document',
  'replace_report_text',
  'select_equipment',
])

export function apply(ctx) {
  console.error('[write-gate] plugin applied, watch ' + SERVER_PREFIX + '*')
  ctx.on('tools/pre-execute', async (exec, next) => {
    const tool = String(exec?.name || '')
    if (tool.startsWith(SERVER_PREFIX)
        && WRITE_TOOLS.has(tool.slice(SERVER_PREFIX.length))) {
      console.error('[write-gate] ask for write tool: ' + tool)
      return {
        kind: 'ask',
        reason: '结构检测系统写操作需要用户确认：' + tool.slice(SERVER_PREFIX.length),
      }
    }
    return next()
  })
}
