<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElCheckbox, ElMessage, ElMessageBox } from 'element-plus'
import type { CheckboxValueType, UploadUserFile } from 'element-plus'
import {
  Back,
  CopyDocument,
  Delete,
  Download,
  FolderOpened,
  Switch,
  UploadFilled,
} from '@element-plus/icons-vue'
import { api } from '@/api'
import type { ReviewCandidate, ReviewRunResult } from '@/api/types'
import { useAppStore } from '@/stores/app'
import { copyToClipboard } from '@/utils/clipboard'

const router = useRouter()
const store = useAppStore()

const ACCEPT = '.docx,.pdf,.txt'
const fileList = ref<UploadUserFile[]>([])

/** 本地行类型：附加稳定行键（勾选状态跨过滤/删除保持） */
interface CandidateRow extends ReviewCandidate {
  _key: string
}

let keySeq = 0

/* ===== 文件大小格式化（文件名 + 大小标签） ===== */
function sizeText(size?: number): string {
  if (typeof size !== 'number') return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

/** 重复文件去重：同名同大小只保留一个，重复添加时提示 */
function onFileChange(_file: UploadUserFile, list: UploadUserFile[]) {
  const seen = new Set<string>()
  const dups = new Set<string>()
  const deduped: UploadUserFile[] = []
  for (const f of list) {
    const key = `${f.name}:${f.size ?? ''}:${f.raw?.lastModified ?? ''}`
    if (seen.has(key)) {
      dups.add(f.name)
      continue
    }
    seen.add(key)
    deduped.push(f)
  }
  if (dups.size) {
    fileList.value = deduped
    ElMessage.warning(`已忽略重复文件：${[...dups].join('、')}`)
  }
}

function removeFile(f: UploadUserFile) {
  fileList.value = fileList.value.filter((x) => x.uid !== f.uid)
}

/** el-upload 文件列表 → File 数组（UploadRawFile 兼容 File） */
function pickFiles(list: UploadUserFile[]): File[] {
  const files: File[] = []
  for (const f of list) {
    if (f.raw) files.push(f.raw)
  }
  return files
}

/* 候选表列（键名与后端 extract_candidates / export_review_docx 一致） */
const COLS: { prop: string; label: string; width?: number }[] = [
  { prop: 'location', label: '位置', width: 150 },
  { prop: 'excerpt', label: '原文片段', width: 200 },
  { prop: 'category', label: '问题类型', width: 110 },
  { prop: 'description', label: '问题描述', width: 220 },
  { prop: 'suggestion', label: '审查建议', width: 220 },
  { prop: 'basis', label: '规范依据', width: 200 },
]

/* 问题类型分组（未命中的归入"其他"） */
const CATEGORY_KEYS = ['结论表述', '依据引用', '数据完整性', '用语规范', '签字盖章'] as const

function catOf(c: ReviewCandidate): string {
  const cat = String(c.category ?? '').trim()
  return (CATEGORY_KEYS as readonly string[]).includes(cat) ? cat : '其他'
}

/* ===== 状态 ===== */
const running = ref(false)
const exporting = ref(false)
const result = ref<ReviewRunResult | null>(null)
const candidates = ref<CandidateRow[]>([])
const selectedKeys = ref(new Set<string>())
const activeCat = ref<string | null>(null)
const editingCell = ref('') // `${_key}:${prop}`，点击进入编辑

const categoryCounts = computed<Record<string, number>>(() => {
  const counts: Record<string, number> = {}
  for (const k of CATEGORY_KEYS) counts[k] = 0
  counts['其他'] = 0
  for (const c of candidates.value) counts[catOf(c)] += 1
  return counts
})

const filteredCandidates = computed(() =>
  activeCat.value ? candidates.value.filter((c) => catOf(c) === activeCat.value) : candidates.value,
)

const checkedCount = computed(() => candidates.value.filter((c) => selectedKeys.value.has(c._key)).length)

const visibleSelectedCount = computed(
  () => filteredCandidates.value.filter((c) => selectedKeys.value.has(c._key)).length,
)

const allVisibleSelected = computed(
  () => filteredCandidates.value.length > 0 && visibleSelectedCount.value === filteredCandidates.value.length,
)

function toggleAllVisible(checked: CheckboxValueType) {
  const want = checked === true
  for (const c of filteredCandidates.value) {
    if (want) selectedKeys.value.add(c._key)
    else selectedKeys.value.delete(c._key)
  }
}

function onRowCheck(rowKey: string, checked: CheckboxValueType) {
  if (checked === true) selectedKeys.value.add(rowKey)
  else selectedKeys.value.delete(rowKey)
}

function toggleCat(cat: string) {
  activeCat.value = activeCat.value === cat ? null : cat
}

/* ===== 长任务计时（借鉴 ReportView progress-card） ===== */
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

function startTimer() {
  elapsed.value = 0
  timer = setInterval(() => {
    elapsed.value += 1
  }, 1000)
}

function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

const elapsedText = computed(() => {
  const m = Math.floor(elapsed.value / 60)
  const s = elapsed.value % 60
  return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`
})

/* ===== 批量审查（单请求同步接口，无法拿块级进度，给固定阶段提示） ===== */
async function onRun() {
  const files = pickFiles(fileList.value)
  if (!files.length) {
    ElMessage.warning('请先选择要审查的报告文件（docx/pdf/txt）')
    return
  }
  if (candidates.value.length) {
    try {
      await ElMessageBox.confirm(
        `重新审查将替换当前 ${candidates.value.length} 条候选意见（新结果不会累加）。是否继续？`,
        '覆盖确认',
        { type: 'warning', confirmButtonText: '重新审查', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  running.value = true
  startTimer()
  try {
    const data = await api.reviewRun(files)
    result.value = data
    activeCat.value = null
    selectedKeys.value = new Set()
    editingCell.value = ''
    candidates.value = data.candidates.map((c) => ({ ...c, _key: `cand-${keySeq++}` }))
    ElMessage.success(
      `审查完成：${data.files.length} 个文件、${data.chunks} 个片段，提取 ${candidates.value.length} 条候选意见`,
    )
    store.setStatus(
      `批量审查完成：${data.files.length} 个文件 / ${data.chunks} 个片段 / ${candidates.value.length} 条候选`,
    )
  } catch {
    /* api 层已提示 */
  } finally {
    stopTimer()
    running.value = false
  }
}

/* ===== 删除（防误删：confirm + 本轮"不再提示"） ===== */
const skipDeleteConfirm = ref(false)

/** confirm 内容渲染为组件，保证"不再提示"勾选框响应式 */
const DeleteConfirmMessage = defineComponent({
  props: { count: { type: Number, required: true } },
  setup(props) {
    return () =>
      h('div', null, [
        h('p', { style: 'margin: 0 0 8px' }, `确定删除勾选的 ${props.count} 条候选意见？`),
        h(
          ElCheckbox,
          {
            modelValue: skipDeleteConfirm.value,
            'onUpdate:modelValue': (v: CheckboxValueType) => {
              skipDeleteConfirm.value = v === true
            },
          },
          { default: () => '本轮删除不再提示（刷新页面前有效）' },
        ),
      ])
  },
})

async function deleteSelected() {
  const selected = candidates.value.filter((c) => selectedKeys.value.has(c._key))
  if (!selected.length) {
    ElMessage.warning('请先勾选要删除的行')
    return
  }
  if (!skipDeleteConfirm.value) {
    try {
      await ElMessageBox.confirm(h(DeleteConfirmMessage, { count: selected.length }), '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
  }
  const removeKeys = new Set(selected.map((c) => c._key))
  candidates.value = candidates.value.filter((c) => !removeKeys.has(c._key))
  for (const k of removeKeys) selectedKeys.value.delete(k)
  ElMessage.success(`已删除 ${selected.length} 条候选意见`)
}

/* ===== 导出审查意见表（只导出勾选行） ===== */
const exportResult = ref<{ name: string; count: number } | null>(null)

async function onExport() {
  const selected = candidates.value.filter((c) => selectedKeys.value.has(c._key))
  if (!selected.length) {
    ElMessage.warning('请先勾选要导出的候选意见')
    return
  }
  exporting.value = true
  try {
    // 只送后端契约字段，剔除表格内部状态
    const payload: ReviewCandidate[] = selected.map((c) => ({
      location: c.location ?? '',
      excerpt: c.excerpt ?? '',
      category: c.category ?? '',
      description: c.description ?? '',
      suggestion: c.suggestion ?? '',
      basis: c.basis ?? '',
    }))
    const name = await api.reviewExport(payload, store.projectName)
    exportResult.value = { name, count: payload.length }
    ElMessage.success(`审查意见表已导出：${name}（${payload.length} 条）`)
    store.setStatus(`审查意见表已导出：${name}`)
  } catch {
    /* api 层已提示 */
  } finally {
    exporting.value = false
  }
}

async function onRevealExport() {
  if (!exportResult.value) return
  try {
    await api.revealFile(exportResult.value.name)
  } catch {
    /* api 层已提示 */
  }
}

async function onCopyExportPath() {
  if (!exportResult.value) return
  if (await copyToClipboard(exportResult.value.name)) ElMessage.success('路径已复制到剪贴板')
  else ElMessage.warning('复制失败，请手动选择路径文本复制')
}
</script>

<template>
  <div class="review-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/internal')">返回工具</el-button>
        <h2>批量审查</h2>
      </div>
    </header>

    <!-- 审查进度面板：单请求同步接口，给固定阶段提示与已用时 -->
    <el-card v-if="running" shadow="never" class="progress-card">
      <div class="progress-body">
        <el-icon class="is-loading progress-icon"><Switch /></el-icon>
        <div>
          <div class="progress-title">正在分块提取审查候选，逐块调用本地大模型…请勿关闭页面</div>
          <div class="progress-sub">
            批量审查为单次同步请求，暂无法展示块级进度，文件越多耗时越长 · 已用时 {{ elapsedText }}
          </div>
        </div>
      </div>
      <el-progress :percentage="50" :show-text="false" status="warning" class="progress-bar" />
    </el-card>

    <!-- 文件选择与运行 -->
    <el-card shadow="never">
      <template #header>审查文件</template>
      <div class="run-row">
        <el-upload
          v-model:file-list="fileList"
          :auto-upload="false"
          multiple
          :accept="ACCEPT"
          :show-file-list="false"
          :on-change="onFileChange"
        >
          <el-button :icon="UploadFilled">选择报告文件（docx / pdf / txt）</el-button>
        </el-upload>
        <el-button
          type="primary"
          :icon="Switch"
          :loading="running"
          :disabled="!fileList.length"
          @click="onRun"
        >
          开始审查
        </el-button>
        <span class="run-tip">大模型逐块提取审查意见并自动匹配规范依据，文件越多耗时越长</span>
      </div>
      <!-- 已选文件标签（文件名 + 大小，可单个移除；重复文件已去重） -->
      <div v-if="fileList.length" class="picked-files">
        <el-tag
          v-for="f in fileList"
          :key="f.uid"
          closable
          type="info"
          class="picked-tag"
          @close="removeFile(f)"
        >
          {{ f.name }}（{{ sizeText(f.size) }}）
        </el-tag>
      </div>
      <el-empty
        v-else
        :image-size="72"
        description="请先选择 docx / pdf / txt 检测报告或记录文件，开始批量审查"
      />
      <div v-if="result" class="run-meta">
        <el-tag size="small" type="success">{{ result.files.length }} 个文件</el-tag>
        <el-tag size="small" type="info">{{ result.chunks }} 个片段</el-tag>
        <span v-if="result.model" class="model-text">模型：{{ result.model }}</span>
      </div>
    </el-card>

    <el-card v-if="!candidates.length" shadow="never" class="help-card">
      <template #header>审查说明</template>
      <div class="help-steps">
        <div class="help-step">
          <span class="help-num">1</span>
          <div><b>选择报告文件</b><p>支持 docx / pdf / txt；可一次选择多个文件批量审查。</p></div>
        </div>
        <div class="help-step">
          <span class="help-num">2</span>
          <div><b>大模型逐块提取</b><p>按片段提取审查意见候选，并自动匹配本地规范条文作为依据。</p></div>
        </div>
        <div class="help-step">
          <span class="help-num">3</span>
          <div><b>人工复核</b><p>候选意见可编辑、删除、导出为审查意见文档，最终以人工判断为准。</p></div>
        </div>
      </div>
    </el-card>

    <!-- 候选意见统计 + 表 -->
    <el-card v-if="candidates.length" shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span>审查意见候选（点击单元格文字可编辑）</span>
          <div class="header-actions">
            <el-button
              size="small"
              type="danger"
              plain
              :icon="Delete"
              :disabled="running"
              @click="deleteSelected"
            >
              删除选中
            </el-button>
            <el-button
              size="small"
              type="primary"
              :icon="Download"
              :loading="exporting"
              :disabled="running"
              @click="onExport"
            >
              导出意见表（{{ checkedCount }} 条已勾选）
            </el-button>
          </div>
        </div>
      </template>

      <!-- 结果统计条：总数 / 类型分组计数（点击过滤）/ 已勾选数 -->
      <div class="stats-bar">
        <el-tag size="small" effect="dark">候选总数 {{ candidates.length }}</el-tag>
        <el-tag size="small" type="success" effect="plain">已勾选 {{ checkedCount }}</el-tag>
        <el-divider direction="vertical" />
        <span class="stats-label">问题类型（点击过滤）：</span>
        <el-tag
          v-for="(count, cat) in categoryCounts"
          :key="cat"
          size="small"
          class="cat-tag"
          :type="activeCat === cat ? 'primary' : 'info'"
          :effect="activeCat === cat ? 'dark' : 'plain'"
          @click="toggleCat(cat)"
        >
          {{ cat }}（{{ count }}）
        </el-tag>
        <el-button v-if="activeCat" link type="primary" size="small" @click="activeCat = null">
          清除过滤
        </el-button>
      </div>

      <el-table :data="filteredCandidates" border stripe height="100%" class="cand-table" row-key="_key">
        <el-table-column width="46" fixed="left" align="center">
          <template #header>
            <el-checkbox
              :model-value="allVisibleSelected"
              :indeterminate="visibleSelectedCount > 0 && !allVisibleSelected"
              @change="toggleAllVisible"
            />
          </template>
          <template #default="{ row }">
            <el-checkbox
              :model-value="selectedKeys.has(row._key)"
              @change="onRowCheck(row._key, $event)"
            />
          </template>
        </el-table-column>
        <el-table-column type="index" label="#" width="52" fixed="left" />
        <el-table-column
          v-for="col in COLS"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          min-width="120"
        >
          <template #default="{ row }">
            <!-- 问题描述：省略 + hover tooltip 全文，点击进入编辑 -->
            <template v-if="col.prop === 'description'">
              <el-input
                v-if="editingCell === `${row._key}:description`"
                v-model="row.description"
                type="textarea"
                :rows="2"
                autosize
                @blur="editingCell = ''"
              />
              <el-tooltip
                v-else
                placement="top"
                :content="String(row.description || '')"
                :disabled="!row.description"
              >
                <div class="desc-cell" @click="editingCell = `${row._key}:description`">
                  {{ row.description || '—' }}
                </div>
              </el-tooltip>
            </template>
            <!-- 规范依据：为空显示灰色"未匹配"占位，点击可手动填写 -->
            <template v-else-if="col.prop === 'basis'">
              <el-input
                v-if="row.basis || editingCell === `${row._key}:basis`"
                v-model="row.basis"
                type="textarea"
                :rows="2"
                autosize
                @blur="editingCell = ''"
              />
              <span
                v-else
                class="cell-empty"
                @click="editingCell = `${row._key}:basis`"
              >未匹配</span>
            </template>
            <el-input v-else v-model="row[col.prop]" type="textarea" :rows="2" autosize />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-empty
      v-else-if="fileList.length && !running"
      :image-size="80"
      :description="`已选择 ${fileList.length} 个文件，点击「开始审查」提取审查候选意见`"
    />

    <!-- 导出结果区：路径 + 打开文件位置 / 复制路径 -->
    <el-card v-if="exportResult" shadow="never" class="export-card">
      <el-result
        icon="success"
        title="审查意见表已导出"
        :sub-title="`${exportResult.name}（${exportResult.count} 条）`"
        style="padding: 8px 0 0"
      />
      <div class="result-actions">
        <el-button type="primary" :icon="FolderOpened" @click="onRevealExport">打开文件位置</el-button>
        <el-button :icon="CopyDocument" @click="onCopyExportPath">复制路径</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.review-view {
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

/* 进度面板（与 ReportView 一致） */
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

.run-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.run-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.picked-files {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.picked-tag {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.run-meta {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.model-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 统计条 */
.stats-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.stats-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.cat-tag {
  cursor: pointer;
}

.table-card {
  flex: 1;
  min-height: 320px;
  display: flex;
  flex-direction: column;
}

.table-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cand-table {
  width: 100%;
}

/* 问题描述：过宽省略 + tooltip 全文 */
.desc-cell {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 28px;
  min-height: 28px;
  cursor: text;
}

/* 规范依据为空的灰色占位 */
.cell-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  cursor: text;
  line-height: 28px;
}

/* 单元格编辑输入框弱化边框，更接近表格内联编辑 */
.cand-table :deep(.el-textarea__inner) {
  box-shadow: none;
  padding: 2px 4px;
  background: transparent;
  min-height: 28px;
}

.cand-table :deep(.el-textarea__inner:focus) {
  background: var(--el-bg-color);
}

/* 导出结果区 */
.export-card :deep(.el-card__body) {
  padding-bottom: 20px;
}

.result-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-top: 4px;
}
</style>
