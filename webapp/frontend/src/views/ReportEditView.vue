<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Download, FolderOpened, Refresh } from '@element-plus/icons-vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'
import type {
  DocCell,
  DocParagraph,
  DocTable,
  ReportDocument,
  ReportHistoryItem,
} from '@/api/types'

interface EditableParagraph extends DocParagraph {
  draft: string
}

interface EditableCell extends DocCell {
  draft: string
}

interface EditableTable extends DocTable {
  rows: EditableCell[][]
}

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const history = ref<ReportHistoryItem[]>([])
const selectedHistory = ref('')
const filepathInput = ref('')
const loading = ref(false)
const saving = ref(false)
const replacing = ref(false)
const doc = ref<ReportDocument | null>(null)
const paragraphs = ref<EditableParagraph[]>([])
const tables = ref<EditableTable[]>([])
const zoom = ref(100)

const findText = ref('')
const replaceText = ref('')

const dirty = computed(() =>
  paragraphs.value.some((p) => p.draft !== p.text)
  || tables.value.some((t) => t.rows.some((r) => r.some((c) => c.draft !== c.text))),
)

const changedParagraphCount = computed(
  () => paragraphs.value.filter((p) => p.draft !== p.text).length,
)

const changedCellCount = computed(() =>
  tables.value.reduce(
    (sum, t) => sum + t.rows.reduce(
      (n, r) => n + r.filter((c) => c.draft !== c.text).length, 0),
    0,
  ),
)

const documentBlocks = computed(() => {
  const pMap = new Map(paragraphs.value.map((p) => [p.index, p]))
  const tMap = new Map(tables.value.map((t) => [t.index, t]))
  return (doc.value?.blocks ?? []).map((block) => ({
    ...block,
    paragraph: block.type === 'paragraph' ? pMap.get(block.index) : undefined,
    table: block.type === 'table' ? tMap.get(block.index) : undefined,
  }))
})

const outline = computed(() =>
  paragraphs.value.filter((p) =>
    p.heading || /标题|Heading/i.test(String(p.style || '')),
  ).slice(0, 30),
)

function paragraphClass(p: EditableParagraph): string {
  if (p.heading || /标题|Heading/i.test(String(p.style || ''))) return 'doc-heading'
  if (/report number/i.test(String(p.style || ''))) return 'doc-report-number'
  return String(p.text || '').trim() ? '' : 'doc-empty'
}

function paragraphRows(p: EditableParagraph): number {
  const length = String(p.draft || '').length
  return Math.max(1, Math.min(8, Math.ceil(length / 55)))
}

function paragraphStyle(p: EditableParagraph): Record<string, string> {
  const style: Record<string, string> = {}
  const align = String(p.alignment || '').toLowerCase()
  if (align) style.textAlign = align
  if (p.size) style.fontSize = `${p.size}pt`
  if (p.bold) style.fontWeight = '700'
  return style
}

function cellRows(cell: EditableCell): number {
  const length = String(cell.draft || '').length
  return Math.max(1, Math.min(8, Math.ceil(length / 14)))
}

/** 把后端返回的合并单元格原点还原成完整网格，避免表格错列。 */
function tableGrid(table: EditableTable) {
  const cells = table.rows.flat()
  const width = Math.max(
    1,
    ...cells.map((cell) => Number(cell.col || 0) + Number(cell.colspan || 1)),
  )
  const height = table.rows.length
  const matrix: Array<Array<{ cell: EditableCell; covered: boolean } | null>> =
    Array.from({ length: height }, () => Array(width).fill(null))
  for (const cell of cells) {
    const row = Number(cell.row || 0)
    const col = Number(cell.col || 0)
    const rowspan = Math.max(1, Number(cell.rowspan || 1))
    const colspan = Math.max(1, Number(cell.colspan || 1))
    if (row >= height || col >= width) continue
    matrix[row][col] = { cell, covered: false }
    for (let r = row; r < Math.min(height, row + rowspan); r += 1) {
      for (let c = col; c < Math.min(width, col + colspan); c += 1) {
        if (r === row && c === col) continue
        matrix[r][c] = { cell, covered: true }
      }
    }
  }
  return matrix
}

function scrollToParagraph(index: number) {
  document.getElementById(`doc-p-${index}`)?.scrollIntoView({
    behavior: 'smooth', block: 'center',
  })
}

function applyDocument(data: ReportDocument) {
  doc.value = data
  filepathInput.value = data.filepath
  selectedHistory.value = ''
  paragraphs.value = data.paragraphs.map((p) => ({ ...p, draft: p.text }))
  tables.value = data.tables.map((t) => ({
    ...t,
    rows: t.rows.map((row) => row.map((cell) => ({ ...cell, draft: cell.text }))),
  }))
}

async function loadDocument(filepath: string) {
  if (!filepath) return
  loading.value = true
  try {
    const data = await api.loadReportDocument(filepath)
    applyDocument(data)
    store.setStatus(`已加载报告：${data.filename}`)
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    history.value = await api.getReportHistory()
  } catch {
    /* api 层已提示 */
  }
}

function onSelectHistory(value: string) {
  if (value) void loadDocument(value)
}

function onLoadInput() {
  const path = filepathInput.value.trim()
  if (!path) {
    ElMessage.warning('请输入报告文件完整路径')
    return
  }
  void loadDocument(path)
}

function onReload() {
  if (doc.value) void loadDocument(doc.value.filepath)
}

function collectEdits() {
  const paragraphEdits = paragraphs.value
    .filter((p) => p.draft !== p.text)
    .map((p) => ({ index: p.index, text: p.draft }))
  const cellEdits: { table: number; row: number; col: number; text: string }[] = []
  for (const table of tables.value) {
    for (const row of table.rows) {
      for (const cell of row) {
        if (cell.draft !== cell.text) {
          cellEdits.push({
            table: table.index,
            row: cell.row,
            col: cell.col,
            text: cell.draft,
          })
        }
      }
    }
  }
  return { paragraphEdits, cellEdits }
}

async function saveDocument(overwrite: boolean) {
  if (!doc.value) return
  const { paragraphEdits, cellEdits } = collectEdits()
  if (!paragraphEdits.length && !cellEdits.length) {
    ElMessage.info('没有检测到修改')
    return
  }
  saving.value = true
  try {
    const result = await api.saveReportDocument({
      filepath: doc.value.filepath,
      paragraphs: paragraphEdits,
      cells: cellEdits,
      overwrite,
    })
    if (!result.saved) {
      ElMessage.info(result.message || '没有保存修改')
      return
    }
    ElMessage.success(
      `报告已保存（段落 ${result.changed_paragraphs ?? 0}，单元格 ${result.changed_cells ?? 0}）`,
    )
    await loadDocument(result.filepath)
  } catch {
    /* api 层已提示 */
  } finally {
    saving.value = false
  }
}

async function onSaveAsNew() {
  await saveDocument(false)
}

async function onOverwrite() {
  if (!doc.value) return
  try {
    await ElMessageBox.confirm(
      `将先备份原文件，再覆盖“${doc.value.filename}”。是否继续？`,
      '覆盖保存',
      { confirmButtonText: '覆盖保存', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await saveDocument(true)
}

async function onReplace() {
  if (!doc.value) return
  const find = findText.value
  if (!find) {
    ElMessage.warning('请输入查找内容')
    return
  }
  if (dirty.value) {
    await saveDocument(false)
    if (dirty.value) return
  }
  if (!doc.value) return
  replacing.value = true
  try {
    const result = await api.replaceReportText({
      filepath: doc.value.filepath,
      find,
      replace: replaceText.value,
      overwrite: false,
    })
    if (!result.saved) {
      ElMessage.info(result.message || '未找到要替换的内容')
      return
    }
    ElMessage.success(`已替换 ${result.replacements ?? 0} 处，并另存为新文件`)
    await loadDocument(result.filepath)
  } catch {
    /* api 层已提示 */
  } finally {
    replacing.value = false
  }
}

async function onDownload() {
  if (!doc.value) return
  if (dirty.value) {
    ElMessage.warning('有未保存修改，请先保存再下载')
    return
  }
  try {
    await api.downloadReportDocument(doc.value.filepath, doc.value.filename)
  } catch {
    /* api 层已提示 */
  }
}

async function onReveal() {
  if (!doc.value) return
  try {
    await api.revealFile(doc.value.filepath)
  } catch {
    /* api 层已提示 */
  }
}

onMounted(async () => {
  if (!store.initialized) {
    try {
      await store.init()
    } catch {
      /* 后端不可用时仍可手动输入路径 */
    }
  }
  await loadHistory()
  const fromQuery = String(route.query.filepath ?? '')
  if (fromQuery) {
    await loadDocument(fromQuery)
    return
  }
  const first = history.value.find((h) => h.exists)
  if (first) {
    selectedHistory.value = first.filepath
    await loadDocument(first.filepath)
  }
})
</script>

<template>
  <div class="report-edit-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/report')">返回报告</el-button>
        <h2>报告修改</h2>
      </div>
      <div class="page-actions">
        <el-tag v-if="dirty" type="warning" size="small">
          未保存：段落 {{ changedParagraphCount }} / 单元格 {{ changedCellCount }}
        </el-tag>
        <el-button :icon="Refresh" :loading="loading" @click="onReload" :disabled="!doc">重新加载</el-button>
        <el-button :icon="Download" @click="onDownload" :disabled="!doc">下载</el-button>
        <el-button @click="onSaveAsNew" :loading="saving" :disabled="!doc">另存为新文件</el-button>
        <el-button type="primary" @click="onOverwrite" :loading="saving" :disabled="!doc">覆盖保存</el-button>
      </div>
    </header>

    <div class="open-bar">
      <el-select
        v-model="selectedHistory"
        class="history-select"
        filterable
        clearable
        placeholder="从最近生成的报告中选择"
        @change="onSelectHistory"
      >
        <el-option
          v-for="h in history"
          :key="h.filepath"
          :label="`${h.generated_at} · ${h.filepath}`"
          :value="h.filepath"
          :disabled="!h.exists"
        />
      </el-select>
      <el-input v-model="filepathInput" class="path-input" placeholder="或输入报告 .docx 完整路径" clearable />
      <el-button @click="onLoadInput">加载</el-button>
      <el-button :icon="FolderOpened" :disabled="!doc" @click="onReveal">打开位置</el-button>
    </div>

    <div v-if="doc" class="doc-meta">
      <span>{{ doc.filename }}</span>
      <span>{{ doc.paragraph_count }} 段 · {{ doc.table_count }} 张表</span>
      <span>修改时间：{{ doc.modified_at }}</span>
    </div>

    <el-empty v-if="!doc && !loading" description="从上方选择或输入报告文件后开始修改" />

    <div v-if="doc" class="workspace">
      <aside class="doc-sidebar">
        <section class="side-card">
          <div class="side-title">文档大纲</div>
          <div class="outline-list">
            <button
              v-for="item in outline"
              :key="item.index"
              class="outline-item"
              @click="scrollToParagraph(item.index)"
            >
              {{ item.draft || item.text || '（空标题）' }}
            </button>
            <div v-if="!outline.length" class="side-empty">未识别到标题</div>
          </div>
        </section>

        <section class="side-card">
          <div class="side-title">查找替换</div>
          <el-input v-model="findText" size="small" placeholder="查找内容" clearable />
          <el-input v-model="replaceText" size="small" placeholder="替换为" clearable class="side-gap" />
          <el-button size="small" type="primary" :loading="replacing" class="side-gap" @click="onReplace">
            全部替换
          </el-button>
          <div class="side-hint">替换会先保存当前修改，再另存为新文件。</div>
        </section>

        <section class="side-card">
          <div class="side-title">文档信息</div>
          <div class="doc-meta-line">{{ doc.filename }}</div>
          <div class="doc-meta-line">{{ doc.paragraph_count }} 段 · {{ doc.table_count }} 张表</div>
          <div class="doc-meta-line">{{ doc.modified_at }}</div>
          <el-button size="small" :icon="FolderOpened" class="side-gap" @click="onReveal">
            打开文件位置
          </el-button>
        </section>
      </aside>

      <main class="document-scroll">
        <div class="zoom-bar">
          <span>页面视图</span>
          <el-slider v-model="zoom" :min="70" :max="130" :step="10" size="small" class="zoom-slider" />
          <span class="zoom-text">{{ zoom }}%</span>
        </div>

        <div class="document-page" :style="{ zoom: `${zoom}%` }">
          <template v-for="block in documentBlocks" :key="`${block.type}-${block.index}`">
            <div
              v-if="block.type === 'paragraph' && block.paragraph"
              :id="`doc-p-${block.paragraph.index}`"
              class="doc-paragraph"
              :class="paragraphClass(block.paragraph)"
            >
              <textarea
                v-model="block.paragraph.draft"
                :rows="paragraphRows(block.paragraph)"
                :style="paragraphStyle(block.paragraph)"
                spellcheck="false"
              />
            </div>

            <table
              v-else-if="block.type === 'table' && block.table"
              class="doc-table"
            >
              <tbody>
                <tr v-for="(gridRow, ri) in tableGrid(block.table)" :key="ri">
                  <template v-for="(entry, ci) in gridRow" :key="`${ri}-${ci}`">
                    <td
                      v-if="entry && !entry.covered"
                      :rowspan="Math.max(1, Number(entry.cell.rowspan || 1))"
                      :colspan="Math.max(1, Number(entry.cell.colspan || 1))"
                    >
                      <textarea
                        v-model="entry.cell.draft"
                        :rows="cellRows(entry.cell)"
                        spellcheck="false"
                      />
                    </td>
                    <td v-else-if="!entry" class="empty-cell"></td>
                    <!-- 被 rowspan/colspan 覆盖的位置不再输出 td，由浏览器自动占位 -->
                  </template>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.report-edit-view {
  height: 100%;
  overflow: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
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

.page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.open-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.history-select {
  width: 380px;
}

.path-input {
  flex: 1;
  min-width: 260px;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-wrap: wrap;
}

.workspace {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 12px;
  flex: 1;
  min-height: 0;
  height: calc(100vh - 220px);
}

.doc-sidebar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
  min-height: 0;
}

.side-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 9px;
  background: var(--el-bg-color);
  padding: 11px 12px;
}

.side-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.outline-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 260px;
  overflow: auto;
}

.outline-item {
  border: 0;
  background: transparent;
  text-align: left;
  padding: 4px 6px;
  border-radius: 5px;
  color: var(--el-text-color-regular);
  font-size: 11.5px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.outline-item:hover {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.side-empty {
  color: var(--el-text-color-placeholder);
  font-size: 11.5px;
  padding: 4px;
}

.side-gap {
  margin-top: 7px;
  width: 100%;
}

.side-hint {
  margin-top: 7px;
  color: var(--el-text-color-secondary);
  font-size: 10.5px;
  line-height: 1.5;
}

.doc-meta-line {
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
  line-height: 1.7;
  word-break: break-all;
}

.document-scroll {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  border-radius: 10px;
  background: #e8edf3;
  padding: 14px 18px 28px;
}

.zoom-bar {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 21cm;
  margin: 0 auto 10px;
  padding: 6px 10px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 2px 8px rgba(30, 50, 70, 0.08);
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
}

.zoom-slider {
  width: 140px;
}

.zoom-text {
  width: 38px;
  text-align: right;
}

.document-page {
  width: 21cm;
  min-height: 29.7cm;
  margin: 0 auto;
  padding: 2.2cm 2.3cm;
  background: #fff;
  box-shadow: 0 8px 28px rgba(30, 50, 70, 0.18);
  box-sizing: border-box;
  transform-origin: top center;
}

.doc-paragraph {
  margin: 0;
  padding: 0;
  min-height: 1.2em;
}

.doc-paragraph textarea {
  display: block;
  width: 100%;
  border: 0;
  outline: none;
  resize: none;
  overflow: hidden;
  background: transparent;
  color: #111;
  font-family: SimSun, "宋体", serif;
  font-size: 14px;
  line-height: 1.65;
  padding: 0;
  margin: 0;
}

.doc-heading textarea {
  font-family: SimHei, "黑体", sans-serif;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
}

.doc-report-number textarea {
  font-size: 12px;
}

.doc-empty {
  min-height: 10px;
}

.doc-empty textarea {
  font-size: 10px;
  line-height: 1.1;
}

.doc-table {
  width: 100%;
  margin: 8px 0;
  border-collapse: collapse;
  table-layout: fixed;
}

.doc-table td {
  border: 1px solid #222;
  padding: 3px 4px;
  vertical-align: middle;
  font-family: SimSun, "宋体", serif;
  font-size: 10.5px;
  line-height: 1.35;
  word-break: break-word;
}

.doc-table td textarea {
  display: block;
  width: 100%;
  border: 0;
  outline: none;
  resize: none;
  overflow: hidden;
  background: transparent;
  color: #111;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  padding: 0;
  margin: 0;
  text-align: inherit;
}

.doc-table .covered-cell {
  border: 0;
  padding: 0;
}

.doc-table .empty-cell {
  border: 1px solid #222;
}

@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: 1fr;
    height: auto;
  }
  .doc-sidebar {
    order: 2;
  }
  .document-scroll {
    max-height: 70vh;
  }
}
</style>
