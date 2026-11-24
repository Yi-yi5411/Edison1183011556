<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import {
  Back,
  DocumentChecked,
  Download,
  EditPen,
  RefreshRight,
  View,
} from '@element-plus/icons-vue'
import { api } from '@/api'
import type {
  OriginalRecordResult,
  ReportAutoInfo,
  ReportGenerateResult,
  ReportHistoryItem,
} from '@/api/types'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()

const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const generatingOriginal = ref(false)
const autoInfo = ref<ReportAutoInfo | null>(null)
const reportResult = ref<ReportGenerateResult | null>(null)
const originalResult = ref<OriginalRecordResult | null>(null)
const draftMode = ref(false)
const error = ref('')
const progress = ref('')
const history = ref<ReportHistoryItem[]>([])
const historyLoading = ref(false)
const form = reactive<Record<string, string>>({})
const dirty = ref(false)
let lastSaved = '{}'

const previewVisible = ref(false)
const previewUrl = ref('')
const previewTitle = ref('')

const counts = computed(() => autoInfo.value?.counts ?? {
  checked: 0, filled: 0, assessed: 0,
})
const missing = computed(() => autoInfo.value?.missing ?? [])
const templateName = computed(() =>
  autoInfo.value?.template?.name || '系统自动匹配',
)
const overviewTemplate = computed(() =>
  autoInfo.value?.overview_template || '',
)
const canGenerate = computed(() =>
  (counts.value.checked > 0 || (counts.value.items ?? 0) > 0)
  && counts.value.filled > 0,
)
const canGenerateOriginal = computed(() =>
  counts.value.checked > 0 && counts.value.filled > 0,
)

interface InfoField {
  key: string
  label: string
  type?: 'text' | 'date' | 'textarea'
  full?: boolean
  auto?: boolean
  placeholder?: string
}

const infoFields: InfoField[] = [
  { key: 'project_name', label: '工程名称', full: true },
  { key: 'report_no', label: '报告编号', auto: true, placeholder: '可自动生成，也可手动修改' },
  { key: 'project_location', label: '工程地点' },
  { key: 'client', label: '委托单位' },
  { key: 'witness', label: '见证单位' },
  { key: 'construction_unit', label: '建设单位' },
  { key: 'contractor', label: '施工单位' },
  { key: 'design_unit', label: '设计单位' },
  { key: 'supervision_unit', label: '监理单位' },
  { key: 'survey_unit', label: '勘察单位' },
  { key: 'structure_type', label: '结构类型' },
  { key: 'building_area', label: '建筑面积(㎡)' },
  { key: 'floor_count', label: '层数' },
  { key: 'building_height', label: '建筑高度(m)' },
  { key: 'start_date', label: '开工日期' },
  { key: 'completion_date', label: '竣工日期' },
  { key: 'inspection_purpose', label: '检测目的' },
  { key: 'tester', label: '检测人' },
  { key: 'writer', label: '报告编写人' },
  { key: 'checker', label: '复核人' },
  { key: 'reviewer', label: '审核人' },
  { key: 'approver', label: '批准人' },
  { key: 'test_date', label: '检测日期', type: 'date' },
  { key: 'report_date', label: '报告日期', type: 'date' },
  {
    key: 'project_overview',
    label: '工程概况',
    type: 'textarea',
    full: true,
    placeholder: '可人工补充工程概况；留空时报告引擎自动组织。',
  },
]

function applyInfo(info: Record<string, string> | undefined) {
  for (const key of Object.keys(form)) delete form[key]
  for (const [key, value] of Object.entries(info || {})) {
    form[key] = String(value ?? '')
  }
  for (const field of infoFields) {
    if (!(field.key in form)) form[field.key] = ''
  }
  lastSaved = JSON.stringify(form)
  dirty.value = false
}

watch(form, () => {
  dirty.value = JSON.stringify(form) !== lastSaved
}, { deep: true })

async function fillNextReportNo() {
  try {
    form.report_no = await api.getNextReportNo()
  } catch {
    /* api 层已提示 */
  }
}

async function useOverviewTemplate() {
  const draft = overviewTemplate.value
  if (!draft) return
  if (String(form.project_overview || '').trim() && form.project_overview !== draft) {
    try {
      await ElMessageBox.confirm(
        '将用系统模板替换当前工程概况内容，替换后仍可继续编辑。是否继续？',
        '套用工程概况模板',
        { confirmButtonText: '套用', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  form.project_overview = draft
}

async function saveInfo(showMessage = true): Promise<boolean> {
  saving.value = true
  try {
    const saved = await api.putReportInfo({ ...form }) as Record<string, string> | null
    if (saved?.project_name) {
      form.project_name = saved.project_name
      store.projectName = saved.project_name
    }
    store.reportInfo = { ...form }
    lastSaved = JSON.stringify(form)
    dirty.value = false
    if (showMessage) ElMessage.success('报告信息已保存')
    return true
  } catch (e) {
    if (showMessage) {
      ElMessage.error(e instanceof Error ? e.message : '报告信息保存失败')
    }
    return false
  } finally {
    saving.value = false
  }
}

function fileName(filepath: string): string {
  return filepath.split(/[\\/]/).pop() || filepath
}

function openPreview(filepath: string, title: string) {
  if (!filepath) return
  previewUrl.value = api.reportPreviewUrl(filepath)
  previewTitle.value = title
  previewVisible.value = true
}

function downloadUrl(filepath: string): string {
  return api.reportDownloadUrl(filepath)
}

async function loadAutoInfo() {
  loading.value = true
  error.value = ''
  try {
    if (!store.initialized) await store.init()
    autoInfo.value = await api.reportAutoInfo()
    applyInfo(autoInfo.value.report_info)
    await store.loadProject()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '自动识别报告信息失败'
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    history.value = await api.getReportHistory()
  } catch {
    /* 历史失败不影响主流程 */
  } finally {
    historyLoading.value = false
  }
}

async function generateReport() {
  if (!canGenerate.value) {
    ElMessage.warning('当前项目还没有可用的检测数据，请先上传或录入数据')
    return
  }
  generating.value = true
  error.value = ''
  progress.value = '正在保存报告信息并自动匹配模板…'
  reportResult.value = null
  try {
    if (!(await saveInfo(false))) {
      ElMessage.warning('报告信息保存失败，已中止生成')
      return
    }
    const data = await api.generateReportStream(
      { draft: draftMode.value },
      (event) => {
        if (event.event === 'log') progress.value = String(event.data.message || '')
        if (event.event === 'error') error.value = String(event.data.message || '')
      },
    )
    reportResult.value = data
    progress.value = ''
    store.setStatus(`报告已生成：${data.filepath}`)
    ElNotification({
      title: data.draft ? '报告草稿生成完成' : '报告生成完成',
      message: `模板自动匹配：${data.template_name || templateName.value}`
        + (data.skipped_items?.length
          ? `；跳过 ${data.skipped_items.length} 项未就绪检测项` : ''),
      type: 'success',
      duration: 5000,
    })
    await loadHistory()
    openPreview(data.filepath, '检测报告预览')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '报告生成失败'
    ElMessage.error(error.value)
  } finally {
    generating.value = false
  }
}

async function generateOriginal() {
  if (!canGenerateOriginal.value) {
    ElMessage.warning('生成原始记录需要先在数据采集页勾选检测项目并录入数据')
    return
  }
  generatingOriginal.value = true
  originalResult.value = null
  try {
    if (!(await saveInfo(false))) {
      ElMessage.warning('报告信息保存失败，已中止生成')
      return
    }
    const data = await api.generateOriginalRecords({
      sheet_keys: store.checkedItems,
      template_map: {},
    })
    originalResult.value = data
    store.setStatus(`原始记录生成完成：${data.files.length} 个文件`)
    ElNotification({
      title: '原始记录生成完成',
      message: `共 ${data.files.length} 个文件，模板由系统自动匹配`,
      type: 'success',
      duration: 5000,
    })
    if (data.files.length) {
      openPreview(data.files[0].filepath, `原始记录预览 · ${fileName(data.files[0].filepath)}`)
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '原始记录生成失败')
  } finally {
    generatingOriginal.value = false
  }
}

function onProjectChanged() {
  reportResult.value = null
  originalResult.value = null
  void loadAutoInfo()
}

onMounted(async () => {
  await loadAutoInfo()
  await loadHistory()
  window.addEventListener('harness-project-changed', onProjectChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('harness-project-changed', onProjectChanged)
})
</script>

<template>
  <div class="report-page" v-loading="loading">
    <header class="page-head">
      <div>
        <div class="page-title-row">
          <el-button :icon="Back" text @click="router.push('/harness')">返回首页</el-button>
          <h1>检测报告</h1>
        </div>
        <p>系统自动识别检测依据、设备、内容和结果，模板自动匹配，无需手工设置。</p>
      </div>
      <div class="head-actions">
        <el-button :icon="RefreshRight" :loading="loading" @click="loadAutoInfo">
          重新识别
        </el-button>
        <el-button :loading="saving" :disabled="!dirty" @click="saveInfo()">
          保存修改
        </el-button>
        <el-checkbox v-model="draftMode" size="small" class="draft-check">
          草稿：仅生成已就绪项
        </el-checkbox>
        <el-button
          type="primary"
          :icon="DocumentChecked"
          :loading="generating"
          :disabled="!canGenerate"
          @click="generateReport"
        >
          {{ draftMode ? '生成报告草稿' : '生成报告' }}
        </el-button>
        <el-button
          :icon="DocumentChecked"
          :loading="generatingOriginal"
          :disabled="!canGenerateOriginal"
          @click="generateOriginal"
        >
          生成原始记录
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="missing.length"
      type="warning"
      show-icon
      :closable="false"
      class="missing-alert"
      :title="missing.join('；')"
    />

    <section class="summary-strip">
      <div class="summary-item">
        <span class="summary-label">检测项目</span>
        <strong>{{ counts.checked }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">已录入行</span>
        <strong>{{ counts.filled }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">已评定</span>
        <strong>{{ counts.assessed }}</strong>
      </div>
      <div class="summary-item template-item">
        <span class="summary-label">报告模板</span>
        <span class="template-name">{{ templateName }}</span>
        <el-tag size="small" type="success" effect="plain">AI 自动匹配</el-tag>
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <div class="card-title">报告信息</div>
        <div class="head-tags">
          <el-tag size="small" effect="plain">AI 自动识别，可人工修改</el-tag>
          <span class="save-state" :class="{ dirty }">{{ dirty ? '有未保存修改' : '已保存' }}</span>
        </div>
      </div>
      <div class="info-grid">
        <div
          v-for="field in infoFields"
          :key="field.key"
          class="info-item"
          :class="{ full: field.full }"
        >
          <label class="info-label">
            {{ field.label }}
            <el-tag v-if="field.auto" size="small" type="success" effect="plain">可自动</el-tag>
            <el-button
              v-if="field.key === 'project_overview'"
              link
              type="primary"
              size="small"
              @click.prevent="useOverviewTemplate"
            >
              套用模板
            </el-button>
          </label>
          <el-date-picker
            v-if="field.type === 'date'"
            v-model="form[field.key]"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            class="info-control"
          />
          <el-input
            v-else-if="field.type === 'textarea'"
            v-model="form[field.key]"
            type="textarea"
            :rows="4"
            :placeholder="field.placeholder"
            class="info-control"
          />
          <el-input
            v-else
            v-model="form[field.key]"
            :placeholder="field.placeholder"
            class="info-control"
          >
            <template v-if="field.auto" #append>
              <el-button @click="fillNextReportNo">生成</el-button>
            </template>
          </el-input>
        </div>
      </div>
      <div class="form-foot">
        <span>修改后点击“保存修改”，生成报告时会自动保存。</span>
        <el-button size="small" :loading="saving" :disabled="!dirty" @click="saveInfo()">
          保存修改
        </el-button>
      </div>
    </section>

    <section class="card section-card">
      <div class="card-head">
        <div class="card-title">二、主要检测依据</div>
        <el-tag size="small" effect="plain">AI 自动判断</el-tag>
      </div>
      <ol v-if="autoInfo?.basis?.length" class="basis-list">
        <li v-for="item in autoInfo.basis" :key="item">{{ item }}</li>
      </ol>
      <el-empty v-else description="勾选检测项目后自动生成依据" :image-size="60" />
    </section>

    <section class="card section-card">
      <div class="card-head">
        <div class="card-title">三、主要检测设备</div>
        <el-tag size="small" effect="plain">AI 自动匹配</el-tag>
      </div>
      <el-table
        v-if="autoInfo?.equipment?.length"
        :data="autoInfo.equipment"
        size="small"
        border
      >
        <el-table-column prop="设备名称" label="设备名称" min-width="180" />
        <el-table-column prop="设备分类编号" label="设备分类编号" min-width="130" />
        <el-table-column prop="最近检定日期" label="最近检定日期" min-width="130" />
        <el-table-column prop="检定证书编号" label="检定证书编号" min-width="180" />
        <el-table-column label="今日使用" width="100">
          <template #default="{ row }">{{ row['今日使用'] }} / {{ row['每日上限'] }}</template>
        </el-table-column>
        <el-table-column prop="是否可用" label="状态" width="110" />
      </el-table>
      <el-empty v-else description="未匹配到报告设备" :image-size="60" />
    </section>

    <section class="card section-card">
      <div class="card-head">
        <div class="card-title">四、检测内容</div>
        <el-tag size="small" effect="plain">AI 自动识别</el-tag>
      </div>
      <p v-if="autoInfo?.content_text" class="content-text">{{ autoInfo.content_text }}</p>
      <el-table
        v-if="autoInfo?.content?.length"
        :data="autoInfo.content"
        size="small"
        border
      >
        <el-table-column prop="item" label="检测项目" min-width="220" />
        <el-table-column prop="component" label="构件" width="90" />
        <el-table-column prop="rows" label="有效行数" width="100" />
      </el-table>
    </section>

    <section class="card section-card">
      <div class="card-head">
        <div class="card-title">五、检测结果</div>
        <el-tag size="small" effect="plain">AI 自动汇总</el-tag>
      </div>
      <el-table
        v-if="autoInfo?.results?.length"
        :data="autoInfo.results"
        size="small"
        border
      >
        <el-table-column prop="item" label="检测项目" min-width="220" />
        <el-table-column prop="component" label="构件" width="90" />
        <el-table-column prop="rows" label="行数" width="80" />
        <el-table-column prop="status" label="评定状态" width="110" />
        <el-table-column prop="conclusion" label="结果说明" min-width="280" show-overflow-tooltip />
      </el-table>
      <el-empty v-else description="录入数据后自动汇总结果" :image-size="60" />
    </section>

    <section v-if="reportResult" class="card result-card">
      <div class="card-head">
        <div class="card-title">报告已生成</div>
        <el-tag size="small" type="success">{{ reportResult.template_name || templateName }}</el-tag>
      </div>
      <div class="result-line">
        <el-icon><DocumentChecked /></el-icon>
        <span class="file-name">{{ fileName(reportResult.filepath) }}</span>
        <span v-if="reportResult.warnings?.length" class="warning-text">
          {{ reportResult.warnings.length }} 条提示
        </span>
      </div>
      <div class="result-actions">
        <el-button :icon="View" @click="openPreview(reportResult.filepath, '检测报告预览')">
          在线预览
        </el-button>
        <el-button
          :icon="EditPen"
          @click="router.push({ path: '/report-edit', query: { filepath: reportResult.filepath } })"
        >
          在线修改
        </el-button>
        <el-button tag="a" :href="downloadUrl(reportResult.filepath)" target="_blank">
          <el-icon><Download /></el-icon> 下载报告
        </el-button>
      </div>
      <div v-if="reportResult.skipped_items?.length" class="warning-list skipped-list">
        <div class="skipped-title">草稿已跳过以下未就绪检测项：</div>
        <div v-for="item in reportResult.skipped_items" :key="item.sheet_key">
          · {{ item.sheet_key }}：{{ item.reason }}
        </div>
      </div>
      <div v-if="reportResult.warnings?.length" class="warning-list">
        <div v-for="warning in reportResult.warnings" :key="warning">· {{ warning }}</div>
      </div>
    </section>

    <section v-if="originalResult" class="card result-card">
      <div class="card-head">
        <div class="card-title">原始记录</div>
        <el-tag size="small" type="success">{{ originalResult.files.length }} 个文件</el-tag>
      </div>
      <div v-for="file in originalResult.files" :key="file.filepath" class="original-row">
        <div class="original-main">
          <el-icon><DocumentChecked /></el-icon>
          <div>
            <div class="file-name">{{ fileName(file.filepath) }}</div>
            <div class="file-meta">{{ file.sheet_key }} · {{ file.template_name }}</div>
          </div>
        </div>
        <div class="original-actions">
          <el-button size="small" :icon="View" @click="openPreview(file.filepath, `原始记录预览 · ${fileName(file.filepath)}`)">
            预览
          </el-button>
          <el-button size="small" tag="a" :href="downloadUrl(file.filepath)" target="_blank">
            下载
          </el-button>
        </div>
      </div>
      <div v-if="originalResult.warnings?.length" class="warning-list">
        <div v-for="warning in originalResult.warnings" :key="warning">· {{ warning }}</div>
      </div>
    </section>

    <el-collapse class="history-collapse">
      <el-collapse-item title="生成历史" name="history">
        <el-table v-loading="historyLoading" :data="history" size="small" border>
          <el-table-column prop="project_name" label="工程" min-width="220" show-overflow-tooltip />
          <el-table-column prop="report_no" label="报告编号" min-width="140" />
          <el-table-column prop="generated_at" label="生成时间" min-width="160" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" text @click="openPreview(row.filepath, '历史报告预览')">
                预览
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <el-alert
      v-if="error"
      class="error-alert"
      type="error"
      :closable="false"
      show-icon
      :title="error"
    />

    <el-dialog
      v-model="previewVisible"
      :title="previewTitle"
      width="92%"
      top="2vh"
      destroy-on-close
      class="preview-dialog"
    >
      <iframe v-if="previewUrl" :src="previewUrl" class="preview-frame" title="文档预览" />
    </el-dialog>
  </div>
</template>

<style scoped>
.report-page {
  max-width: 1240px;
  margin: 0 auto;
  padding: 18px 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}
.page-head h1 {
  margin: 0;
  font-size: 22px;
  letter-spacing: 0.5px;
}
.page-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.page-title-row .el-button {
  margin-left: -10px;
  color: var(--el-text-color-secondary);
}
.page-head p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.draft-check {
  margin-right: 2px;
  white-space: nowrap;
}
.summary-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
}
.summary-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding-right: 18px;
  border-right: 1px solid var(--el-border-color-lighter);
}
.summary-item:last-child {
  border-right: none;
}
.summary-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.summary-item strong {
  font-size: 19px;
  color: var(--el-color-primary);
}
.template-item {
  margin-left: auto;
  align-items: center;
  padding-right: 0;
  border-right: none;
  flex-wrap: wrap;
}
.template-name {
  font-size: 12.5px;
  font-weight: 600;
}
.card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
  padding: 14px 16px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.card-title {
  font-size: 14px;
  font-weight: 700;
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 18px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  padding: 2px 0 8px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.info-item.full {
  grid-column: 1 / -1;
}
.info-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.info-label .el-button {
  margin-left: auto;
}
.info-control {
  width: 100%;
}
.head-tags {
  display: flex;
  align-items: center;
  gap: 10px;
}
.save-state {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}
.save-state.dirty {
  color: var(--el-color-warning);
}
.form-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
}
.basis-list {
  margin: 0;
  padding-left: 22px;
  color: var(--el-text-color-regular);
  font-size: 12.5px;
  line-height: 1.9;
}
.content-text {
  margin: 0 0 10px;
  color: var(--el-text-color-regular);
  font-size: 12.5px;
  line-height: 1.7;
}
.result-card {
  border-color: var(--el-color-success-light-5);
  background: linear-gradient(180deg, var(--el-color-success-light-9), var(--el-bg-color));
}
.result-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.file-name {
  font-weight: 600;
  word-break: break-all;
}
.warning-text {
  color: var(--el-color-warning);
  font-size: 11.5px;
}
.result-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.warning-list {
  margin-top: 10px;
  color: var(--el-color-warning);
  font-size: 11.5px;
  line-height: 1.7;
}
.skipped-list {
  padding: 9px 11px;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  color: #b45309;
}
.skipped-title {
  font-weight: 600;
  margin-bottom: 2px;
}
.original-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.original-row:last-child {
  border-bottom: none;
}
.original-main {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.file-meta {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
.original-actions {
  flex: none;
  display: flex;
  gap: 6px;
}
.history-collapse {
  margin-top: 2px;
}
.missing-alert,
.error-alert {
  margin: 0;
}
.preview-frame {
  width: 100%;
  height: 78vh;
  border: 0;
  background: #525659;
}
@media (max-width: 720px) {
  .report-page {
    padding: 12px;
  }
  .info-grid {
    grid-template-columns: 1fr;
  }
  .summary-item {
    border-right: none;
    padding-right: 10px;
  }
  .template-item {
    margin-left: 0;
  }
}
</style>
