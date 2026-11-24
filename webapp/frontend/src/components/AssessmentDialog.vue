<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Plus, Promotion, Upload } from '@element-plus/icons-vue'
import { api } from '@/api'
import type {
  AssessmentDetail,
  AssessmentOptions,
  AssessmentResult,
  AssessmentSpec,
} from '@/api/types'

const props = defineProps<{ modelValue: boolean; sheetKey: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'done'): void
}>()

interface RawRow {
  floor: string
  component_type: string
  component_code: string
  axis: string
  grade: string
  zones: string
}

const loading = ref(false)
const running = ref(false)
const detail = ref<AssessmentDetail | null>(null)
const result = ref<AssessmentResult | null>(null)
const rawRows = ref<RawRow[]>([])
const rawJson = ref('')
const designGrade = ref('')
const excelInput = ref<HTMLInputElement>()
const importingExcel = ref(false)
const options = reactive<AssessmentOptions>({
  no_drawing: false,
  table_no: '1',
  include_component_stats: false,
})

const spec = computed<AssessmentSpec | null>(() => detail.value?.spec ?? null)
const errorText = computed(() => (result.value?.errors ?? []).join('；'))
const warnings = computed(() => result.value?.warnings ?? [])
const conclusionType = computed(() => result.value?.conclusion_type || '')
const conclusionTagType = computed(() => {
  if (conclusionType.value === '类型一') return 'success'
  if (conclusionType.value === '类型三') return 'info'
  return 'warning'
})

function reboundCoreExample(): Record<string, unknown> {
  return {
    method: '修正系数法',
    components: [
      {
        floor: '1F',
        component_type: '墙',
        component_code: 'Q1',
        axis: '1/A',
        grade: 'C30',
        diameter: 100,
        zones: [35.2, 34.8, 36.1, 35.5, 34.9],
        cores: [
          { actual: 35.6, zone: 35.0 },
          { actual: 36.1, zone: 35.2 },
          { actual: 35.9, zone: 34.9 },
          { actual: 36.3, zone: 35.4 },
          { actual: 35.8, zone: 35.1 },
          { actual: 36.0, zone: 35.3 },
        ],
      },
    ],
  }
}

function emptyRow(component?: string | null): RawRow {
  return {
    floor: '',
    component_type: component || '',
    component_code: '',
    axis: '',
    grade: '',
    zones: '',
  }
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const summaryRows = computed(() => {
  const summary = result.value?.summary
  if (!summary || typeof summary !== 'object') return []
  return Object.entries(summary)
    .filter(([, value]) => value === null || typeof value !== 'object')
    .map(([key, value]) => ({ key, value: formatValue(value) }))
})

const detailRows = computed(() => {
  const details = result.value?.details
  return Array.isArray(details) ? details : []
})

function close() {
  emit('update:modelValue', false)
}

async function load() {
  if (!props.sheetKey) return
  loading.value = true
  result.value = null
  try {
    const data = await api.getAssessment(props.sheetKey)
    detail.value = data
    result.value = data.result ?? null
    options.no_drawing = !!data.options?.no_drawing
    options.table_no = data.options?.table_no || '1'
    options.include_component_stats = !!data.options?.include_component_stats
    designGrade.value = String((data.input as Record<string, unknown> | null)?.design_grade ?? '')
    if (data.spec?.id === 'rebound_core') {
      rawRows.value = []
      rawJson.value = JSON.stringify(
        (data.input as Record<string, unknown> | null) || reboundCoreExample(),
        null,
        2,
      )
    } else if (data.spec?.needs_raw_input) {
      rawJson.value = ''
      const input = data.input as { components?: Record<string, unknown>[] } | null
      const comps = Array.isArray(input?.components) ? input.components : []
      rawRows.value = comps.length
        ? comps.map((c) => ({
            floor: String(c.floor ?? ''),
            component_type: String(c.component_type ?? data.component ?? ''),
            component_code: String(c.component_code ?? c.component ?? ''),
            axis: String(c.axis ?? ''),
            grade: String(c.grade ?? ''),
            zones: Array.isArray(c.zones) ? c.zones.join(', ') : String(c.zones ?? ''),
          }))
        : [emptyRow(data.component)]
    } else {
      rawJson.value = ''
      rawRows.value = []
    }
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

function addRawRow() {
  rawRows.value.push(emptyRow(detail.value?.component))
}

function pickAssessmentExcel() {
  excelInput.value?.click()
}

async function onAssessmentExcelFile(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (!files.length || !props.sheetKey) return
  importingExcel.value = true
  try {
    const merged: Record<string, unknown>[] = []
    let importedCount = 0
    const allWarnings: string[] = []
    for (const file of files) {
      const data = await api.importAssessmentExcel(props.sheetKey, file)
      const comps = Array.isArray((data.input as { components?: Record<string, unknown>[] })?.components)
        ? (data.input as { components: Record<string, unknown>[] }).components
        : []
      merged.push(...comps)
      importedCount += Number(data.components ?? comps.length)
      if (data.warnings?.length) allWarnings.push(...data.warnings)
    }
    if (spec.value?.id === 'rebound_core') {
      rawJson.value = JSON.stringify({ components: merged }, null, 2)
    } else {
      rawRows.value = merged.length
        ? merged.map((c) => ({
            floor: String(c.floor ?? ''),
            component_type: String(c.component_type ?? detail.value?.component ?? ''),
            component_code: String(c.component_code ?? c.component ?? ''),
            axis: String(c.axis ?? ''),
            grade: String(c.grade ?? ''),
            zones: Array.isArray(c.zones) ? c.zones.join(', ') : String(c.zones ?? ''),
          }))
        : [emptyRow(detail.value?.component)]
    }
    const warn = allWarnings.length ? `（${allWarnings.length} 条提示）` : ''
    ElMessage.success(`已从 ${files.length} 个文件导入 ${importedCount} 条原始数据${warn}`)
  } catch {
    /* api 层已提示 */
  } finally {
    importingExcel.value = false
  }
}

function removeRawRow(index: number) {
  rawRows.value.splice(index, 1)
  if (!rawRows.value.length) rawRows.value.push(emptyRow(detail.value?.component))
}

function buildInput(): Record<string, unknown> | undefined {
  if (spec.value?.id === 'brick') {
    return { design_grade: designGrade.value.trim() }
  }
  if (!spec.value?.needs_raw_input) return undefined
  if (spec.value?.id === 'rebound_core') {
    let parsed: unknown
    try {
      parsed = JSON.parse(rawJson.value || '{}')
    } catch (err) {
      throw new Error('原始数据 JSON 格式不正确：' + (err instanceof Error ? err.message : String(err)))
    }
    if (!parsed || typeof parsed !== 'object' || !Array.isArray((parsed as Record<string, unknown>).components)) {
      throw new Error('原始数据 JSON 必须包含 components 数组')
    }
    return parsed as Record<string, unknown>
  }
  const components = rawRows.value
    .filter((row) => String(row.component_code || '').trim() || String(row.zones || '').trim())
    .map((row) => ({
      floor: row.floor.trim(),
      component_type: row.component_type.trim(),
      component_code: row.component_code.trim(),
      axis: row.axis.trim(),
      grade: row.grade.trim(),
      zones: String(row.zones || '')
        .split(/[,，、;；\s]+/)
        .map((v) => v.trim())
        .filter(Boolean)
        .map((v) => Number(v))
        .filter((v) => Number.isFinite(v)),
    }))
  if (!components.length) {
    throw new Error('请至少填写一条原始数据（构件编号和测区换算值）')
  }
  return { components }
}

async function run() {
  running.value = true
  try {
    const input = buildInput()
    const data = await api.runAssessment(props.sheetKey, {
      input,
      options: { ...options },
    })
    result.value = data
    if (data.ok) {
      ElMessage.success(`评定完成：${data.conclusion_type || ''}`)
      emit('done')
    } else {
      ElMessage.warning('评定未通过，请查看错误信息')
    }
  } catch (err) {
    if (err instanceof Error && err.message) ElMessage.warning(err.message)
  } finally {
    running.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) void load()
  },
  { immediate: true },
)

watch(
  () => props.sheetKey,
  () => {
    if (props.modelValue) void load()
  },
)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="`检测评定 · ${spec?.name || sheetKey}`"
    width="900px"
    top="6vh"
    destroy-on-close
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <input
      ref="excelInput"
      type="file"
      multiple
      accept=".xlsx,.xlsm,.csv,.docx"
      class="hidden-file-input"
      @change="onAssessmentExcelFile"
    />
    <div v-loading="loading" class="assessment-dialog">
      <el-alert
        v-if="spec && !spec.implemented"
        type="warning"
        show-icon
        :closable="false"
        title="该检测项目的评定规则尚未接入，暂不能自动生成结论。"
      />
      <template v-else-if="spec">
        <el-alert
          v-if="spec.needs_raw_input"
          type="info"
          show-icon
          :closable="false"
          :title="spec.description || '请填写原始数据后运行评定。'"
        />
        <el-alert
          v-else
          type="info"
          show-icon
          :closable="false"
          title="将读取当前工作表的已保存数据执行评定；运行前请先保存表格。"
        />

        <div v-if="spec.needs_raw_input && spec.id === 'rebound_core'" class="raw-section">
          <div class="section-head">
            <span>原始数据（测区换算值 + 成对芯样数据）</span>
            <el-button size="small" :icon="Upload" :loading="importingExcel" @click="pickAssessmentExcel">
              导入文件
            </el-button>
          </div>
          <el-alert
            type="info"
            show-icon
            :closable="false"
            title="按 JSON 填写：components[].zones 为测区换算值；cores 为 [{actual: 芯样实测强度, zone: 对应测区换算值}]；同修正批芯样数 n≥6、直径一致。"
          />
          <el-input v-model="rawJson" type="textarea" :rows="14" class="raw-json" />
        </div>
        <div v-else-if="spec.needs_raw_input" class="raw-section">
          <div class="section-head">
            <span>原始数据</span>
            <div>
              <el-button size="small" :icon="Upload" :loading="importingExcel" @click="pickAssessmentExcel">
                导入文件
              </el-button>
              <el-button size="small" :icon="Plus" @click="addRawRow">添加构件</el-button>
            </div>
          </div>
          <el-table :data="rawRows" size="small" border>
            <el-table-column label="楼层" width="80">
              <template #default="{ row }"><el-input v-model="row.floor" size="small" /></template>
            </el-table-column>
            <el-table-column label="构件类型" width="100">
              <template #default="{ row }"><el-input v-model="row.component_type" size="small" /></template>
            </el-table-column>
            <el-table-column label="构件编号" width="120">
              <template #default="{ row }"><el-input v-model="row.component_code" size="small" /></template>
            </el-table-column>
            <el-table-column label="轴线" width="90">
              <template #default="{ row }"><el-input v-model="row.axis" size="small" /></template>
            </el-table-column>
            <el-table-column label="设计强度等级" width="110">
              <template #default="{ row }"><el-input v-model="row.grade" size="small" placeholder="C30" /></template>
            </el-table-column>
            <el-table-column label="测区换算值（逗号分隔）" min-width="250">
              <template #default="{ row }">
                <el-input v-model="row.zones" size="small" placeholder="35.2, 34.8, 36.1 ..." />
              </template>
            </el-table-column>
            <el-table-column label="" width="52">
              <template #default="{ $index }">
                <el-button size="small" text type="danger" :icon="Delete" @click="removeRawRow($index)" />
              </template>
            </el-table-column>
          </el-table>
        </div>

        <el-form v-if="spec.id === 'brick'" label-width="130px" class="option-form">
          <el-form-item label="设计强度等级">
            <el-select v-model="designGrade" clearable placeholder="不填则只报告评定等级" style="width: 220px">
              <el-option v-for="grade in ['MU30', 'MU25', 'MU20', 'MU15', 'MU10']" :key="grade" :label="grade" :value="grade" />
            </el-select>
            <span class="form-tip">填写后自动判断是否满足设计要求；不填只输出砖强度评定等级</span>
          </el-form-item>
        </el-form>

        <el-form label-width="130px" class="option-form">
          <el-form-item label="报告表号">
            <el-input v-model="options.table_no" placeholder="如 5.1；默认 1" style="width: 180px" />
            <span class="form-tip">结论中的“详见表xxx”会替换为该表号；报告生成时自动使用实际表号</span>
          </el-form-item>
          <el-form-item label="无图纸">
            <el-switch v-model="options.no_drawing" />
            <span class="form-tip">设计值为“/”或明确无图纸时打开，强制输出类型三</span>
          </el-form-item>
          <el-form-item label="输出构件统计">
            <el-switch v-model="options.include_component_stats" />
            <span class="form-tip">仅截面尺寸/厚度/间距使用；对应提示词中的“模板2”，不默认选用</span>
          </el-form-item>
        </el-form>

        <el-button type="primary" :icon="Promotion" :loading="running" @click="run">
          运行评定
        </el-button>

        <div v-if="result" class="result-section">
          <el-divider />
          <div class="result-head">
            <span class="result-title">评定结果</span>
            <el-tag v-if="result.conclusion_type" :type="conclusionTagType" size="small">
              {{ result.conclusion_type }}
            </el-tag>
            <el-tag v-if="result.source === 'raw_input'" size="small" type="info">原始数据</el-tag>
            <el-tag v-else size="small" type="info">工作表数据</el-tag>
          </div>
          <el-alert v-if="errorText" type="error" show-icon :closable="false" :title="errorText" />
          <div v-if="result.conclusion" class="conclusion-box">{{ result.conclusion }}</div>
          <el-alert
            v-for="(w, i) in warnings"
            :key="i"
            type="warning"
            show-icon
            :closable="false"
            :title="w"
            class="warning-item"
          />
          <el-descriptions v-if="summaryRows.length" :column="2" border size="small" class="summary-box">
            <el-descriptions-item v-for="item in summaryRows" :key="item.key" :label="item.key">
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="detailRows.length" class="detail-section">
            <div class="section-head">异常明细（{{ detailRows.length }}）</div>
            <el-table :data="detailRows" size="small" border>
              <el-table-column prop="floor" label="楼层" width="90" />
              <el-table-column prop="component" label="构件/位置" min-width="160" />
              <el-table-column prop="point" label="测点" min-width="120" />
              <el-table-column prop="class" label="判定" width="120" />
              <el-table-column prop="deviation" label="偏差(mm)" width="100" />
            </el-table>
          </div>
        </div>
      </template>
      <el-empty v-else description="未读取到评定规则" />
    </div>
    <template #footer>
      <el-button @click="close">关闭</el-button>
      <el-button
        v-if="spec?.implemented"
        type="primary"
        :icon="Promotion"
        :loading="running"
        @click="run"
      >
        运行评定
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.assessment-dialog {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hidden-file-input {
  display: none;
}

.raw-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.raw-json :deep(.el-textarea__inner) {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.option-form {
  margin-top: 6px;
}

.form-tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.result-section {
  margin-top: 8px;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.result-title {
  font-weight: 600;
}

.conclusion-box {
  padding: 10px 14px;
  background: var(--el-fill-color-light);
  border-left: 4px solid var(--el-color-primary);
  border-radius: 4px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.warning-item {
  margin-top: 6px;
}

.summary-box {
  margin-top: 10px;
}

.detail-section {
  margin-top: 12px;
}
</style>
