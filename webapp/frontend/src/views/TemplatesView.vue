<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back,
  Delete,
  Download,
  Refresh,
  Star,
  Upload,
  View,
} from '@element-plus/icons-vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'
import type { OriginalTemplateInfo, ReportTemplateInfo } from '@/api/types'

const router = useRouter()
const store = useAppStore()

const activeTab = ref<'report' | 'original'>('report')
const loading = ref(false)
const reportTemplates = ref<ReportTemplateInfo[]>([])
const originalTemplates = ref<OriginalTemplateInfo[]>([])
const defaults = ref<Record<string, string>>({})

/* 检测项目基础名（树中项目名，不含构件后缀） */
const baseItemOptions = computed(() => {
  const groups: { label: string; options: { label: string; value: string }[] }[] = []
  for (const p of store.plugins) {
    const items = Object.keys(p.tree ?? {})
    if (!items.length) continue
    groups.push({
      label: p.structure_type || '其他',
      options: items.map((item) => ({ label: item, value: item })),
    })
  }
  return groups
})

const baseItemLabels = computed(() => {
  const map = new Map<string, string>()
  for (const group of baseItemOptions.value) {
    for (const opt of group.options) map.set(opt.value, opt.label)
  }
  return map
})

function engineLabel(engine: string): string {
  if (engine === 'native_docx') return '系统原生'
  if (engine === 'docx_import') return '导入 DOCX'
  return 'DOC 存档'
}

function engineTagType(engine: string): 'success' | 'primary' | 'info' {
  if (engine === 'native_docx') return 'success'
  if (engine === 'docx_import') return 'primary'
  return 'info'
}

function itemLabel(item: string): string {
  return baseItemLabels.value.get(item) ?? item
}

async function loadTemplates() {
  loading.value = true
  try {
    await Promise.all([store.loadReportTemplates(), store.loadOriginalTemplates()])
    reportTemplates.value = store.reportTemplates
    originalTemplates.value = store.originalTemplates
    defaults.value = store.originalDefaults
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    if (!store.initialized) await store.init()
    else if (!store.plugins.length) await store.loadPlugins()
  } catch {
    /* 后端不可用时仍尝试读模板 */
  }
  await loadTemplates()
})

/* ===== 报告模板 ===== */
const reportFileInput = ref<HTMLInputElement>()

function pickReportPackage() {
  reportFileInput.value?.click()
}

async function onReportFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const result = await api.uploadReportTemplate(file)
    const warn = result.warnings?.length ? `（${result.warnings.length} 条提示）` : ''
    ElMessage.success(`报告模板包导入成功：${result.template.name}${warn}`)
    await loadTemplates()
  } catch {
    /* api 层已提示 */
  }
}

async function onSetDefaultReport(row: any) {
  try {
    await api.setDefaultReportTemplate(row.id)
    ElMessage.success(`已设默认报告模板：${row.name}`)
    await loadTemplates()
  } catch {
    /* api 层已提示 */
  }
}

async function onExportReport(row: any) {
  try {
    await api.exportReportTemplate(row.id, `${row.name}.zip`)
    store.setStatus(`已导出模板包：${row.name}`)
  } catch {
    /* api 层已提示 */
  }
}

async function onDeleteReport(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除报告模板“${row.name}”吗？`, '删除模板', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await api.deleteReportTemplate(row.id)
    ElMessage.success('报告模板已删除')
    await loadTemplates()
  } catch {
    /* api 层已提示 */
  }
}

const reportDetailVisible = ref(false)
const reportDetail = ref<ReportTemplateInfo | null>(null)

async function onReportDetail(row: any) {
  try {
    reportDetail.value = await api.getReportTemplate(row.id)
    reportDetailVisible.value = true
  } catch {
    /* api 层已提示 */
  }
}

/* ===== 原始记录模板 ===== */
const originalFileInput = ref<HTMLInputElement>()
const uploadVisible = ref(false)
const uploadForm = reactive({
  name: '',
  code: '',
  items: [] as string[],
  setDefault: true,
})
const uploadFiles = ref<File[]>([])
const uploadFileName = computed(() => {
  if (!uploadFiles.value.length) return ''
  return uploadFiles.value.length === 1
    ? uploadFiles.value[0].name
    : `${uploadFiles.value.length} 个文件`
})
const uploadIsDoc = computed(() =>
  uploadFiles.value.some((f) => f.name.toLowerCase().endsWith('.doc')))
const uploading = ref(false)

function openOriginalUpload() {
  uploadForm.name = ''
  uploadForm.code = ''
  uploadForm.items = []
  uploadForm.setDefault = true
  uploadFiles.value = []
  uploadVisible.value = true
}

function pickOriginalFile() {
  originalFileInput.value?.click()
}

function onOriginalFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (!files.length) return
  uploadFiles.value = files
  if (!uploadForm.name && files.length === 1) {
    uploadForm.name = files[0].name.replace(/\.(docx?|DOCX?)$/, '')
  }
}

async function submitOriginalUpload() {
  const files = uploadFiles.value
  if (!files.length) {
    ElMessage.warning('请选择模板文件')
    return
  }
  if (files.length === 1 && !uploadForm.name.trim()) {
    ElMessage.warning('请填写模板名称')
    return
  }
  uploading.value = true
  try {
    let saved = 0
    for (const file of files) {
      const name = files.length === 1
        ? uploadForm.name.trim()
        : file.name.replace(/\.(docx?|DOCX?)$/, '')
      await api.uploadOriginalTemplate({
        file,
        name,
        code: files.length === 1 ? uploadForm.code.trim() : '',
        detection_items: uploadForm.items,
        // 多文件批量导入时不能把每个模板都设为默认，避免互相覆盖
        set_default: files.length === 1 && uploadForm.setDefault,
      })
      saved += 1
    }
    ElMessage.success(`已导入 ${saved} 个原始记录模板`)
    uploadVisible.value = false
    await loadTemplates()
  } catch {
    /* api 层已提示 */
  } finally {
    uploading.value = false
  }
}

const defaultDialogVisible = ref(false)
const defaultTemplate = ref<OriginalTemplateInfo | null>(null)
const defaultItems = ref<string[]>([])

function openDefaultDialog(row: any) {
  if (!row.fillable) {
    ElMessage.warning('DOC 存档模板不支持自动填充，不能设为默认')
    return
  }
  defaultTemplate.value = row
  defaultItems.value = [...(row.default_for ?? [])]
  defaultDialogVisible.value = true
}

async function saveDefaultItems() {
  if (!defaultTemplate.value) return
  try {
    await api.setOriginalDefaults(defaultTemplate.value.id, defaultItems.value)
    ElMessage.success('原始记录默认模板已保存')
    defaultDialogVisible.value = false
    await loadTemplates()
  } catch {
    /* api 层已提示 */
  }
}

async function onDownloadOriginal(row: any) {
  try {
    await api.downloadOriginalTemplate(row.id, `${row.name}.docx`)
    store.setStatus(`已下载模板：${row.name}`)
  } catch {
    /* api 层已提示 */
  }
}

async function onDownloadReference(row: any) {
  try {
    await api.downloadReferenceDoc(row.id, `${row.name}_参考.doc`)
    store.setStatus('官方参考模板已下载')
  } catch {
    /* api 层已提示 */
  }
}

async function onDeleteOriginal(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除原始记录模板“${row.name}”吗？`, '删除模板', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await api.deleteOriginalTemplate(row.id)
    ElMessage.success('原始记录模板已删除')
    await loadTemplates()
  } catch {
    /* api 层已提示 */
  }
}

const previewVisible = ref(false)
const previewData = ref<Record<string, any> | null>(null)

async function onPreviewOriginal(row: any) {
  try {
    previewData.value = await api.previewOriginalTemplate(row.id)
    previewVisible.value = true
  } catch {
    /* api 层已提示 */
  }
}

function previewColumnsText(value: unknown): string {
  if (value === 'all' || value === undefined || value === null) return '全部列'
  if (Array.isArray(value)) return value.join('、')
  return String(value)
}
</script>

<template>
  <div class="templates-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/library')">返回资料库</el-button>
        <h2>模板库</h2>
        <el-tag size="small" type="info" effect="plain">报告模板 + 原始记录模板</el-tag>
      </div>
      <div class="page-actions">
        <el-button text @click="router.push('/report')">报告生成</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="loadTemplates">刷新</el-button>
      </div>
    </header>

    <input ref="reportFileInput" type="file" accept=".zip" class="hidden-input" @change="onReportFileChange" />
    <input ref="originalFileInput" type="file" multiple accept=".docx,.doc" class="hidden-input" @change="onOriginalFileChange" />

    <el-tabs v-model="activeTab" class="template-tabs">
      <el-tab-pane label="报告模板库" name="report">
        <el-alert
          type="info"
          show-icon
          :closable="false"
          class="hint-alert"
          title="报告模板包为 ZIP，需包含 manifest.json（8 个章节 + 结果一览表）。可先导出内置模板包，修改后再导入。"
        />
        <div class="toolbar">
          <el-button type="primary" :icon="Upload" @click="pickReportPackage">上传报告模板包</el-button>
          <span class="toolbar-hint">内置模板直接引用 report_template/，导入模板存放在 data/templates/report/</span>
        </div>
        <el-table v-loading="loading" :data="reportTemplates" border stripe class="template-table">
          <el-table-column prop="name" label="模板名称" min-width="220">
            <template #default="{ row }">
              <span class="name-cell">{{ row.name }}</span>
              <el-tag v-if="row.is_default" size="small" type="success" style="margin-left: 6px">默认</el-tag>
              <el-tag v-if="!row.available" size="small" type="danger" style="margin-left: 6px">文件缺失</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="来源" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.builtin ? 'warning' : 'primary'">
                {{ row.builtin ? '内置' : '导入' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="章节/结果表" width="110">
            <template #default="{ row }">{{ row.chapter_count }} / {{ row.table_count }}</template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" width="170" />
          <el-table-column label="操作" width="290" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text :icon="Star" :disabled="row.is_default || !row.available" @click="onSetDefaultReport(row)">设默认</el-button>
              <el-button size="small" text :icon="Download" @click="onExportReport(row)">导出</el-button>
              <el-button size="small" text :icon="View" @click="onReportDetail(row)">详情</el-button>
              <el-button size="small" text type="danger" :icon="Delete" :disabled="row.builtin || row.is_default" @click="onDeleteReport(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="原始记录库" name="original">
        <el-alert
          type="info"
          show-icon
          :closable="false"
          class="hint-alert"
          title="内置模板为系统原生 DOCX（无需 Office）；也可上传自定义 .docx（支持占位符/表头标签/表头匹配）。官方 .doc 仅作参考下载。"
        />
        <div class="toolbar">
          <el-button type="primary" :icon="Upload" @click="openOriginalUpload">上传原始记录模板</el-button>
          <span class="toolbar-hint">适用检测项目按项目树中的项目名匹配；一个模板可适用多个项目</span>
        </div>
        <el-table v-loading="loading" :data="originalTemplates" border stripe class="template-table">
          <el-table-column prop="name" label="模板名称" min-width="240">
            <template #default="{ row }">
              <span class="name-cell">{{ row.name }}</span>
              <el-tag v-if="row.builtin" size="small" type="warning" style="margin-left: 6px">内置</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="code" label="编号" width="120" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="engineTagType(row.engine)">{{ engineLabel(row.engine) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="适用检测项目" min-width="260">
            <template #default="{ row }">
              <template v-if="row.detection_items?.length">
                <el-tag v-for="item in row.detection_items.slice(0, 3)" :key="item" size="small" class="item-tag">
                  {{ itemLabel(item) }}
                </el-tag>
                <el-tag v-if="row.detection_items.length > 3" size="small" type="info">
                  +{{ row.detection_items.length - 3 }}
                </el-tag>
              </template>
              <span v-else class="muted">通用兜底</span>
            </template>
          </el-table-column>
          <el-table-column label="默认用于" min-width="220">
            <template #default="{ row }">
              <el-tag v-for="item in row.default_for" :key="item" size="small" type="success" class="item-tag">
                {{ itemLabel(item) }}
              </el-tag>
              <span v-if="!row.default_for?.length" class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="参考 .doc" width="120">
            <template #default="{ row }">
              <el-button
                v-if="row.reference_available"
                size="small"
                text
                :icon="Download"
                @click="onDownloadReference(row)"
              >
                官方模板
              </el-button>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="330" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text :icon="Star" :disabled="!row.fillable" @click="openDefaultDialog(row)">设默认</el-button>
              <el-button size="small" text :icon="Download" @click="onDownloadOriginal(row)">下载</el-button>
              <el-button size="small" text :icon="View" @click="onPreviewOriginal(row)">预览</el-button>
              <el-button size="small" text type="danger" :icon="Delete" :disabled="row.builtin || row.default_for?.length" @click="onDeleteOriginal(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="defaults-hint">
          当前默认映射：<span v-if="!Object.keys(defaults).length" class="muted">全部使用内置默认</span>
          <el-tag v-for="(tid, item) in defaults" :key="item" size="small" class="item-tag">
            {{ itemLabel(String(item)) }} → {{ originalTemplates.find((t) => t.id === tid)?.name ?? tid }}
          </el-tag>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-card shadow="never" class="help-card">
      <template #header>模板使用说明</template>
      <div class="help-steps">
        <div class="help-step">
          <span class="help-num">1</span>
          <div><b>报告模板</b><p>ZIP 包需包含 manifest.json；可导出内置模板，修改后再导入。</p></div>
        </div>
        <div class="help-step">
          <span class="help-num">2</span>
          <div><b>原始记录模板</b><p>按检测项目设置默认模板；.docx 可自动填充，.doc 需先转存为 .docx。</p></div>
        </div>
        <div class="help-step">
          <span class="help-num">3</span>
          <div><b>生成时自动匹配</b><p>报告生成页会优先使用项目选择或模板库默认模板。</p></div>
        </div>
      </div>
    </el-card>

    <!-- 报告模板详情 -->
    <el-dialog v-model="reportDetailVisible" title="报告模板详情" width="760px">
      <template v-if="reportDetail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="名称">{{ reportDetail.name }}</el-descriptions-item>
          <el-descriptions-item label="默认">{{ reportDetail.is_default ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="章节数">{{ reportDetail.chapter_count }}</el-descriptions-item>
          <el-descriptions-item label="结果表数">{{ reportDetail.table_count }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="reportDetail.missing?.length" class="warn-box">
          <div class="warn-title">缺失文件</div>
          <ul><li v-for="(m, i) in reportDetail.missing" :key="i">{{ m }}</li></ul>
        </div>
        <pre class="manifest-pre">{{ JSON.stringify(reportDetail.manifest, null, 2) }}</pre>
      </template>
    </el-dialog>

    <!-- 原始记录上传 -->
    <el-dialog v-model="uploadVisible" title="上传原始记录模板" width="620px">
      <el-form label-width="110px">
        <el-form-item label="模板文件">
          <el-button :icon="Upload" @click="pickOriginalFile">选择 .docx / .doc（可多选）</el-button>
          <span class="file-name">{{ uploadFileName || '未选择' }}</span>
        </el-form-item>
        <el-form-item v-if="uploadFiles.length > 1" label="文件列表">
          <div class="upload-file-list">
            <el-tag v-for="file in uploadFiles" :key="file.name" size="small" type="info">
              {{ file.name }}
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item label="模板名称">
          <el-input
            v-model="uploadForm.name"
            :disabled="uploadFiles.length > 1"
            :placeholder="uploadFiles.length > 1 ? '多个文件将按文件名命名' : '如：混凝土抗压强度检测原始记录'"
          />
        </el-form-item>
        <el-form-item label="检测编号">
          <el-input v-model="uploadForm.code" :disabled="uploadFiles.length > 1" placeholder="如 JJ0224005（可留空）" />
        </el-form-item>
        <el-form-item label="适用检测项目">
          <el-select v-model="uploadForm.items" multiple filterable placeholder="可多选；留空表示通用兜底" style="width: 100%">
            <el-option-group v-for="g in baseItemOptions" :key="g.label" :label="g.label">
              <el-option v-for="opt in g.options" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="uploadForm.setDefault" :disabled="!uploadFiles.length || uploadIsDoc || uploadFiles.length > 1" />
          <span class="muted" style="margin-left: 8px">多文件或 DOC 存档模板不能设为默认</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitOriginalUpload">导入</el-button>
      </template>
    </el-dialog>

    <!-- 设置原始记录默认适用项目 -->
    <el-dialog v-model="defaultDialogVisible" title="设置默认原始记录模板" width="560px">
      <div class="dialog-hint">
        模板：<b>{{ defaultTemplate?.name }}</b><br />
        勾选的检测项目将默认使用该模板（保存后覆盖这些项目原来的默认模板）。
      </div>
      <el-select v-model="defaultItems" multiple filterable placeholder="选择适用检测项目" style="width: 100%">
        <el-option-group v-for="g in baseItemOptions" :key="g.label" :label="g.label">
          <el-option v-for="opt in g.options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-option-group>
      </el-select>
      <template #footer>
        <el-button @click="defaultDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDefaultItems">保存</el-button>
      </template>
    </el-dialog>

    <!-- 原始记录预览 -->
    <el-dialog v-model="previewVisible" title="原始记录模板预览" width="760px">
      <template v-if="previewData">
        <el-descriptions :column="2" border size="small" style="margin-bottom: 10px">
          <el-descriptions-item label="名称">{{ previewData.name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ previewData.kind }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="previewData.kind === 'native'">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="检测编号">{{ previewData.code || '—' }}</el-descriptions-item>
            <el-descriptions-item label="适用项目">{{ (previewData.detection_items ?? []).join('、') || '通用' }}</el-descriptions-item>
            <el-descriptions-item label="包含列">{{ previewColumnsText(previewData.columns) }}</el-descriptions-item>
            <el-descriptions-item label="版式">{{ previewData.orientation === 'landscape' ? '横向 A4' : '纵向 A4' }}</el-descriptions-item>
            <el-descriptions-item label="备注">{{ previewData.notes || '—' }}</el-descriptions-item>
          </el-descriptions>
        </div>
        <div v-else-if="previewData.kind === 'docx'">
          <div class="preview-block">
            <div class="preview-title">占位符</div>
            <el-tag v-for="p in previewData.placeholders ?? []" :key="p" size="small" class="item-tag">{{ p }}</el-tag>
            <span v-if="!previewData.placeholders?.length" class="muted">未检测到占位符</span>
          </div>
          <div class="preview-block">
            <div class="preview-title">正文段落</div>
            <div v-for="(p, i) in (previewData.paragraphs ?? []).slice(0, 20)" :key="i" class="preview-line">{{ p }}</div>
          </div>
          <div class="preview-block">
            <div class="preview-title">表格</div>
            <div v-for="(t, ti) in (previewData.tables ?? []).slice(0, 5)" :key="ti" class="preview-table-title">
              表格 {{ Number(ti) + 1 }}（{{ t.length }} 行）
            </div>
          </div>
        </div>
        <el-alert v-else type="warning" show-icon :closable="false" :title="previewData.message" />
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.templates-view {
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

.hidden-input {
  display: none;
}

.template-tabs {
  flex: 1;
  min-height: 0;
}

.template-tabs :deep(.el-tabs__content) {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  box-shadow: var(--shadow-sm);
  padding: 14px;
}

.template-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}

.hint-alert {
  margin-bottom: 10px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.toolbar-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.template-table {
  width: 100%;
}

.name-cell {
  font-weight: 600;
}

.item-tag {
  margin: 0 4px 4px 0;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.defaults-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.file-name {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.upload-file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 110px;
  overflow: auto;
}

.dialog-hint {
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.manifest-pre {
  max-height: 380px;
  overflow: auto;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
}

.warn-box {
  margin-top: 10px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.warn-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.warn-box ul {
  margin: 0;
  padding-left: 20px;
}

.preview-block {
  margin-top: 10px;
}

.preview-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.preview-line {
  font-size: 13px;
  line-height: 1.7;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  padding: 2px 0;
}

.preview-table-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
