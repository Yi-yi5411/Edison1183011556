<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import { ArrowRight, Back, DataLine, Picture, Promotion } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { ScanFileResult, ScanRunResult } from '@/api/types'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()

const ACCEPT = '.jpg,.jpeg,.png,.bmp,.webp,.pdf'
const MAX_IMAGES = 10

/* ===== 文件选择与预览 ===== */
const fileList = ref<UploadUserFile[]>([])

/** 文件大小格式化（文件名 + 大小标签） */
function sizeText(size?: number): string {
  if (typeof size !== 'number') return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function removeFile(f: UploadUserFile) {
  fileList.value = fileList.value.filter((x) => x.uid !== f.uid)
}

function onExceed() {
  ElMessage.warning(`最多选择 ${MAX_IMAGES} 张图片，请先移除已选图片再添加`)
}

/** el-upload 文件列表 → File 数组（UploadRawFile 兼容 File） */
function pickFiles(): File[] {
  const files: File[] = []
  for (const f of fileList.value) {
    if (f.raw) files.push(f.raw)
  }
  return files
}

/* ===== 视觉模型下拉（GET /api/scan/vision_models，选中持久化 localStorage） ===== */
const VISION_MODEL_KEY = 'wb-vision-model'
const models = ref<string[]>([])
const visionModel = ref(localStorage.getItem(VISION_MODEL_KEY) ?? '')

watch(visionModel, (v) => {
  try {
    if (v) localStorage.setItem(VISION_MODEL_KEY, v)
    else localStorage.removeItem(VISION_MODEL_KEY)
  } catch {
    /* 存储不可用时忽略 */
  }
})

async function loadModels() {
  try {
    const data = await api.scanVisionModels()
    models.value = data.models ?? []
  } catch {
    /* api 层已提示 */
  }
}

/* ===== 识别目标检测项目下拉（来自插件子项，键名即后端 ITEM_COLUMNS 键） ===== */
interface DetectionOption {
  group: string
  items: { value: string; label: string }[]
}

const detectionOptions = computed<DetectionOption[]>(() => {
  const groups: DetectionOption[] = []
  const seen = new Set<string>()
  for (const p of store.plugins) {
    const items: { value: string; label: string }[] = []
    for (const sub of p.sub_items ?? []) {
      if (seen.has(sub.name)) continue
      seen.add(sub.name)
      items.push({ value: sub.name, label: sub.name })
    }
    if (items.length) groups.push({ group: p.name, items })
  }
  return groups
})

const detectionItem = ref('') // 空 = 由 AI 自动判定检测项目

/* ===== 开始识别（同步长任务：进度面板 + 已用时计时） ===== */
const running = ref(false)
const runResult = ref<ScanRunResult | null>(null)

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

async function onRun() {
  const files = pickFiles()
  if (!files.length) {
    ElMessage.warning('请先选择要识别的图片/PDF 文件')
    return
  }
  running.value = true
  startTimer()
  try {
    const data = await api.scanRun(files, detectionItem.value || undefined)
    runResult.value = data
    const okCount = data.files.filter((f) => !f.error).length
    ElMessage.success(
      `识别完成：成功 ${okCount}/${data.files.length} 个文件，共 ${data.field_warnings.length} 处需人工复核`,
    )
    store.setStatus(`扫描识别完成：${okCount}/${data.files.length} 个文件识别成功`)
  } catch {
    /* api 层已提示 */
  } finally {
    stopTimer()
    running.value = false
  }
}

/* ===== 结果展示：按文件分组（文件名小标题 + 预览表 + 警告逐条） ===== */
const fileResults = computed<ScanFileResult[]>(() => runResult.value?.files ?? [])

/* 对齐行数组 → 表格行对象（c0..cn 按列头顺序） */
interface ResultRow {
  _idx: number
  [col: string]: string | number
}

function fileRows(f: ScanFileResult): ResultRow[] {
  const rows = f.rows ?? []
  return rows.map((cells, i) => {
    const obj: ResultRow = { _idx: i + 1 }
    cells.forEach((v, ci) => {
      obj[`c${ci}`] = v ?? ''
    })
    return obj
  })
}

/* ===== 回填到目标工作表 ===== */
const targetSheet = ref('')
const fillingName = ref('') // 正在回填的文件名（逐文件 loading）
const filledInfo = ref<{ sheet: string; count: number } | null>(null)

/* 目标工作表选项：显示各表 key 与行数 */
const sheetOptions = computed(() =>
  Object.entries(store.sheets).map(([key, sheet]) => ({
    value: key,
    label: `${key}（${sheet.rows?.length ?? 0} 行）`,
  })),
)

async function onFill(f: ScanFileResult) {
  if (f.error) {
    ElMessage.warning(`该文件识别失败，无法回填：${f.error}`)
    return
  }
  if (!f.rows.length) {
    ElMessage.warning('该文件没有识别出可回填的数据行')
    return
  }
  if (!targetSheet.value) {
    ElMessage.warning('请选择回填的目标工作表')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将把 ${f.rows.length} 行记录回填到「${targetSheet.value}」，已存在的同键数据如何处理以后端逻辑为准。是否继续？`,
      '回填确认',
      { type: 'warning', confirmButtonText: '确认回填', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  fillingName.value = f.filename
  try {
    await api.scanFill(targetSheet.value, f.rows)
    await store.loadProject()
    filledInfo.value = { sheet: targetSheet.value, count: f.rows.length }
    ElNotification({
      title: '回填成功',
      message: `已将 ${f.rows.length} 行记录回填到「${targetSheet.value}」`,
      type: 'success',
      duration: 6000,
    })
    store.setStatus(`扫描识别结果已回填：${targetSheet.value}（${f.rows.length} 行）`)
  } catch {
    /* api 层已提示 */
  } finally {
    fillingName.value = ''
  }
}

onMounted(() => {
  void loadModels()
})
</script>

<template>
  <div class="scan-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/internal')">返回工具</el-button>
        <h2>扫描识别</h2>
      </div>
    </header>

    <!-- 识别进度面板：逐文件同步处理，给固定阶段提示与已用时 -->
    <el-card v-if="running" shadow="never" class="progress-card">
      <div class="progress-body">
        <el-icon class="is-loading progress-icon"><DataLine /></el-icon>
        <div>
          <div class="progress-title">视觉模型识别中，每张图约数十秒…请勿关闭页面</div>
          <div class="progress-sub">
            识别为逐文件同步处理，暂无法展示单文件进度 · 已用时 {{ elapsedText }}
          </div>
        </div>
      </div>
      <el-progress :percentage="50" :show-text="false" status="warning" class="progress-bar" />
    </el-card>

    <!-- 识别设置 -->
    <el-card shadow="never">
      <template #header>识别设置</template>
      <div class="setup-row">
        <el-upload
          v-model:file-list="fileList"
          list-type="picture-card"
          :auto-upload="false"
          multiple
          :accept="ACCEPT"
          :limit="MAX_IMAGES"
          :on-exceed="onExceed"
        >
          <el-icon :size="20"><Picture /></el-icon>
        </el-upload>
        <div v-if="fileList.length" class="picked-info">
          已选 {{ fileList.length }} / {{ MAX_IMAGES }} 张
        </div>
      </div>
      <!-- 已选文件标签（图片名 + 大小，可单个移除） -->
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
      <div class="option-row">
        <span class="option-label">视觉模型</span>
        <el-select v-model="visionModel" clearable placeholder="自动探测本地视觉模型" class="option-select">
          <el-option v-for="m in models" :key="m" :label="m" :value="m" />
        </el-select>
        <span class="option-label">识别目标</span>
        <el-select v-model="detectionItem" clearable placeholder="由 AI 自动判定检测项目" class="option-select">
          <el-option-group v-for="g in detectionOptions" :key="g.group" :label="g.group">
            <el-option v-for="it in g.items" :key="it.value" :label="it.label" :value="it.value" />
          </el-option-group>
        </el-select>
        <el-button
          type="primary"
          :icon="DataLine"
          :loading="running"
          :disabled="!fileList.length"
          @click="onRun"
        >
          开始识别
        </el-button>
        <span class="run-tip">单张图片约 1~2 分钟，最多 {{ MAX_IMAGES }} 张，多图逐张识别</span>
      </div>
    </el-card>

    <el-card v-if="!fileResults.length" shadow="never" class="help-card">
      <template #header>识别流程</template>
      <div class="help-steps">
        <div class="help-step">
          <span class="help-num">1</span>
          <div><b>选择原始记录图片</b><p>支持 JPG / PNG / PDF，最多 {{ MAX_IMAGES }} 张；手写或打印表格均可。</p></div>
        </div>
        <div class="help-step">
          <span class="help-num">2</span>
          <div><b>选择视觉模型与识别目标</b><p>可自动探测本地模型，也可指定检测项目；AI 判定仅供参考。</p></div>
        </div>
        <div class="help-step">
          <span class="help-num">3</span>
          <div><b>核对并回填</b><p>识别结果逐文件展示，可编辑后回填到当前项目的工作表。</p></div>
        </div>
      </div>
    </el-card>

    <!-- 识别结果：按文件分组展示 -->
    <el-card v-if="fileResults.length" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>识别结果（共 {{ fileResults.length }} 个文件）</span>
          <div class="fill-row">
            <span class="option-label">目标工作表</span>
            <el-select
              v-model="targetSheet"
              placeholder="选择回填的目标工作表"
              class="sheet-select"
              clearable
              filterable
            >
              <el-option v-for="it in sheetOptions" :key="it.value" :label="it.label" :value="it.value" />
            </el-select>
          </div>
        </div>
      </template>

      <!-- 回填成功提示 + 跳转 -->
      <el-alert v-if="filledInfo" type="success" show-icon :closable="false" class="filled-alert">
        <template #title>
          <span>已将 {{ filledInfo.count }} 行记录回填到「{{ filledInfo.sheet }}」</span>
          <el-button
            type="primary"
            size="small"
            :icon="ArrowRight"
            style="margin-left: 12px"
            @click="router.push('/project')"
          >
            跳转到项目页查看
          </el-button>
        </template>
      </el-alert>

      <div v-for="f in fileResults" :key="f.filename" class="file-group">
        <div class="file-title">
          <span class="file-name">{{ f.filename }}</span>
          <el-tag v-if="f.detection_item" size="small" effect="plain">
            检测项目：{{ f.detection_item }}
          </el-tag>
          <el-tag v-if="f.sub_item" size="small" effect="plain">子项：{{ f.sub_item }}</el-tag>
          <el-tag size="small" :type="f.error ? 'danger' : f.rows.length ? 'success' : 'warning'">
            {{ f.error ? '识别失败' : `${f.rows.length} 行数据` }}
          </el-tag>
          <el-button
            type="success"
            size="small"
            :icon="Promotion"
            :loading="fillingName === f.filename"
            :disabled="!!f.error || !f.rows.length"
            class="fill-btn"
            @click="onFill(f)"
          >
            回填本文件
          </el-button>
        </div>

        <el-alert
          v-if="f.error"
          type="error"
          show-icon
          :closable="false"
          class="file-alert"
          :title="`识别失败：${f.error}`"
        />
        <template v-else>
          <!-- field_warnings 黄色警示逐条列出；无警告显示绿色"识别干净" -->
          <el-alert
            v-if="f.field_warnings.length"
            type="warning"
            show-icon
            :closable="false"
            class="file-alert"
            :title="`本文件 ${f.field_warnings.length} 处字段需人工复核：`"
          >
            <ul class="warn-list">
              <li v-for="(w, i) in f.field_warnings" :key="i">{{ w }}</li>
            </ul>
          </el-alert>
          <el-alert
            v-else
            type="success"
            show-icon
            :closable="false"
            class="file-alert"
            title="识别干净，无需复核"
          />

          <el-table
            v-if="f.rows.length"
            :data="fileRows(f)"
            border
            stripe
            size="small"
            max-height="320"
            class="result-table"
          >
            <el-table-column type="index" label="#" width="52" fixed="left" />
            <el-table-column
              v-for="(col, ci) in f.columns"
              :key="`${col}-${ci}`"
              :prop="`c${ci}`"
              :label="col"
              min-width="110"
            />
          </el-table>
          <el-empty v-else description="未识别出数据行" :image-size="60" />
        </template>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.scan-view {
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

.setup-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.setup-row :deep(.el-upload--picture-card) {
  width: 84px;
  height: 84px;
  line-height: 86px;
}

.setup-row :deep(.el-upload-list--picture-card .el-upload-list__item) {
  width: 84px;
  height: 84px;
}

.picked-info {
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

.option-row {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.option-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.option-select {
  width: 220px;
}

.run-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.result-card {
  flex: none;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.fill-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sheet-select {
  width: 260px;
}

.filled-alert {
  margin-bottom: 12px;
}

.filled-alert :deep(.el-alert__title) {
  display: inline-flex;
  align-items: center;
}

/* 文件分组 */
.file-group + .file-group {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.file-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.file-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.fill-btn {
  margin-left: auto;
}

.file-alert {
  margin: 0 0 10px;
}

.warn-list {
  margin: 6px 0 0;
  padding-left: 18px;
}

.warn-list li {
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.result-table {
  width: 100%;
}
</style>
