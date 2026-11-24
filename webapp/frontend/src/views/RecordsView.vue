<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back,
  Document,
  FolderOpened,
  Refresh,
  Search,
} from '@element-plus/icons-vue'
import { api } from '@/api'
import type {
  OriginalRecord,
  ReportRecord,
} from '@/api/types'

const router = useRouter()
const route = useRoute()

const tab = ref<'report' | 'original'>(route.query.tab === 'original' ? 'original' : 'report')
const loading = ref(false)
const q = ref('')
const project = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const reportRows = ref<ReportRecord[]>([])
const originalRows = ref<OriginalRecord[]>([])

const detailVisible = ref(false)
const selectedReport = ref<ReportRecord | null>(null)
const selectedOriginal = ref<OriginalRecord | null>(null)
const detailLoading = ref(false)

async function loadRecords() {
  loading.value = true
  try {
    const params = {
      q: q.value.trim(),
      project: project.value.trim(),
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    }
    if (tab.value === 'report') {
      const data = await api.listReportRecords(params)
      reportRows.value = data.items
      total.value = data.total
    } else {
      const data = await api.listOriginalRecords(params)
      originalRows.value = data.items
      total.value = data.total
    }
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function reloadAll() {
  await loadRecords()
}

function onTabChange() {
  page.value = 1
  void router.replace({ query: { ...route.query, tab: tab.value } })
  void loadRecords()
}

watch(
  () => route.query.tab,
  (value) => {
    const next = value === 'original' ? 'original' : 'report'
    if (next === tab.value) return
    tab.value = next
    page.value = 1
    void loadRecords()
  },
)

function search() {
  page.value = 1
  void loadRecords()
}

function resetFilters() {
  q.value = ''
  project.value = ''
  page.value = 1
  void loadRecords()
}

function onPageChange(value: number) {
  page.value = value
  void loadRecords()
}

async function revealFile(filepath: string) {
  if (!filepath) return
  try {
    await api.revealFile(filepath)
  } catch {
    /* api 层已提示 */
  }
}

function editReport(filepath: string) {
  if (!filepath) return
  router.push({ path: '/report-edit', query: { filepath } })
}

async function deleteReport(row: any) {
  try {
    await ElMessageBox.confirm(
      `仅删除报告记录，不会删除磁盘文件：\n${row.filepath}`,
      '删除报告记录',
      { confirmButtonText: '删除记录', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.deleteReportRecord(row.id)
    ElMessage.success('报告记录已删除（文件保留）')
    await reloadAll()
  } catch {
    /* api 层已提示 */
  }
}

async function deleteOriginal(row: any) {
  try {
    await ElMessageBox.confirm(
      `仅删除原始记录，不会删除磁盘文件：\n${row.filepath}`,
      '删除原始记录',
      { confirmButtonText: '删除记录', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.deleteOriginalRecord(row.id)
    ElMessage.success('原始记录已删除（文件保留）')
    await reloadAll()
  } catch {
    /* api 层已提示 */
  }
}

async function openReportDetail(row: any) {
  detailLoading.value = true
  detailVisible.value = true
  selectedReport.value = row
  selectedOriginal.value = null
  try {
    selectedReport.value = await api.getReportRecord(row.id)
  } catch {
    /* api 层已提示 */
  } finally {
    detailLoading.value = false
  }
}

async function openOriginalDetail(row: any) {
  detailLoading.value = true
  detailVisible.value = true
  selectedOriginal.value = row
  selectedReport.value = null
  try {
    selectedOriginal.value = await api.getOriginalRecord(row.id)
  } catch {
    /* api 层已提示 */
  } finally {
    detailLoading.value = false
  }
}

async function downloadSnapshot(row: any) {
  if (!row.has_snapshot) return
  try {
    await api.downloadOriginalSnapshot(row.id, `${row.sheet_key}_快照.json`)
  } catch {
    /* api 层已提示 */
  }
}

function filenameOf(filepath: string): string {
  return filepath.split(/[\\/]/).pop() || filepath
}

function formatSize(value: number): string {
  if (!value) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

function tablesText(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join('、') : '—'
  if (typeof value === 'number') return String(value)
  return '—'
}

function warningsText(value: unknown): string {
  return Array.isArray(value) && value.length ? value.join('；') : '无'
}

onMounted(async () => {
  await loadRecords()
})
</script>

<template>
  <div class="records-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/library')">返回资料库</el-button>
        <h2>记录库</h2>
        <el-tag type="info" size="small" effect="plain">报告记录 + 原始记录</el-tag>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="reloadAll">刷新</el-button>
        <el-button :icon="Document" @click="router.push('/report')">生成报告</el-button>
      </div>
    </header>

    <section class="records-card">
      <div class="records-toolbar">
        <el-radio-group v-model="tab" size="small" @change="onTabChange">
          <el-radio-button value="report">报告记录</el-radio-button>
          <el-radio-button value="original">原始记录</el-radio-button>
        </el-radio-group>
        <div class="filter-row">
          <el-input
            v-model="q"
            size="small"
            clearable
            placeholder="关键词：报告编号 / 文件名 / 检测项"
            :prefix-icon="Search"
            class="filter-input"
            @keyup.enter="search"
            @clear="search"
          />
          <el-input
            v-model="project"
            size="small"
            clearable
            placeholder="项目名"
            class="filter-project"
            @keyup.enter="search"
            @clear="search"
          />
          <el-button size="small" type="primary" @click="search">查询</el-button>
          <el-button size="small" @click="resetFilters">重置</el-button>
        </div>
      </div>

      <el-table
        v-if="tab === 'report'"
        v-loading="loading"
        :data="reportRows"
        size="small"
        border
        class="records-table"
        empty-text="暂无报告记录"
      >
        <el-table-column label="报告编号" width="150" prop="report_no" show-overflow-tooltip />
        <el-table-column label="文件" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="file-name">{{ filenameOf(row.filepath) }}</span>
            <el-tag v-if="!row.exists" type="danger" size="small" style="margin-left: 6px">文件缺失</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="项目" prop="project_name" min-width="180" show-overflow-tooltip />
        <el-table-column label="模板" prop="template_name" min-width="150" show-overflow-tooltip />
        <el-table-column label="引擎" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.engine === 'agent' ? 'success' : 'info'">
              {{ row.engine === 'agent' ? 'Agent' : '直接' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="表数" width="70">
          <template #default="{ row }">{{ tablesText(row.tables) }}</template>
        </el-table-column>
        <el-table-column label="生成时间" width="150" prop="generated_at" />
        <el-table-column label="操作" width="235" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openReportDetail(row)">详情</el-button>
            <el-button link size="small" :disabled="!row.exists" @click="revealFile(row.filepath)">定位</el-button>
            <el-button link size="small" @click="editReport(row.filepath)">修改</el-button>
            <el-button link size="small" type="danger" @click="deleteReport(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else
        v-loading="loading"
        :data="originalRows"
        size="small"
        border
        class="records-table"
        empty-text="暂无原始记录"
      >
        <el-table-column label="检测项目" min-width="220">
          <template #default="{ row }">
            {{ row.sheet_key }}
            <el-tag v-if="row.has_snapshot" size="small" type="success" style="margin-left: 6px">快照</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="file-name">{{ filenameOf(row.filepath) }}</span>
            <el-tag v-if="!row.exists" type="danger" size="small" style="margin-left: 6px">文件缺失</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="项目" prop="project_name" min-width="180" show-overflow-tooltip />
        <el-table-column label="模板" prop="template_name" min-width="150" show-overflow-tooltip />
        <el-table-column label="行数" width="70" prop="rows_count" />
        <el-table-column label="生成时间" width="150" prop="generated_at" />
        <el-table-column label="操作" width="235" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openOriginalDetail(row)">详情</el-button>
            <el-button link size="small" :disabled="!row.exists" @click="revealFile(row.filepath)">定位</el-button>
            <el-button v-if="row.has_snapshot" link size="small" @click="downloadSnapshot(row)">快照</el-button>
            <el-button link size="small" type="danger" @click="deleteOriginal(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          small
          @current-change="onPageChange"
        />
      </div>
    </section>

    <el-dialog v-model="detailVisible" title="记录详情" width="min(760px, 92vw)">
      <div v-loading="detailLoading">
        <template v-if="selectedReport">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="报告编号">{{ selectedReport.report_no || '—' }}</el-descriptions-item>
            <el-descriptions-item label="引擎">{{ selectedReport.engine }}</el-descriptions-item>
            <el-descriptions-item label="项目" :span="2">{{ selectedReport.project_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="模板" :span="2">{{ selectedReport.template_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="报告文件" :span="2">{{ selectedReport.filepath }}</el-descriptions-item>
            <el-descriptions-item label="数据表数">{{ tablesText(selectedReport.tables) }}</el-descriptions-item>
            <el-descriptions-item label="已评定项">{{ selectedReport.assessed_count }}</el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ formatSize(selectedReport.file_size) }}</el-descriptions-item>
            <el-descriptions-item label="生成时间">{{ selectedReport.generated_at }}</el-descriptions-item>
            <el-descriptions-item label="警告" :span="2">{{ warningsText(selectedReport.warnings) }}</el-descriptions-item>
          </el-descriptions>
        </template>
        <template v-else-if="selectedOriginal">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="检测项目" :span="2">{{ selectedOriginal.sheet_key }}</el-descriptions-item>
            <el-descriptions-item label="基础项目">{{ selectedOriginal.base_item || '—' }}</el-descriptions-item>
            <el-descriptions-item label="模板">{{ selectedOriginal.template_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="项目" :span="2">{{ selectedOriginal.project_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="记录文件" :span="2">{{ selectedOriginal.filepath }}</el-descriptions-item>
            <el-descriptions-item label="数据行数">{{ selectedOriginal.rows_count }}</el-descriptions-item>
            <el-descriptions-item label="生成时间">{{ selectedOriginal.generated_at }}</el-descriptions-item>
            <el-descriptions-item label="数据快照">{{ selectedOriginal.has_snapshot ? `${formatSize(selectedOriginal.snapshot_size)}` : '无' }}</el-descriptions-item>
            <el-descriptions-item label="警告">{{ warningsText(selectedOriginal.warnings) }}</el-descriptions-item>
          </el-descriptions>
          <div class="detail-actions">
            <el-button
              v-if="selectedOriginal.has_snapshot"
              type="primary"
              size="small"
              @click="downloadSnapshot(selectedOriginal)"
            >
              下载数据快照
            </el-button>
            <el-button size="small" :icon="FolderOpened" @click="revealFile(selectedOriginal.filepath)">定位文件</el-button>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.records-view {
  height: 100%;
  overflow: auto;
  padding: 14px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.page-header {
  flex: none;
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
  gap: 6px;
}
.records-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
  padding: 10px 12px 12px;
}
.records-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.filter-input {
  width: 260px;
}
.filter-project {
  width: 170px;
}
.records-table {
  width: 100%;
}
.file-name {
  font-family: Consolas, monospace;
  font-size: 11.5px;
}
.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.detail-actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}
@media (max-width: 720px) {
  .filter-input,
  .filter-project {
    width: 100%;
  }
}
</style>
