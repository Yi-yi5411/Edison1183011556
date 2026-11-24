<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import { Back, Plus, Refresh, Search, Upload, UploadFilled } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { Personnel } from '@/api/types'

const router = useRouter()
const loading = ref(false)
const items = ref<Personnel[]>([])
const total = ref(0)
const q = ref('')
const roleFilter = ref('')
const activeOnly = ref(false)

const ROLES = ['检测人', '报告编写人', '复核人', '审核人', '批准人', '项目负责人', '其他']

const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref('')
const importVisible = ref(false)
const importing = ref(false)
const importFileList = ref<UploadUserFile[]>([])
const form = reactive({
  name: '',
  role: '',
  cert_no: '',
  phone: '',
  organization: '',
  note: '',
  active: true,
})

async function load() {
  loading.value = true
  try {
    const data = await api.listPersonnel({
      q: q.value.trim(),
      role: roleFilter.value,
      active_only: activeOnly.value,
      limit: 500,
    })
    items.value = data.items
    total.value = data.total
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = ''
  form.name = ''
  form.role = ''
  form.cert_no = ''
  form.phone = ''
  form.organization = ''
  form.note = ''
  form.active = true
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openImport() {
  importFileList.value = []
  importVisible.value = true
}

async function submitImport() {
  const files: File[] = []
  for (const item of importFileList.value) {
    if (item.raw) files.push(item.raw as unknown as File)
  }
  if (!files.length) {
    ElMessage.warning('请先选择人员 Excel 文件')
    return
  }
  importing.value = true
  try {
    let created = 0
    let updated = 0
    let skipped = 0
    const warnings: string[] = []
    for (const file of files) {
      const data = await api.importPersonnel(file)
      created += data.created
      updated += data.updated
      skipped += data.skipped
      if (data.warnings?.length) warnings.push(...data.warnings)
    }
    importVisible.value = false
    importFileList.value = []
    await load()
    const skippedText = skipped ? `，跳过 ${skipped} 行` : ''
    ElMessage.success(`新增 ${created} 人，更新 ${updated} 人${skippedText}`)
    if (warnings.length) {
      ElMessage.warning(`导入提示：${warnings.slice(0, 3).join('；')}`)
    }
  } catch {
    /* api 层已提示 */
  } finally {
    importing.value = false
  }
}

function openEdit(row: unknown) {
  const item = row as Personnel
  editingId.value = item.id
  form.name = item.name
  form.role = item.role
  form.cert_no = item.cert_no
  form.phone = item.phone
  form.organization = item.organization
  form.note = item.note
  form.active = item.active
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写姓名')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.updatePersonnel(editingId.value, { ...form })
      ElMessage.success('人员信息已保存')
    } else {
      await api.createPersonnel({ ...form })
      ElMessage.success('人员已添加到人员库')
    }
    dialogVisible.value = false
    await load()
  } catch {
    /* api 层已提示 */
  } finally {
    saving.value = false
  }
}

async function remove(row: unknown) {
  const item = row as Personnel
  try {
    await ElMessageBox.confirm(`确定从人员库删除「${item.name}」？`, '删除人员', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await api.deletePersonnel(item.id)
    ElMessage.success('人员已删除')
    await load()
  } catch {
    /* api 层已提示 */
  }
}

function search() {
  void load()
}

function resetFilters() {
  q.value = ''
  roleFilter.value = ''
  activeOnly.value = false
  void load()
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="personnel-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/library')">返回资料库</el-button>
        <h2>人员库</h2>
        <el-tag size="small" type="info" effect="plain">{{ total }} 人</el-tag>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button :icon="Upload" @click="openImport">导入 Excel</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增人员</el-button>
      </div>
    </header>

    <section class="personnel-card">
      <div class="toolbar">
        <el-input
          v-model="q"
          :prefix-icon="Search"
          placeholder="搜索姓名 / 证书编号 / 电话 / 单位"
          clearable
          class="search-input"
          @keyup.enter="search"
          @clear="search"
        />
        <el-select v-model="roleFilter" placeholder="全部岗位" clearable class="role-select" @change="search">
          <el-option v-for="role in ROLES" :key="role" :label="role" :value="role" />
        </el-select>
        <el-checkbox v-model="activeOnly" @change="search">只看启用</el-checkbox>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="items" border stripe empty-text="人员库还没有人员，点击右上角新增">
        <el-table-column prop="name" label="姓名" min-width="110" show-overflow-tooltip />
        <el-table-column label="岗位" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.role" size="small" effect="plain">{{ row.role }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="cert_no" label="证书编号" min-width="150" show-overflow-tooltip />
        <el-table-column prop="phone" label="联系电话" width="135" />
        <el-table-column prop="organization" label="所属单位" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'" size="small">
              {{ row.active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="importVisible" title="导入人员 Excel" width="560px" :close-on-click-modal="false">
      <el-upload
        v-model:file-list="importFileList"
        drag
        multiple
        :auto-upload="false"
        :limit="10"
        accept=".xlsx,.xlsm,.csv,.docx"
      >
        <el-icon class="import-icon"><UploadFilled /></el-icon>
        <div class="import-text">拖拽文件到此处，或点击选择</div>
        <div class="import-hint">支持 Excel / CSV / Word 表格，可一次选择多个文件</div>
      </el-upload>
      <div class="import-tip">
        表头需包含“姓名”；可选列：岗位、证书编号、联系电话、所属单位、备注、状态。
        同名且证书编号或电话相同的人员会更新，否则新增。
      </div>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑人员' : '新增人员'" width="560px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="姓名" required>
              <el-input v-model="form.name" placeholder="请输入姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="岗位">
              <el-select v-model="form.role" placeholder="选择岗位" clearable style="width: 100%">
                <el-option v-for="role in ROLES" :key="role" :label="role" :value="role" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="证书编号">
              <el-input v-model="form.cert_no" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系电话">
              <el-input v-model="form.phone" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="所属单位">
              <el-input v-model="form.organization" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="启用状态">
              <el-switch v-model="form.active" active-text="启用" inactive-text="停用" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.personnel-view {
  height: 100%;
  overflow: auto;
  padding: 18px 22px 30px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
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
  font-size: 20px;
}

.page-actions {
  display: flex;
  gap: 6px;
}

.personnel-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
  box-shadow: var(--shadow-sm);
  padding: 12px 14px 14px;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.search-input {
  width: 280px;
}

.role-select {
  width: 130px;
}

.muted {
  color: var(--el-text-color-placeholder);
}

.import-icon {
  font-size: 34px;
  color: var(--el-color-primary);
  margin-bottom: 6px;
}

.import-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.import-hint {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}

.import-tip {
  margin-top: 12px;
  padding: 9px 11px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.7;
}
</style>
