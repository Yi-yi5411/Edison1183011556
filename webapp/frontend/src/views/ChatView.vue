<script setup lang="ts">
/**
 * 自研 Web 对话页：DSH 只做 agent 引擎（ACP over WebSocket），
 * 会话、消息、工具轨迹与输入都由本产品渲染。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { ChatDotRound, Collection, FolderOpened, Paperclip, Promotion, SwitchButton, Tickets } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { IngestImportResult, IngestRecognizeResult, ScanCommitResult, ScanJob, ScanPlan, ScanTarget } from '@/api/types'
import { logout } from '@/auth'

const router = useRouter()

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  thinking?: string
  streaming?: boolean
  error?: boolean
  at?: number
}

interface ToolEvent {
  id: string
  title: string
  status: string
  kind?: string
  detail?: string
  at?: number
}

interface WorkspaceItem {
  id: string
  kind: 'report' | 'original' | 'upload' | 'snapshot'
  name: string
  path: string
  filepath: string
  size: number
  at: number
  exists: boolean
  preview: 'docx' | 'pdf' | 'image' | 'text' | 'none'
  downloadable: boolean
  meta: string
  detail: string
  where: string
}

interface WorkspaceSection {
  key: string
  title: string
  items: WorkspaceItem[]
  total: number
}

interface WorkspaceOverview {
  project: {
    name: string
    checked_count: number
    filled_count: number
    assessed_count: number
    total_rows: number
    snapshot_at: number
    snapshot_name: string
  }
  query: string
  limit: number
  counts: Record<string, number>
  total: number
  missing: Record<string, number>
  missing_total: number
  sections: WorkspaceSection[]
}

interface PlanEntry {
  content: string
  status?: string
  priority?: string
}

const messages = ref<ChatMessage[]>([])
const tools = ref<ToolEvent[]>([])
const plan = ref<PlanEntry[]>([])
const draft = ref('')
const busy = ref(false)
const connected = ref(false)
const connecting = ref(false)
const sessionId = ref('')
const modelName = ref('')
const modelConfig = ref<any>(null)
const modelValue = ref('')
const sessions = ref<Array<{ sessionId: string; title?: string; project?: string; updatedAt?: number; busy?: boolean; queue?: number }>>([])
const titles = ref<Record<string, string>>({})
const activeTitle = ref('')
const reportCard = ref<{ preview: string; download: string } | null>(null)
const projects = ref<Array<{ filepath: string; project_name: string }>>([])
const projectPath = ref('')
const currentProjectPath = ref('')
const activeProject = ref('')
const viewMode = ref<'chat' | 'trajectory'>('chat')
const workbenchOpen = ref(false)
const wbEntered = ref(false)
const wbProject = ref('')
const workspace = ref<WorkspaceOverview | null>(null)
const wsLoading = ref(false)
const wsQuery = ref('')
const wsFilter = ref('all')
const wsSelected = ref<WorkspaceItem | null>(null)
const wsPreview = ref<{ kind: 'text'; content: string; truncated: boolean } | { kind: 'image' | 'pdf'; url: string } | { kind: 'docx' } | null>(null)
const docPreview = ref<{ item: WorkspaceItem; url: string } | null>(null)
let wsTimer: ReturnType<typeof setTimeout> | null = null
const uploadInput = ref<HTMLInputElement | null>(null)
const ingestOpen = ref(false)
const ingestFile = ref('')
const ingestName = ref('')
const ingestData = ref<IngestRecognizeResult | null>(null)
const ingestIndex = ref(0)
const ingestComponent = ref('')
const ingestSheetKey = ref('')
const ingestParams = ref<Record<string, unknown>>({})
const ingestAppend = ref(false)
const ingestLoading = ref(false)
const ingestBusy = ref(false)
const ingestError = ref('')
const ingestResult = ref<IngestImportResult | null>(null)
const scanOpen = ref(false)
const scanFile = ref('')
const scanName = ref('')
const scanJob = ref<ScanJob | null>(null)
const scanPlan = ref<ScanPlan | null>(null)
const scanItem = ref('')
const scanSheetKey = ref('')
const scanParams = ref<Record<string, unknown>>({})
const scanAppend = ref(false)
const scanLoading = ref(false)
const scanBusy = ref(false)
const scanError = ref('')
const scanResult = ref<ScanCommitResult | null>(null)
const scanDraftReport = ref<{ filepath: string; url: string } | null>(null)
const scanPhase = ref('')
let scanTimer: ReturnType<typeof setInterval> | null = null
let scanPolling = false
let scanStartedAt = 0
const panelMode = ref<'' | 'plugins' | 'automation'>('')
const plugins = ref<Array<{ name: string; version: string; profile: string; kind: string }>>([])
const mcpInfo = ref<{ name: string; tools: number } | null>(null)
const automation = ref<{ project_name?: string; checked_count?: number; filled_count?: number; assessed_count?: number } | null>(null)
const tasks = ref<any[]>([])
const chatJobs = ref<any[]>([])
const queueCount = ref(0)
const usage = ref<{ used: number; size: number } | null>(null)
const expandedThinking = ref<Record<string, boolean>>({})
let taskTimer: ReturnType<typeof setInterval> | null = null
const showAllProjects = ref(false)
const showSessions = ref(false)
const sessionQuery = ref('')
const memoryOpen = ref(false)
const memoryCount = ref(0)
const memoryInfo = ref<any>(null)

const sessionGroups = computed(() => {
  const all = [...sessions.value]
  if (sessionId.value && !all.some(item => item.sessionId === sessionId.value)) {
    all.unshift({
      sessionId: sessionId.value,
      title: activeTitle.value || '新会话',
      project: activeProject.value || projectName.value,
    })
  }
  const groups = new Map<string, Array<{ sessionId: string; title?: string; project?: string; updatedAt?: number; busy?: boolean; queue?: number }>>()
  const query = sessionQuery.value.trim().toLowerCase()
  for (const item of all) {
    if (!showAllProjects.value && item.project && item.project !== activeProject.value) continue
    // 空白会话不进入历史列表（当前会话保留），避免测试/空壳会话堆满工作区
    if (!String(item.title || '').trim() && item.sessionId !== sessionId.value) continue
    if (query) {
      const haystack = [item.title, item.project, item.sessionId].join(' ').toLowerCase()
      if (!haystack.includes(query)) continue
    }
    const key = item.project || activeProject.value || '当前工程'
    const bucket = groups.get(key) || []
    bucket.push(item)
    groups.set(key, bucket)
  }
  return Array.from(groups, ([project, items]) => ({ project, items }))
})

const sessionCount = computed(() => sessionGroups.value.reduce((total, group) => total + group.items.length, 0))

const wsFilters = computed(() => {
  const counts = workspace.value?.counts || {}
  return [
    { key: 'all', label: '全部', count: workspace.value?.total || 0 },
    { key: 'reports', label: '报告', count: counts.reports || 0 },
    { key: 'originals', label: '原始记录', count: counts.originals || 0 },
    { key: 'uploads', label: '附件', count: counts.uploads || 0 },
    { key: 'snapshots', label: '快照', count: counts.snapshots || 0 },
  ]
})

const wsSections = computed(() => {
  const sections = workspace.value?.sections || []
  if (wsFilter.value === 'all') return sections.filter(section => section.items.length)
  return sections.filter(section => section.key === wsFilter.value)
})

const wsVisibleCount = computed(() => wsSections.value.reduce((total, section) => total + section.items.length, 0))
const wsTextPreview = computed(() => (wsPreview.value?.kind === 'text' ? wsPreview.value : null))
const wsImagePreview = computed(() => (wsPreview.value?.kind === 'image' ? wsPreview.value : null))
const wsPdfPreview = computed(() => (wsPreview.value?.kind === 'pdf' ? wsPreview.value : null))

function wsSnapshotText() {
  const project = workspace.value?.project
  if (!project) return '正在读取工程快照'
  if (!project.snapshot_at) return '工程尚未保存快照'
  return (project.snapshot_name || '工程快照') + ' · ' + relativeTime(project.snapshot_at)
}

const ingestCandidate = computed(() => ingestData.value?.candidates?.[ingestIndex.value] || null)
const ingestSpecs = computed(() => {
  const cand = ingestCandidate.value
  return cand && cand.requires_setup ? (cand.param_specs || []) : []
})
const ingestComponents = computed(() => ingestCandidate.value?.components || [])
const ingestHeaders = computed(() => (ingestData.value?.header || []).slice(0, 10))
const ingestPreview = computed(() => (ingestData.value?.preview || []).map(row => row.slice(0, 10)))
const scanTarget = computed(() => scanPlan.value?.targets?.find(t => t.sheet_key === scanSheetKey.value) || null)
const scanNeedParams = computed(() => Boolean(scanPlan.value?.requires_setup && scanTarget.value && !scanTarget.value.exists))
const scanSpecs = computed(() => (scanNeedParams.value ? (scanPlan.value?.param_specs || []) : []))
const scanHeaders = computed(() => (scanJob.value?.result?.columns || []).slice(0, 10))
const scanPreview = computed(() => (scanJob.value?.result?.rows || []).slice(0, 3).map(row => row.slice(0, 10)))
const scanConfidence = computed(() => {
  const value = scanJob.value?.result?.classification?.confidence
  return typeof value === 'number' ? Math.round(value * 100) + '%' : ''
})
const scanWarningLines = computed(() =>
  (scanResult.value?.warnings || []).map((raw) => {
    const text = String(raw)
    try {
      const item = JSON.parse(text)
      if (item && typeof item === 'object') {
        const bits: string[] = []
        if (item['行'] != null) bits.push('第 ' + item['行'] + ' 行')
        if (item['字段']) bits.push(String(item['字段']))
        if (item['值'] != null && String(item['值']) !== '') bits.push('“' + item['值'] + '”')
        if (item['问题']) bits.push(String(item['问题']))
        if (bits.length) return bits.join(' · ')
      }
    } catch {
      // 保留原始文本
    }
    return text
  })
)


type TimelineItem =
  | { kind: 'message'; at: number; message: ChatMessage }
  | { kind: 'tool'; at: number; tool: ToolEvent }

const timeline = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = [
    ...messages.value.map(message => ({ kind: 'message' as const, at: message.at || 0, message })),
    ...tools.value.map(tool => ({ kind: 'tool' as const, at: tool.at || 0, tool })),
  ]
  return items.sort((left, right) => left.at - right.at)
})
const projectName = ref('')
const user = ref('')
const scroller = ref<HTMLElement | null>(null)

const switching = ref(false)

let socket: WebSocket | null = null
let assistantId: string | null = null
let manualClose = false
let disposed = false
let superseded = false
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function scheduleReconnect() {
  if (reconnectTimer || disposed || manualClose || superseded) return
  connecting.value = true
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (!disposed && !manualClose && !superseded) connect()
  }, 1500)
}

const presets = [
  { label: '工程体检', text: '读取当前工程，列出已勾选的检测项目、每个项目的行数与评定状态，并指出缺什么。' },
  { label: '录入数据', text: '把这份原始记录导入当前工程：<粘贴文件路径或表格>。按表头匹配工作表，导入后重算并告诉我结果。' },
  { label: '生成报告', text: '按当前工程生成检测报告，使用默认模板；返回 filepath 和 preview_url。' },
  { label: '预览报告', text: '预览刚生成的报告，给出可点击的 preview_url（前面拼 http://127.0.0.1:8765）。' },
]

const canSend = computed(() => connected.value && draft.value.trim().length > 0)
const runState = computed(() => {
  if (!connected.value) return connecting.value ? '连接中…' : '已断开'
  if (busy.value) return queueCount.value ? '后台执行 · 待执行 ' + queueCount.value : '后台执行中'
  return '已连接'
})

function wsUrl() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams({ resume: '1' })
  if (sessionId.value) params.set('session', sessionId.value)
  return protocol + '//' + location.host + '/api/chat/ws?' + params.toString()
}

function storageKey(id: string) {
  return 'chat:msgs:' + id
}

function saveTitles() {
  localStorage.setItem('chat:titles', JSON.stringify(titles.value))
}

function persist() {
  if (!sessionId.value) return
  try {
    localStorage.setItem(storageKey(sessionId.value), JSON.stringify(messages.value))
    saveTitles()
  } catch {
    /* 本地存储满时忽略 */
  }
}

function loadTranscript(id: string, history?: any) {
  if (history && Array.isArray(history.messages)) {
    messages.value = history.messages
      .filter((item: any) => item && (item.role === 'user' || item.role === 'assistant'))
      .map((item: any, index: number) => ({
        id: String(item.id || id + '-' + index),
        role: item.role as 'user' | 'assistant',
        text: String(item.text || ''),
        thinking: item.thinking ? String(item.thinking) : undefined,
        streaming: false,
        error: Boolean(item.error),
        at: Number(item.at || 0) * (Number(item.at || 0) < 1e12 ? 1000 : 1),
      }))
    tools.value = Array.isArray(history.tools) ? history.tools : []
    plan.value = Array.isArray(history.plan) ? history.plan : []
    if (history.title) activeTitle.value = history.title
  } else {
    try {
      const raw = localStorage.getItem(storageKey(id))
      messages.value = raw ? JSON.parse(raw) : []
    } catch {
      messages.value = []
    }
  }
  reportCard.value = null
  const last = [...messages.value].reverse().find(item => item.role === 'assistant')
  if (last?.text) scanReport(last.text)
  scrollToBottom()
}

function applySnapshot(payload: any) {
  switching.value = false
  sessionId.value = payload.sessionId || ''
  activeTitle.value = payload.title || ''
  user.value = payload.user || ''
  applyConfig(payload.configOptions || [])
  loadTranscript(sessionId.value, payload.history)
  memoryCount.value = Number(payload.memoryCount || 0)
  queueCount.value = Math.max(0, Number(payload.queue || 0))
  busy.value = Boolean(payload.busy)
  const snapUsage = payload.usage || {}
  usage.value = Number(snapUsage.size || 0) > 0
    ? { used: Number(snapUsage.used || 0), size: Number(snapUsage.size || 0) }
    : null
  assistantId = payload.assistantId ? String(payload.assistantId) : null
  if (busy.value && assistantId) {
    const current = messages.value.find(item => item.id === assistantId)
    if (current) current.streaming = true
  }
}

async function openMemory() {
  memoryOpen.value = true
  try {
    const response = await fetch('/api/chat/memory', { credentials: 'same-origin' })
    const payload = await response.json()
    memoryInfo.value = payload?.data || null
    memoryCount.value = Number(memoryInfo.value?.count || 0)
  } catch {
    ElMessage.warning('读取工程记忆失败')
  }
}

function titleOf(id: string) {
  return titles.value[id] || ('会话 ' + id.slice(0, 6))
}

function relativeTime(value?: number) {
  if (!value) return ''
  const ms = value > 1e12 ? value : value * 1000
  const diff = Math.max(0, Date.now() - ms)
  const minute = 60_000
  const hour = 60 * minute
  if (diff < minute) return '刚刚'
  if (diff < hour) return Math.floor(diff / minute) + ' 分钟前'
  if (diff < 24 * hour) return Math.floor(diff / hour) + ' 小时前'
  const date = new Date(ms)
  const now = new Date()
  if (date.getFullYear() === now.getFullYear()) {
    return (date.getMonth() + 1) + '月' + date.getDate() + '日'
  }
  return date.getFullYear() + '年' + (date.getMonth() + 1) + '月' + date.getDate() + '日'
}

function rememberTitle(text: string) {
  if (!sessionId.value || titles.value[sessionId.value]) return
  titles.value[sessionId.value] = text.slice(0, 18)
  saveTitles()
}

function resumeSession(id: string) {
  if (!id) return
  if (id === sessionId.value) {
    showSessions.value = false
    return
  }
  if (!socket || socket.readyState !== WebSocket.OPEN) return
  if (switching.value) return
  switching.value = true
  socket.send(JSON.stringify({ type: 'resume', sessionId: id }))
  showSessions.value = false
}

function renameSession(target: { sessionId: string; title?: string }) {
  ElMessageBox.prompt('会话名称', '重命名会话', {
    inputValue: target.title || titleOf(target.sessionId),
    confirmButtonText: '保存',
    cancelButtonText: '取消',
  })
    .then(({ value }) => {
      const title = String(value || '').trim()
      if (!title) return
      if (target.sessionId === sessionId.value) activeTitle.value = title
      titles.value[target.sessionId] = title
      socket?.send(JSON.stringify({ type: 'rename_session', sessionId: target.sessionId, title }))
    })
    .catch(() => undefined)
}

function deleteSession(target: { sessionId: string; title?: string }) {
  ElMessageBox.confirm('删除后不再出现在会话列表（不会删除磁盘上的会话文件）。', '删除会话', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => {
      socket?.send(JSON.stringify({ type: 'delete_session', sessionId: target.sessionId }))
    })
    .catch(() => undefined)
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderMarkdown(source: string): string {
  const blocks: string[] = []
  let text = source.replace(/```([\w-]*)\n?([\s\S]*?)```/g, (_match, _lang, body) => {
    blocks.push('<pre class="md-code"><code>' + escapeHtml(body) + '</code></pre>')
    return '\u0000' + (blocks.length - 1) + '\u0000'
  })
  text = escapeHtml(text)
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  text = text.replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, '<img alt="$1" src="$2" loading="lazy" />')
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  const lines = text.split('\n')
  const out: string[] = []
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const next = lines[index + 1] || ''
    if (line.includes('|') && /^\s*\|?\s*:?-{2,}/.test(next)) {
      const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
      const headers = cells(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].includes('|')) {
        rows.push(cells(lines[index]))
        index += 1
      }
      index -= 1
      out.push(
        '<table class="md-table"><thead><tr>' +
          headers.map(cell => '<th>' + cell + '</th>').join('') +
          '</tr></thead><tbody>' +
          rows.map(row => '<tr>' + row.map(cell => '<td>' + cell + '</td>').join('') + '</tr>').join('') +
          '</tbody></table>',
      )
      continue
    }
    const heading = line.match(/^(#{1,3})\s+(.*)$/)
    if (heading) {
      const level = heading[1].length + 2
      out.push('<h' + level + '>' + heading[2] + '</h' + level + '>')
      continue
    }
    if (/^\s*[-*]\s+/.test(line)) {
      out.push('<div class="md-li">• ' + line.replace(/^\s*[-*]\s+/, '') + '</div>')
      continue
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      out.push('<div class="md-li">' + line + '</div>')
      continue
    }
    out.push(line)
  }
  text = out.join('\n').replace(/\n/g, '<br>')
  return text.replace(/\u0000(\d+)\u0000/g, (_m, index) => blocks[Number(index)] || '')
}

function answerPermission(id: string, allow: boolean) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'permission_response', id, allow }))
  }
}

function reportHref(path: string) {
  if (/^https?:\/\//.test(path)) return path
  return location.origin + (path.startsWith('/') ? path : '/' + path)
}

function scanReport(text: string) {
  if (!text) return
  const preview = text.match(/\/api\/report\/preview\?filepath=[^\s"'<>)]+/)
  const download = text.match(/\/api\/report\/download\?filepath=[^\s"'<>)]+/)
  if (!preview && !download) return
  reportCard.value = {
    preview: preview ? reportHref(preview[0]) : '',
    download: download ? reportHref(download[0]) : '',
  }
}

function scrollToBottom() {
  void nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  })
}

function pushMessage(role: 'user' | 'assistant', text: string, extra: Partial<ChatMessage> = {}) {
  const id = Math.random().toString(36).slice(2)
  messages.value.push({ id, role, text, at: Date.now(), ...extra })
  scrollToBottom()
  return id
}

function ensureAssistant(): ChatMessage {
  if (assistantId) {
    const existing = messages.value.find(item => item.id === assistantId)
    if (existing) return existing
  }
  const id = pushMessage('assistant', '', { streaming: true })
  assistantId = id
  return messages.value.find(item => item.id === id) as ChatMessage
}

function modelLabel(value: string): string {
  for (const group of modelConfig.value?.options || []) {
    for (const option of group.options || []) {
      if (option.value === value) return option.name || option.value
    }
  }
  return value
}

// DSH 的模型配置只负责选择；这里仅用于提示/切换图片所需的视觉模型。
const VISION_MODEL_HINTS = ['qwen3.6:35b', 'qwen2.5vl:7b']

function isVisionModel(name: string): boolean {
  const text = String(name || '').toLowerCase()
  return VISION_MODEL_HINTS.some(item => text.includes(item))
}

function applyConfig(options: any[]) {
  const model = (options || []).find(item => item?.category === 'model')
  modelConfig.value = model || null
  modelValue.value = model?.currentValue || ''
  modelName.value = modelLabel(modelValue.value)
}

function changeModel() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return
  socket.send(JSON.stringify({ type: 'set_model', value: modelValue.value }))
}

const ctxPercent = computed(() => {
  const item = usage.value
  if (!item || item.size <= 0) return 0
  return Math.min(100, Math.max(1, Math.round((item.used / item.size) * 100)))
})

function thinkingTitle(message: ChatMessage): string {
  return message.streaming && !message.text ? '思考中…' : '已深度思考'
}

function thinkingOpenState(message: ChatMessage): boolean {
  return expandedThinking.value[message.id]
    ?? Boolean(message.streaming && !message.text)
}

function onThinkingToggle(event: Event, id: string) {
  const open = (event.target as HTMLDetailsElement)?.open
  expandedThinking.value[id] = Boolean(open)
}

function handleUpdate(update: any) {
  const kind = update?.sessionUpdate
  if (kind === 'agent_message_chunk') {
    const text = update?.content?.text
    if (typeof text === 'string') {
      const message = ensureAssistant()
      message.text += text
      scanReport(message.text)
      scrollToBottom()
    }
  } else if (kind === 'agent_thought_chunk') {
    // 思考过程：与正文分开渲染，默认展开、完成后可折叠
    const text = update?.content?.text
    if (typeof text === 'string') {
      const message = ensureAssistant()
      message.thinking = (message.thinking || '') + text
      scrollToBottom()
    }
  } else if (kind === 'usage_update') {
    const used = Number(update.used || 0)
    const size = Number(update.size || 0)
    if (size > 0) usage.value = { used, size }
  } else if (kind === 'config_option_update') {
    // 模型等配置在内核侧变化时同步下拉框状态
    if (Array.isArray(update.configOptions)) applyConfig(update.configOptions)
  } else if (kind === 'tool_call' || kind === 'tool_call_update') {
    const id = String(update.toolCallId || update.id || Math.random())
    let raw = update.rawInput ?? update.rawOutput ?? update.content
    // tool_call_update 的 content 是 [{type:'content',content:{type:'text',...}}]
    if (Array.isArray(raw)) {
      const texts = raw.map((item: any) => item?.content?.text || '').filter(Boolean)
      if (texts.length) raw = texts.join('\n')
    }
    let detail = ''
    if (raw !== undefined && raw !== null) {
      try {
        detail = JSON.stringify(raw, null, 2).slice(0, 4000)
      } catch {
        detail = String(raw)
      }
    }
    const existing = tools.value.find(item => item.id === id)
    if (detail) scanReport(detail)
    if (existing) {
      existing.title = update.title || existing.title
      existing.status = update.status || existing.status
      if (detail) existing.detail = detail
    } else {
      tools.value.push({
        id,
        title: update.title || '工具调用',
        status: update.status || 'pending',
        kind: update.kind,
        detail,
        at: Date.now(),
      })
    }
    scrollToBottom()
  } else if (kind === 'plan') {
    plan.value = Array.isArray(update.entries) ? update.entries : []
  }
}

function connect() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
  connecting.value = true
  const ws = new WebSocket(wsUrl())
  socket = ws
  ws.onopen = () => {
    connected.value = true
    connecting.value = false
  }
  ws.onmessage = event => {
    let payload: any
    try {
      payload = JSON.parse(event.data)
    } catch {
      return
    }
    if (payload.type === 'ready' || payload.type === 'resumed') {
      applySnapshot(payload)
    } else if (payload.type === 'session_title') {
      activeTitle.value = payload.sessionId === sessionId.value ? payload.title : activeTitle.value
      titles.value[payload.sessionId] = payload.title
    } else if (payload.type === 'sessions') {
      sessions.value = Array.isArray(payload.items) ? payload.items : []
    } else if (payload.type === 'permission_request') {
      const tool = payload.params?.toolCall || {}
      let inputSummary = ''
      const input = tool.rawInput ?? tool.input
      if (input !== undefined && input !== null) {
        try {
          inputSummary = JSON.stringify(input, null, 2).slice(0, 1200)
        } catch {
          inputSummary = String(input).slice(0, 1200)
        }
      }
      ElMessageBox.confirm(
        '<div style="text-align:left">'
        + '<div>工具：<b>' + escapeHtml(String(tool.title || tool.toolCallId || '未命名工具')) + '</b></div>'
        + (inputSummary
          ? '<pre style="max-height:180px;overflow:auto;margin-top:8px;font-size:12px;white-space:pre-wrap;">'
            + escapeHtml(inputSummary) + '</pre>'
          : '')
        + '<div style="margin-top:8px">允许本次执行吗？</div></div>',
        '权限确认',
        {
          confirmButtonText: '允许一次',
          cancelButtonText: '拒绝',
          type: 'warning',
          dangerouslyUseHTMLString: true,
        },
      )
        .then(() => answerPermission(payload.id, true))
        .catch(() => answerPermission(payload.id, false))
    } else if (payload.type === 'config') {
      applyConfig(payload.configOptions || [])
    } else if (payload.type === 'update') {
      handleUpdate(payload.params?.update)
    } else if (payload.type === 'permission') {
      ElMessage.info('工具调用已自动授权（本机模式）')
    } else if (payload.type === 'queued') {
      queueCount.value = Math.max(0, Number(payload.queue || 0))
      busy.value = true
    } else if (payload.type === 'queue') {
      queueCount.value = Math.max(0, Number(payload.queue || 0))
      if (payload.busy !== undefined) busy.value = Boolean(payload.busy)
      else if (!queueCount.value) busy.value = false
    } else if (payload.type === 'cancel_notice') {
      pushMessage('assistant', String(payload.text || '已取消'))
      persist()
    } else if (payload.type === 'prompt_start') {
      busy.value = true
      queueCount.value = Math.max(0, Number(payload.queue || 0))
      assistantId = null
    } else if (payload.type === 'prompt_end') {
      queueCount.value = Math.max(0, Number(payload.queue || 0))
      busy.value = queueCount.value > 0
      const current = assistantId ? messages.value.find(item => item.id === assistantId) : null
      if (current) current.streaming = false
      else if (String(payload.stopReason || '') === 'cancelled') pushMessage('assistant', '已停止')
      if (payload.memoryCount !== undefined) memoryCount.value = Number(payload.memoryCount || 0)
      assistantId = null
      persist()
    } else if (payload.type === 'error') {
      const jobError = payload.jobId !== undefined
      if (jobError) {
        queueCount.value = Math.max(0, Number(payload.queue || 0))
        busy.value = queueCount.value > 0
      }
      if (String(payload.message || '').includes('接管') || String(payload.message || '').includes('另一个窗口')) {
        superseded = true
      }
      if (!jobError) {
        switching.value = false
        ElMessage.error(String(payload.message || '对话失败'))
        return
      }
      const target = assistantId ? messages.value.find(item => item.id === assistantId) : null
      if (target) {
        target.error = true
        target.text = target.text || ('对话失败：' + payload.message)
        target.streaming = false
      } else {
        pushMessage('assistant', '对话失败：' + payload.message, { error: true })
      }
      assistantId = null
      persist()
    } else if (payload.type === 'closed') {
      switching.value = false
      const reason = String(payload.reason || '对话进程已结束')
      if (reason.includes('接管') || reason.includes('另一个窗口')) superseded = true
      ElMessage.error(reason)
      connected.value = false
      busy.value = false
      queueCount.value = 0
      try {
        ws.close()
      } catch {
        /* 已关闭 */
      }
    }
  }
  ws.onclose = () => {
    connected.value = false
    connecting.value = false
    switching.value = false
    if (socket === ws) socket = null
    if (!manualClose && !disposed && !superseded) scheduleReconnect()
  }
  ws.onerror = () => {
    connecting.value = false
  }
}

function send(text?: string) {
  const value = (text ?? draft.value).trim()
  if (!value) return
  if (!connected.value || !socket || socket.readyState !== WebSocket.OPEN) {
    ElMessage.warning('对话连接未就绪，请稍后重试')
    return
  }
  if (queueCount.value >= 20) {
    ElMessage.warning('排队任务过多（最多 20 条），请等待当前任务完成')
    return
  }
  pushMessage('user', value)
  rememberTitle(value)
  draft.value = ''
  persist()
  busy.value = true
  queueCount.value = Math.max(1, queueCount.value + 1)
  socket.send(JSON.stringify({ type: 'prompt', text: value }))
}

function stop() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    ElMessage.warning('对话连接未就绪')
    return
  }
  socket.send(JSON.stringify({ type: 'cancel' }))
}

function newSession() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return
  if (switching.value) return
  switching.value = true
  showSessions.value = false
  socket.send(JSON.stringify({ type: 'new_session' }))
}

function go(path: string) {
  void router.push(path)
}

async function onLogout() {
  await logout()
  void router.replace('/login')
}

async function loadProjects() {
  try {
    const [current, list] = await Promise.all([api.currentProject(), api.listProjects()])
    const info: any = current || {}
    projectName.value = String(info.project_name || projectName.value || '未命名工程')
    activeProject.value = projectName.value
    const items: any[] = (list as any)?.items || []
    projects.value = items
      .filter(item => item && item.filepath && item.source !== '自动备份')
      .map(item => ({
        filepath: String(item.filepath),
        project_name: String(item.name || item.project_name || '未命名工程'),
      }))
    if (info.filepath && !projects.value.some(item => item.filepath === info.filepath)) {
      projects.value.unshift({ filepath: String(info.filepath), project_name: projectName.value })
    }
    projectPath.value = String(info.filepath || projects.value[0]?.filepath || '')
    currentProjectPath.value = projectPath.value
  } catch {
    /* 忽略：沿用默认工程名 */
  }
}

async function switchProject() {
  const target = projects.value.find(item => item.filepath === projectPath.value)
  if (!target || target.filepath === currentProjectPath.value) return
  try {
    await ElMessageBox.confirm('切换工程会新建一个会话，当前对话保留在会话列表中。', '切换工程', {
      confirmButtonText: '切换并新建会话',
      cancelButtonText: '取消',
    })
  } catch {
    projectPath.value = currentProjectPath.value
    return
  }
  try {
    await api.activateProject(target.filepath)
    projectName.value = target.project_name
    activeProject.value = target.project_name
    currentProjectPath.value = target.filepath
    ElMessage.success('已切换工程：' + target.project_name)
    await loadProjects()
    newSession()
  } catch (error) {
    ElMessage.error((error as Error).message || '切换工程失败')
    projectPath.value = currentProjectPath.value
  }
}

const createOpen = ref(false)
const createFormRef = ref<FormInstance>()
const createSubmitting = ref(false)
const createForm = reactive({ name: '' })
// Windows 文件名非法字符，工程名会用作目录名
const INVALID_NAME_CHARS = /[\\/:*?"<>|]/

function validateProjectName(_rule: unknown, value: string, callback: (error?: Error) => void) {
  const name = String(value || '').trim()
  if (!name) return callback(new Error('请输入工程名称'))
  if (name.length < 2 || name.length > 60) return callback(new Error('长度需在 2–60 个字符之间'))
  if (INVALID_NAME_CHARS.test(name)) return callback(new Error('不能包含 \\ / : * ? " < > | 等字符'))
  if (projects.value.some(p => p.project_name === name)) return callback(new Error('已存在同名工程，请换一个名称'))
  callback()
}

const createRules: FormRules = {
  name: [
    { required: true, message: '请输入工程名称', trigger: 'blur' },
    { validator: validateProjectName, trigger: 'blur' },
  ],
}

function createProject() {
  createForm.name = ''
  createFormRef.value?.clearValidate()
  createOpen.value = true
}

async function submitCreateProject() {
  const form = createFormRef.value
  if (!form) return
  const valid = await form.validate().catch(() => false)
  if (!valid) return
  const name = createForm.name.trim()
  createSubmitting.value = true
  try {
    await api.newProject(name)
    await loadProjects()
    activeProject.value = name
    projectName.value = name
    newSession()
    createOpen.value = false
    ElMessage.success('已创建工程：' + name)
    wbEntered.value = true
    wbProject.value = name
    void loadWorkspace()
  } catch (error) {
    ElMessage.error('创建工程失败：' + (error instanceof Error ? error.message : String(error)))
  } finally {
    createSubmitting.value = false
  }
}

function formatSize(size: number) {
  if (size > 1024 * 1024) return (size / 1024 / 1024).toFixed(1) + ' MB'
  if (size > 1024) return Math.round(size / 1024) + ' KB'
  return size + ' B'
}

function wsKindLabel(kind: WorkspaceItem['kind']) {
  return ({ report: '报告', original: '原始', upload: '附件', snapshot: '快照' } as Record<string, string>)[kind] || '文件'
}

function queueWorkspaceSearch() {
  if (wsTimer) clearTimeout(wsTimer)
  wsTimer = setTimeout(() => {
    wsTimer = null
    void loadWorkspace()
  }, 250)
}

function setWsFilter(key: string) {
  wsFilter.value = key
  wsSelected.value = null
  wsPreview.value = null
}

async function loadWorkspace() {
  wsLoading.value = true
  try {
    const response = await fetch('/api/workspace/overview?q=' + encodeURIComponent(wsQuery.value.trim()) + '&limit=60', {
      credentials: 'same-origin',
    })
    const body = await response.json()
    if (!body.ok) throw new Error(body.message || '读取工作区失败')
    workspace.value = body.data
    if (wsSelected.value) {
      const all = (workspace.value?.sections || []).flatMap((section: WorkspaceSection) => section.items)
      const fresh = all.find((item: WorkspaceItem) => item.id === wsSelected.value?.id)
      if (fresh) wsSelected.value = fresh
      else {
        wsSelected.value = null
        wsPreview.value = null
      }
    }
  } catch (error) {
    ElMessage.error((error as Error).message || '读取工作区失败')
  } finally {
    wsLoading.value = false
  }
}

function openDocPreview(item: WorkspaceItem) {
  if (!item.exists) {
    ElMessage.warning('文件已不存在，记录仍保留在库中')
    return
  }
  docPreview.value = { item, url: api.reportPreviewUrl(item.filepath) }
}

async function selectWorkspaceItem(item: WorkspaceItem) {
  wsSelected.value = item
  wsPreview.value = null
  if (!item.exists) {
    ElMessage.warning('文件已不存在，记录仍保留在库中')
    return
  }
  if (item.preview === 'docx') {
    openDocPreview(item)
    return
  }
  if (item.preview === 'image' || item.preview === 'pdf') {
    wsPreview.value = {
      kind: item.preview,
      url: '/api/workspace/file?path=' + encodeURIComponent(item.path),
    }
    return
  }
  if (item.preview !== 'text') {
    wsPreview.value = null
    return
  }
  try {
    const response = await fetch('/api/workspace/file?path=' + encodeURIComponent(item.path))
    const body = await response.json()
    if (!body.ok) throw new Error(body.message || '读取文件失败')
    const content = String(body.data.content || '')
    const clipped = content.length > 16000
    wsPreview.value = {
      kind: 'text',
      content: clipped ? content.slice(0, 16000) : content,
      truncated: Boolean(body.data.truncated) || clipped,
    }
  } catch (error) {
    ElMessage.error((error as Error).message || '读取文件失败')
  }
}

function downloadWorkspaceItem(item: WorkspaceItem) {
  if (!item.downloadable) {
    ElMessage.warning('文件已不存在或不在项目目录内')
    return
  }
  window.open('/api/workspace/download?path=' + encodeURIComponent(item.path), '_blank')
}

async function revealWorkspaceItem(item: WorkspaceItem) {
  if (!item.exists) {
    ElMessage.warning('文件已不存在，记录仍保留在库中')
    return
  }
  try {
    await api.revealReport(item.filepath)
    ElMessage.success('已在本机定位文件')
  } catch (error) {
    ElMessage.error((error as Error).message || '定位文件失败')
  }
}

function openPlugins() {
  go('/plugins')
}

async function loadTasks() {
  try {
    const response = await fetch('/api/tasks?limit=6', { credentials: 'same-origin' })
    const body = await response.json()
    if (body.ok) tasks.value = body.data?.items || []
  } catch {
    /* 任务面板不可用时保留旧数据 */
  }
}

async function loadChatJobs() {
  try {
    const response = await fetch('/api/chat/jobs?limit=6', { credentials: 'same-origin' })
    const body = await response.json()
    if (body.ok) chatJobs.value = body.data?.items || []
  } catch {
    /* 后端不可用时保留旧数据 */
  }
}

function chatJobStatusText(status: string) {
  return ({ queued: '排队中', running: '执行中', done: '已完成', failed: '失败', cancelled: '已停止', interrupted: '已中断' } as Record<string, string>)[status] || status
}

function chatJobTitle(job: any) {
  return String(job?.title || job?.prompt || '对话任务').slice(0, 60)
}

async function cancelChatJob(id: string) {
  try {
    const response = await fetch('/api/chat/jobs/' + encodeURIComponent(id) + '/cancel', {
      method: 'POST',
      credentials: 'same-origin',
    })
    const body = await response.json()
    if (!body.ok) throw new Error(body.message || '停止失败')
    ElMessage.info('已提交停止请求')
    await loadChatJobs()
  } catch (error) {
    ElMessage.error((error as Error).message || '停止对话任务失败')
  }
}

function stopTaskTimer() {
  if (taskTimer) {
    clearInterval(taskTimer)
    taskTimer = null
  }
}

async function openAutomation() {
  showSessions.value = false
  workbenchOpen.value = false
  panelMode.value = 'automation'
  stopTaskTimer()
  try {
    automation.value = (await api.getWorkflowStatus()) as any
  } catch {
    automation.value = null
  }
  await Promise.all([loadTasks(), loadChatJobs()])
  if (panelMode.value !== 'automation') return
  stopTaskTimer()
  taskTimer = setInterval(() => {
    void loadTasks()
    void loadChatJobs()
  }, 1500)
}

async function startParallelTasks() {
  try {
    const response = await fetch('/api/tasks/assess', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sheet_keys: [], title: '并行评定已勾选检测项' }),
    })
    const body = await response.json()
    if (!body.ok) throw new Error(body.message || '启动失败')
    ElMessage.success('并行任务已启动，完成后自动写回工程')
    await loadTasks()
  } catch (error) {
    ElMessage.error((error as Error).message || '启动并行任务失败')
  }
}

async function cancelTask(id: string) {
  try {
    const response = await fetch('/api/tasks/' + encodeURIComponent(id) + '/cancel', {
      method: 'POST',
      credentials: 'same-origin',
    })
    const body = await response.json()
    if (!body.ok) throw new Error(body.message || '停止失败')
    ElMessage.info('已提交停止请求')
    await loadTasks()
  } catch (error) {
    ElMessage.error((error as Error).message || '停止任务失败')
  }
}

function taskStatusText(status: string) {
  return ({ running: '运行中', done: '已完成', partial: '部分失败', failed: '失败', cancelled: '已停止', interrupted: '已中断' } as Record<string, string>)[status] || status
}

function taskFailedItems(task: any) {
  return (task.items || []).filter((item: any) => item.status === 'failed' && item.message)
}

function taskItemName(item: any) {
  if (!item) return '检测项'
  if (item.component) return `${item.base}（${item.component}）`
  return item.base || item.key || '检测项'
}

function openChat() {
  showSessions.value = false
  workbenchOpen.value = false
}

function openWorkbench() {
  stopTaskTimer()
  workbenchOpen.value = true
  showSessions.value = false
  panelMode.value = ''
  docPreview.value = null
  void loadProjects()
  if (wbEntered.value) void loadWorkspace()
}

/** 进入工程：当前工程直接进入；其他工程先切换（切换会新建会话） */
async function enterProject(project: { filepath: string; project_name: string }) {
  const isCurrent = project.project_name === activeProject.value
    && project.filepath === currentProjectPath.value
  if (!isCurrent) {
    projectPath.value = project.filepath
    await switchProject()
    if (project.filepath !== currentProjectPath.value) return // 用户取消或切换失败
  }
  wbProject.value = project.project_name
  wbEntered.value = true
  wsFilter.value = 'all'
  wsQuery.value = ''
  wsSelected.value = null
  wsPreview.value = null
  void loadWorkspace()
}

function backToProjects() {
  wbEntered.value = false
  wbProject.value = ''
}

function wbNewSession() {
  workbenchOpen.value = false
  newSession()
}

function wbOpenSession(id: string) {
  workbenchOpen.value = false
  if (id !== sessionId.value) resumeSession(id)
}

/** 工作台内展示已进入工程的会话（含当前未命名会话） */
const wbSessions = computed(() => {
  const target = wbProject.value || activeProject.value
  const all = [...sessions.value]
  if (sessionId.value && !all.some(item => item.sessionId === sessionId.value)) {
    all.unshift({
      sessionId: sessionId.value,
      title: activeTitle.value || '新会话',
      project: activeProject.value,
    })
  }
  return all.filter(item => !item.project || item.project === target)
})

function closePanel() {
  stopTaskTimer()
  panelMode.value = ''
  docPreview.value = null
}

function closeIngest() {
  if (ingestBusy.value) return
  ingestOpen.value = false
  ingestData.value = null
  ingestResult.value = null
  ingestError.value = ''
}

function ingestCandidateLabel(candidate: any) {
  const target = candidate.component ? '（' + candidate.component + '）' : ''
  return candidate.item + target + ' · 匹配 ' + candidate.matched + '/' + candidate.total_columns
}

function applyIngestCandidate(index: number) {
  const candidate = ingestData.value?.candidates?.[index]
  if (!candidate) return
  ingestIndex.value = index
  const component = candidate.component_guess || candidate.component || candidate.components?.[0] || ''
  ingestComponent.value = component
  ingestSheetKey.value = component ? candidate.item + '（' + component + '）' : candidate.sheet_key
  const params: Record<string, unknown> = {}
  for (const spec of candidate.param_specs || []) {
    if (spec.default !== undefined && spec.default !== null) params[spec.key] = spec.default
  }
  ingestParams.value = params
}

function onIngestCandidateChange() {
  applyIngestCandidate(ingestIndex.value)
}

function paramOptions(spec: any) {
  return (spec.options || []).map((option: any) => {
    if (option && typeof option === 'object') {
      return { label: String(option.label ?? option.value ?? ''), value: option.value ?? option.label }
    }
    return { label: String(option), value: option }
  })
}

function changeIngestComponent() {
  const candidate = ingestCandidate.value
  if (!candidate) return
  ingestSheetKey.value = ingestComponent.value
    ? candidate.item + '（' + ingestComponent.value + '）'
    : candidate.item
}

function normalizedIngestParams() {
  const out: Record<string, unknown> = {}
  for (const spec of ingestSpecs.value) {
    let value = ingestParams.value[spec.key]
    if (value === undefined || value === null || String(value).trim() === '') continue
    if (spec.type === 'int') value = Number.parseInt(String(value), 10)
    else if (spec.type === 'float') value = Number.parseFloat(String(value))
    else if (spec.type === 'bool') value = value === true || value === 'true'
    out[spec.key] = value
  }
  return out
}

async function openIngest(relPath: string, name: string) {
  ingestOpen.value = true
  ingestFile.value = relPath
  ingestName.value = name
  ingestData.value = null
  ingestResult.value = null
  ingestError.value = ''
  ingestLoading.value = true
  try {
    const data = await api.ingestRecognize(relPath)
    ingestData.value = data
    if (data.kind !== 'table') {
      ingestError.value = data.next?.hint || '该文件不是可识别的数据表，请改用扫描识别。'
      return
    }
    if (!data.candidates?.length) {
      ingestError.value = '没有找到匹配的采集工作表。可以确认文件表头，或先在数据采集页建表后再导入。'
      return
    }
    applyIngestCandidate(0)
  } catch (error) {
    ingestError.value = (error as Error).message || '识别失败'
  } finally {
    ingestLoading.value = false
  }
}

async function submitIngest() {
  const sheetKey = ingestSheetKey.value.trim()
  if (!sheetKey) {
    ingestError.value = '请选择或填写要导入的采集工作表'
    return
  }
  for (const spec of ingestSpecs.value) {
    if (!spec.required) continue
    const value = ingestParams.value[spec.key]
    if (value === undefined || value === null || String(value).trim() === '') {
      ingestError.value = '请填写采集参数：' + (spec.label || spec.key)
      return
    }
  }
  ingestBusy.value = true
  ingestError.value = ''
  try {
    const params = normalizedIngestParams()
    if (ingestCandidate.value?.requires_setup) {
      const checked = await api.checkItem(sheetKey, true, params) as any
      if (checked?.requires_setup) {
        throw new Error('采集参数未生效，请补全参数后重试')
      }
    }
    const result = await api.ingestImport({
      filepath: ingestFile.value,
      sheet_key: sheetKey,
      append: ingestAppend.value,
      auto_assess: true,
      params,
    })
    ingestResult.value = result
    const verdict = result.assessment?.conclusion || (result.ready ? '评定通过' : '已导入，评定待补录')
    ElMessage.success('已导入 ' + result.imported + ' 行到 ' + result.sheet_key + '：' + verdict)
    await loadWorkspace()
  } catch (error) {
    ingestError.value = (error as Error).message || '导入失败'
  } finally {
    ingestBusy.value = false
  }
}

function attachIngestOnly() {
  if (!ingestFile.value) return
  draft.value += (draft.value ? '\n' : '') + '[附件] ' + ingestFile.value
  ElMessage.info('已仅作为附件加入输入框，没有写入工程数据')
  closeIngest()
}

function goIngestSheet() {
  go('/project')
  closeIngest()
}


function stopScanTimer() {
  if (scanTimer) {
    clearInterval(scanTimer)
    scanTimer = null
  }
  scanPolling = false
}

function closeScan() {
  if (scanBusy.value) return
  stopScanTimer()
  scanOpen.value = false
  scanJob.value = null
  scanPlan.value = null
  scanResult.value = null
  scanDraftReport.value = null
  scanError.value = ''
  scanPhase.value = ''
  scanLoading.value = false
}

function scanTargetLabel(target: ScanTarget) {
  const parts = [target.component || target.sheet_key]
  if (target.checked) parts.push('已勾选')
  if (target.exists) parts.push('已有 ' + target.rows + ' 行')
  else parts.push('新建')
  return parts.join(' · ')
}

function defaultScanParams() {
  const params: Record<string, unknown> = {}
  for (const spec of scanPlan.value?.param_specs || []) {
    if (spec.default !== undefined && spec.default !== null) params[spec.key] = spec.default
  }
  scanParams.value = params
}

function applyScanTarget(key: string) {
  scanSheetKey.value = key
  const target = scanPlan.value?.targets?.find(t => t.sheet_key === key)
  if (target && !target.exists && scanPlan.value?.requires_setup) defaultScanParams()
}

function onScanTargetChange() {
  applyScanTarget(scanSheetKey.value)
}

async function loadScanPlan(item: string) {
  if (!item) {
    scanError.value = '识别结果里没有检测项目，无法查询采集表'
    scanLoading.value = false
    return
  }
  scanPlan.value = null
  scanSheetKey.value = ''
  scanLoading.value = true
  scanError.value = ''
  scanPhase.value = '正在匹配检测项目与采集表…'
  try {
    const plan = await api.scanTargets(item)
    if (!scanOpen.value) return
    scanPlan.value = plan
    scanItem.value = plan.detection_item
    applyScanTarget(plan.suggested_sheet_key)
    scanPhase.value = ''
  } catch (error) {
    scanError.value = (error as Error).message || '查询检测项目失败'
  } finally {
    scanLoading.value = false
  }
}

function onScanItemChange() {
  void loadScanPlan(scanItem.value)
}

async function pollScan() {
  const job = scanJob.value
  if (!job?.id || scanPolling) return
  if (!scanOpen.value) {
    stopScanTimer()
    return
  }
  scanPolling = true
  try {
    const next = await api.scanJob(job.id)
    if (!scanOpen.value) return
    scanJob.value = next
    if (next.status === 'done') {
      stopScanTimer()
      scanPhase.value = '已识别，正在查询检测项目…'
      const item = next.result?.detection_item || next.detection_item || ''
      await loadScanPlan(item)
      scanLoading.value = false
    } else if (next.status === 'failed' || next.status === 'interrupted') {
      stopScanTimer()
      scanLoading.value = false
      scanPhase.value = ''
      scanError.value = next.error || '识别失败，可改为仅作为附件'
    } else {
      scanPhase.value = '正在 OCR → 识别表格 → 判断检测项目…'
      if (Date.now() - scanStartedAt > 300000) {
        stopScanTimer()
        scanLoading.value = false
        scanError.value = '识别超时，可改为仅作为附件或稍后重试'
      }
    }
  } catch (error) {
    scanLoading.value = false
    scanError.value = (error as Error).message || '读取识别状态失败'
    stopScanTimer()
  } finally {
    scanPolling = false
  }
}

async function startScanUpload(relPath: string, name: string) {
  stopScanTimer()
  scanOpen.value = true
  scanFile.value = relPath
  scanName.value = name
  scanJob.value = null
  scanPlan.value = null
  scanResult.value = null
  scanDraftReport.value = null
  scanError.value = ''
  scanParams.value = {}
  scanSheetKey.value = ''
  scanAppend.value = false
  scanLoading.value = true
  scanBusy.value = false
  scanPhase.value = '正在提交识别作业…'
  scanStartedAt = Date.now()
  try {
    const job = await api.scanSubmit(relPath)
    if (!scanOpen.value) return
    scanJob.value = job
    scanPhase.value = '正在 OCR → 识别表格 → 判断检测项目…'
    scanTimer = setInterval(() => { void pollScan() }, 1500)
    void pollScan()
  } catch (error) {
    scanLoading.value = false
    scanPhase.value = ''
    scanError.value = (error as Error).message || '提交识别作业失败'
  }
}

function normalizedScanParams() {
  const out: Record<string, unknown> = {}
  for (const spec of scanSpecs.value) {
    let value = scanParams.value[spec.key]
    if (value === undefined || value === null || String(value).trim() === '') continue
    if (spec.type === 'int') value = Number.parseInt(String(value), 10)
    else if (spec.type === 'float') value = Number.parseFloat(String(value))
    else if (spec.type === 'bool') value = value === true || value === 'true'
    out[spec.key] = value
  }
  return out
}

async function attachScanOnly() {
  if (scanBusy.value) return
  const path = scanFile.value
  if (!path) return
  let attachment = '[附件] ' + path
  const isImage = /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(scanName.value)
  const isPdf = /\.pdf$/i.test(scanName.value)
  if (isImage || isPdf) {
    try {
      const response = await fetch('/api/scan/ocr-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filepath: path, max_chars: 20000 }),
      })
      const body = await response.json()
      if (body.ok && String(body.data?.text || '').trim()) {
        attachment += '\n\n[图片/扫描件 OCR 文本，已由项目 PaddleOCR 识别，可直接使用]\n' + String(body.data.text).trim()
      }
    } catch {
      // OCR 失败时仍然保留附件
    }
  }
  draft.value += (draft.value ? '\n' : '') + attachment
  ElMessage.info('已仅作为附件加入输入框，没有写入工程数据')
  closeScan()
}

function goScanSheet() {
  go('/project')
  closeScan()
}


async function requestScanReport() {
  scanPhase.value = '正在生成报告草稿…'
  try {
    const report = await api.generateReport({ draft: true })
    if (report.filepath) {
      scanDraftReport.value = {
        filepath: report.filepath,
        url: api.reportPreviewUrl(report.filepath),
      }
      ElMessage.success('报告草稿已生成')
    }
  } catch (error) {
    scanError.value = '数据已写入并评定，但报告生成失败：' + ((error as Error).message || '未知错误')
  }
}

async function generateScanReport() {
  if (scanBusy.value || !scanResult.value) return
  scanBusy.value = true
  scanError.value = ''
  try {
    await requestScanReport()
  } finally {
    scanBusy.value = false
    scanPhase.value = ''
  }
}

async function submitScan(withReport: boolean) {
  const plan = scanPlan.value
  const job = scanJob.value
  if (!plan || !job) {
    scanError.value = '识别结果尚未准备好'
    return
  }
  const sheetKey = scanSheetKey.value.trim()
  if (!sheetKey) {
    scanError.value = '请选择要写入的采集工作表'
    return
  }
  for (const spec of scanSpecs.value) {
    if (!spec.required) continue
    const value = scanParams.value[spec.key]
    if (value === undefined || value === null || String(value).trim() === '') {
      scanError.value = '请填写采集参数：' + (spec.label || spec.key)
      return
    }
  }
  scanBusy.value = true
  scanError.value = ''
  scanResult.value = null
  scanDraftReport.value = null
  try {
    const params = normalizedScanParams()
    const target = scanPlan.value?.targets?.find(t => t.sheet_key === sheetKey)
    if (plan.requires_setup && target && !target.exists) {
      scanPhase.value = '正在建立采集表并写入参数…'
      const checked = await api.checkItem(sheetKey, true, params) as { requires_setup?: boolean }
      if (checked?.requires_setup) throw new Error('采集参数未生效，请补全参数后重试')
    }
    scanPhase.value = '正在写入识别数据并自动评定…'
    const result = await api.scanCommit({
      job_id: job.id,
      sheet_key: sheetKey,
      append: scanAppend.value,
      params,
      auto_assess: true,
    })
    scanResult.value = result
    const verdict = result.assessment?.conclusion || (result.ready ? '评定通过' : '已导入，评定待补录')
    ElMessage.success('已写入 ' + result.imported + ' 行到 ' + result.sheet_key + '：' + verdict)
    await loadWorkspace()
    if (withReport) await requestScanReport()
  } catch (error) {
    scanError.value = (error as Error).message || '写入识别数据失败'
  } finally {
    scanBusy.value = false
    scanPhase.value = ''
  }
}

function openScanReport() {
  const report = scanDraftReport.value
  if (!report) return
  const item: WorkspaceItem = {
    id: 'scan-report',
    kind: 'report',
    name: '本次扫描生成报告.docx',
    path: '',
    filepath: report.filepath,
    size: 0,
    at: Math.floor(Date.now() / 1000),
    exists: true,
    preview: 'docx',
    downloadable: true,
    meta: '本次生成',
    detail: '扫描识别 → 写入采集 → 自动评定',
    where: '',
  }
  closeScan()
  docPreview.value = { item, url: report.url }
}

async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error('读取文件失败'))
      reader.readAsDataURL(file)
    })
    const response = await fetch('/api/workspace/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: file.name, data }),
    })
    const body = await response.json()
    if (!body.ok) throw new Error(body.message || '上传失败')
    const imageFile = String(file.type || '').startsWith('image/') ||
      /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(file.name)
    const tableFile = /\.(xlsx|xlsm|csv|docx|doc)$/i.test(file.name)
    if (tableFile) {
      // 表格/Word 数据表先让用户确认识别结果，再决定是否导入工程。
      await openIngest(body.data.path, file.name)
      return
    }
    const scanUpload = imageFile || /\.pdf$/i.test(file.name)
    if (scanUpload) {
      // 图片/扫描件先走“OCR → 识别表格 → 判断检测项目”链路；
      // 用户确认目标采集表和参数后才会写入工程，未提到的项目不会勾选。
      await startScanUpload(body.data.path, file.name)
      return
    }
    const attachment = '[附件] ' + body.data.path
    ElMessage.success('已上传：' + body.data.path)
    draft.value += (draft.value ? '\n' : '') + attachment
    if (workbenchOpen.value && wbEntered.value) {
      wsFilter.value = 'uploads'
      await loadWorkspace()
    }
  } catch (error) {
    ElMessage.error((error as Error).message || '上传失败')
  }
}

onMounted(async () => {
  try {
    titles.value = JSON.parse(localStorage.getItem('chat:titles') || '{}')
  } catch {
    titles.value = {}
  }
  connect()
  void loadProjects()
})

onBeforeUnmount(() => {
  persist()
  disposed = true
  manualClose = true
  stopTaskTimer()
  stopScanTimer()
  if (wsTimer) clearTimeout(wsTimer)
  if (reconnectTimer) clearTimeout(reconnectTimer)
  socket?.close()
})
</script>

<template>
  <div class="chat-app">
    <aside class="chat-side">
      <div class="side-brand">
        <img src="/brand/logo.svg" alt="" />
        <div>
          <div class="name">工程检测harness</div>
          <div class="sub">数据管理平台</div>
        </div>
      </div>

      <div class="project-switch">
        <label>工程</label>
        <div class="project-row">
          <select v-model="projectPath" @change="switchProject">
            <option v-for="item in projects" :key="item.filepath" :value="item.filepath">{{ item.project_name }}</option>
          </select>
          <button type="button" class="project-new" title="新建工程" @click="createProject">＋</button>
        </div>
      </div>

      <button class="new-session" type="button" @click="newSession">＋ 新建会话</button>

      <nav class="side-nav">
        <button :class="{ active: !workbenchOpen && !showSessions }" type="button" @click="openChat"><el-icon><ChatDotRound /></el-icon>对话</button>
        <button :class="{ active: workbenchOpen }" type="button" @click="openWorkbench"><el-icon><FolderOpened /></el-icon>工作区</button>
        <button type="button" @click="go('/project')"><el-icon><FolderOpened /></el-icon>数据采集</button>
        <button type="button" @click="openPlugins"><el-icon><Collection /></el-icon>插件管理</button>
        <button type="button" @click="openAutomation"><el-icon><Tickets /></el-icon>自动化任务</button>
      </nav>

      <div class="side-sessions">
        <div class="side-sessions-head">
          <span>最近会话</span>
          <span class="side-head-actions">
            <button type="button" class="memory-btn" :title="'本工程长期记忆'" @click="openMemory">记忆 {{ memoryCount }}</button>
            <button type="button" @click="showSessions = true">全部</button>
          </span>
        </div>
        <input v-model="sessionQuery" class="side-search" type="search" placeholder="搜索会话" />
        <label class="side-scope"><input v-model="showAllProjects" type="checkbox" />全部工程</label>
        <div class="side-session-list">
          <div v-if="!sessionGroups.length" class="side-empty">暂无会话</div>
          <div v-for="group in sessionGroups" :key="group.project" class="side-group">
            <div class="side-group-title">{{ group.project }}</div>
            <button
              v-for="item in group.items"
              :key="item.sessionId"
              type="button"
              class="side-session-row"
              :class="{ active: item.sessionId === sessionId }"
              @click="resumeSession(item.sessionId)"
            >
              <span class="side-session-title">
                <span
                  v-if="item.busy"
                  class="side-run-dot"
                  :title="item.queue ? '后台执行中，待执行 ' + item.queue : '后台执行中'"
                ></span>
                <span class="side-session-text">{{ item.title || (item.sessionId === sessionId ? '新会话' : titleOf(item.sessionId)) }}</span>
              </span>
              <span class="side-session-time">{{ relativeTime(item.updatedAt) }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="side-foot">
        <span class="user">{{ user || 'admin' }}</span>
        <button type="button" title="退出登录" @click="onLogout"><el-icon><SwitchButton /></el-icon></button>
      </div>
    </aside>

    <main class="chat-main">
      <header class="chat-top">
        <div v-if="!showSessions && !workbenchOpen" class="top-title">{{ activeTitle || '新会话' }}</div>
        <div v-else class="ws-title">{{ workbenchOpen ? '工程工作台' : '会话记录' }}</div>
        <div v-if="!showSessions && !workbenchOpen" class="tabs">
          <button type="button" :class="{ active: viewMode === 'chat' }" @click="viewMode = 'chat'">对话</button>
          <button type="button" :class="{ active: viewMode === 'trajectory' }" @click="viewMode = 'trajectory'">轨迹</button>
        </div>
        <span class="top-proj">{{ projectName }}</span>
        <span class="spacer" />
        <span
          v-if="usage && !workbenchOpen"
          class="ctx-usage"
          :title="'上下文已用 ' + usage.used + ' / ' + usage.size + ' tokens'"
        >
          <span class="ctx-bar"><i :style="{ width: ctxPercent + '%' }" :class="{ warn: ctxPercent >= 80 }" /></span>
          <span class="ctx-num">上下文 {{ ctxPercent }}%</span>
        </span>
        <span class="conn" :class="{ ok: connected, busy }">{{ runState }}</span>
        <button v-if="!showSessions" type="button" class="top-files" :class="{ active: workbenchOpen }" @click="workbenchOpen ? openChat() : openWorkbench()">
          {{ workbenchOpen ? '返回对话' : '工作台' }}
        </button>
      </header>

      <div class="chat-body">
        <section v-if="showSessions" class="session-workspace">
          <div class="ws-head">
            <div>
              <div class="ws-eyebrow">工作区 · {{ activeProject || projectName }}</div>
              <h2>会话记录</h2>
              <p>选择一个会话继续，或新建会话开始一次新的检测工作。</p>
            </div>
            <button type="button" class="ws-new" @click="newSession">＋ 新建会话</button>
          </div>
          <div class="ws-search">
            <input v-model="sessionQuery" type="search" placeholder="搜索会话标题或会话 ID" />
            <span>{{ sessionCount }} 个会话</span>
          </div>
          <div v-if="!sessionGroups.length" class="ws-empty">
            {{ sessionQuery ? '没有匹配的会话。' : '当前工程还没有会话记录。' }}
          </div>
          <div v-for="group in sessionGroups" :key="group.project" class="ws-group">
            <div class="ws-group-head">
              <span>{{ group.project }}</span>
              <span>{{ group.items.length }} 个会话</span>
            </div>
            <div class="ws-list">
              <div
                v-for="item in group.items"
                :key="item.sessionId"
                class="ws-row"
                :class="{ active: item.sessionId === sessionId }"
                role="button"
                tabindex="0"
                @click="resumeSession(item.sessionId)"
                @keydown.enter="resumeSession(item.sessionId)"
              >
                <span class="ws-dot" :class="{ active: item.sessionId === sessionId }" />
                <span class="ws-row-main">
                  <span class="ws-row-title">{{ item.title || (item.sessionId === sessionId ? '新会话' : titleOf(item.sessionId)) }}</span>
                  <span class="ws-row-meta">会话 {{ item.sessionId.slice(0, 8) }} · {{ item.project || activeProject || projectName }}</span>
                </span>
                <span class="ws-row-time">{{ relativeTime(item.updatedAt) }}</span>
                <span class="ws-row-actions">
                  <button type="button" title="重命名" @click.stop="renameSession(item)">✎</button>
                  <button type="button" title="删除" @click.stop="deleteSession(item)">×</button>
                </span>
              </div>
            </div>
          </div>
        </section>

        <template v-else>
      <section v-if="workbenchOpen" class="workbench">
        <template v-if="!wbEntered">
          <div class="wb-head">
            <div>
              <div class="wb-eyebrow">工程工作台</div>
              <h2>选择工程开始对话</h2>
              <p>进入工程后可继续该工程的会话或新建对话，并查看该工程的报告与原始记录。</p>
            </div>
            <button type="button" class="ws-new" @click="createProject">＋ 新建工程</button>
          </div>
          <div v-if="!projects.length" class="wb-empty">暂无工程，点击右上角「新建工程」创建。</div>
          <div class="wb-project-list">
            <button
              v-for="p in projects"
              :key="p.filepath"
              type="button"
              class="wb-project"
              :class="{ active: p.project_name === activeProject }"
              @click="enterProject(p)"
            >
              <span class="wb-project-name">{{ p.project_name }}</span>
              <span class="wb-project-path" :title="p.filepath">{{ p.filepath }}</span>
              <span v-if="p.project_name === activeProject" class="wb-current">当前</span>
            </button>
          </div>
        </template>
        <template v-else>
          <div class="wb-head">
            <div>
              <button type="button" class="wb-back" @click="backToProjects">← 工程列表</button>
              <h2>{{ wbProject || activeProject || projectName }}</h2>
              <p>点击会话即在该工程内继续对话任务；下方为该工程的报告、原始记录、附件与快照。</p>
            </div>
            <button type="button" class="ws-new" @click="wbNewSession">＋ 新建对话</button>
          </div>

          <div class="wb-block">
            <div class="wb-block-title">该工程的会话 <i>{{ wbSessions.length }}</i></div>
            <div v-if="!wbSessions.length" class="wb-empty">该工程还没有会话，点击右上角「新建对话」开始。</div>
            <div class="wb-session-list">
              <button
                v-for="item in wbSessions"
                :key="item.sessionId"
                type="button"
                class="wb-session"
                :class="{ active: item.sessionId === sessionId }"
                @click="wbOpenSession(item.sessionId)"
              >
                <span v-if="item.busy" class="side-run-dot" title="后台执行中"></span>
                <span class="wb-session-title">{{ item.title || (item.sessionId === sessionId ? '新会话' : titleOf(item.sessionId)) }}</span>
                <span class="wb-session-time">{{ relativeTime(item.updatedAt) }}</span>
                <span class="wb-session-go">{{ item.sessionId === sessionId ? '当前会话' : '继续 →' }}</span>
              </button>
            </div>
          </div>

          <div class="wb-block">
            <div class="wb-block-title">工程产物</div>
            <div class="wb-artifacts">
              <section class="wsp-project">
                <div class="wsp-project-head">
                  <div class="wsp-project-name">
                    <div class="wsp-eyebrow">当前工程</div>
                    <b :title="workspace?.project.name || projectName">{{ workspace?.project.name || projectName }}</b>
                  </div>
                  <button type="button" @click="go('/project')">数据采集</button>
                </div>
                <div class="wsp-stats">
                  <div><b>{{ workspace?.project.checked_count ?? 0 }}</b><span>勾选</span></div>
                  <div><b>{{ workspace?.project.filled_count ?? 0 }}</b><span>已录入</span></div>
                  <div><b>{{ workspace?.project.assessed_count ?? 0 }}</b><span>已评定</span></div>
                  <div><b>{{ workspace?.project.total_rows ?? 0 }}</b><span>数据行</span></div>
                </div>
                <div class="wsp-snapshot"><span class="wsp-dot" />{{ wsSnapshotText() }}</div>
              </section>
              <div class="wsp-search">
                <input v-model="wsQuery" type="search" placeholder="搜索报告、原始记录、附件" @input="queueWorkspaceSearch" />
                <button v-if="wsQuery" type="button" title="清空搜索" @click="wsQuery = ''; loadWorkspace()">×</button>
              </div>
              <div class="wsp-filters">
                <button
                  v-for="filter in wsFilters"
                  :key="filter.key"
                  type="button"
                  :class="{ active: wsFilter === filter.key }"
                  @click="setWsFilter(filter.key)"
                >
                  {{ filter.label }}<i>{{ filter.count }}</i>
                </button>
              </div>
              <div class="wsp-list">
                <div v-if="wsLoading && !workspace" class="wsp-empty">正在整理工程产物…</div>
                <template v-for="section in wsSections" :key="section.key">
                  <div v-if="wsFilter === 'all'" class="wsp-group">
                    <span>{{ section.title }}</span>
                    <b>{{ section.total }}</b>
                  </div>
                  <button
                    v-for="item in section.items"
                    :key="item.id"
                    type="button"
                    class="wsp-row"
                    :class="{ active: wsSelected?.id === item.id, missing: !item.exists }"
                    @click="selectWorkspaceItem(item)"
                  >
                    <span class="wsp-kind" :class="item.kind">{{ wsKindLabel(item.kind) }}</span>
                    <span class="wsp-row-main">
                      <span class="wsp-row-name" :title="item.name">{{ item.name }}</span>
                      <span class="wsp-row-meta">{{ item.meta }}<template v-if="item.where"> · {{ item.where }}</template><template v-if="item.at"> · {{ relativeTime(item.at) }}</template></span>
                    </span>
                    <span class="wsp-row-size">{{ item.exists ? formatSize(item.size) : '缺失' }}</span>
                  </button>
                </template>
                <div v-if="!wsLoading && !wsVisibleCount" class="wsp-empty">
                  {{ wsQuery ? '没有匹配的工程文件。' : '当前工程还没有报告、原始记录或附件。' }}
                </div>
              </div>
              <div v-if="wsSelected" class="wsp-preview">
                <div class="wsp-preview-head">
                  <div>
                    <b :title="wsSelected.name">{{ wsSelected.name }}</b>
                    <span>{{ wsSelected.detail }}</span>
                  </div>
                  <button type="button" title="关闭详情" @click="wsSelected = null; wsPreview = null">×</button>
                </div>
                <div class="wsp-actions">
                  <button v-if="wsSelected.preview === 'docx'" type="button" @click="openDocPreview(wsSelected)">在线预览</button>
                  <button v-if="wsSelected.downloadable" type="button" @click="downloadWorkspaceItem(wsSelected)">下载</button>
                  <button v-if="wsSelected.exists" type="button" @click="revealWorkspaceItem(wsSelected)">定位</button>
                </div>
                <pre v-if="wsTextPreview" class="wsp-text">{{ wsTextPreview.content }}<span v-if="wsTextPreview.truncated" class="wsp-truncated">… 内容较长，已截断</span></pre>
                <img v-else-if="wsImagePreview" class="wsp-image" :src="wsImagePreview.url" alt="" />
                <iframe v-else-if="wsPdfPreview" :src="wsPdfPreview.url" title="PDF 预览" class="wsp-pdf" />
                <div v-else-if="wsSelected.preview === 'docx'" class="wsp-doc">
                  <span class="wsp-doc-badge">DOCX</span>
                  <div>Word 文档<br /><i>在线预览会调用本机 Word 转 PDF</i></div>
                  <button type="button" @click="openDocPreview(wsSelected)">预览</button>
                </div>
                <div v-else-if="!wsSelected.exists" class="wsp-missing">文件已不存在，记录仍保留在库中。</div>
                <div v-else class="wsp-binary">此格式暂不支持面板内预览，可下载或定位文件。</div>
              </div>
              <div class="wsp-foot">
                <button type="button" @click="uploadInput?.click()">上传附件</button>
                <span>仅显示当前工程产物，不遍历源码目录</span>
              </div>
            </div>
          </div>
        </template>
      </section>

      <section ref="scroller" class="messages" v-show="viewMode === 'chat' && !workbenchOpen">
        <div v-if="messages.length === 0" class="empty">
          <img src="/brand/logo.svg" alt="" />
          <h2>描述你要完成的检测工作</h2>
          <p>对话会识别意图，自动加载检测项、录入数据、评定并生成报告。</p>
          <div class="presets">
            <button v-for="item in presets" :key="item.label" type="button" @click="send(item.text)">
              {{ item.label }}
            </button>
          </div>
        </div>

        <div v-for="message in messages" :key="message.id" class="msg" :class="message.role">
          <div class="avatar" v-if="message.role === 'assistant'">AI</div>
          <div class="bubble" :class="{ error: message.error }">
            <details
              v-if="message.thinking"
              class="thinking"
              :class="{ live: message.streaming && !message.text }"
              :open="thinkingOpenState(message)"
              @toggle="onThinkingToggle($event, message.id)"
            >
              <summary>{{ thinkingTitle(message) }}</summary>
              <div class="thinking-body">{{ message.thinking }}</div>
            </details>
            <div
              v-if="message.text && message.role === 'assistant' && !message.error"
              class="md"
              v-html="renderMarkdown(message.text)"
            />
            <pre v-else-if="message.text">{{ message.text }}</pre>
            <span v-if="message.streaming" class="typing">▍</span>
          </div>
        </div>

        <div v-if="tools.length" class="tools">
          <div v-for="tool in tools" :key="tool.id" class="tool">
            <span class="tool-status" :class="tool.status">{{ tool.status }}</span>
            <span class="tool-title">{{ tool.title }}</span>
            <details v-if="tool.detail" class="tool-detail">
              <summary>详情</summary>
              <pre>{{ tool.detail }}</pre>
            </details>
          </div>
        </div>

        <div v-if="plan.length" class="plan">
          <div class="plan-title">执行计划</div>
          <div v-for="(entry, index) in plan" :key="index" class="plan-row">
            <span class="plan-status">{{ entry.status || 'pending' }}</span>
            <span>{{ entry.content }}</span>
          </div>
        </div>
      </section>

      <section v-show="viewMode === 'trajectory' && !workbenchOpen" class="trajectory">
        <div v-if="timeline.length === 0" class="traj-empty">暂无轨迹</div>
        <div v-for="(item, index) in timeline" :key="index" class="traj-item">
          <template v-if="item.kind === 'message'">
            <span class="traj-badge" :class="item.message.role">{{ item.message.role === 'user' ? '你' : 'AI' }}</span>
            <div class="traj-text">{{ item.message.text }}</div>
          </template>
          <template v-else>
            <span class="traj-badge tool">工具</span>
            <div class="traj-text">{{ item.tool.title }} · {{ item.tool.status }}</div>
          </template>
        </div>
      </section>

      <aside v-if="panelMode" class="files">
        <header class="files-head">
          <span class="files-title">{{ panelMode === 'plugins' ? '插件' : '自动化任务' }}</span>
          <span class="files-head-spacer" />
          <button type="button" class="panel-close" title="关闭" @click="closePanel">×</button>
        </header>

        <div v-if="panelMode === 'plugins'" class="panel-body">
          <div class="panel-note">DSH 插件 / bundle（只读）</div>
          <div v-for="item in plugins" :key="item.profile + item.name" class="plugin-row">
            <span class="plugin-name">{{ item.name }}</span>
            <span class="plugin-ver">{{ item.version }}</span>
            <span class="plugin-kind">{{ item.profile }} · {{ item.kind }}</span>
          </div>
          <div v-if="mcpInfo" class="mcp-row">MCP {{ mcpInfo.name }} · {{ mcpInfo.tools }} 个工具</div>
        </div>

        <div v-else-if="panelMode === 'automation'" class="panel-body">
          <div class="panel-note">当前工程检测流程</div>
          <div class="auto-row"><span>工程</span><b>{{ automation?.project_name || projectName }}</b></div>
          <div class="auto-row"><span>勾选</span><b>{{ automation?.checked_count ?? 0 }} 项</b></div>
          <div class="auto-row"><span>已录入</span><b>{{ automation?.filled_count ?? 0 }} 项</b></div>
          <div class="auto-row"><span>已评定</span><b>{{ automation?.assessed_count ?? 0 }} 项</b></div>
          <button class="panel-link" type="button" @click="go('/workflow')">打开流程总览</button>

          <div class="task-head">
            <span>对话任务</span>
            <span class="task-workers">后台执行 · 可排队</span>
          </div>
          <div class="panel-note small">对话回合在服务端常驻执行，关闭页面或切换工作区不会中断；再次打开会自动续上进度。</div>
          <div v-for="job in chatJobs" :key="job.id" class="task-card chat-job">
            <div class="task-top">
              <b :title="chatJobTitle(job)">{{ chatJobTitle(job) }}</b>
              <span class="task-status" :class="job.status">{{ chatJobStatusText(job.status) }}</span>
            </div>
            <div class="task-meta">
              {{ job.status === 'queued' ? '等待执行' : job.status === 'running' ? '正在执行' : '会话任务' }}
              <span v-if="job.created_at"> · {{ relativeTime(job.created_at) }}</span>
              <span v-if="job.queue"> · 后面还有 {{ job.queue }} 条</span>
            </div>
            <div class="job-prompt" :title="job.prompt">{{ job.prompt }}</div>
            <div v-if="job.assistant" class="job-assistant">{{ job.assistant }}</div>
            <button v-if="job.status === 'queued' || job.status === 'running'" class="task-stop" type="button" @click="cancelChatJob(job.id)">停止</button>
          </div>
          <div v-if="!chatJobs.length" class="panel-empty">暂无对话任务。发送一条消息后，即使关闭页面也会在后台继续执行。</div>

          <div class="task-head">
            <span>并行任务</span>
            <span class="task-workers">受控并发 · 快照隔离</span>
          </div>
          <div class="task-actions">
            <button class="task-start" type="button" :disabled="tasks.some((t) => t.status === 'running')" @click="startParallelTasks">
              并行评定已勾选项
            </button>
            <button class="task-refresh" type="button" @click="openAutomation">刷新</button>
          </div>
          <div class="panel-note small">先对工程做只读快照，各检测项并行评定，全部结束后一次性写回，避免边算边写。</div>

          <div v-for="task in tasks" :key="task.id" class="task-card">
            <div class="task-top">
              <b>{{ task.title || '并行评定' }}</b>
              <span class="task-status" :class="task.status">{{ taskStatusText(task.status) }}</span>
            </div>
            <div class="task-meta">
              {{ task.completed }}/{{ task.total }} 项 · {{ task.workers }} 并行
              <span v-if="task.failed"> · {{ task.failed }} 失败</span>
              <span v-if="task.cancelled"> · {{ task.cancelled }} 取消</span>
            </div>
            <div class="task-bar"><i :style="{ width: Math.round(((task.completed + task.failed) / Math.max(task.total, 1)) * 100) + '%' }" :class="task.status" /></div>
            <div v-for="item in task.items" :key="item.key" class="task-item">
              <span class="task-dot" :class="item.status" />
              <span class="task-item-name" :title="taskItemName(item)">{{ taskItemName(item) }}</span>
              <span class="task-item-state">{{ taskStatusText(item.status) }}</span>
            </div>
            <div v-for="item in taskFailedItems(task)" :key="'err-' + item.key" class="task-error">{{ item.message }}</div>
            <button v-if="task.status === 'running'" class="task-stop" type="button" @click="cancelTask(task.id)">停止（已开始的项会跑完）</button>
          </div>
          <div v-if="!tasks.length" class="panel-empty">暂无并行任务。点击上方按钮，把已勾选检测项一次性并行评定。</div>

          <div class="panel-note small">ACP 会话不暴露 DSH 定时任务；此面板展示工程流程进度。</div>
        </div>
      </aside>
        </template>
      </div>

      <div v-if="reportCard && !showSessions && !workbenchOpen" class="report-card">
        <span class="report-icon">📄</span>
        <span class="report-text">检测报告已生成</span>
        <a v-if="reportCard.preview" :href="reportCard.preview" target="_blank" rel="noopener">预览</a>
        <a v-if="reportCard.download" :href="reportCard.download" target="_blank" rel="noopener">下载</a>
        <button type="button" class="report-close" @click="reportCard = null">×</button>
      </div>

      <footer v-if="!showSessions && !workbenchOpen" class="composer" :class="{ 'with-files': panelMode }">
        <textarea
          v-model="draft"
          rows="2"
          placeholder="描述你的需求，例如：把这份回弹法记录导进来，然后生成报告并预览"
          @keydown.enter.exact.prevent="send()"
        />
        <div class="composer-actions">
          <button class="icon-btn" type="button" title="上传文件" @click="uploadInput?.click()">
            <el-icon><Paperclip /></el-icon>
          </button>
          <input ref="uploadInput" type="file" hidden @change="uploadFile" />
          <span class="ws-chip">{{ projectName }}</span>
          <select v-if="modelConfig" v-model="modelValue" class="model-select" @change="changeModel">
            <optgroup v-for="group in modelConfig.options" :key="group.group" :label="group.group || '模型'">
              <option v-for="option in group.options" :key="option.value" :value="option.value">{{ option.name }}{{ isVisionModel(option.name || option.value) ? ' · 视觉' : '' }}</option>
            </optgroup>
          </select>
          <span v-else-if="modelName" class="top-model">{{ modelName }}</span>
          <span class="spacer" />
          <span class="hint">{{ busy ? (queueCount ? '待执行 ' + queueCount + ' · 可继续发送' : '后台执行中 · 可继续发送') : 'Enter 发送 · Shift+Enter 换行' }}</span>
          <button v-if="busy" class="stop" type="button" @click="stop">停止全部</button>
          <button class="send" type="button" :disabled="!canSend" @click="send()">
            <el-icon><Promotion /></el-icon>
          </button>
        </div>
      </footer>
    </main>

    <div v-if="memoryOpen" class="memory-mask" @click.self="memoryOpen = false">
      <div class="memory-panel">
        <div class="memory-head">
          <div>
            <b>工程长期记忆</b>
            <span>{{ memoryInfo?.project || projectName }}</span>
          </div>
          <button type="button" @click="memoryOpen = false">×</button>
        </div>
        <div v-if="memoryInfo?.snapshot" class="memory-stats">
          <span>已勾选 <b>{{ memoryInfo.snapshot.checked || 0 }}</b></span>
          <span>已录入 <b>{{ memoryInfo.snapshot.filled || 0 }}</b></span>
          <span>已评定 <b>{{ memoryInfo.snapshot.assessed || 0 }}</b></span>
          <span>数据 <b>{{ memoryInfo.snapshot.rows || 0 }}</b> 行</span>
        </div>
        <div v-if="memoryInfo?.reports?.length" class="memory-section">
          <div class="memory-label">最近报告</div>
          <div v-for="item in memoryInfo.reports" :key="item" class="memory-path">{{ item }}</div>
        </div>
        <div v-if="memoryInfo?.summaries?.length" class="memory-section">
          <div class="memory-label">最近工作</div>
          <div v-for="item in memoryInfo.summaries" :key="item.sessionId" class="memory-row">
            <div class="memory-row-title">{{ item.title || '未命名会话' }}</div>
            <div class="memory-row-text">{{ item.user }}<template v-if="item.summary"> → {{ item.summary }}</template></div>
          </div>
        </div>
        <div v-else class="memory-empty">还没有历史记忆。完成一次对话后，任务摘要和报告路径会自动记入本工程。</div>
        <div class="memory-foot">新会话首轮会自动带上这些背景；已恢复的会话不会重复注入。</div>
      </div>
    </div>

    <div v-if="ingestOpen" class="ingest-mask" @click.self="closeIngest">
      <div class="ingest-panel">
        <header class="ingest-head">
          <div class="ingest-title">
            <b :title="ingestName">{{ ingestName }}</b>
            <span>确认识别结果后再写入工程</span>
          </div>
          <button type="button" title="关闭" :disabled="ingestBusy" @click="closeIngest">×</button>
        </header>

        <div v-if="ingestLoading" class="ingest-state">正在识别表头与检测项目…</div>
        <div v-else-if="ingestError && !ingestData" class="ingest-state error">{{ ingestError }}</div>

        <div v-else-if="ingestResult" class="ingest-result">
          <div class="ingest-ok">已导入 {{ ingestResult.imported }} 行</div>
          <div class="ingest-kv"><span>采集工作表</span><b>{{ ingestResult.sheet_key }}</b></div>
          <div class="ingest-kv"><span>当前行数</span><b>{{ ingestResult.rows }}</b></div>
          <div class="ingest-kv"><span>匹配列</span><b>{{ ingestResult.matched_columns }}</b></div>
          <div class="ingest-kv"><span>评定</span><b :class="ingestResult.ready ? 'good' : 'warn'">
            {{ ingestResult.assessment?.conclusion || (ingestResult.ready ? '通过' : '待补录') }}
          </b></div>
          <div v-if="ingestResult.assessment?.errors?.length" class="ingest-note error">
            <div v-for="item in ingestResult.assessment.errors" :key="item">· {{ item }}</div>
          </div>
          <div v-if="ingestResult.assessment?.warnings?.length" class="ingest-note warn">
            <div v-for="item in ingestResult.assessment.warnings" :key="item">· {{ item }}</div>
          </div>
          <div v-if="ingestResult.warnings?.length" class="ingest-note">
            <div v-for="item in ingestResult.warnings" :key="item">· {{ item }}</div>
          </div>
          <div class="ingest-result-actions">
            <button type="button" class="primary" @click="goIngestSheet">去采集页逐格校正</button>
            <button type="button" @click="closeIngest">完成</button>
          </div>
        </div>

        <div v-else-if="ingestData" class="ingest-body">
          <div class="ingest-filemeta">
            <span>{{ ingestData.format }} · {{ ingestData.table?.rows || 0 }} 行 · {{ ingestData.table?.columns || 0 }} 列</span>
            <span v-if="ingestData.assessment_family">识别族：{{ ingestData.assessment_family }}</span>
          </div>
          <div v-if="ingestData.warnings?.length" class="ingest-note warn">
            <div v-for="item in ingestData.warnings" :key="item">· {{ item }}</div>
          </div>

          <label class="ingest-label">识别为检测项目</label>
          <select v-model.number="ingestIndex" class="ingest-input" @change="onIngestCandidateChange">
            <option v-for="(candidate, index) in ingestData.candidates" :key="candidate.sheet_key + index" :value="index">
              {{ ingestCandidateLabel(candidate) }}
            </option>
          </select>

          <label v-if="ingestComponents.length" class="ingest-label">构件</label>
          <select v-if="ingestComponents.length" v-model="ingestComponent" class="ingest-input" @change="changeIngestComponent">
            <option v-for="component in ingestComponents" :key="component" :value="component">{{ component }}</option>
          </select>

          <label class="ingest-label">写入采集工作表</label>
          <input v-model="ingestSheetKey" class="ingest-input" placeholder="例如：钻芯法检测（梁）" />

          <template v-if="ingestSpecs.length">
            <div class="ingest-section-title">先补充采集参数，再导入</div>
            <div class="ingest-params">
              <div v-for="spec in ingestSpecs" :key="spec.key" class="ingest-field">
                <label>{{ spec.label || spec.key }}<i v-if="spec.required">*</i></label>
                <select v-if="spec.type === 'enum'" v-model="ingestParams[spec.key]" class="ingest-input">
                  <option v-for="option in paramOptions(spec)" :key="String(option.value)" :value="option.value">{{ option.label }}</option>
                </select>
                <select v-else-if="spec.type === 'bool'" v-model="ingestParams[spec.key]" class="ingest-input">
                  <option :value="true">是</option>
                  <option :value="false">否</option>
                </select>
                <input v-else v-model="ingestParams[spec.key]" class="ingest-input"
                  :type="(spec.type === 'int' || spec.type === 'float') ? 'number' : 'text'"
                  :step="spec.type === 'float' ? 'any' : undefined"
                  :placeholder="spec.note || ''" />
              </div>
            </div>
          </template>

          <div class="ingest-section-title">表头与样例行</div>
          <div class="ingest-table-wrap">
            <table class="ingest-table">
              <thead>
                <tr><th v-for="(header, index) in ingestHeaders" :key="index">{{ header || '（空列）' }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, rowIndex) in ingestPreview" :key="rowIndex">
                  <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="ingest-hint">识别有误时：改选检测项目/构件，或修正上面的工作表名；单元格内容可在导入后到采集页逐格校正。</p>
          <label class="ingest-check">
            <input v-model="ingestAppend" type="checkbox" />
            追加到现有数据（不勾选则覆盖当前表）
          </label>
          <div v-if="ingestError" class="ingest-note error">{{ ingestError }}</div>

          <div class="ingest-actions">
            <button type="button" @click="attachIngestOnly">仅作为附件</button>
            <span class="spacer" />
            <button type="button" :disabled="ingestBusy" @click="closeIngest">取消</button>
            <button type="button" class="primary" :disabled="ingestBusy" @click="submitIngest">
              {{ ingestBusy ? '导入中…' : '导入并自动评定' }}
            </button>
          </div>
        </div>
      </div>
    </div>


    <div v-if="scanOpen" class="ingest-mask" @click.self="closeScan">
      <div class="ingest-panel">
        <header class="ingest-head">
          <div class="ingest-title">
            <b :title="scanName">{{ scanName }}</b>
            <span>OCR → 识别表格 → 确认检测项目 → 写入工程</span>
          </div>
          <button type="button" title="关闭" :disabled="scanBusy" @click="closeScan">×</button>
        </header>

        <div v-if="scanLoading && !scanPlan" class="ingest-state">
          <div>{{ scanPhase || '正在识别图片…' }}</div>
          <div class="ingest-actions">
            <span class="spacer" />
            <button type="button" @click="closeScan">关闭</button>
          </div>
        </div>

        <div v-else-if="scanError && !scanPlan" class="ingest-state error">
          <div>{{ scanError }}</div>
          <div class="ingest-actions">
            <span class="spacer" />
            <button type="button" @click="attachScanOnly">仅作为附件</button>
            <button type="button" @click="closeScan">关闭</button>
          </div>
        </div>

        <div v-else-if="scanResult" class="ingest-result">
          <div class="ingest-ok">已写入 {{ scanResult.imported }} 行</div>
          <div class="ingest-kv"><span>检测项目</span><b>{{ scanPlan?.detection_item }}</b></div>
          <div class="ingest-kv"><span>采集工作表</span><b>{{ scanResult.sheet_key }}</b></div>
          <div class="ingest-kv"><span>当前行数</span><b>{{ scanResult.rows }}</b></div>
          <div class="ingest-kv"><span>匹配列</span><b>{{ scanResult.matched_columns }}</b></div>
          <div class="ingest-kv"><span>评定</span><b :class="scanResult.ready ? 'good' : 'warn'">
            {{ scanResult.assessment?.conclusion || (scanResult.ready ? '通过' : '待补录') }}
          </b></div>
          <div v-if="scanResult.assessment?.errors?.length" class="ingest-note error">
            <div v-for="item in scanResult.assessment.errors" :key="item">· {{ item }}</div>
          </div>
          <div v-if="scanResult.assessment?.warnings?.length" class="ingest-note warn">
            <div v-for="item in scanResult.assessment.warnings" :key="item">· {{ item }}</div>
          </div>
          <div v-if="scanWarningLines.length" class="ingest-note">
            <div v-for="(item, index) in scanWarningLines" :key="index">· {{ item }}</div>
          </div>
          <div v-if="scanDraftReport" class="ingest-note good">报告草稿已生成，可直接查看。</div>
          <div v-if="scanError" class="ingest-note error">{{ scanError }}</div>
          <div class="ingest-result-actions">
            <button v-if="scanDraftReport" type="button" class="primary" @click="openScanReport">查看报告</button>
            <button v-else type="button" :disabled="scanBusy" @click="generateScanReport">
              {{ scanBusy ? '生成中…' : '生成报告草稿' }}
            </button>
            <button type="button" @click="goScanSheet">去采集页逐格校正</button>
            <button type="button" @click="closeScan">完成</button>
          </div>
        </div>

        <div v-else-if="scanPlan" class="ingest-body">
          <div class="ingest-filemeta">
            <span>识别为：{{ scanPlan.detection_item }}<template v-if="scanConfidence"> · 置信度 {{ scanConfidence }}</template></span>
            <span>{{ scanJob?.result?.rows?.length || 0 }} 行 · {{ scanJob?.result?.columns?.length || 0 }} 列</span>
          </div>

          <label class="ingest-label">检测项目</label>
          <select v-model="scanItem" class="ingest-input" @change="onScanItemChange">
            <option v-for="item in scanPlan.candidates" :key="item" :value="item">{{ item }}</option>
          </select>

          <label class="ingest-label">写入采集工作表（只勾选这一项）</label>
          <select v-model="scanSheetKey" class="ingest-input" @change="onScanTargetChange">
            <option v-for="target in scanPlan.targets" :key="target.sheet_key" :value="target.sheet_key">
              {{ scanTargetLabel(target) }}
            </option>
          </select>
          <p v-if="scanPlan.requires_setup && scanTarget?.exists" class="ingest-hint">
            目标表已存在，沿用已有采集参数，不会重建或清空。
          </p>

          <template v-if="scanSpecs.length">
            <div class="ingest-section-title">先补充采集参数，再写入</div>
            <div class="ingest-params">
              <div v-for="spec in scanSpecs" :key="spec.key" class="ingest-field">
                <label>{{ spec.label || spec.key }}<i v-if="spec.required">*</i></label>
                <select v-if="spec.type === 'enum'" v-model="scanParams[spec.key]" class="ingest-input">
                  <option v-for="option in paramOptions(spec)" :key="String(option.value)" :value="option.value">{{ option.label }}</option>
                </select>
                <select v-else-if="spec.type === 'bool'" v-model="scanParams[spec.key]" class="ingest-input">
                  <option :value="true">是</option>
                  <option :value="false">否</option>
                </select>
                <input v-else v-model="scanParams[spec.key]" class="ingest-input"
                  :type="(spec.type === 'int' || spec.type === 'float') ? 'number' : 'text'"
                  :step="spec.type === 'float' ? 'any' : undefined"
                  :placeholder="spec.note || ''" />
              </div>
            </div>
          </template>

          <div class="ingest-section-title">识别出的表头与样例行</div>
          <div class="ingest-table-wrap">
            <table class="ingest-table">
              <thead>
                <tr><th v-for="(header, index) in scanHeaders" :key="index">{{ header || '（空列）' }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, rowIndex) in scanPreview" :key="rowIndex">
                  <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="ingest-hint">
            只勾选本次识别出的检测项目，不会批量勾选未提到的项目。确认后写入采集表、自动评定，并可继续生成报告草稿。
          </p>
          <label class="ingest-check">
            <input v-model="scanAppend" type="checkbox" />
            追加到现有数据（不勾选则覆盖当前表）
          </label>
          <div v-if="scanError" class="ingest-note error">{{ scanError }}</div>

          <div class="ingest-actions">
            <button type="button" :disabled="scanBusy" @click="attachScanOnly">仅作为附件</button>
            <span class="spacer" />
            <button type="button" :disabled="scanBusy" @click="closeScan">取消</button>
            <button type="button" :disabled="scanBusy" @click="submitScan(false)">导入并评定</button>
            <button type="button" class="primary" :disabled="scanBusy" @click="submitScan(true)">
              {{ scanBusy ? (scanPhase || '处理中…') : '导入、评定并生成报告' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="docPreview" class="doc-mask" @click.self="docPreview = null">
      <div class="doc-panel">
        <header class="doc-head">
          <div class="doc-title">
            <b :title="docPreview.item.name">{{ docPreview.item.name }}</b>
            <span>{{ docPreview.item.detail }}</span>
          </div>
          <div class="doc-actions">
            <button v-if="docPreview.item.downloadable" type="button" @click="downloadWorkspaceItem(docPreview.item)">下载</button>
            <button v-if="docPreview.item.exists" type="button" @click="revealWorkspaceItem(docPreview.item)">定位</button>
            <button type="button" title="关闭" @click="docPreview = null">×</button>
          </div>
        </header>
        <iframe :src="docPreview.url" title="Word 文档预览" class="doc-frame" />
        <div class="doc-foot">首次预览会调用本机 Word 转 PDF，需要几秒；关闭后再次打开会复用缓存。</div>
      </div>
    </div>

    <el-dialog v-model="createOpen" title="新建工程" width="440px" :close-on-click-modal="false" @closed="createFormRef?.clearValidate()">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top" @submit.prevent="submitCreateProject">
        <el-form-item label="工程名称" prop="name">
          <el-input
            v-model="createForm.name"
            maxlength="60"
            show-word-limit
            placeholder="例如：xx 项目 1# 楼"
            @keyup.enter="submitCreateProject"
          />
        </el-form-item>
        <div class="create-hint">工程名称将作为数据目录名，创建后可在工作台切换。</div>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :loading="createSubmitting" @click="submitCreateProject">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.chat-app {
  position: fixed;
  inset: 0;
  display: flex;
  background: #f7f9fc;
  color: #1f2937;
}
.chat-side {
  width: 248px;
  flex: none;
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  background: #0e3a5c;
  color: #fff;
}
.side-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 6px 18px;
}
.side-brand img {
  width: 36px;
  height: 36px;
  border-radius: 9px;
}
.side-brand .name {
  font-size: 15px;
  font-weight: 700;
}
.side-brand .sub {
  font-size: 11px;
  opacity: 0.65;
}
.new-session {
  margin: 2px 0 14px;
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  text-align: left;
  font-size: 13px;
  cursor: pointer;
}
.new-session:hover {
  background: rgba(255, 255, 255, 0.16);
}
.side-nav {
  display: grid;
  gap: 2px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.side-nav button {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.side-nav button:hover,
.side-nav button.active {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}
.side-sessions {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-top: 12px;
}
.side-sessions-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
}
.side-sessions-head button {
  border: 0;
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
  font-size: 11px;
  cursor: pointer;
}
.side-search {
  width: 100%;
  box-sizing: border-box;
  margin: 0 0 7px;
  padding: 7px 9px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
  font-size: 12px;
  outline: none;
}
.side-search::placeholder {
  color: rgba(255, 255, 255, 0.45);
}
.side-scope {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px 7px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
}
.side-session-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}
.side-group {
  margin-bottom: 8px;
}
.side-group-title {
  padding: 7px 8px 4px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-session-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.side-session-row:hover {
  background: rgba(255, 255, 255, 0.08);
}
.side-session-row.active {
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}
.side-session-title {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 5px;
}
.side-session-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-run-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.14);
  animation: side-pulse 1.6s ease-in-out infinite;
}
@keyframes side-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.side-session-time {
  flex: none;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
}
.side-empty {
  padding: 12px 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
}
.side-section {
  margin: 16px 8px 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
}
.session-item:hover {
  background: rgba(255, 255, 255, 0.08);
}
.session-item .actions {
  display: none;
  margin-left: auto;
  gap: 2px;
}
.session-item:hover .actions {
  display: inline-flex;
}
.session-item .actions button {
  border: 0;
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 12px;
  padding: 0 3px;
}
.session-item .actions button:hover {
  color: #fff;
}
.session-item.active {
  background: rgba(255, 255, 255, 0.1);
}
.session-item .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #67c23a;
}
.session-item .dot.idle {
  background: #94a3b8;
}
.session-item .title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 8px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}
.side-foot .user {
  flex: 1;
}
.side-foot button {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 16px;
}
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.chat-top {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 22px;
  border-bottom: 1px solid #e6ebf2;
  background: #fff;
}
.top-title {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 700;
  color: #0e3a5c;
}
.top-proj {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #6b7280;
}
.top-model {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef4fb;
  color: #2563a8;
}
.model-select {
  font-size: 12px;
  color: #2563a8;
  border: 1px solid #dbe4ef;
  border-radius: 7px;
  padding: 3px 6px;
  background: #f8fbff;
  max-width: 220px;
}
.spacer {
  flex: 1;
}
.conn {
  font-size: 11px;
  color: #b45309;
}
.conn.ok {
  color: #15803d;
}
.conn.busy {
  color: #0369a1;
}
.ctx-usage {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #64748b;
}
.ctx-bar {
  display: inline-block;
  width: 52px;
  height: 5px;
  border-radius: 999px;
  background: #e6ebf2;
  overflow: hidden;
}
.ctx-bar i {
  display: block;
  height: 100%;
  background: #2563a8;
  border-radius: 999px;
}
.ctx-bar i.warn {
  background: #b45309;
}
.session-workspace {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 28px 34px 40px;
  background: #fff;
}
.workbench {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 28px 34px 40px;
  background: #fff;
}
.wb-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 18px;
  border-bottom: 1px solid #edf1f6;
  margin-bottom: 18px;
}
.wb-head h2 {
  margin: 4px 0 6px;
  font-size: 20px;
  color: #0e3a5c;
}
.wb-head p {
  margin: 0;
  font-size: 12.5px;
  color: #64748b;
}
.wb-eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  color: #94a3b8;
  text-transform: uppercase;
}
.wb-back {
  border: 0;
  background: transparent;
  color: #2563a8;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 0;
}
.wb-back:hover {
  text-decoration: underline;
}
.wb-empty {
  padding: 28px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  border: 1px dashed #dbe4ef;
  border-radius: 12px;
  background: #f8fafc;
}
.wb-project-list,
.wb-session-list {
  display: grid;
  gap: 10px;
}
.wb-project {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  text-align: left;
  padding: 14px 18px;
  border: 1px solid #e6ebf2;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.wb-project:hover,
.wb-project.active {
  border-color: #2563a8;
  box-shadow: 0 4px 14px rgba(37, 99, 168, 0.12);
}
.wb-project-name {
  font-size: 14px;
  font-weight: 700;
  color: #0e3a5c;
}
.wb-project-path {
  flex: 1;
  min-width: 0;
  font-size: 11.5px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-current {
  flex: none;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eaf3fc;
  color: #2563a8;
}
.wb-block {
  margin-bottom: 26px;
}
.wb-block-title {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
  margin: 4px 0 10px;
}
.wb-block-title i {
  font-style: normal;
  color: #94a3b8;
  font-weight: 400;
  margin-left: 4px;
}
.wb-artifacts {
  border: 1px solid #e6ebf2;
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
}
.wb-session {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: left;
  padding: 11px 16px;
  border: 1px solid #e6ebf2;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
}
.wb-session:hover {
  border-color: #2563a8;
}
.wb-session.active {
  border-color: #2563a8;
  background: #f4f9ff;
}
.wb-session-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-session-time {
  flex: none;
  font-size: 11px;
  color: #94a3b8;
}
.wb-session-go {
  flex: none;
  font-size: 11px;
  color: #2563a8;
}
.create-hint {
  margin-top: 2px;
  font-size: 12px;
  color: #94a3b8;
}
.ws-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #edf1f6;
}
.ws-eyebrow {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: #94a3b8;
  margin-bottom: 6px;
}
.ws-head h2 {
  margin: 0 0 6px;
  font-size: 24px;
  color: #0e3a5c;
}
.ws-head p {
  margin: 0;
  font-size: 13px;
  color: #64748b;
}
.ws-new {
  flex: none;
  padding: 9px 14px;
  border: 0;
  border-radius: 8px;
  background: #0e3a5c;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.ws-new:hover {
  background: #164e73;
}
.ws-scope {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #64748b;
  cursor: pointer;
}
.ws-scope input {
  accent-color: #0e3a5c;
}
.ws-group {
  margin-top: 24px;
}
.ws-group-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #64748b;
}
.ws-group-head span:first-child {
  color: #334155;
  font-weight: 600;
}
.ws-search {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
  padding: 0 2px 8px;
}
.ws-search input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  background: #fff;
  color: #1e293b;
  font-size: 12px;
  outline: none;
}
.ws-search input:focus {
  border-color: #9bbdd6;
  box-shadow: 0 0 0 2px rgba(37, 99, 168, 0.08);
}
.ws-search span {
  flex: none;
  font-size: 11px;
  color: #94a3b8;
}
.ws-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 2px;
}
.ws-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  outline: none;
}
.ws-row:hover,
.ws-row:focus-visible {
  background: #f4f8fb;
}
.ws-row.active {
  background: #edf6fc;
}
.ws-dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: #cbd5e1;
}
.ws-dot.active {
  background: #0e3a5c;
}
.ws-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ws-row-title {
  color: #1e293b;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-row-meta {
  color: #94a3b8;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-row-time {
  flex: none;
  min-width: 56px;
  text-align: right;
  font-size: 11px;
  color: #94a3b8;
}
.ws-row-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
}
.ws-row:hover .ws-row-actions,
.ws-row:focus-visible .ws-row-actions {
  opacity: 1;
}
.ws-row-actions button {
  border: 0;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 13px;
}
.ws-row-actions button:hover {
  color: #b91c1c;
}
.ws-empty {
  margin-top: 28px;
  padding: 28px;
  border: 1px dashed #dbe4ef;
  border-radius: 10px;
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
}
.ws-title {
  font-size: 14px;
  font-weight: 600;
  color: #0e3a5c;
}
.messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 0;
}
.empty {
  max-width: 720px;
  margin: 8vh auto 0;
  text-align: center;
  padding: 0 24px;
}
.empty img {
  width: 52px;
  height: 52px;
  border-radius: 13px;
}
.empty h2 {
  margin: 18px 0 8px;
  font-size: 24px;
  color: #0e3a5c;
}
.empty p {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
}
.presets {
  margin-top: 22px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.presets button {
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid #dbe4ef;
  background: #fff;
  color: #334155;
  font-size: 12px;
  cursor: pointer;
}
.presets button:hover {
  border-color: #7aa7c7;
  color: #0e3a5c;
}
.msg {
  display: flex;
  gap: 10px;
  max-width: 900px;
  margin: 0 auto 16px;
  padding: 0 28px;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0e3a5c;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e6ebf2;
  font-size: 13px;
  line-height: 1.75;
}
.msg.user .bubble {
  background: #0e3a5c;
  border-color: #0e3a5c;
  color: #fff;
}
.bubble.error {
  border-color: #fecaca;
  background: #fff7f7;
  color: #b91c1c;
}
.thinking {
  margin-bottom: 6px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 12px;
  overflow: hidden;
}
.thinking summary {
  cursor: pointer;
  user-select: none;
  padding: 6px 10px;
  color: #64748b;
  font-weight: 600;
  list-style: none;
}
.thinking summary::before {
  content: '▸ ';
}
.thinking[open] summary::before {
  content: '▾ ';
}
.thinking.live summary {
  color: #2563a8;
  animation: blink 1.6s infinite;
}
.thinking-body {
  max-height: 260px;
  overflow: auto;
  padding: 0 10px 8px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #64748b;
  line-height: 1.7;
}
.bubble pre {
  margin: 0;
  font: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble :deep(.md) {
  line-height: 1.75;
}
.bubble :deep(.md-code) {
  background: #0f172a;
  color: #e2e8f0;
  padding: 10px 12px;
  border-radius: 8px;
  overflow: auto;
  font-size: 12px;
  margin: 6px 0;
  white-space: pre;
}
.bubble :deep(code) {
  background: #eef2f7;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}
.bubble :deep(.md-li) {
  padding-left: 4px;
}
.bubble :deep(h3),
.bubble :deep(h4),
.bubble :deep(h5) {
  margin: 8px 0 4px;
  font-size: 14px;
}
.bubble :deep(a) {
  color: #2563a8;
}
.bubble :deep(.md-table) {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
  width: 100%;
}
.bubble :deep(.md-table th),
.bubble :deep(.md-table td) {
  border: 1px solid #e2e8f0;
  padding: 6px 8px;
  text-align: left;
}
.bubble :deep(.md-table th) {
  background: #f1f5f9;
}
.bubble :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
.tool-detail {
  width: 100%;
  font-size: 11px;
  color: #64748b;
}
.tool-detail summary {
  cursor: pointer;
}
.tool-detail pre {
  margin: 4px 0 8px;
  padding: 8px 10px;
  border: 1px solid #e6ebf2;
  border-radius: 6px;
  background: #f8fafc;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
}
.typing {
  color: #2563a8;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.tools,
.plan {
  max-width: 900px;
  margin: 0 auto 12px;
  padding: 0 28px;
}
.tool {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #475569;
  padding: 3px 0;
}
.tool-status {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #eef2f7;
  color: #64748b;
}
.tool-status.completed {
  background: #ecfdf3;
  color: #15803d;
}
.tool-status.failed {
  background: #fef2f2;
  color: #b91c1c;
}
.plan {
  border: 1px solid #e6ebf2;
  border-radius: 10px;
  background: #fff;
  padding: 10px 14px;
}
.plan-title {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  margin-bottom: 6px;
}
.plan-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
  color: #334155;
}
.plan-status {
  color: #94a3b8;
  min-width: 64px;
}
.report-card {
  flex: none;
  max-width: 900px;
  width: 100%;
  margin: 0 auto 6px;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #dbe4ef;
  border-radius: 10px;
  background: #fff;
  font-size: 12px;
  color: #334155;
}
.report-icon {
  font-size: 16px;
}
.report-text {
  flex: 1;
  font-weight: 600;
  color: #0e3a5c;
}
.report-card a {
  color: #2563a8;
  text-decoration: none;
  padding: 3px 10px;
  border-radius: 7px;
  background: #eef4fb;
}
.report-card a:hover {
  background: #dbeafe;
}
.report-close {
  border: 0;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 14px;
}
.composer {
  flex: none;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
  padding: 10px 28px 18px;
}
@media (min-width: 861px) {
  .composer.with-files {
    max-width: none;
    width: calc(100% - 320px);
    margin-left: 0;
  }
}
.composer textarea {
  width: 100%;
  resize: none;
  border: 1px solid #dbe4ef;
  border-radius: 12px;
  padding: 12px 14px 34px;
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  background: #fff;
  font-family: inherit;
}
.composer textarea:focus {
  border-color: #7aa7c7;
  box-shadow: 0 0 0 3px rgba(37, 99, 168, 0.08);
}
.composer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: -30px;
  padding: 0 10px 0 14px;
}
.hint {
  flex: 1;
  font-size: 11px;
  color: #94a3b8;
}
.stop {
  border: 1px solid #dbe4ef;
  background: #fff;
  color: #475569;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.send {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 9px;
  background: #0e3a5c;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.send:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
.project-switch {
  margin: 0 6px 10px;
  display: grid;
  gap: 4px;
}
.project-switch label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
}
.project-row {
  display: flex;
  gap: 6px;
}
.project-switch select {
  flex: 1;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 6px 8px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-size: 12px;
}
.project-new {
  width: 30px;
  flex: none;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  cursor: pointer;
  font-size: 14px;
}
.project-switch select option {
  color: #1f2937;
}
.session-group {
  margin: 10px 10px 2px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
  letter-spacing: 0.3px;
}
.tabs {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: 8px;
  background: #f1f5f9;
}
.tabs button {
  border: 0;
  background: transparent;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
}
.tabs button.active {
  background: #fff;
  color: #0e3a5c;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}
.top-files {
  border: 1px solid #dbe4ef;
  background: #fff;
  color: #475569;
  padding: 4px 10px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
}
.top-files.active {
  border-color: #7aa7c7;
  color: #0e3a5c;
  background: #eef4fb;
}
.chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.chat-body .messages {
  flex: 1;
  min-width: 0;
}
.trajectory {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 20px 28px;
  background: #f7f9fc;
}
.traj-empty {
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
  margin-top: 40px;
}
.traj-item {
  display: flex;
  gap: 10px;
  max-width: 900px;
  margin: 0 auto 8px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #e6ebf2;
  border-radius: 10px;
}
.traj-badge {
  flex: none;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 20px;
  background: #eef4fb;
  color: #2563a8;
}
.traj-badge.assistant {
  background: #eef4fb;
}
.traj-badge.tool {
  background: #f1f5f9;
  color: #475569;
}
.traj-text {
  flex: 1;
  font-size: 12px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}
.files {
  width: 320px;
  flex: none;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #e6ebf2;
  background: #fff;
}
.files-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #e6ebf2;
  font-size: 12px;
  font-weight: 600;
  color: #0e3a5c;
}
.files-head-spacer {
  flex: 1;
}
.files-head .ws-refresh,
.files-head .panel-close {
  margin-left: 0;
  border: 1px solid #dbe4ef;
  background: #fff;
  color: #475569;
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 10px;
  line-height: 1.4;
  cursor: pointer;
}
.files-head .ws-refresh:disabled {
  color: #a0aec0;
  cursor: default;
}
.files-head .panel-close {
  width: 24px;
  padding: 2px 0;
  font-size: 16px;
  line-height: 1.2;
  text-align: center;
  color: #94a3b8;
}
.wsp-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wsp-project {
  border: 1px solid #dbe7f3;
  background: linear-gradient(135deg, #f3f8fd, #fff);
  border-radius: 12px;
  padding: 12px;
}
.wsp-project-head {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
}
.wsp-project-name {
  flex: 1;
  min-width: 0;
}
.wsp-project-name b {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.5;
  color: #0e3a5c;
  word-break: break-all;
}
.wsp-eyebrow {
  margin-bottom: 3px;
  font-size: 9px;
  letter-spacing: 0.08em;
  color: #7b93a8;
}
.wsp-project-head button {
  flex: none;
  border: 1px solid #c7d9e8;
  background: #fff;
  color: #0e3a5c;
  border-radius: 7px;
  padding: 5px 8px;
  font-size: 10px;
  cursor: pointer;
}
.wsp-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}
.wsp-stats div {
  min-width: 0;
  padding: 6px 3px;
  border: 1px solid #e6eef7;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  text-align: center;
}
.wsp-stats b {
  display: block;
  font-size: 14px;
  line-height: 1.3;
  color: #0e3a5c;
}
.wsp-stats span {
  display: block;
  overflow: hidden;
  font-size: 9px;
  color: #7b8ea3;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wsp-snapshot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 9px;
  line-height: 1.5;
  color: #64748b;
  word-break: break-word;
}
.wsp-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2f9e6e;
}
.wsp-search {
  position: relative;
}
.wsp-search input {
  box-sizing: border-box;
  width: 100%;
  padding: 8px 28px 8px 10px;
  border: 1px solid #dbe4ef;
  border-radius: 9px;
  background: #f8fafc;
  font-size: 11px;
  color: #1f2937;
  outline: none;
}
.wsp-search input:focus {
  border-color: #7aa7c7;
  background: #fff;
}
.wsp-search button {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  color: #94a3b8;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}
.wsp-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.wsp-filters button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  padding: 4px 8px;
  font-size: 10px;
  color: #64748b;
  cursor: pointer;
}
.wsp-filters button.active {
  border-color: #0e3a5c;
  background: #0e3a5c;
  color: #fff;
}
.wsp-filters i {
  font-style: normal;
  font-size: 9px;
  opacity: 0.75;
}
.wsp-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.wsp-group {
  display: flex;
  justify-content: space-between;
  margin: 8px 2px 3px;
  font-size: 10px;
  color: #7b8ea3;
}
.wsp-group b {
  font-weight: 500;
  color: #94a3b8;
}
.wsp-hidden-note {
  margin: 5px 2px 2px;
  border-radius: 7px;
  background: #f8fafc;
  padding: 6px 8px;
  font-size: 9px;
  line-height: 1.5;
  color: #94a3b8;
}
.wsp-row {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 7px 6px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  font-family: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.wsp-row:hover {
  background: #f4f8fc;
}
.wsp-row.active {
  border-color: #c7dff2;
  background: #eaf3fb;
}
.wsp-row.missing {
  opacity: 0.65;
}
.wsp-kind {
  flex: none;
  width: 30px;
  padding: 2px 0;
  border-radius: 4px;
  background: #eef4fb;
  font-size: 9px;
  color: #2563a8;
  text-align: center;
}
.wsp-kind.report {
  background: #e8f2fd;
  color: #1d4ed8;
}
.wsp-kind.original {
  background: #eaf7ef;
  color: #15803d;
}
.wsp-kind.upload {
  background: #fff4e6;
  color: #b45309;
}
.wsp-kind.snapshot {
  background: #f1f0fd;
  color: #6d28d9;
}
.wsp-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.wsp-row-name {
  overflow: hidden;
  font-size: 11px;
  color: #1f2937;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wsp-row-meta {
  overflow: hidden;
  font-size: 9px;
  color: #94a3b8;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wsp-row-size {
  flex: none;
  max-width: 42px;
  overflow: hidden;
  font-size: 9px;
  color: #94a3b8;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wsp-empty {
  padding: 18px 8px;
  font-size: 11px;
  line-height: 1.7;
  color: #94a3b8;
  text-align: center;
}
.wsp-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px solid #e6ebf2;
  padding-top: 10px;
}
.wsp-preview-head {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
}
.wsp-preview-head div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.wsp-preview-head b {
  overflow: hidden;
  font-size: 11px;
  color: #0e3a5c;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wsp-preview-head span {
  overflow: hidden;
  font-size: 9px;
  color: #94a3b8;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wsp-preview-head > button {
  flex: none;
  border: 0;
  background: transparent;
  color: #94a3b8;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}
.wsp-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.wsp-actions button,
.wsp-doc button {
  border: 1px solid #dbe4ef;
  border-radius: 6px;
  background: #fff;
  padding: 4px 8px;
  font-size: 10px;
  color: #0e3a5c;
  cursor: pointer;
}
.wsp-text {
  max-height: 220px;
  margin: 0;
  overflow: auto;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px;
  font-size: 10px;
  line-height: 1.6;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}
.wsp-truncated {
  display: block;
  margin-top: 6px;
  color: #b45309;
}
.wsp-image {
  max-width: 100%;
  border: 1px solid #eef2f7;
  border-radius: 8px;
}
.wsp-pdf {
  width: 100%;
  height: 260px;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #f8fafc;
}
.wsp-doc {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px dashed #c7d9e8;
  border-radius: 8px;
  padding: 9px;
  font-size: 10px;
  line-height: 1.5;
  color: #475569;
}
.wsp-doc-badge {
  flex: none;
  border-radius: 4px;
  background: #e8f2fd;
  padding: 4px 5px;
  font-size: 9px;
  color: #1d4ed8;
}
.wsp-doc div {
  flex: 1;
  min-width: 0;
}
.wsp-doc i {
  font-style: normal;
  color: #94a3b8;
}
.wsp-missing {
  border-radius: 8px;
  background: #fff7ed;
  padding: 10px;
  font-size: 10px;
  line-height: 1.6;
  color: #b45309;
}
.wsp-binary {
  border-radius: 8px;
  background: #f8fafc;
  padding: 10px;
  font-size: 10px;
  color: #94a3b8;
}
.wsp-foot {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  margin-top: auto;
  border-top: 1px solid #f1f5f9;
  padding-top: 10px;
}
.wsp-foot button {
  border: 1px solid #dbe4ef;
  border-radius: 7px;
  background: #fff;
  padding: 5px 9px;
  font-size: 10px;
  color: #0e3a5c;
  cursor: pointer;
}
.wsp-foot span {
  font-size: 9px;
  line-height: 1.5;
  color: #a0aec0;
}
.ingest-mask {
  position: fixed;
  inset: 0;
  z-index: 61;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
}
.ingest-panel {
  display: flex;
  flex-direction: column;
  width: min(720px, 94vw);
  max-height: min(780px, 90vh);
  overflow: hidden;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.25);
}
.ingest-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-bottom: 1px solid #e6ebf2;
  padding: 12px 16px;
}
.ingest-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ingest-title b {
  overflow: hidden;
  font-size: 13px;
  color: #0e3a5c;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ingest-title span {
  font-size: 10px;
  color: #94a3b8;
}
.ingest-head > button {
  flex: none;
  border: 0;
  background: transparent;
  padding: 0 4px;
  font-size: 18px;
  line-height: 1;
  color: #94a3b8;
  cursor: pointer;
}
.ingest-body,
.ingest-result {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 16px 16px;
}
.ingest-state {
  padding: 32px 16px;
  text-align: center;
  font-size: 12px;
  color: #64748b;
}
.ingest-state.error {
  color: #b42318;
}
.ingest-filemeta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-bottom: 10px;
  font-size: 10.5px;
  color: #64748b;
}
.ingest-label {
  display: block;
  margin: 10px 0 5px;
  font-size: 11px;
  font-weight: 600;
  color: #334155;
}
.ingest-input {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #dbe4ef;
  border-radius: 7px;
  background: #fff;
  padding: 7px 9px;
  font-size: 11.5px;
  color: #1f2937;
  outline: none;
}
.ingest-input:focus {
  border-color: #0e3a5c;
}
.ingest-section-title {
  margin: 14px 0 6px;
  font-size: 11px;
  font-weight: 600;
  color: #0e3a5c;
}
.ingest-params {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 10px;
}
.ingest-field {
  min-width: 0;
}
.ingest-field > label {
  display: block;
  margin-bottom: 4px;
  font-size: 10px;
  color: #64748b;
}
.ingest-field i {
  margin-left: 3px;
  font-style: normal;
  color: #dc2626;
}
.ingest-table-wrap {
  max-height: 170px;
  overflow: auto;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
}
.ingest-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 9.5px;
}
.ingest-table th,
.ingest-table td {
  max-width: 130px;
  overflow: hidden;
  border-bottom: 1px solid #eef2f7;
  border-right: 1px solid #eef2f7;
  padding: 5px 7px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ingest-table th {
  position: sticky;
  top: 0;
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
.ingest-hint {
  margin: 7px 0 10px;
  font-size: 10px;
  line-height: 1.6;
  color: #94a3b8;
}
.ingest-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  color: #475569;
  cursor: pointer;
}
.ingest-check input {
  accent-color: #0e3a5c;
}
.ingest-note {
  margin-top: 8px;
  border-radius: 7px;
  background: #f8fafc;
  padding: 7px 9px;
  font-size: 10px;
  line-height: 1.6;
  color: #64748b;
}
.ingest-note.warn {
  background: #fffbeb;
  color: #b45309;
}
.ingest-note.error {
  background: #fef2f2;
  color: #b42318;
}
.ingest-actions,
.ingest-result-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid #eef2f7;
}
.ingest-actions .spacer {
  flex: 1;
}
.ingest-actions button,
.ingest-result-actions button {
  border: 1px solid #dbe4ef;
  border-radius: 7px;
  background: #fff;
  padding: 6px 11px;
  font-size: 11px;
  color: #0e3a5c;
  cursor: pointer;
}
.ingest-actions button.primary,
.ingest-result-actions button.primary {
  border-color: #0e3a5c;
  background: #0e3a5c;
  color: #fff;
}
.ingest-actions button:disabled {
  opacity: 0.55;
  cursor: default;
}
.ingest-ok {
  margin-bottom: 8px;
  font-size: 16px;
  font-weight: 700;
  color: #15803d;
}
.ingest-kv {
  display: flex;
  align-items: baseline;
  gap: 10px;
  border-bottom: 1px dashed #eef2f7;
  padding: 6px 0;
  font-size: 11px;
  color: #64748b;
}
.ingest-kv b {
  margin-left: auto;
  color: #1f2937;
  text-align: right;
  word-break: break-all;
}
.ingest-kv b.good {
  color: #15803d;
}
.ingest-kv b.warn {
  color: #b45309;
}
@media (max-width: 600px) {
  .ingest-mask {
    padding: 10px;
  }
  .ingest-params {
    grid-template-columns: minmax(0, 1fr);
  }
}
.doc-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
}
.doc-panel {
  display: flex;
  flex-direction: column;
  width: min(1000px, 94vw);
  height: min(760px, 90vh);
  overflow: hidden;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.25);
}
.doc-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-bottom: 1px solid #e6ebf2;
  padding: 12px 16px;
}
.doc-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.doc-title b {
  overflow: hidden;
  font-size: 13px;
  color: #0e3a5c;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-title span {
  overflow: hidden;
  font-size: 10px;
  color: #94a3b8;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.doc-actions button {
  border: 1px solid #dbe4ef;
  border-radius: 6px;
  background: #fff;
  padding: 4px 8px;
  font-size: 11px;
  color: #0e3a5c;
  cursor: pointer;
}
.doc-actions button:last-child {
  border: 0;
  padding: 0 4px;
  font-size: 18px;
  line-height: 1;
  color: #94a3b8;
}
.doc-frame {
  flex: 1;
  width: 100%;
  border: 0;
  background: #f8fafc;
}
.doc-foot {
  border-top: 1px solid #e6ebf2;
  padding: 7px 16px;
  font-size: 10px;
  color: #94a3b8;
}
.icon-btn {
  width: 26px;
  height: 26px;
  border: 1px solid #dbe4ef;
  border-radius: 7px;
  background: #fff;
  color: #475569;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.ws-chip {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #64748b;
  padding: 3px 8px;
  border-radius: 999px;
  background: #f1f5f9;
}
.side-section .scope {
  float: right;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
}
.side-section .scope input {
  accent-color: #7aa7c7;
}
.panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.panel-note {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 8px;
}
.panel-note.small {
  margin-top: 10px;
  line-height: 1.6;
}
.plugin-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  padding: 8px 10px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  margin-bottom: 6px;
}
.plugin-name {
  font-size: 12px;
  color: #1f2937;
  word-break: break-all;
}
.plugin-ver {
  font-size: 11px;
  color: #2563a8;
}
.plugin-kind {
  grid-column: 1 / -1;
  font-size: 10px;
  color: #94a3b8;
}
.mcp-row {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f0f9ff;
  color: #075985;
  font-size: 11px;
}
.auto-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 2px;
  font-size: 12px;
  color: #475569;
  border-bottom: 1px dashed #eef2f7;
}
.auto-row span {
  flex: 0 0 auto;
  white-space: nowrap;
}
.auto-row b {
  min-width: 0;
  color: #0e3a5c;
  text-align: right;
  line-height: 1.5;
  word-break: break-all;
}
.panel-link {
  margin-top: 12px;
  width: 100%;
  padding: 7px 10px;
  border: 1px solid #dbe4ef;
  border-radius: 8px;
  background: #fff;
  color: #2563a8;
  font-size: 12px;
  cursor: pointer;
}

.task-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #eef2f7;
  font-size: 13px;
  font-weight: 600;
  color: #0e3a5c;
}
.task-workers {
  font-size: 10px;
  font-weight: 400;
  color: #94a3b8;
}
.task-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.task-start {
  flex: 1;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: #0e3a5c;
  color: #fff;
  font-size: 12px;
  cursor: pointer;
}
.task-start:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
.task-refresh {
  padding: 8px 10px;
  border: 1px solid #dbe4ef;
  border-radius: 8px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
}
.task-card {
  margin-top: 10px;
  padding: 9px 10px;
  border: 1px solid #e6ebf2;
  border-radius: 9px;
  background: #fbfdff;
}
.task-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.task-top b {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #1f2937;
}
.task-status {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 999px;
  background: #eef2f7;
  color: #64748b;
  font-size: 10px;
}
.task-status.running {
  background: #fef3c7;
  color: #b45309;
}
.task-status.done {
  background: #dcfce7;
  color: #15803d;
}
.task-status.failed,
.task-status.partial {
  background: #fee2e2;
  color: #b91c1c;
}
.task-status.cancelled,
.task-status.interrupted {
  background: #f1f5f9;
  color: #64748b;
}
.task-status.queued {
  background: #dbeafe;
  color: #1d4ed8;
}
.chat-job {
  border-left: 3px solid #bfdbfe;
}
.job-prompt {
  margin-top: 5px;
  color: #475569;
  font-size: 11px;
  line-height: 1.55;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}
.job-assistant {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed #e2e8f0;
  color: #64748b;
  font-size: 10px;
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}
.task-meta {
  margin-top: 4px;
  font-size: 10px;
  color: #94a3b8;
}
.task-bar {
  height: 4px;
  margin: 6px 0 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8eef6;
}
.task-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2563a8;
  transition: width 0.3s ease;
}
.task-bar i.done {
  background: #16a34a;
}
.task-bar i.failed,
.task-bar i.partial {
  background: #dc2626;
}
.task-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 11px;
}
.task-dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
}
.task-dot.running {
  background: #f59e0b;
}
.task-dot.done {
  background: #16a34a;
}
.task-dot.failed {
  background: #dc2626;
}
.task-item-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #475569;
}
.task-item-state {
  flex: 0 0 auto;
  color: #94a3b8;
  font-size: 10px;
}
.task-error {
  margin-top: 4px;
  padding: 5px 6px;
  border-radius: 6px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 10px;
  line-height: 1.5;
  word-break: break-word;
}
.task-stop {
  margin-top: 7px;
  width: 100%;
  padding: 5px 8px;
  border: 1px solid #fecaca;
  border-radius: 7px;
  background: #fff;
  color: #b91c1c;
  font-size: 11px;
  cursor: pointer;
}
.panel-empty {
  margin-top: 10px;
  padding: 14px 10px;
  border: 1px dashed #dbe4ef;
  border-radius: 9px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.7;
  text-align: center;
}


.side-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.side-head-actions .memory-btn {
  color: #bfe0f5;
}
.memory-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.42);
}
.memory-panel {
  width: min(700px, 100%);
  max-height: 82vh;
  overflow: auto;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.28);
}
.memory-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid #eef2f7;
}
.memory-head b {
  display: block;
  color: #0e3a5c;
  font-size: 17px;
}
.memory-head span {
  display: block;
  margin-top: 3px;
  color: #94a3b8;
  font-size: 11px;
}
.memory-head button {
  border: 0;
  background: transparent;
  color: #94a3b8;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}
.memory-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 14px 20px;
  background: #f8fbfe;
}
.memory-stats span {
  padding: 5px 10px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #e2ebf4;
  color: #64748b;
  font-size: 12px;
}
.memory-stats b {
  color: #0e3a5c;
}
.memory-section {
  padding: 14px 20px 0;
}
.memory-label {
  margin-bottom: 7px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #94a3b8;
}
.memory-path {
  padding: 6px 9px;
  border-radius: 6px;
  background: #f8fafc;
  color: #334155;
  font-size: 11px;
  word-break: break-all;
  margin-bottom: 5px;
}
.memory-row {
  padding: 8px 0;
  border-bottom: 1px dashed #eef2f7;
}
.memory-row-title {
  color: #0e3a5c;
  font-size: 12px;
  font-weight: 600;
}
.memory-row-text {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.memory-empty {
  padding: 24px 20px;
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
}
.memory-foot {
  margin-top: 14px;
  padding: 12px 20px 18px;
  border-top: 1px solid #eef2f7;
  color: #94a3b8;
  font-size: 11px;
}

@media (max-width: 1100px) {
  .files {
    width: 260px;
  }
}
@media (max-width: 860px) {
  .chat-side {
    display: none;
  }
  .chat-top {
    gap: 8px;
    padding: 0 12px;
  }
  .top-title,
  .top-proj,
  .tabs {
    display: none;
  }
  .conn,
  .top-files {
    white-space: nowrap;
    font-size: 11px;
  }
  .composer {
    padding-left: 12px;
    padding-right: 12px;
  }
  .hint {
    display: none;
  }
  .composer-actions {
    gap: 6px;
  }
  .ws-chip {
    max-width: 110px;
  }
}
</style>
