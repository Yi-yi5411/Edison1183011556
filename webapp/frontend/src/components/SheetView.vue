<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import { ArrowDown, DocumentChecked, EditPen, Grid, Lock, Plus, Upload, UploadFilled } from '@element-plus/icons-vue'
import { copyToClipboard } from '@/utils/clipboard'
import type { VxeColumnPropTypes, VxeTableDefines, VxeTableInstance } from 'vxe-table'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'
import AssessmentDialog from '@/components/AssessmentDialog.vue'
import type {
  AssessmentResult,
  CellValue,
  ColumnDef,
  MergeRange,
  SheetRow,
  SheetRowLike,
} from '@/api/types'

const props = defineProps<{ sheetKey: string }>()
const store = useAppStore()

/** vxe-table 行对象：按列 key 展开存储，_rid 作行唯一键 */
interface TableRowData {
  _rid: string
  [key: string]: CellValue
}

const tableRef = ref<VxeTableInstance>()
const tableWrapRef = ref<HTMLElement>()
const tableData = ref<TableRowData[]>([])
const calcLoading = ref(false)
const exporting = ref(false)
/** 有未保存编辑时为 true */
const dirty = ref(false)
/** 自动保存失败时为 true（表格上方红色提示） */
const saveError = ref(false)
/** 本地隐藏的列 key（仅影响展示，不影响保存/计算） */
const hiddenCols = ref<string[]>([])
const assessmentVisible = ref(false)
const importVisible = ref(false)
const importFileList = ref<UploadUserFile[]>([])
const importAppend = ref(false)
const importing = ref(false)

/** 向 MainLayout 上报未保存状态（关闭标签页前确认用） */
const sheetDirtyMap = inject<Record<string, boolean>>('sheetDirtyMap', reactive<Record<string, boolean>>({}))

watch(
  dirty,
  (v) => {
    sheetDirtyMap[props.sheetKey] = v
  },
  { immediate: true },
)

const sheet = computed(() => store.sheets[props.sheetKey])
const assessment = computed<AssessmentResult | null>(
  () => sheet.value?.assessment?.result ?? null,
)
const assessmentTagType = computed(() =>
  assessment.value?.conclusion_type === '类型一' ? 'success' : 'warning',
)
const pluginName = computed(() => store.pluginMap.get(props.sheetKey)?.name ?? props.sheetKey)
const isBrick = computed(() => String(sheet.value?.base_item || props.sheetKey).includes('砖强度检测'))
const quickComponents = computed(() => {
  const values = new Set<string>()
  for (const row of tableData.value) {
    const comp = String(row['构件编号'] ?? '').trim()
    if (comp) values.add(comp)
  }
  if (!values.size) {
    for (let i = 1; i <= 10; i += 1) values.add(String(i))
  }
  return [...values].sort((a, b) => {
    const na = Number(a)
    const nb = Number(b)
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb
    return a.localeCompare(b, 'zh-CN')
  })
})
const quickPreview = computed(() => quickRows.value.map((row) => {
  const values = [row.v1, row.v2, row.v3, row.v4, row.v5]
    .map((v) => Number(String(v ?? '').replace(/,/g, '')))
    .filter((v) => Number.isFinite(v) && v > 0)
  if (!values.length) return { avg: '', strength: '' }
  const avg = values.reduce((a, b) => a + b, 0) / values.length
  const strength = 0.02 * avg ** 2 - 0.45 * avg + 1.25
  return {
    avg: avg.toFixed(1),
    strength: strength >= 0 ? strength.toFixed(2) : '',
  }
}))

const GENERIC_COMPONENT_FIELDS = [
  '楼栋', '楼层', '批次', '构件编号', '构件位置及名称', '构件位置及类型',
  '构件位置', '轴线编号', '轴号编号', '构件类型',
]
const genericComponentField = computed(() => {
  const keys = columnDefs.value.map((c) => c.key)
  return ['构件编号', '构件位置及名称', '构件位置及类型', '构件位置']
    .find((key) => keys.includes(key)) ?? ''
})
const genericHeaderColumns = computed(() => {
  const allowed = new Set(GENERIC_COMPONENT_FIELDS)
  return columnDefs.value.filter((c) => allowed.has(c.key) && c.editable !== false)
})
const genericHeaderKeys = computed(() => new Set(genericHeaderColumns.value.map((c) => c.key)))
const genericValueColumns = computed(() =>
  columnDefs.value.filter((c) => c.editable !== false && !genericHeaderKeys.value.has(c.key)),
)
const genericComponents = computed(() => {
  const field = genericComponentField.value
  if (!field) return []
  const values = new Set<string>()
  for (const row of tableData.value) {
    const value = String(row[field] ?? '').trim()
    if (value) values.add(value)
  }
  return [...values].sort((a, b) => {
    const na = Number(a)
    const nb = Number(b)
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb
    return a.localeCompare(b, 'zh-CN')
  })
})
const columnDefs = computed<ColumnDef[]>(() => normalizeColumns(sheet.value?.columns ?? []))
const columnKeys = computed(() => columnDefs.value.map((c) => c.key))
const visibleColumns = computed(() =>
  columnDefs.value.filter((c) => !hiddenCols.value.includes(c.key)),
)

/* ===== Excel 风格选区复制/粘贴 ===== */
interface CellPos {
  row: number
  col: number
}

interface CellRange {
  r1: number
  c1: number
  r2: number
  c2: number
}

const activeCell = ref<CellPos | null>(null)
const anchorCell = ref<CellPos | null>(null)
const selection = ref<CellRange | null>(null)
const mergeLoading = ref(false)
const smartMergeVisible = ref(false)
const smartMergeColumns = ref<number[]>([])
const headerSelectedColumns = ref<number[]>([])
const headerAnchorColumn = ref<number | null>(null)
const contextMenu = ref({ visible: false, x: 0, y: 0 })
const contextMenuRef = ref<HTMLElement>()
const batchInsertVisible = ref(false)
const batchInsertCount = ref(5)
const batchInsertAbove = ref(true)
const batchFillVisible = ref(false)
const batchFillMode = ref<'value' | 'increment' | 'down'>('value')
const batchFillValue = ref('')
const batchFillStep = ref('1')
const findVisible = ref(false)
const findText = ref('')
const replaceText = ref('')
const findScope = ref<'all' | 'selection'>('all')
const quickVisible = ref(false)
const quickSaving = ref(false)
const quickComponent = ref('')
const quickBatch = ref('')
const quickLocation = ref('')
const quickAxis = ref('')
const quickRows = ref<{ zone: string; v1: string; v2: string; v3: string; v4: string; v5: string; sourceIndex: number }[]>([])
const genericQuickVisible = ref(false)
const genericQuickSaving = ref(false)
const genericQuickComponent = ref('')
const genericQuickHeader = ref<Record<string, string>>({})
const genericQuickRows = ref<{ sourceIndex: number; values: Record<string, string> }[]>([])

/* ===== 列定义归一化（容忍字符串/对象两种形态） ===== */
/** 工作表快照的 columns 是字符串；从插件列定义补回宽度/类型/计算标记 */
function findColumnMeta(label: string): ColumnDef | undefined {
  const base = sheet.value?.base_item
  const all = store.plugins.flatMap((p) => p.columns ?? [])
  const matches = all.filter((c) => c.key === label || c.label === label)
  if (!matches.length) return undefined
  return matches.find((c) => !base || c.sub_item === base) ?? matches[0]
}

function estimateWidth(label: string): number {
  const length = [...String(label || '')].length
  return Math.max(110, Math.min(260, 15 * (length + 4) + 20))
}

function normalizeColumns(raw: ColumnDef[] | string[]): ColumnDef[] {
  return raw
    .map((item): ColumnDef => {
      if (typeof item === 'string') {
        const meta = findColumnMeta(item)
        return {
          key: item,
          label: item,
          type: meta?.type || 'text',
          width: meta?.width || estimateWidth(item),
          editable: meta ? (meta.editable !== false && !meta.calc) : true,
          calc: !!meta?.calc,
        }
      }
      return {
        key: item.key,
        label: item.label || item.key,
        type: item.type || 'text',
        width: item.width || estimateWidth(item.label || item.key),
        editable: item.editable !== false && !item.calc,
        calc: !!item.calc,
      }
    })
    .filter((c) => !!c.key)
}

/** 只读计算列（表头加锁提示） */
function isCalcColumn(col: ColumnDef): boolean {
  return !!col.calc || col.editable === false
}

/* ===== 行数据转换 ===== */
let ridSeed = 0

function buildTableRows(rows: SheetRowLike[]): TableRowData[] {
  const keys = columnKeys.value
  return rows.map((r) => {
    const obj: TableRowData = { _rid: `r${ridSeed++}` }
    if (Array.isArray(r)) {
      keys.forEach((k, i) => {
        obj[k] = r[i] ?? null
      })
    } else if (r && typeof r === 'object') {
      const rec = r as Record<string, CellValue>
      keys.forEach((k) => {
        obj[k] = rec[k] ?? null
      })
    }
    return obj
  })
}

function rowsToArray(): SheetRow[] {
  const keys = columnKeys.value
  return tableData.value.map((row) => keys.map((k) => row[k] ?? null))
}

/** 服务端返回计算后的行/合并：原地更新，保留选区与行对象 */
function applyServerRows(rows: SheetRow[], merges?: RawMerge[]) {
  const keys = columnKeys.value
  if (rows.length !== tableData.value.length) {
    tableData.value = buildTableRows(rows)
  } else {
    rows.forEach((r, ri) => {
      const target = tableData.value[ri]
      if (!target) return
      keys.forEach((k, ci) => {
        const value = Array.isArray(r) ? (r[ci] ?? null) : null
        if (target[k] !== value) target[k] = value
      })
    })
  }
  if (merges) {
    setServerMerges(merges)
  }
  void nextTick().then(() => applyMerges())
}

function setServerMerges(merges?: RawMerge[]) {
  if (!merges) return
  const target = store.sheets[props.sheetKey]
  if (target) target.merges = merges as unknown as MergeRange[]
}

function normalizeRange(a: CellPos, b: CellPos): CellRange {
  return {
    r1: Math.min(a.row, b.row),
    c1: Math.min(a.col, b.col),
    r2: Math.max(a.row, b.row),
    c2: Math.max(a.col, b.col),
  }
}

function onCellClick(params: Record<string, any>) {
  const field = params?.column?.field
  const rowIndex = Number(params?.rowIndex)
  const colIndex = visibleColumns.value.findIndex((c) => c.key === field)
  if (!field || !Number.isFinite(rowIndex) || colIndex < 0 || rowIndex < 0) return
  const pos: CellPos = { row: rowIndex, col: colIndex }
  const event = params?.$event as MouseEvent | undefined
  if (event?.shiftKey && anchorCell.value) {
    selection.value = normalizeRange(anchorCell.value, pos)
  } else {
    anchorCell.value = pos
    selection.value = normalizeRange(pos, pos)
  }
  activeCell.value = pos
  headerSelectedColumns.value = []
  headerAnchorColumn.value = null
  tableWrapRef.value?.focus()
}

function onHeaderClick(params: Record<string, any>) {
  const field = params?.column?.field
  const full = columnKeys.value.indexOf(field)
  if (full < 0) return
  const event = params?.$event as MouseEvent | undefined
  if (event?.ctrlKey || event?.metaKey) {
    const set = new Set(headerSelectedColumns.value)
    if (set.has(full)) set.delete(full)
    else set.add(full)
    headerSelectedColumns.value = [...set]
    headerAnchorColumn.value = full
  } else if (event?.shiftKey && headerAnchorColumn.value !== null) {
    const a = Math.min(headerAnchorColumn.value, full)
    const b = Math.max(headerAnchorColumn.value, full)
    headerSelectedColumns.value = Array.from({ length: b - a + 1 }, (_, i) => a + i)
  } else {
    headerSelectedColumns.value = [full]
    headerAnchorColumn.value = full
  }
  selection.value = null
  activeCell.value = null
}

function headerCellClassName(params: Record<string, any>): string {
  const full = columnKeys.value.indexOf(params?.column?.field)
  return full >= 0 && headerSelectedColumns.value.includes(full)
    ? 'header-col-selected'
    : ''
}

function onCellContextMenu(params: Record<string, any>) {
  const event = params?.$event as MouseEvent | undefined
  event?.preventDefault()
  const field = params?.column?.field
  const rowIndex = Number(params?.rowIndex)
  const colIndex = visibleColumns.value.findIndex((c) => c.key === field)
  if (!field || !Number.isFinite(rowIndex) || colIndex < 0 || rowIndex < 0) return
  const inside = selection.value
    && rowIndex >= selection.value.r1 && rowIndex <= selection.value.r2
    && colIndex >= selection.value.c1 && colIndex <= selection.value.c2
  if (!inside) {
    anchorCell.value = { row: rowIndex, col: colIndex }
    activeCell.value = { row: rowIndex, col: colIndex }
    selection.value = { r1: rowIndex, r2: rowIndex, c1: colIndex, c2: colIndex }
  }
  contextMenu.value = {
    visible: true,
    x: Math.max(8, Math.min(event?.clientX ?? 0, window.innerWidth - 230)),
    y: Math.max(8, Math.min(event?.clientY ?? 0, window.innerHeight - 600)),
  }
}

function formatCellValue(params: Record<string, any>): string | number {
  const label = String(params?.column?.title || '')
  const value = params?.cellValue
  if (label.includes('截面积') && value !== '' && value !== null && value !== undefined) {
    const num = Number(String(value).replace(/,/g, ''))
    if (Number.isFinite(num)) return num.toFixed(2)
  }
  return value === null || value === undefined ? '' : (value as string | number)
}

function cellClassName(params: Record<string, any>): string {
  const rowIndex = Number(params?.rowIndex)
  const field = params?.column?.field
  const colIndex = visibleColumns.value.findIndex((c) => c.key === field)
  if (!Number.isFinite(rowIndex) || colIndex < 0) return ''
  const fullCol = columnKeys.value.indexOf(field)
  const classes: string[] = []
  if (mergedAnchorKeys.value.has(`${rowIndex}:${fullCol}`)) classes.push('cell-merged')
  const range = selection.value
  if (range
    && rowIndex >= range.r1 && rowIndex <= range.r2
    && colIndex >= range.c1 && colIndex <= range.c2) {
    classes.push('cell-selected')
  }
  return classes.join(' ')
}

const selectionLabel = computed(() => {
  if (!selection.value) return ''
  const rows = selection.value.r2 - selection.value.r1 + 1
  const cols = selection.value.c2 - selection.value.c1 + 1
  return `${rows}×${cols}`
})

function escapeDelimited(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  if (/[\t\r\n"]/.test(text)) return '"' + text.replace(/"/g, '""') + '"'
  return text
}

function selectionText(): string {
  const range = selection.value
  if (!range) return ''
  const cols = visibleColumns.value
  const lines: string[] = []
  for (let r = range.r1; r <= range.r2; r += 1) {
    const cells: string[] = []
    for (let c = range.c1; c <= range.c2; c += 1) {
      const col = cols[c]
      if (!col) {
        cells.push('')
        continue
      }
      const fullCol = columnKeys.value.indexOf(col.key)
      const anchor = fullCol >= 0 ? mergeAnchor(r, fullCol) : undefined
      const valueRow = tableData.value[anchor?.sr ?? r]
      const valueKey = columnKeys.value[anchor?.sc ?? fullCol]
      cells.push(valueRow && valueKey ? escapeDelimited(valueRow[valueKey]) : '')
    }
    lines.push(cells.join('\t'))
  }
  return lines.join('\r\n')
}

function parseDelimited(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"'
          i += 1
        } else {
          quoted = false
        }
      } else {
        cell += ch
      }
    } else if (ch === '"') {
      quoted = true
    } else if (ch === '\t') {
      row.push(cell)
      cell = ''
    } else if (ch === '\n') {
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else if (ch !== '\r') {
      cell += ch
    }
  }
  row.push(cell)
  if (row.some((x) => x !== '') || rows.length === 0) rows.push(row)
  while (rows.length > 1 && rows[rows.length - 1].every((x) => x === '')) {
    rows.pop()
  }
  return rows
}

function ensureRow(index: number): TableRowData {
  while (tableData.value.length <= index) {
    const row: TableRowData = { _rid: `r${ridSeed++}` }
    for (const key of columnKeys.value) row[key] = ''
    tableData.value.push(row)
  }
  return tableData.value[index]
}

async function pasteText(text: string) {
  const rows = parseDelimited(text)
  const start = selection.value
    ? { row: selection.value.r1, col: selection.value.c1 }
    : activeCell.value
  if (!start) {
    ElMessage.warning('请先点击一个单元格，再粘贴')
    return
  }
  if (!rows.length || (rows.length === 1 && rows[0].length === 1 && rows[0][0] === '')) {
    ElMessage.warning('剪贴板没有可粘贴的数据')
    return
  }
  const cols = visibleColumns.value
  const singleColumn = rows.every((r) => r.length <= 1)
  const targets = new Map<string, { row: number; key: string; value: string }>()
  const used = new Set<string>()
  let skipped = 0

  for (let r = 0; r < rows.length; r += 1) {
    for (let c = 0; c < rows[r].length; c += 1) {
      const targetCol = start.col + c
      if (targetCol >= cols.length) break
      const sourceCol = cols[targetCol]
      const fullCol = columnKeys.value.indexOf(sourceCol.key)
      if (fullCol < 0) continue
      let targetRow = start.row + r
      let anchor = mergeAnchor(targetRow, fullCol)

      // 单列内容粘贴到纵向合并列：每个值占一个合并块，跳过已用锚点
      if (singleColumn) {
        let guard = 0
        while (anchor && used.has(`${anchor.sr}:${anchor.sc}`) && guard < 10000) {
          targetRow = anchor.er + 1
          ensureRow(targetRow)
          anchor = mergeAnchor(targetRow, fullCol)
          guard += 1
        }
      }

      const anchorRow = anchor?.sr ?? targetRow
      const anchorFullCol = anchor?.sc ?? fullCol
      const anchorKey = columnKeys.value[anchorFullCol]
      const anchorVisibleIndex = cols.findIndex((x) => x.key === anchorKey)
      const anchorCol = anchorVisibleIndex >= 0 ? cols[anchorVisibleIndex] : null
      if (!anchorCol || anchorCol.editable === false) {
        skipped += 1
        continue
      }

      const key = `${anchorRow}:${anchorFullCol}`
      const value = rows[r][c] ?? ''
      const existing = targets.get(key)
      if (value !== '' || !existing) {
        targets.set(key, { row: anchorRow, key: anchorKey, value })
      }
      used.add(key)
    }
  }

  if (!targets.size) {
    ElMessage.warning('粘贴区域没有可编辑单元格')
    return
  }

  for (const target of targets.values()) {
    const row = ensureRow(target.row)
    row[target.key] = target.value
  }

  const range = normalizeRange(
    start,
    { row: start.row + rows.length - 1, col: Math.min(start.col + rows[0].length - 1, cols.length - 1) },
  )
  selection.value = range
  anchorCell.value = start
  activeCell.value = start
  dirty.value = true
  scheduleSave()
  await nextTick()
  applyMerges()
  const suffix = skipped ? `，跳过 ${skipped} 个只读/隐藏单元格` : ''
  ElMessage.success(`已粘贴 ${targets.size} 个单元格${suffix}`)
}

function clearSelectionValues() {
  const range = selection.value
  if (!range) return
  const cols = visibleColumns.value
  const cleared = new Set<string>()
  for (let r = range.r1; r <= range.r2; r += 1) {
    for (let c = range.c1; c <= range.c2; c += 1) {
      const col = cols[c]
      if (!col) continue
      const fullCol = columnKeys.value.indexOf(col.key)
      if (fullCol < 0) continue
      const anchor = mergeAnchor(r, fullCol)
      const targetRow = anchor?.sr ?? r
      const targetFullCol = anchor?.sc ?? fullCol
      const targetKey = columnKeys.value[targetFullCol]
      const targetCol = cols.find((x) => x.key === targetKey)
      if (!targetCol || targetCol.editable === false) continue
      const key = `${targetRow}:${targetFullCol}`
      if (cleared.has(key)) continue
      cleared.add(key)
      const row = tableData.value[targetRow]
      if (row) row[targetKey] = ''
    }
  }
  dirty.value = true
  scheduleSave()
}

function clipboardAllowed(event: ClipboardEvent): boolean {
  const table = tableWrapRef.value
  if (!table) return false
  const target = event.target instanceof Node ? event.target : null
  const active = document.activeElement as Node | null
  const targetInTable = !!target && (target === table || table.contains(target))
  const activeInTable = !!active && (active === table || table.contains(active))
  // 复制事件通常落在当前焦点元素或 body；只有表格拥有焦点时才接管，
  // 避免抢走项目树、弹窗等地方的原生复制。
  const targetIsPage = target === document.body || target === document.documentElement
  if (!targetInTable && !(targetIsPage && activeInTable)) return false
  const editable = (node: Node | null) => {
    if (!node || !(node instanceof Element)) return false
    return !!node.closest('input, textarea, select, [contenteditable="true"], .el-select, .el-dialog')
  }
  return !editable(target) && !editable(active)
}

function onCopy(event: ClipboardEvent) {
  if (!clipboardAllowed(event)) return
  const text = selectionText()
  if (!text) return
  event.preventDefault()
  event.clipboardData?.setData('text/plain', text)
  ElMessage.success(`已复制 ${selectionLabel.value} 单元格`)
}

function onCut(event: ClipboardEvent) {
  if (!clipboardAllowed(event)) return
  const text = selectionText()
  if (!text) return
  event.preventDefault()
  event.clipboardData?.setData('text/plain', text)
  clearSelectionValues()
  ElMessage.success(`已剪切 ${selectionLabel.value} 单元格`)
}

function onPaste(event: ClipboardEvent) {
  if (!clipboardAllowed(event)) return
  const text = event.clipboardData?.getData('text/plain') ?? ''
  if (!text) return
  event.preventDefault()
  void pasteText(text)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeContextMenu()
  const table = tableWrapRef.value
  if (!table) return
  const active = document.activeElement
  if (!active || !table.contains(active)) return
  if (active instanceof Element
    && active.closest('input, textarea, select, [contenteditable="true"], .el-select, .el-dialog')) {
    return
  }
  if (!activeCell.value) return
  const pos = activeCell.value
  const col = visibleColumns.value[pos.col]
  const row = tableData.value[pos.row]
  if (!col || !row || col.editable === false) return

  if ((event.ctrlKey || event.metaKey) && event.code === 'Space') {
    event.preventDefault()
    selectEntireColumn()
    return
  }
  if (event.shiftKey && event.code === 'Space') {
    event.preventDefault()
    selectEntireRow()
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'h') {
    event.preventDefault()
    openFindReplace()
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'n') {
    event.preventDefault()
    openBatchInsert()
    return
  }

  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd') {
    event.preventDefault()
    void fillDownSelection()
    return
  }

  // Excel 习惯：单击选中后直接键入即可覆盖单元格；双击或 F2 进入编辑。
  if (event.key === 'F2') {
    const editor = tableRef.value as unknown as {
      setEditCell?: (row: TableRowData, field: string) => void
    }
    if (editor?.setEditCell) {
      editor.setEditCell(row, col.key)
      event.preventDefault()
    }
    return
  }

  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (event.ctrlKey || event.metaKey || event.altKey) return
    clearSelectionValues()
    event.preventDefault()
    return
  }

  if (event.ctrlKey || event.metaKey || event.altKey) return
  if (event.isComposing || event.key.length !== 1) return
  const editor = tableRef.value as unknown as {
    setEditCell?: (row: TableRowData, field: string) => void
  }
  if (!editor?.setEditCell) return
  row[col.key] = event.key
  editor.setEditCell(row, col.key)
  event.preventDefault()
}

/* ===== 编辑渲染器：数值列带输入校验，只读列不启用 ===== */
function editRenderFor(col: ColumnDef): VxeColumnPropTypes.EditRender | undefined {
  if (col.editable === false) return undefined
  const t = (col.type ?? 'text').toLowerCase()
  if (t === 'number' || t === 'float') return { name: 'VxeInput', props: { type: 'number' } }
  if (t === 'int' || t === 'integer') return { name: 'VxeInput', props: { type: 'integer' } }
  return { name: 'VxeInput' }
}

/* ===== 数据加载与合并展示 ===== */
let loadedOnce = false

async function reload() {
  const current = sheet.value
  tableData.value = current ? buildTableRows(current.rows ?? []) : []
  dirty.value = false
  selection.value = null
  activeCell.value = null
  anchorCell.value = null
  await nextTick()
  applyMerges()
  const hasValue = tableData.value.some((row) =>
    columnKeys.value.some((k) => String(row[k] ?? '').trim() !== ''),
  )
  if (!loadedOnce && hasValue && store.activeTab === props.sheetKey) {
    loadedOnce = true
    void runCalc()
  }
}

/** vxe-table 类型库未声明实例方法 setMergeCells（与同名 props 冲突），运行时存在，此处窄化断言 */
type MergeCellsMethod = (merges: VxeTableDefines.MergeOptions[]) => void

interface MergeBlock {
  sr: number
  sc: number
  er: number
  ec: number
}

type RawMerge = MergeRange | [number, number, number, number]

/** 后端 sheet_snapshot 的 merges 实际为 [row, col, rowSpan, colSpan] 数组，兼容对象形态 */
function parseMerge(raw: RawMerge): MergeBlock | null {
  if (Array.isArray(raw)) {
    const [sr, sc, rowSpan, colSpan] = raw
    if (![sr, sc, rowSpan, colSpan].every((n) => Number.isFinite(n))) return null
    return { sr, sc, er: sr + Math.max(1, rowSpan) - 1, ec: sc + Math.max(1, colSpan) - 1 }
  }
  if (!raw || typeof raw !== 'object') return null
  const sr = Number(raw.start_row)
  const sc = Number(raw.start_col)
  const er = Number(raw.end_row)
  const ec = Number(raw.end_col)
  if (![sr, sc, er, ec].every((n) => Number.isFinite(n))) return null
  return { sr, sc, er, ec }
}

/** 把后端合并坐标规整为 0-based，并过滤越界区域 */
function mergeBlocks(): MergeBlock[] {
  const rowCount = tableData.value.length
  const colCount = columnKeys.value.length
  const blocks: MergeBlock[] = []
  for (const raw of (sheet.value?.merges ?? []) as unknown as RawMerge[]) {
    const parsed = parseMerge(raw)
    if (!parsed) continue
    let { sr, sc, er, ec } = parsed
    // 兼容旧版 1-based 合并坐标
    if (er >= rowCount || ec >= colCount) {
      sr -= 1
      er -= 1
      sc -= 1
      ec -= 1
    }
    er = Math.min(er, rowCount - 1)
    ec = Math.min(ec, colCount - 1)
    if (sr < 0 || sc < 0 || er < sr || ec < sc) continue
    blocks.push({ sr, sc, er, ec })
  }
  return blocks
}

function mergeAnchor(row: number, col: number): MergeBlock | undefined {
  return mergeBlocks().find(
    (m) => row >= m.sr && row <= m.er && col >= m.sc && col <= m.ec,
  )
}

const mergedAnchorKeys = computed(() =>
  new Set(mergeBlocks().map((m) => `${m.sr}:${m.sc}`)),
)

function applyMerges() {
  const $table = tableRef.value
  if (!$table) return
  $table.clearMergeCells()
  const blocks = mergeBlocks()
  if (!blocks.length || !tableData.value.length) return
  const options: VxeTableDefines.MergeOptions[] = []
  for (const m of blocks) {
    const row = tableData.value[m.sr]
    const col = $table.getColumnByField(columnKeys.value[m.sc])
    if (!row || !col) continue
    options.push({
      row,
      col,
      rowspan: m.er - m.sr + 1,
      colspan: m.ec - m.sc + 1,
    })
  }
  if (options.length) {
    ;(tableRef.value as unknown as { setMergeCells: MergeCellsMethod }).setMergeCells(options)
  }
}

/* ===== 批量保存：失焦/回车触发，防抖后整体覆盖 PUT ===== */
let saveTimer: number | undefined

function scheduleSave() {
  dirty.value = true
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    void flushSave()
  }, 800)
}

async function flushSave(): Promise<void> {
  window.clearTimeout(saveTimer)
  if (!dirty.value) return
  dirty.value = false
  const rows = rowsToArray()
  store.setStatus(`「${pluginName.value}」保存中…`)
  try {
    const data = await api.putSheetRows(props.sheetKey, rows) as {
      rows?: SheetRow[]
      merges?: RawMerge[]
      recalc_error?: string
    }
    const savedRows = asRowsArray(data)
    applyServerRows(savedRows, data?.merges)
    store.patchSheetRows(props.sheetKey, savedRows)
    saveError.value = false
    if (data?.recalc_error) {
      store.setStatus(`「${pluginName.value}」已保存，自动计算提示：${data.recalc_error}`)
    } else {
      store.setStatus(`「${pluginName.value}」表格数据已自动保存并计算`)
    }
  } catch {
    dirty.value = true
    saveError.value = true
    store.setStatus(`「${pluginName.value}」自动保存失败，请检查后端服务后重试`)
  }
}

/** 保存失败后的手动重试 */
async function retrySave() {
  saveError.value = false
  await flushSave()
}

function onEditClosed() {
  scheduleSave()
}

onMounted(() => {
  window.addEventListener('copy', onCopy as EventListener)
  window.addEventListener('cut', onCut as EventListener)
  window.addEventListener('paste', onPaste as EventListener)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('click', onWindowClick)
  window.addEventListener('scroll', closeContextMenu, true)
  window.addEventListener('dsh-flush-sheets', onFlushRequest)
})

watch(
  () => props.sheetKey,
  () => {
    selection.value = null
    activeCell.value = null
    anchorCell.value = null
  },
)

watch(hiddenCols, () => {
  selection.value = null
  activeCell.value = null
  anchorCell.value = null
})

watch(
  () => store.activeTab,
  (active) => {
    if (active !== props.sheetKey || loadedOnce) return
    const hasValue = tableData.value.some((row) =>
      columnKeys.value.some((k) => String(row[k] ?? '').trim() !== ''),
    )
    if (!hasValue) return
    loadedOnce = true
    void runCalc()
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('copy', onCopy as EventListener)
  window.removeEventListener('cut', onCut as EventListener)
  window.removeEventListener('paste', onPaste as EventListener)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('click', onWindowClick)
  window.removeEventListener('scroll', closeContextMenu, true)
  window.removeEventListener('dsh-flush-sheets', onFlushRequest)
  void flushSave()
  delete sheetDirtyMap[props.sheetKey]
})

/* 项目重载 / 切换表签时先落盘再刷新 */
watch(
  [() => props.sheetKey, () => store.projectVersion],
  async () => {
    // 工程切换时只重新读取；不能再把旧工程的本地行 flush 到新工程
    await reload()
  },
  { immediate: true },
)

/* ===== 计算：后端 CalcEngine 自动计算列并回填 ===== */
function asRowsArray(data: unknown): SheetRow[] {
  const rows = Array.isArray(data)
    ? data
    : data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).rows)
      ? ((data as Record<string, unknown>).rows as unknown[])
      : null
  if (!rows) throw new Error('计算结果格式异常')
  return rows as SheetRow[]
}

async function runCalc() {
  await flushSave()
  calcLoading.value = true
  try {
    const data = await api.calcSheet(props.sheetKey, rowsToArray()) as {
      rows?: SheetRow[]
      merges?: RawMerge[]
    }
    const rows = asRowsArray(data)
    applyServerRows(rows, data?.merges)
    store.patchSheetRows(props.sheetKey, rows)
    store.setStatus(`「${pluginName.value}」计算完成`)
    await nextTick()
    applyMerges()
  } catch (err) {
    if (err instanceof Error && err.message === '计算结果格式异常') ElMessage.error(err.message)
  } finally {
    calcLoading.value = false
  }
}

/* ===== 导入数据文件（Excel / CSV / Word 表格） ===== */
function openImportDialog() {
  importFileList.value = []
  importAppend.value = false
  importVisible.value = true
}

async function submitImport() {
  const files: File[] = []
  for (const item of importFileList.value) {
    if (item.raw) files.push(item.raw as unknown as File)
  }
  if (!files.length) {
    ElMessage.warning('请先选择要导入的文件')
    return
  }
  importing.value = true
  try {
    await flushSave()
    let imported = 0
    const warnings: string[] = []
    for (let i = 0; i < files.length; i += 1) {
      // 多文件默认合并：第一个文件覆盖，后续追加；勾选“追加”则全部追加
      const data = await api.importSheetExcel(
        props.sheetKey,
        files[i],
        importAppend.value || i > 0,
      ) as {
        imported?: number
        warnings?: string[]
      }
      imported += Number(data?.imported ?? 0)
      if (data?.warnings?.length) warnings.push(...data.warnings)
    }
    await store.loadProject()
    importVisible.value = false
    importFileList.value = []
    const warn = warnings.length ? `（${warnings.length} 条提示）` : ''
    ElMessage.success(`已导入 ${files.length} 个文件，共 ${imported} 行数据${warn}`)
    store.setStatus(`文件导入完成：${files.length} 个文件 / ${imported} 行`)
  } catch {
    /* api 层已提示 */
  } finally {
    importing.value = false
  }
}

/* ===== 检测评定 ===== */
async function openAssessment() {
  await flushSave()
  assessmentVisible.value = true
}

async function onAssessmentDone() {
  await store.loadProject()
  store.setStatus('评定结果已保存，报告生成时将使用评定结论')
}

/* ===== 导出 Excel ===== */
async function exportExcel() {
  exporting.value = true
  try {
    const name = await api.exportSheet(props.sheetKey, `${pluginName.value}.xlsx`)
    store.setStatus(`已导出 Excel：${name}`)
  } catch {
    /* api 层已提示 */
  } finally {
    exporting.value = false
  }
}

function onMoreCommand(command: unknown) {
  const cmd = String(command)
  if (cmd === 'calc') void runCalc()
  if (cmd === 'export') void exportExcel()
}

function rawMergeToRange(raw: RawMerge): MergeRange | null {
  if (Array.isArray(raw)) {
    const [row, col, rowSpan, colSpan] = raw
    return {
      start_row: row,
      end_row: row + Math.max(1, rowSpan) - 1,
      start_col: col,
      end_col: col + Math.max(1, colSpan) - 1,
    }
  }
  return raw ?? null
}

async function mergeSelection() {
  if (!selection.value) {
    ElMessage.warning('请先选择要合并的单元格区域')
    return
  }
  const { r1, r2, c1, c2 } = selection.value
  if (r1 === r2 && c1 === c2) {
    ElMessage.warning('请至少选择 2 个单元格再合并')
    return
  }
  const startCol = visibleColumns.value[c1]
  const endCol = visibleColumns.value[c2]
  const startFullCol = columnKeys.value.indexOf(startCol?.key ?? '')
  const endFullCol = columnKeys.value.indexOf(endCol?.key ?? '')
  if (startFullCol < 0 || endFullCol < 0) return
  mergeLoading.value = true
  try {
    await flushSave()
    const data = await api.mergeSheet(props.sheetKey, [{
      start_row: r1,
      end_row: r2,
      start_col: startFullCol,
      end_col: endFullCol,
    }], true) as { merges?: RawMerge[] }
    setServerMerges(data?.merges)
    await nextTick()
    applyMerges()
    ElMessage.success('已合并居中')
  } catch {
    /* api 层已提示 */
  } finally {
    mergeLoading.value = false
  }
}

async function unmergeSelection() {
  const range = selection.value ?? (activeCell.value
    ? { r1: activeCell.value.row, r2: activeCell.value.row, c1: activeCell.value.col, c2: activeCell.value.col }
    : null)
  if (!range) {
    ElMessage.warning('请先选择要取消合并的单元格')
    return
  }
  const startCol = visibleColumns.value[range.c1]
  const endCol = visibleColumns.value[range.c2]
  const startFullCol = columnKeys.value.indexOf(startCol?.key ?? '')
  const endFullCol = columnKeys.value.indexOf(endCol?.key ?? '')
  if (startFullCol < 0 || endFullCol < 0) return
  const blocks = mergeBlocks().filter((m) => !(
    m.er < range.r1 || m.sr > range.r2 || m.ec < startFullCol || m.sc > endFullCol
  ))
  if (!blocks.length) {
    ElMessage.info('当前选区没有合并单元格')
    return
  }
  const removed = new Set(blocks.map((m) => `${m.sr}:${m.sc}`))
  const remaining: MergeRange[] = []
  for (const raw of (sheet.value?.merges ?? []) as unknown as RawMerge[]) {
    const item = rawMergeToRange(raw)
    if (!item) continue
    if (!removed.has(`${item.start_row}:${item.start_col}`)) remaining.push(item)
  }
  mergeLoading.value = true
  try {
    await flushSave()
    const data = await api.mergeSheet(props.sheetKey, remaining, false) as { merges?: RawMerge[] }
    setServerMerges(data?.merges)
    await nextTick()
    applyMerges()
    ElMessage.success('已取消合并')
  } catch {
    /* api 层已提示 */
  } finally {
    mergeLoading.value = false
  }
}

function onMergeCommand(command: unknown) {
  if (String(command) === 'merge') void mergeSelection()
  else if (String(command) === 'smart-merge') void openSmartMerge()
  else void unmergeSelection()
}

function selectedHeaderCandidates(): number[] {
  if (!headerSelectedColumns.value.length) return []
  const selected = new Set(headerSelectedColumns.value)
  return smartMergeCandidates.value
    .map((item) => item.index)
    .filter((index) => selected.has(index))
}

const SMART_MERGE_KEYWORDS = [
  '楼栋', '楼层', '批次', '构件编号', '构件位置', '构件名称',
  '轴线', '轴号', '检测部位', '构件类型', '部位',
]
const SMART_MERGE_EXCLUDED = ['备注', '结论', '序号']

/** 智能合并可处理的列（与后端候选列保持一致；砖强度另含统计列） */
const smartMergeCandidates = computed(() => {
  const brickStats = new Set([0, 1, 2, 3, 12, 13, 14, 15, 16, 17, 18])
  return columnDefs.value
    .map((col, index) => ({ col, index }))
    .filter(({ col, index }) => {
      if (isBrick.value) return brickStats.has(index)
      const label = String(col.label || '')
      if (!label || SMART_MERGE_EXCLUDED.some((w) => label.includes(w))) return false
      return SMART_MERGE_KEYWORDS.some((w) => label.includes(w))
    })
})

function columnIndexAtVisible(visibleIndex: number): number {
  const key = visibleColumns.value[visibleIndex]?.key
  return key ? columnKeys.value.indexOf(key) : -1
}

function defaultSmartMergeColumns(): number[] {
  if (headerSelectedColumns.value.length) {
    return selectedHeaderCandidates()
  }
  if (selection.value) {
    const selected = new Set<number>()
    const start = Math.min(selection.value.c1, selection.value.c2)
    const end = Math.max(selection.value.c1, selection.value.c2)
    for (let visible = start; visible <= end; visible += 1) {
      const index = columnIndexAtVisible(visible)
      if (index >= 0) selected.add(index)
    }
    if (selected.size) {
      return smartMergeCandidates.value
        .map((item) => item.index)
        .filter((index) => selected.has(index))
    }
  }
  if (activeCell.value) {
    const index = columnIndexAtVisible(activeCell.value.col)
    if (smartMergeCandidates.value.some((item) => item.index === index)) return [index]
  }
  return smartMergeCandidates.value.map((item) => item.index)
}

function openSmartMerge() {
  const defaults = defaultSmartMergeColumns()
  if (!defaults.length) {
    ElMessage.warning(headerSelectedColumns.value.length
      ? '所选列中没有可智能合并的分组列'
      : '请先点击列头选择要合并的列（Ctrl/Shift 可多选）')
    return
  }
  smartMergeColumns.value = defaults
  smartMergeVisible.value = true
}

function selectAllSmartMergeColumns() {
  smartMergeColumns.value = smartMergeCandidates.value.map((item) => item.index)
}

async function confirmSmartMerge() {
  if (!smartMergeColumns.value.length) {
    ElMessage.warning('请至少勾选一列再合并')
    return
  }
  mergeLoading.value = true
  try {
    await flushSave()
    const data = await api.smartMergeSheet(
      props.sheetKey, smartMergeColumns.value,
    ) as { merges?: RawMerge[]; merged_columns?: number[] }
    setServerMerges(data.merges)
    await nextTick()
    applyMerges()
    smartMergeVisible.value = false
    const count = Array.isArray(data.merged_columns) ? data.merged_columns.length : smartMergeColumns.value.length
    ElMessage.success(isBrick.value
      ? `已按批次/构件合并 ${count} 列`
      : `已智能合并 ${count} 个分组列`)
  } catch {
    /* api 层已提示 */
  } finally {
    mergeLoading.value = false
  }
}

function closeContextMenu() {
  contextMenu.value.visible = false
}

function onWindowClick(event: MouseEvent) {
  if (!contextMenu.value.visible) return
  const target = event.target
  if (contextMenuRef.value && target instanceof Node
    && contextMenuRef.value.contains(target)) return
  closeContextMenu()
}

function onFlushRequest(event: Event) {
  const detail = (event as CustomEvent<{ wait?: (p: Promise<void>) => void }>).detail
  const pending = flushSave()
  if (detail?.wait) detail.wait(pending)
  else void pending
}

async function copySelectionToClipboard() {
  const text = selectionText()
  if (!text) {
    ElMessage.warning('请先选择要复制的单元格')
    return false
  }
  const ok = await copyToClipboard(text)
  if (ok) ElMessage.success(`已复制 ${selectionLabel.value} 单元格`)
  else ElMessage.warning('复制失败，请使用 Ctrl+C')
  return ok
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    if (!text) {
      ElMessage.warning('剪贴板为空')
      return
    }
    await pasteText(text)
  } catch {
    ElMessage.warning('浏览器未授权读取剪贴板，请使用 Ctrl+V 粘贴')
  }
}

async function insertRowAt(above: boolean) {
  const row = selection.value?.r1 ?? activeCell.value?.row ?? 0
  const index = above ? row : row + 1
  try {
    await flushSave()
    const data = await api.insertSheetRows(props.sheetKey, index, 1) as {
      rows?: SheetRow[]
      merges?: RawMerge[]
    }
    applyServerRows(data.rows ?? [], data.merges)
    await nextTick()
    applyMerges()
    const col = selection.value?.c1 ?? 0
    selection.value = { r1: index, r2: index, c1: col, c2: col }
    anchorCell.value = { row: index, col }
    activeCell.value = { row: index, col }
    ElMessage.success(above ? '已在上方插入行' : '已在下方插入行')
  } catch {
    /* api 层已提示 */
  }
}

async function deleteSelectedRows() {
  if (!selection.value) {
    ElMessage.warning('请先选择要删除的行')
    return
  }
  const { r1, r2 } = selection.value
  const count = r2 - r1 + 1
  try {
    await ElMessageBox.confirm(`确定删除第 ${r1 + 1}~${r2 + 1} 行？`, '删除行', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await flushSave()
    const data = await api.deleteSheetRows(props.sheetKey, r1, count) as {
      rows?: SheetRow[]
      merges?: RawMerge[]
    }
    applyServerRows(data.rows ?? [], data.merges)
    await nextTick()
    applyMerges()
    selection.value = null
    activeCell.value = null
    anchorCell.value = null
    ElMessage.success(`已删除 ${count} 行`)
  } catch {
    /* api 层已提示 */
  }
}

async function fillDownSelection() {
  if (!selection.value || selection.value.r1 >= selection.value.r2) {
    ElMessage.warning('请选择至少两行')
    return
  }
  const range = selection.value
  const cols = visibleColumns.value.slice(range.c1, range.c2 + 1)
  try {
    await flushSave()
    const data = await api.fillDown(
      props.sheetKey,
      cols.map((c) => c.key),
      range.r1,
      range.r2,
    ) as { rows?: SheetRow[] }
    if (data.rows) applyServerRows(data.rows)
    await runCalc()
    ElMessage.success('已向下填充')
  } catch {
    /* api 层已提示 */
  }
}

async function autoSumSelection() {
  if (!selection.value) {
    ElMessage.warning('请先选择要汇总的单元格')
    return
  }
  const range = selection.value
  const cols = visibleColumns.value
  const values: number[] = []
  for (let r = range.r1; r <= range.r2; r += 1) {
    const row = tableData.value[r]
    if (!row) continue
    for (let c = range.c1; c <= range.c2; c += 1) {
      const col = cols[c]
      const raw = col ? row[col.key] : null
      const n = Number(String(raw ?? '').replace(/,/g, ''))
      if (Number.isFinite(n) && String(raw ?? '').trim() !== '') values.push(n)
    }
  }
  if (!values.length) {
    ElMessage.info('选区内没有可求和的数字')
    return
  }
  const sum = values.reduce((a, b) => a + b, 0)
  const avg = sum / values.length
  await ElMessageBox.alert(
    `数值个数：${values.length}\n合计：${sum.toFixed(4).replace(/\.?0+$/, '')}\n平均值：${avg.toFixed(4).replace(/\.?0+$/, '')}`,
    '选区汇总',
    { confirmButtonText: '关闭' },
  )
}

function loadQuickComponent() {
  const comp = String(quickComponent.value || '').trim()
  const source = tableData.value
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => String(row['构件编号'] ?? '').trim() === comp)
    .sort((a, b) => Number(a.row['测区号'] || 0) - Number(b.row['测区号'] || 0))
  quickRows.value = source.map(({ row, index }) => ({
    zone: String(row['测区号'] ?? ''),
    v1: String(row['回弹值1'] ?? ''),
    v2: String(row['回弹值2'] ?? ''),
    v3: String(row['回弹值3'] ?? ''),
    v4: String(row['回弹值4'] ?? ''),
    v5: String(row['回弹值5'] ?? ''),
    sourceIndex: index,
  }))
  const first = source[0]?.row
  if (first) {
    if (!quickBatch.value) quickBatch.value = String(first['批次'] ?? '')
    quickLocation.value = String(first['构件位置及类型'] ?? '')
    quickAxis.value = String(first['轴号编号'] ?? '')
  }
}

function openQuickEntry() {
  if (!tableData.value.length) {
    ElMessage.warning('当前工作表没有数据行')
    return
  }
  if (!isBrick.value) {
    openGenericQuickEntry()
    return
  }
  const first = tableData.value.find((row) =>
    String(row['构件编号'] ?? '').trim() !== '') ?? tableData.value[0]
  quickComponent.value = String(first?.['构件编号'] ?? quickComponents.value[0] ?? '1')
  quickBatch.value = String(first?.['批次'] ?? '')
  quickLocation.value = String(first?.['构件位置及类型'] ?? '')
  quickAxis.value = String(first?.['轴号编号'] ?? '')
  loadQuickComponent()
  quickVisible.value = true
}

function loadGenericComponent() {
  const field = genericComponentField.value
  const component = genericQuickComponent.value
  const source = tableData.value
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => String(row[field] ?? '').trim() === component)
  const header: Record<string, string> = {}
  for (const col of genericHeaderColumns.value) {
    header[col.key] = String(source[0]?.row[col.key] ?? '')
  }
  if (field) header[field] = component
  genericQuickHeader.value = header
  genericQuickRows.value = source.length
    ? source.map(({ row, index }) => {
        const values: Record<string, string> = {}
        for (const col of genericValueColumns.value) {
          values[col.key] = String(row[col.key] ?? '')
        }
        return { sourceIndex: index, values }
      })
    : [{ sourceIndex: -1, values: blankGenericValues() }]
}

function blankGenericValues(): Record<string, string> {
  const values: Record<string, string> = {}
  for (const col of genericValueColumns.value) values[col.key] = ''
  return values
}

function addGenericQuickRow() {
  genericQuickRows.value.push({
    sourceIndex: -1,
    values: blankGenericValues(),
  })
}

function openGenericQuickEntry() {
  const field = genericComponentField.value
  if (!field) {
    ElMessage.warning('当前表格没有构件编号或构件位置列，无法使用快速录入')
    return
  }
  // 尚未录入构件时也允许直接开始，不再要求先回主表建构件
  genericQuickComponent.value = genericComponents.value[0] || '1'
  loadGenericComponent()
  genericQuickVisible.value = true
}

async function saveGenericQuickEntry() {
  if (!genericQuickRows.value.length) {
    ElMessage.warning('当前构件没有可保存的数据行')
    return
  }
  genericQuickSaving.value = true
  try {
    const field = genericComponentField.value
    if (field) genericQuickHeader.value[field] = genericQuickComponent.value
    for (const item of genericQuickRows.value) {
      if (item.sourceIndex < 0) {
        const index = tableData.value.length
        ensureRow(index)
        item.sourceIndex = index
      }
      const row = tableData.value[item.sourceIndex]
      if (!row) continue
      for (const [key, value] of Object.entries(genericQuickHeader.value)) {
        row[key] = value
      }
      for (const [key, value] of Object.entries(item.values)) {
        row[key] = value
      }
    }
    dirty.value = true
    await flushSave()
    try {
      const merged = await api.smartMergeSheet(props.sheetKey) as { merges?: RawMerge[] }
      setServerMerges(merged.merges)
      await nextTick()
      applyMerges()
    } catch {
      /* 合并失败不阻断保存 */
    }
    genericQuickVisible.value = false
    ElMessage.success('构件数据已保存并自动计算')
  } catch {
    /* api 层已提示 */
  } finally {
    genericQuickSaving.value = false
  }
}

async function saveQuickEntry(goNext = false) {
  if (!quickRows.value.length) {
    ElMessage.warning('当前构件没有可保存的测区行')
    return
  }
  quickSaving.value = true
  try {
    for (const item of quickRows.value) {
      const row = tableData.value[item.sourceIndex]
      if (!row) continue
      row['批次'] = quickBatch.value
      row['构件编号'] = quickComponent.value
      row['构件位置及类型'] = quickLocation.value
      row['轴号编号'] = quickAxis.value
      row['测区号'] = item.zone
      row['回弹值1'] = item.v1
      row['回弹值2'] = item.v2
      row['回弹值3'] = item.v3
      row['回弹值4'] = item.v4
      row['回弹值5'] = item.v5
    }
    dirty.value = true
    await flushSave()
    if (isBrick.value) {
      try {
        const merged = await api.smartMergeSheet(props.sheetKey) as { merges?: RawMerge[] }
        setServerMerges(merged.merges)
        await nextTick()
        applyMerges()
      } catch {
        /* 合并失败不阻断保存 */
      }
    }
    const currentIndex = quickComponents.value.indexOf(quickComponent.value)
    if (goNext && currentIndex >= 0 && currentIndex < quickComponents.value.length - 1) {
      quickComponent.value = quickComponents.value[currentIndex + 1]
      loadQuickComponent()
      ElMessage.success('已保存，已切换到下一构件')
    } else {
      quickVisible.value = false
      ElMessage.success('砖回弹数据已保存并自动计算')
    }
  } catch {
    /* api 层已提示 */
  } finally {
    quickSaving.value = false
  }
}

async function runContextAction(action: string) {
  closeContextMenu()
  if (action === 'copy') await copySelectionToClipboard()
  else if (action === 'cut') {
    if (await copySelectionToClipboard()) clearSelectionValues()
  } else if (action === 'paste') await pasteFromClipboard()
  else if (action === 'clear') clearSelectionValues()
  else if (action === 'merge') await mergeSelection()
  else if (action === 'unmerge') await unmergeSelection()
  else if (action === 'insert-above') await insertRowAt(true)
  else if (action === 'insert-below') await insertRowAt(false)
  else if (action === 'delete-rows') await deleteSelectedRows()
  else if (action === 'fill-down') await fillDownSelection()
  else if (action === 'sum') await autoSumSelection()
  else if (action === 'batch-insert') openBatchInsert()
  else if (action === 'batch-fill') openBatchFill()
  else if (action === 'find') openFindReplace()
  else if (action === 'select-row') selectEntireRow()
  else if (action === 'select-col') selectEntireColumn()
  else if (action === 'hide-cols') hideSelectedColumns()
  else if (action === 'show-cols') showAllColumns()
}

function selectEntireRow() {
  const row = selection.value?.r1 ?? activeCell.value?.row
  if (row === undefined) return
  selection.value = { r1: row, r2: row, c1: 0, c2: visibleColumns.value.length - 1 }
  anchorCell.value = { row, col: 0 }
  activeCell.value = { row, col: 0 }
}

function selectEntireColumn() {
  const col = selection.value?.c1 ?? activeCell.value?.col
  if (col === undefined || !tableData.value.length) return
  selection.value = { r1: 0, r2: tableData.value.length - 1, c1: col, c2: col }
  anchorCell.value = { row: 0, col }
  activeCell.value = { row: 0, col }
}

function hideSelectedColumns() {
  if (!selection.value) {
    ElMessage.warning('请先选择要隐藏的列')
    return
  }
  const cols = visibleColumns.value.slice(selection.value.c1, selection.value.c2 + 1)
  if (!cols.length) return
  const next = [...new Set([...hiddenCols.value, ...cols.map((c) => c.key)])]
  if (next.length >= columnDefs.value.length) {
    ElMessage.warning('至少需要保留一列')
    return
  }
  hiddenCols.value = next
}

function showAllColumns() {
  hiddenCols.value = []
}

function openBatchInsert() {
  if (!selection.value && !activeCell.value) {
    ElMessage.warning('请先选择插入位置')
    return
  }
  batchInsertCount.value = 5
  batchInsertAbove.value = true
  batchInsertVisible.value = true
}

async function confirmBatchInsert() {
  const row = selection.value?.r1 ?? activeCell.value?.row ?? 0
  const index = batchInsertAbove.value ? row : row + 1
  const count = Math.max(1, Math.min(200, Number(batchInsertCount.value) || 1))
  try {
    await flushSave()
    const data = await api.insertSheetRows(props.sheetKey, index, count) as {
      rows?: SheetRow[]
      merges?: RawMerge[]
    }
    applyServerRows(data.rows ?? [], data.merges)
    await nextTick()
    applyMerges()
    batchInsertVisible.value = false
    selection.value = null
    activeCell.value = null
    anchorCell.value = null
    ElMessage.success(`已插入 ${count} 行`)
  } catch {
    /* api 层已提示 */
  }
}

function openBatchFill() {
  if (!selection.value || (selection.value.r1 === selection.value.r2 && selection.value.c1 === selection.value.c2)) {
    ElMessage.warning('请先选择要填充的单元格区域')
    return
  }
  batchFillMode.value = 'value'
  batchFillValue.value = ''
  batchFillStep.value = '1'
  batchFillVisible.value = true
}

async function confirmBatchFill() {
  const range = selection.value
  if (!range) return
  const cols = visibleColumns.value.slice(range.c1, range.c2 + 1)
  const editableCols = cols.filter((c) => c.editable !== false)
  if (!editableCols.length) {
    ElMessage.warning('选区没有可编辑列')
    return
  }
  const values = batchFillValue.value.split(/[,，\s]+/).filter(Boolean)
  const start = Number(values[0] ?? batchFillValue.value)
  const step = Number(batchFillStep.value || '1')
  if ((batchFillMode.value === 'increment') && (!Number.isFinite(start) || !Number.isFinite(step))) {
    ElMessage.warning('起始值和步长必须是数字')
    return
  }
  for (const col of editableCols) {
    const firstValue = tableData.value[range.r1]?.[col.key] ?? ''
    for (let r = range.r1; r <= range.r2; r += 1) {
      const row = tableData.value[r]
      if (!row) continue
      if (batchFillMode.value === 'down') {
        if (r > range.r1) row[col.key] = firstValue
      } else if (batchFillMode.value === 'value') {
        row[col.key] = batchFillValue.value
      } else {
        const value = start + (r - range.r1) * step
        row[col.key] = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)))
      }
    }
  }
  dirty.value = true
  batchFillVisible.value = false
  await flushSave()
  ElMessage.success('批量填充完成')
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function collectFindMatches() {
  const needle = findText.value.trim()
  if (!needle) return []
  const regex = new RegExp(escapeRegExp(needle), 'i')
  const cols = visibleColumns.value
  const range = findScope.value === 'selection' ? selection.value : null
  const rows = range
    ? Array.from({ length: range.r2 - range.r1 + 1 }, (_, i) => range.r1 + i)
    : tableData.value.map((_, i) => i)
  const colRange = range
    ? Array.from({ length: range.c2 - range.c1 + 1 }, (_, i) => range.c1 + i)
    : cols.map((_, i) => i)
  const matches: { row: number; col: number }[] = []
  for (const r of rows) {
    const row = tableData.value[r]
    if (!row) continue
    for (const c of colRange) {
      const col = cols[c]
      if (col && regex.test(String(row[col.key] ?? ''))) matches.push({ row: r, col: c })
    }
  }
  return matches
}

function openFindReplace() {
  findText.value = ''
  replaceText.value = ''
  findScope.value = 'all'
  findVisible.value = true
}

function findNextMatch() {
  const matches = collectFindMatches()
  if (!matches.length) {
    ElMessage.info('没有找到匹配内容')
    return
  }
  const first = matches[0]
  anchorCell.value = { row: first.row, col: first.col }
  activeCell.value = { row: first.row, col: first.col }
  selection.value = { r1: first.row, r2: first.row, c1: first.col, c2: first.col }
  ElMessage.success(`找到 ${matches.length} 个匹配单元格`)
}

async function replaceAllMatches() {
  const needle = findText.value.trim()
  if (!needle) {
    ElMessage.warning('请输入查找内容')
    return
  }
  const regex = new RegExp(escapeRegExp(needle), 'gi')
  const cols = visibleColumns.value
  const range = findScope.value === 'selection' ? selection.value : null
  const rows = range
    ? Array.from({ length: range.r2 - range.r1 + 1 }, (_, i) => range.r1 + i)
    : tableData.value.map((_, i) => i)
  const colRange = range
    ? Array.from({ length: range.c2 - range.c1 + 1 }, (_, i) => range.c1 + i)
    : cols.map((_, i) => i)
  let cells = 0
  for (const r of rows) {
    const row = tableData.value[r]
    if (!row) continue
    for (const c of colRange) {
      const col = cols[c]
      if (!col || col.editable === false) continue
      const text = String(row[col.key] ?? '')
      if (!regex.test(text)) continue
      regex.lastIndex = 0
      row[col.key] = text.replace(regex, replaceText.value)
      cells += 1
    }
  }
  if (!cells) {
    ElMessage.info('没有可替换的内容')
    return
  }
  dirty.value = true
  findVisible.value = false
  await flushSave()
  ElMessage.success(`已替换 ${cells} 个单元格`)
}
</script>

<template>
  <div class="sheet-view">
    <div class="sheet-toolbar">
      <el-button :loading="calcLoading" @click="runCalc">计算</el-button>
      <el-button type="primary" :icon="DocumentChecked" @click="openAssessment">
        评定 / 结论
      </el-button>
      <el-button :icon="Upload" :loading="importing" @click="openImportDialog">导入文件</el-button>
      <el-button :icon="EditPen" @click="openQuickEntry">快速录入</el-button>
      <el-dropdown trigger="click" @command="onMoreCommand">
        <el-button :loading="exporting">
          更多
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export">导出 Excel</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-popover placement="bottom-start" :width="240" trigger="click">
        <template #reference>
          <el-button :icon="Grid">列</el-button>
        </template>
        <div class="col-filter-hint">勾选以显示或隐藏列（仅影响本地展示，不影响保存）</div>
        <el-checkbox-group v-model="hiddenCols" class="col-filter-list">
          <el-checkbox v-for="col in columnDefs" :key="col.key" :value="col.key">{{ col.label }}</el-checkbox>
        </el-checkbox-group>
      </el-popover>
      <el-dropdown trigger="click" @command="onMergeCommand">
        <el-button
          :loading="mergeLoading"
          title="点击列头可直接选列；Ctrl/Shift 可多选，智能合并只处理选中列"
        >
          合并
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="merge">合并居中</el-dropdown-item>
            <el-dropdown-item command="smart-merge">{{ isBrick ? '按批次/构件智能合并' : '智能合并' }}</el-dropdown-item>
            <el-dropdown-item command="unmerge">取消合并</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="toolbar-spacer" />
      <span class="sheet-meta">{{ pluginName }}</span>
      <el-tag v-if="headerSelectedColumns.length" size="small" type="primary">
        已选 {{ headerSelectedColumns.length }} 列
      </el-tag>
      <el-tag size="small" effect="plain" type="info">{{ tableData.length }} 行</el-tag>
      <el-tag v-if="dirty" size="small" type="warning">未保存</el-tag>
      <el-tooltip
        v-if="assessment?.ok"
        :content="assessment.conclusion || ''"
        placement="top"
        :show-after="200"
      >
        <el-tag :type="assessmentTagType" size="small">评定：{{ assessment.conclusion_type }}</el-tag>
      </el-tooltip>
      <el-tag v-else-if="assessment && !assessment.ok" size="small" type="danger">
        评定未通过
      </el-tag>
    </div>

    <el-alert v-if="saveError" class="save-alert" type="error" show-icon @close="saveError = false">
      <template #title>自动保存失败，本次修改可能未同步到后端</template>
      <el-button size="small" type="danger" plain @click="retrySave">重试保存</el-button>
    </el-alert>

    <div class="sheet-table-wrap" ref="tableWrapRef" tabindex="0">
      <vxe-table
        ref="tableRef"
        :data="tableData"
        height="auto"
        auto-resize
        border
        stripe
        keep-source
        show-overflow
        show-header-overflow
        :row-config="{ keyField: '_rid', isHover: true }"
        :column-config="{ resizable: true }"
        :edit-config="{ trigger: 'dblclick', mode: 'cell', showStatus: true }"
        :keyboard-config="{ isClip: false }"
        :mouse-config="{ selected: true }"
        :menu-config="{ body: { options: [] } }"
        :scroll-y="{ enabled: true, gt: 200 }"
        :cell-class-name="cellClassName"
        :header-cell-class-name="headerCellClassName"
        class="sheet-table"
        @header-cell-click="onHeaderClick"
        @cell-click="onCellClick"
        @cell-menu="onCellContextMenu"
        @edit-closed="onEditClosed"
      >
        <template #empty>
          <el-empty :image-size="80" description="暂无数据，点击表头下方输入行或直接双击单元格录入" />
        </template>
        <vxe-column type="seq" title="#" width="52" fixed="left" />
        <vxe-column
          v-for="col in columnDefs"
          :key="col.key"
          :field="col.key"
          :title="col.label"
          :width="col.width"
          :visible="!hiddenCols.includes(col.key)"
          :edit-render="editRenderFor(col)"
          :formatter="formatCellValue"
          :class-name="col.editable === false ? 'cell-readonly' : ''"
        >
          <template v-if="isCalcColumn(col)" #header>
            <span class="col-header">
              {{ col.label }}
              <el-tooltip content="自动计算列，由系统计算" placement="top" :show-after="200">
                <el-icon class="col-lock"><Lock /></el-icon>
              </el-tooltip>
            </span>
          </template>
        </vxe-column>
      </vxe-table>
    </div>

    <div
      v-if="contextMenu.visible"
      ref="contextMenuRef"
      class="sheet-context-menu"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      @click.stop
      @contextmenu.prevent
    >
      <button type="button" @click="runContextAction('copy')">复制<em>Ctrl+C</em></button>
      <button type="button" @click="runContextAction('cut')">剪切<em>Ctrl+X</em></button>
      <button type="button" @click="runContextAction('paste')">粘贴<em>Ctrl+V</em></button>
      <button type="button" @click="runContextAction('clear')">清空内容<em>Delete</em></button>
      <div class="menu-separator" />
      <button type="button" @click="runContextAction('merge')">合并居中</button>
      <button type="button" @click="runContextAction('unmerge')">取消合并</button>
      <div class="menu-separator" />
      <button type="button" @click="runContextAction('insert-above')">上方插入行</button>
      <button type="button" @click="runContextAction('insert-below')">下方插入行</button>
      <button type="button" @click="runContextAction('delete-rows')">删除选中行</button>
      <button type="button" @click="runContextAction('batch-insert')">批量插入行…</button>
      <div class="menu-separator" />
      <button type="button" @click="runContextAction('fill-down')">向下填充<em>Ctrl+D</em></button>
      <button type="button" @click="runContextAction('batch-fill')">批量填充…</button>
      <button type="button" @click="runContextAction('sum')">选区汇总</button>
      <div class="menu-separator" />
      <button type="button" @click="runContextAction('select-row')">选中整行</button>
      <button type="button" @click="runContextAction('select-col')">选中整列</button>
      <button type="button" @click="runContextAction('hide-cols')">隐藏选中列</button>
      <button type="button" @click="runContextAction('show-cols')">显示全部列</button>
      <div class="menu-separator" />
      <button type="button" @click="runContextAction('find')">查找替换…<em>Ctrl+H</em></button>
    </div>

    <el-dialog
      v-model="smartMergeVisible"
      title="智能合并 — 选择要合并的列"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="只合并下面勾选的分组列，未勾选的列不会参与；上一次自动合并产生的同列旧合并会被清除。"
        style="margin-bottom: 12px"
      />
      <div class="smart-merge-tools">
        <el-button size="small" text @click="selectAllSmartMergeColumns">全选可合并列</el-button>
        <el-button size="small" text @click="smartMergeColumns = []">清空</el-button>
        <span class="smart-merge-count">已选 {{ smartMergeColumns.length }} 列</span>
      </div>
      <el-checkbox-group v-model="smartMergeColumns" class="smart-merge-list">
        <el-checkbox
          v-for="item in smartMergeCandidates"
          :key="item.index"
          :value="item.index"
        >
          {{ item.col.label }}
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="smartMergeVisible = false">取消</el-button>
        <el-button type="primary" :loading="mergeLoading" @click="confirmSmartMerge">
          只合并勾选列
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="quickVisible" title="砖回弹快速录入" width="900px" top="5vh" :close-on-click-modal="false">
      <div class="quick-head">
        <el-form inline label-width="72px" class="quick-form">
          <el-form-item label="构件编号">
            <el-select
              v-model="quickComponent"
              filterable
              style="width: 110px"
              @change="loadQuickComponent"
            >
              <el-option v-for="comp in quickComponents" :key="comp" :label="`构件 ${comp}`" :value="comp" />
            </el-select>
          </el-form-item>
          <el-form-item label="批次">
            <el-input v-model="quickBatch" placeholder="批次" style="width: 100px" />
          </el-form-item>
          <el-form-item label="构件位置">
            <el-input v-model="quickLocation" placeholder="如 1FQ 1" style="width: 170px" />
          </el-form-item>
          <el-form-item label="轴号">
            <el-input v-model="quickAxis" placeholder="可选" style="width: 120px" />
          </el-form-item>
        </el-form>
        <div class="quick-meta">
          当前 {{ quickRows.length }} 个测区 · 保存后自动计算构件平均强度和批次评定
        </div>
      </div>

      <el-table
        v-if="quickRows.length"
        :data="quickRows"
        border
        size="small"
        max-height="430"
        class="quick-table"
      >
        <el-table-column prop="zone" label="测区" width="58" align="center" />
        <el-table-column label="回弹值1" width="92">
          <template #default="{ row }"><el-input v-model="row.v1" size="small" inputmode="decimal" /></template>
        </el-table-column>
        <el-table-column label="回弹值2" width="92">
          <template #default="{ row }"><el-input v-model="row.v2" size="small" inputmode="decimal" /></template>
        </el-table-column>
        <el-table-column label="回弹值3" width="92">
          <template #default="{ row }"><el-input v-model="row.v3" size="small" inputmode="decimal" /></template>
        </el-table-column>
        <el-table-column label="回弹值4" width="92">
          <template #default="{ row }"><el-input v-model="row.v4" size="small" inputmode="decimal" /></template>
        </el-table-column>
        <el-table-column label="回弹值5" width="92">
          <template #default="{ row }"><el-input v-model="row.v5" size="small" inputmode="decimal" /></template>
        </el-table-column>
        <el-table-column label="平均回弹值" width="100" align="center">
          <template #default="{ $index }">{{ quickPreview[$index]?.avg || '—' }}</template>
        </el-table-column>
        <el-table-column label="强度换算值" width="110" align="center">
          <template #default="{ $index }">{{ quickPreview[$index]?.strength || '—' }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else :image-size="60" description="当前构件没有测区行，请检查构件编号" />

      <div class="quick-tip">
        每个测区录 5 个回弹值，按 Tab 可在 5 个输入框之间快速切换；保存后由后端统一计算。
      </div>
      <template #footer>
        <el-button @click="quickVisible = false">取消</el-button>
        <el-button type="primary" :loading="quickSaving" @click="saveQuickEntry(false)">保存本构件</el-button>
        <el-button :loading="quickSaving" @click="saveQuickEntry(true)">保存并下一构件</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="genericQuickVisible" title="快速录入" width="1100px" top="5vh" :close-on-click-modal="false">
      <div class="quick-head">
        <el-form inline label-width="86px" class="quick-form">
          <el-form-item label="构件">
            <el-select
              v-model="genericQuickComponent"
              filterable
              allow-create
              default-first-option
              style="width: 180px"
              @change="loadGenericComponent"
            >
              <el-option v-for="comp in genericComponents" :key="comp" :label="comp" :value="comp" />
            </el-select>
          </el-form-item>
          <el-form-item v-for="col in genericHeaderColumns" :key="col.key" :label="col.label">
            <el-input
              v-model="genericQuickHeader[col.key]"
              :placeholder="col.label"
              style="width: 130px"
            />
          </el-form-item>
        </el-form>
        <div class="quick-meta">
          <span>当前构件 {{ genericQuickRows.length }} 行 · 可直接输入新构件编号，编辑后保存自动计算</span>
          <el-button link size="small" :icon="Plus" @click="addGenericQuickRow">添加一行</el-button>
        </div>
      </div>

      <el-table
        v-if="genericQuickRows.length"
        :data="genericQuickRows"
        border
        size="small"
        max-height="440"
        class="quick-table"
      >
        <el-table-column type="index" label="#" width="48" align="center" />
        <el-table-column
          v-for="col in genericValueColumns"
          :key="col.key"
          :label="col.label"
          :min-width="Math.max(110, Number(col.width) || 110)"
        >
          <template #default="{ row }">
            <el-input v-model="row.values[col.key]" size="small" />
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else :image-size="60" description="当前构件没有数据行" />

      <div class="quick-tip">
        按构件集中录入，避免在整张表中来回滚动；保存后自动触发计算和分组合并。
      </div>
      <template #footer>
        <el-button @click="genericQuickVisible = false">取消</el-button>
        <el-button type="primary" :loading="genericQuickSaving" @click="saveGenericQuickEntry">
          保存本构件
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchInsertVisible" title="批量插入行" width="420px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="插入位置">
          <el-radio-group v-model="batchInsertAbove">
            <el-radio :value="true">当前行上方</el-radio>
            <el-radio :value="false">当前行下方</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="插入行数">
          <el-input-number v-model="batchInsertCount" :min="1" :max="200" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchInsertVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmBatchInsert">插入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchFillVisible" title="批量填充" width="480px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="填充方式">
          <el-radio-group v-model="batchFillMode">
            <el-radio value="value">固定值</el-radio>
            <el-radio value="increment">递增序列</el-radio>
            <el-radio value="down">向下填充首值</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="batchFillMode !== 'down'" :label="batchFillMode === 'increment' ? '起始值' : '填充值'">
          <el-input v-model="batchFillValue" placeholder="请输入内容" />
        </el-form-item>
        <el-form-item v-if="batchFillMode === 'increment'" label="步长">
          <el-input v-model="batchFillStep" placeholder="如 1" />
        </el-form-item>
      </el-form>
      <div class="dialog-tip">只填充选区内可编辑列，计算列不会被覆盖。</div>
      <template #footer>
        <el-button @click="batchFillVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmBatchFill">填充</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="findVisible" title="查找替换" width="480px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="查找内容">
          <el-input v-model="findText" placeholder="输入要查找的文字或数字" @keyup.enter="findNextMatch" />
        </el-form-item>
        <el-form-item label="替换为">
          <el-input v-model="replaceText" placeholder="可留空表示删除匹配内容" />
        </el-form-item>
        <el-form-item label="查找范围">
          <el-radio-group v-model="findScope">
            <el-radio value="all">整张工作表</el-radio>
            <el-radio value="selection" :disabled="!selection">当前选区</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="findVisible = false">关闭</el-button>
        <el-button @click="findNextMatch">查找</el-button>
        <el-button type="primary" @click="replaceAllMatches">全部替换</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="导入数据文件" width="560px" :close-on-click-modal="false">
      <el-upload
        v-model:file-list="importFileList"
        drag
        multiple
        :auto-upload="false"
        :limit="20"
        accept=".xlsx,.xlsm,.csv,.docx"
      >
        <el-icon class="import-upload-icon"><UploadFilled /></el-icon>
        <div class="import-upload-text">拖拽文件到此处，或点击选择</div>
        <div class="import-upload-hint">
          支持 Excel（.xlsx/.xlsm）、CSV、Word 表格（.docx），可一次选择多个文件
        </div>
      </el-upload>
      <div class="import-options">
        <el-checkbox v-model="importAppend">追加到现有数据（不覆盖）</el-checkbox>
        <span class="import-order">多文件按选择顺序解析，默认第一个覆盖、后续追加</span>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <AssessmentDialog
      v-model="assessmentVisible"
      :sheet-key="props.sheetKey"
      @done="onAssessmentDone"
    />
  </div>
</template>

<style scoped>
.sheet-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sheet-toolbar {
  flex: none;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.header-col-selected) {
  background: var(--el-color-primary-light-8) !important;
  color: var(--el-color-primary) !important;
}

.smart-merge-tools {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}

.smart-merge-count {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.smart-merge-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 12px;
  max-height: 320px;
  overflow-y: auto;
  padding: 4px 2px;
}

.toolbar-spacer {
  flex: 1;
}

.sheet-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.save-alert {
  flex: none;
}

.col-header {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.col-lock {
  font-size: 12px;
  color: var(--el-color-warning);
  cursor: help;
}

.col-filter-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.col-filter-list {
  display: flex;
  flex-direction: column;
  max-height: 260px;
  overflow: auto;
}

.sheet-table-wrap {
  flex: 1;
  min-height: 0;
  outline: none;
}

.sheet-table-wrap:focus {
  outline: none;
}

.sheet-table :deep(.cell-selected) {
  background-color: var(--el-color-primary-light-8) !important;
  box-shadow: inset 0 0 0 1px var(--el-color-primary-light-5);
}

.sheet-table :deep(.cell-selected:hover) {
  background-color: var(--el-color-primary-light-7) !important;
}

.sheet-table :deep(.cell-merged) .vxe-cell {
  justify-content: center;
  text-align: center;
}

.sheet-table {
  width: 100%;
}

.sheet-context-menu {
  position: fixed;
  z-index: 3000;
  width: 210px;
  padding: 5px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color-overlay);
  box-shadow: 0 10px 30px rgba(20, 40, 60, 0.18);
  max-height: calc(100vh - 16px);
  overflow-y: auto;
}

.sheet-context-menu button {
  width: 100%;
  height: 30px;
  padding: 0 9px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sheet-context-menu button:hover {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.sheet-context-menu em {
  font-style: normal;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.menu-separator {
  height: 1px;
  margin: 4px 6px;
  background: var(--el-border-color-lighter);
}

.dialog-tip {
  padding: 8px 10px;
  border-radius: 7px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.quick-head {
  margin-top: -4px;
}

.quick-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 8px;
}

.quick-form :deep(.el-form-item) {
  margin-bottom: 6px;
}

.quick-meta {
  margin: 0 0 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.quick-table :deep(.el-input__inner) {
  text-align: center;
  padding: 0 4px;
}

.quick-tip {
  margin-top: 9px;
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
}

.import-upload-icon {
  font-size: 34px;
  color: var(--el-color-primary);
  margin-bottom: 6px;
}

.import-upload-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.import-upload-hint {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}

.import-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.import-order {
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}
</style>
