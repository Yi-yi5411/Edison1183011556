<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import { Back, QuestionFilled, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { NormClause, NormCodeStat, NormQaQueryResult, NormQaStatus } from '@/api/types'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()

/** el-upload 文件列表 → File 数组（UploadRawFile 兼容 File） */
function pickFiles(list: UploadUserFile[]): File[] {
  const files: File[] = []
  for (const f of list) {
    if (f.raw) files.push(f.raw)
  }
  return files
}

/** 逐文件导入统计（后端 import_files 返回对象数组，types.ts 声明为 string[]，此处局部细化） */
interface NormImportFileStat {
  file: string
  code?: string
  count?: number
  error?: string
}

/** 导入结果摘要（用于导入卡内的反馈区） */
interface ImportSummary {
  imported: number
  total: number
  invalidFiles: string[]
}

function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

/* ===== 规范库状态 ===== */
const status = ref<NormQaStatus | null>(null)
const statusLoading = ref(false)

async function loadStatus() {
  statusLoading.value = true
  try {
    status.value = await api.normqaStatus()
  } catch {
    /* api 层已提示 */
  } finally {
    statusLoading.value = false
  }
}

const codeStats = computed<NormCodeStat[]>(() => status.value?.codes ?? [])

/** 规范库为空（状态加载成功且 0 条）时给出引导 */
const libEmpty = computed(() => status.value !== null && (status.value.total ?? 0) === 0)

/* ===== 导入规范文件 ===== */
const mode = ref<'append' | 'rebuild'>('append')
const fileList = ref<UploadUserFile[]>([])
const importing = ref(false)
const importSummary = ref<ImportSummary | null>(null)
const ACCEPT = '.md,.markdown,.txt,.docx'

async function onImport() {
  const files = pickFiles(fileList.value)
  if (!files.length) {
    ElMessage.warning('请先选择要导入的规范文件（md/txt/docx）')
    return
  }
  importing.value = true
  importSummary.value = null
  try {
    const result = await api.normqaImport(files, mode.value)
    // 逐文件统计：count 为 0 或带 error 的文件视为无有效条文
    const stats = result.files as unknown as NormImportFileStat[] | undefined
    const invalidFiles = Array.isArray(stats)
      ? stats.filter((s) => s.error || !s.count).map((s) => basename(s.file))
      : []
    importSummary.value = { imported: result.imported, total: result.total, invalidFiles }
    ElMessage.success(`导入完成：新增 ${result.imported} 条条文，库内共 ${result.total} 条`)
    store.setStatus(`规范库导入完成：新增 ${result.imported} 条（共 ${result.total} 条）`)
    fileList.value = []
    await loadStatus()
  } catch {
    /* api 层已提示 */
  } finally {
    importing.value = false
  }
}

/* ===== 检索 ===== */
const question = ref('')
const querying = ref(false)
const queryResult = ref<NormQaQueryResult | null>(null)

/* 查询历史：仅本次会话内存（不持久化，刷新即清），最多 8 条，最新在前 */
const queryHistory = ref<string[]>([])

function pushHistory(term: string) {
  const t = term.trim()
  if (!t) return
  queryHistory.value = [t, ...queryHistory.value.filter((x) => x !== t)].slice(0, 8)
}

function removeHistory(term: string) {
  queryHistory.value = queryHistory.value.filter((x) => x !== term)
}

function clearHistory() {
  queryHistory.value = []
}

/* 结果树：按来源规范（code + code_name）分组 → 条文（chapter + title + body 预览） */
interface ClauseNode {
  key: string
  clause: NormClause
}
interface CodeGroup {
  key: string
  code: string
  codeName: string
  clauses: ClauseNode[]
}

const groupedClauses = computed<CodeGroup[]>(() => {
  const groups: CodeGroup[] = []
  const map = new Map<string, CodeGroup>()
  for (const clause of queryResult.value?.clauses ?? []) {
    const key = clause.code || '（未知规范）'
    let group = map.get(key)
    if (!group) {
      group = { key: `g:${key}`, code: clause.code || '—', codeName: clause.code_name || '', clauses: [] }
      map.set(key, group)
      groups.push(group)
    }
    group.clauses.push({ key: `c${clause.id ?? group.clauses.length}`, clause })
  }
  return groups
})

const clauseKeys = computed(() => groupedClauses.value.flatMap((g) => g.clauses.map((c) => c.key)))

function normalize(text: string): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}

/** 条文体预览：截断 80 字（全文通过 hover tooltip 查看） */
function preview(text: string, len = 80): string {
  const t = normalize(text)
  return t.length > len ? `${t.slice(0, len)}…` : t
}

async function doQuery(q?: string) {
  const text = (q ?? question.value).trim()
  if (!text) {
    ElMessage.warning('请输入要查询的规范条文号或问题')
    return
  }
  if (q !== undefined) question.value = q
  querying.value = true
  queryResult.value = null
  try {
    queryResult.value = await api.normqaQuery(text)
    pushHistory(text)
  } catch {
    /* api 层已提示 */
  } finally {
    querying.value = false
  }
}

function onCandidateClick(term: string) {
  void doQuery(term)
}

const resultTypeText = computed(() => {
  switch (queryResult.value?.type) {
    case 'exact':
      return '条号精确命中'
    case 'search':
      return '关键词检索命中'
    case 'candidates':
      return '未命中条文，可点击术语候选重查'
    case 'empty':
      return '未检索到相关条文'
    default:
      return ''
  }
})

/* ===== AI 解释（选中条文或全部命中，纯文本展示） ===== */
const treeRef = ref()
const explaining = ref(false)
const explainText = ref('')
const explainQuestion = ref('')
const explainElapsed = ref(0)

let explainTimer: ReturnType<typeof setInterval> | null = null

function startExplainTimer() {
  explainElapsed.value = 0
  explainTimer = setInterval(() => {
    explainElapsed.value += 1
  }, 1000)
}

function stopExplainTimer() {
  if (explainTimer) clearInterval(explainTimer)
  explainTimer = null
}

onBeforeUnmount(() => {
  stopExplainTimer()
})

const explainElapsedText = computed(() => {
  const m = Math.floor(explainElapsed.value / 60)
  const s = explainElapsed.value % 60
  return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`
})

async function explain() {
  if (!groupedClauses.value.length) {
    ElMessage.warning('请先检索并命中条文后再请求解释')
    return
  }
  // 勾选了条文则只解释选中项，否则解释全部命中条文
  const checked = new Set<string>(
    (treeRef.value?.getCheckedKeys(true) ?? []).map(String),
  )
  const clauses: NormClause[] = groupedClauses.value
    .flatMap((g) => g.clauses)
    .filter((c) => (checked.size ? checked.has(c.key) : true))
    .map((c) => c.clause)
  if (!clauses.length) {
    ElMessage.warning('没有可解释的条文')
    return
  }
  explaining.value = true
  explainQuestion.value = question.value
  explainText.value = ''
  startExplainTimer()
  try {
    const result = await api.normqaExplain(question.value, clauses as unknown as Record<string, unknown>[])
    explainText.value = result.answer
    store.setStatus('规范条文解释已生成')
  } catch {
    /* api 层已提示 */
  } finally {
    stopExplainTimer()
    explaining.value = false
  }
}

onMounted(() => {
  void loadStatus()
})
</script>

<template>
  <div class="normqa-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/internal')">返回工具</el-button>
        <h2>规范问答</h2>
      </div>
    </header>

    <!-- 规范库为空时的引导 -->
    <el-alert
      v-if="libEmpty"
      type="warning"
      show-icon
      :closable="false"
      title="规范库为空，请先导入规范文件后再查询"
      description="在下方「导入规范文件」中选择 md / txt / docx 文件导入，条文标题需按「### 条号 标题」格式书写。"
    />

    <!-- 规范库状态 -->
    <el-card shadow="never" class="status-card">
      <template #header>
        <div class="card-header">
          <span>规范库状态</span>
          <el-button :icon="Refresh" :loading="statusLoading" size="small" @click="loadStatus">
            刷新
          </el-button>
        </div>
      </template>
      <div v-loading="statusLoading">
        <div class="status-total">
          库内条文：<b>{{ status?.total ?? 0 }}</b> 条
          <span v-if="status?.db_path" class="db-path">（{{ status.db_path }}）</span>
        </div>
        <div v-if="codeStats.length" class="code-tags">
          <el-tag
            v-for="c in codeStats"
            :key="c.code"
            class="code-tag"
            type="info"
            effect="plain"
          >
            {{ c.code }}{{ c.code_name ? ` ${c.code_name}` : '' }}（{{ c.count }} 条）
          </el-tag>
        </div>
        <div v-else class="empty-tip">规范库为空，请先导入规范文件</div>
      </div>
    </el-card>

    <!-- 导入 -->
    <el-card shadow="never">
      <template #header>导入规范文件</template>
      <div class="import-row">
        <el-radio-group v-model="mode" :disabled="importing">
          <el-radio value="append">增量导入（同条覆盖）</el-radio>
          <el-radio value="rebuild">全量重建（清空后导入）</el-radio>
        </el-radio-group>
        <el-upload
          v-model:file-list="fileList"
          class="import-upload"
          :auto-upload="false"
          multiple
          :accept="ACCEPT"
          :disabled="importing"
          :on-exceed="() => {}"
        >
          <el-button :icon="Upload" :loading="importing">选择文件（md / txt / docx）</el-button>
        </el-upload>
        <el-button type="primary" :loading="importing" @click="onImport">开始导入</el-button>
      </div>

      <!-- 导入结果摘要 -->
      <el-alert
        v-if="importSummary"
        :type="importSummary.invalidFiles.length ? 'warning' : 'success'"
        show-icon
        :closable="false"
        class="import-summary"
      >
        <template #title>
          本次导入 {{ importSummary.imported }} 条条文 / 库内共 {{ importSummary.total }} 条
        </template>
        <div v-if="importSummary.invalidFiles.length" class="invalid-files">
          <div>以下 {{ importSummary.invalidFiles.length }} 个文件未解析出有效条文：</div>
          <ul>
            <li v-for="f in importSummary.invalidFiles" :key="f">{{ f }}</li>
          </ul>
          <div>请检查文件格式：条文标题需按「### 条号 标题」书写（如 <code>### 4.2.2 一般规定</code>）。</div>
        </div>
      </el-alert>
    </el-card>

    <!-- 查询 -->
    <el-card shadow="never" class="query-card">
      <template #header>
        <div class="card-header">
          <span>条文检索</span>
          <el-tag v-if="queryResult" size="small" :type="groupedClauses.length ? 'success' : 'warning'">
            {{ resultTypeText }}
          </el-tag>
        </div>
      </template>
      <div class="query-row">
        <el-input
          v-model="question"
          clearable
          placeholder="输入条号（如 4.2.2）或自然语言问题，回车查询"
          @keyup.enter="doQuery()"
        >
          <template #append>
            <el-button :icon="Search" :loading="querying" @click="doQuery()">查 询</el-button>
          </template>
        </el-input>
        <el-button
          type="success"
          :icon="QuestionFilled"
          :loading="explaining"
          :disabled="!groupedClauses.length"
          @click="explain"
        >
          AI 解释
        </el-button>
      </div>

      <!-- 查询历史（仅本次会话，点击重查） -->
      <div v-if="queryHistory.length" class="history-row">
        <span class="history-label">最近查询：</span>
        <el-tag
          v-for="t in queryHistory"
          :key="t"
          class="history-tag"
          closable
          @click="doQuery(t)"
          @close="removeHistory(t)"
        >
          {{ t }}
        </el-tag>
        <el-button link size="small" @click="clearHistory">清空</el-button>
      </div>

      <div v-if="queryResult" class="query-meta">
        <span v-if="groupedClauses.length" class="meta-text">
          命中 {{ clauseKeys.length }} 条条文 · 勾选后可只解释选中项
        </span>
      </div>

      <!-- 术语候选 -->
      <div v-if="queryResult?.candidates?.length" class="candidates">
        <span class="candidates-label">术语候选：</span>
        <el-button
          v-for="c in queryResult.candidates"
          :key="c.term"
          size="small"
          type="primary"
          plain
          @click="onCandidateClick(c.term)"
        >
          {{ c.label || `${c.term}（${c.count} 处）` }}
        </el-button>
      </div>

      <!-- 结果树：来源规范分组 → 条文 -->
      <el-tree
        v-if="groupedClauses.length"
        ref="treeRef"
        :data="groupedClauses"
        :props="{ children: 'clauses' }"
        node-key="key"
        show-checkbox
        default-expand-all
        class="result-tree"
      >
        <template #default="{ data }">
          <template v-if="'clause' in data">
            <div class="clause-node">
              <span class="clause-no">{{ data.clause.chapter }}</span>
              <span class="clause-title">{{ data.clause.title }}</span>
              <el-tooltip
                placement="top"
                :show-after="300"
                :content="normalize(data.clause.body)"
                :disabled="!normalize(data.clause.body)"
              >
                <span class="clause-preview">{{ preview(data.clause.body) }}</span>
              </el-tooltip>
            </div>
          </template>
          <template v-else>
            <span class="code-node">
              {{ data.code }} <span class="code-name">{{ data.codeName }}</span>
              <el-tag size="small" type="info" effect="plain">{{ data.clauses.length }} 条</el-tag>
            </span>
          </template>
        </template>
      </el-tree>
      <el-empty
        v-else-if="queryResult"
        :image-size="72"
        :description="resultTypeText || '暂无结果'"
      />
      <el-empty
        v-else
        :image-size="72"
        description="输入条号（如 5.1.2）或自然语言问题"
      />
    </el-card>

    <!-- AI 解释：进行中显示进度面板（本地大模型约 10~60 秒） -->
    <el-card v-if="explaining" shadow="never" class="progress-card">
      <div class="progress-body">
        <el-icon class="is-loading progress-icon"><QuestionFilled /></el-icon>
        <div>
          <div class="progress-title">本地大模型正在依据条文作答，约 10~60 秒…</div>
          <div class="progress-sub">请勿关闭页面 · 已用时 {{ explainElapsedText }}</div>
        </div>
      </div>
      <el-progress :percentage="50" :show-text="false" status="warning" class="progress-bar" />
    </el-card>

    <!-- AI 解释结果（纯文本只读区，不做 Markdown 渲染） -->
    <el-card v-else-if="explainText" shadow="never">
      <template #header>
        AI 解释<span v-if="explainQuestion" class="explain-question">（{{ explainQuestion }}）</span>
      </template>
      <div class="explain-box">
        <pre>{{ explainText }}</pre>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.normqa-view {
  height: 100%;
  overflow: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-title h2 {
  margin: 0;
  font-size: 18px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-total {
  margin-bottom: 8px;
}

.db-path {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 8px;
}

.code-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-tip {
  color: var(--el-text-color-secondary);
}

.import-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.import-upload {
  display: inline-block;
  margin-right: 4px;
}

.import-summary {
  margin-top: 12px;
}

.invalid-files ul {
  margin: 6px 0;
  padding-left: 20px;
}

.invalid-files li {
  line-height: 1.8;
  color: var(--el-text-color-regular);
}

.query-row {
  display: flex;
  gap: 12px;
}

.query-row .el-input {
  flex: 1;
}

.history-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.history-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.history-tag {
  cursor: pointer;
}

.query-meta {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 18px;
}

.meta-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.candidates {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.candidates-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.result-tree {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px;
}

.code-node {
  font-weight: 600;
}

.code-name {
  font-weight: 400;
  color: var(--el-text-color-secondary);
  margin: 0 8px;
}

.clause-node {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.clause-no {
  font-weight: 600;
  color: var(--el-color-primary);
  white-space: nowrap;
}

.clause-title {
  white-space: nowrap;
}

.clause-preview {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: help;
}

/* AI 解释进度面板：样式沿用 ReportView progress-card */
.progress-card :deep(.el-card__body) {
  padding: 14px 16px;
}

.progress-body {
  display: flex;
  align-items: center;
  gap: 14px;
}

.progress-icon {
  font-size: 30px;
  color: var(--el-color-warning);
}

.progress-title {
  font-weight: 600;
}

.progress-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.progress-bar {
  margin-top: 10px;
}

.explain-question {
  font-weight: 400;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* 纯文本解释区：白底只读、等宽换行展示，不渲染 Markdown */
.explain-box {
  min-height: 48px;
  background: #ffffff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 14px;
  max-height: 420px;
  overflow: auto;
}

html.dark .explain-box {
  background: var(--el-bg-color);
}

.explain-box pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.8;
  color: var(--el-text-color-primary);
}
</style>
