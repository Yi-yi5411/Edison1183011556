<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Refresh, Search } from '@element-plus/icons-vue'
import { api } from '@/api'
import type {
  EquipmentLocal,
  EquipmentRemotePage,
  EquipmentRemoteRecord,
  EquipmentStatus,
} from '@/api/types'

const router = useRouter()
const status = ref<EquipmentStatus | null>(null)
const loggedIn = ref(false)
const loginLoading = ref(false)
const loginForm = reactive({
  username: '06055',
  password: '',
  captcha: '',
})
const captcha = reactive({ key: '', image: '' })
const captchaLoading = ref(false)

const remote = ref<EquipmentRemotePage>({ records: [], total: 0, page_no: 1, page_size: 20 })
const remoteLoading = ref(false)
const remoteQuery = reactive({ keyword: '', status: '' })
const remotePage = ref(1)
const remotePageSize = ref(20)
const remoteSelection = ref<EquipmentRemoteRecord[]>([])
const syncLoading = ref(false)

const local = ref<EquipmentLocal[]>([])
const localTotal = ref(0)
const localLoading = ref(false)
const localQuery = ref('')
const localSelectedOnly = ref(false)
const activeTab = ref<'remote' | 'local'>('remote')

function onTabChange(name: string | number) {
  if (name === 'local') loadLibrary()
}

function errText(e: unknown): string {
  return e instanceof Error ? e.message : '操作失败'
}

async function loadStatus() {
  try {
    status.value = await api.equipmentStatus()
    loggedIn.value = !!status.value?.logged_in
  } catch {
    // 后端未启动时由全局请求层提示
  }
}

async function loadCaptcha() {
  captchaLoading.value = true
  try {
    const data = await api.equipmentCaptcha()
    captcha.key = data.key
    captcha.image = data.image
    loginForm.captcha = ''
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    captchaLoading.value = false
  }
}

async function doLogin() {
  if (!loginForm.username.trim()) {
    ElMessage.warning('请输入设备系统账号')
    return
  }
  if (!loginForm.password) {
    ElMessage.warning('请输入设备系统密码')
    return
  }
  if (!loginForm.captcha.trim()) {
    ElMessage.warning('请输入验证码')
    return
  }
  loginLoading.value = true
  try {
    status.value = await api.equipmentLogin({
      username: loginForm.username.trim(),
      password: loginForm.password,
      captcha: loginForm.captcha.trim(),
      check_key: captcha.key,
    })
    loggedIn.value = !!status.value?.logged_in
    loginForm.password = ''
    ElMessage.success('设备管理系统登录成功')
    await Promise.all([loadRemote(1), loadLibrary()])
  } catch (e) {
    ElMessage.error(errText(e))
    await loadCaptcha()
  } finally {
    loginLoading.value = false
  }
}

async function doLogout() {
  try {
    status.value = await api.equipmentLogout()
    loggedIn.value = false
    remote.value = { records: [], total: 0, page_no: 1, page_size: 20 }
    ElMessage.success('已退出设备管理系统')
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

async function loadRemote(page = remotePage.value) {
  if (!loggedIn.value) return
  remoteLoading.value = true
  try {
    remotePage.value = page
    remote.value = await api.equipmentRemote({
      page_no: page,
      page_size: remotePageSize.value,
      keyword: remoteQuery.keyword.trim(),
      status: remoteQuery.status,
    })
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    remoteLoading.value = false
  }
}

function searchRemote() {
  loadRemote(1)
}

function onRemoteSelection(rows: EquipmentRemoteRecord[]) {
  remoteSelection.value = rows
}

async function syncSelected() {
  if (!remoteSelection.value.length) {
    ElMessage.warning('请先在远程设备列表中勾选设备')
    return
  }
  syncLoading.value = true
  try {
    const ids = remoteSelection.value.map((r) => String(r.id))
    const res = await api.equipmentSync(ids, false)
    ElMessage.success(`已同步 ${res.synced} 台设备到本地库`)
    await Promise.all([loadStatus(), loadLibrary()])
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    syncLoading.value = false
  }
}

async function syncAll() {
  try {
    await ElMessageBox.confirm(
      `将同步当前设备系统中全部 ${remote.value.total} 台设备到本地库，设备较多时耗时较长。确定继续吗？`,
      '全量同步',
      { type: 'warning', confirmButtonText: '开始同步', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  syncLoading.value = true
  try {
    const res = await api.equipmentSync([], true)
    ElMessage.success(`已同步 ${res.synced} 台设备`)
    await Promise.all([loadStatus(), loadLibrary()])
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    syncLoading.value = false
  }
}

async function loadLibrary() {
  localLoading.value = true
  try {
    const data = await api.equipmentLibrary(localQuery.value.trim(), localSelectedOnly.value)
    local.value = data.records
    localTotal.value = data.total
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    localLoading.value = false
  }
}

async function toggleSelected(row: any, selected: boolean) {
  try {
    await api.equipmentSelect([row.id], selected)
    row.selected = selected
    ElMessage.success(selected ? '已设为报告优先' : '已取消报告优先')
  } catch (e) {
    row.selected = !selected
    ElMessage.error(errText(e))
  }
}

async function removeLocal(row: any) {
  try {
    await ElMessageBox.confirm(`确定从本地设备库删除“${row.name}”吗？`, '删除设备', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.equipmentDelete([row.id])
    ElMessage.success('已删除')
    await Promise.all([loadStatus(), loadLibrary()])
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

onMounted(async () => {
  await loadStatus()
  await Promise.all([loadLibrary(), loggedIn.value ? loadRemote(1) : loadCaptcha()])
})
</script>

<template>
  <div class="equipment-page">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/library')">返回资料库</el-button>
        <h2>设备库</h2>
        <el-tag size="small" type="info" effect="plain">设备管理系统同步 + 报告优先选用</el-tag>
      </div>
    </header>
    <el-card shadow="never" class="status-card">
      <div class="status-row">
        <div>
          <div class="status-title">设备管理系统</div>
          <div class="status-sub">
            {{ status?.base_url || '—' }}
            <span v-if="loggedIn"> · 账号 {{ status?.username }}</span>
            <span v-if="loggedIn && status?.expires_at"> · 有效期至 {{ status.expires_at }}</span>
          </div>
        </div>
        <div class="status-actions">
          <el-tag :type="loggedIn ? 'success' : 'info'">
            {{ loggedIn ? '已连接' : '未登录' }}
          </el-tag>
          <el-tag type="warning">本地 {{ status?.local_count ?? localTotal }} 台</el-tag>
          <el-button size="small" text @click="router.push('/workflow')">流程总览</el-button>
          <el-button v-if="loggedIn" size="small" @click="doLogout">退出登录</el-button>
          <el-button v-else size="small" type="primary" @click="loadCaptcha">刷新验证码</el-button>
        </div>
      </div>

      <div v-if="!loggedIn" class="login-box">
        <el-alert
          type="info"
          :closable="false"
          title="设备数据来自设备管理系统，首次使用需用设备系统账号和验证码登录"
          description="登录状态仅保存在本机后端；账号密码不会写入报告。"
        />
        <el-form :inline="true" class="login-form" @submit.prevent="doLogin">
          <el-form-item label="账号">
            <el-input v-model="loginForm.username" placeholder="设备系统账号" style="width: 140px" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="loginForm.password"
              type="password"
              show-password
              placeholder="设备系统密码"
              style="width: 180px"
              @keyup.enter="doLogin"
            />
          </el-form-item>
          <el-form-item label="验证码">
            <el-input
              v-model="loginForm.captcha"
              placeholder="验证码"
              maxlength="8"
              style="width: 110px"
              @keyup.enter="doLogin"
            />
            <img
              v-if="captcha.image"
              :src="captcha.image"
              class="captcha-img"
              title="点击刷新验证码"
              @click="loadCaptcha"
            />
            <el-button :icon="Refresh" :loading="captchaLoading" circle @click="loadCaptcha" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loginLoading" @click="doLogin">登录并加载设备</el-button>
          </el-form-item>
        </el-form>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" class="equipment-tabs" @tab-change="onTabChange">
      <el-tab-pane label="远程设备" name="remote" :disabled="!loggedIn">
        <el-card shadow="never">
          <div class="toolbar">
            <el-input
              v-model="remoteQuery.keyword"
              placeholder="设备名称搜索"
              clearable
              style="width: 240px"
              :prefix-icon="Search"
              @keyup.enter="searchRemote"
              @clear="searchRemote"
            />
            <el-select v-model="remoteQuery.status" placeholder="设备状态" clearable style="width: 120px">
              <el-option label="在用" value="在用" />
              <el-option label="停用" value="停用" />
            </el-select>
            <el-button type="primary" @click="searchRemote">查询</el-button>
            <el-button :disabled="!remoteSelection.length" :loading="syncLoading" @click="syncSelected">
              同步选中（{{ remoteSelection.length }}）
            </el-button>
            <el-button :loading="syncLoading" @click="syncAll">全量同步</el-button>
          </div>
          <el-table
            v-loading="remoteLoading"
            :data="remote.records"
            row-key="id"
            border
            stripe
            max-height="calc(100vh - 390px)"
            @selection-change="onRemoteSelection"
          >
            <el-table-column type="selection" width="44" reserve-selection />
            <el-table-column prop="equipmentName" label="设备名称" min-width="170" show-overflow-tooltip />
            <el-table-column prop="equipmentId1" label="受控编号" width="115" />
            <el-table-column prop="equipmentType1" label="规格型号" width="130" show-overflow-tooltip />
            <el-table-column prop="equipmentId5_dictText" label="状态" width="80" />
            <el-table-column prop="equipmentPlace2_dictText" label="管理部门" width="120" show-overflow-tooltip />
            <el-table-column prop="codes" label="授权使用人" width="100" />
            <el-table-column prop="codetwo" label="最近检定日期" width="110" />
            <el-table-column prop="code" label="检定证书编号" min-width="155" show-overflow-tooltip />
            <el-table-column prop="equipmentDate" label="下次检定日期" width="110" />
          </el-table>
          <el-pagination
            class="pager"
            background
            layout="total, sizes, prev, pager, next"
            :total="remote.total"
            :current-page="remotePage"
            :page-size="remotePageSize"
            :page-sizes="[10, 20, 50, 100]"
            @current-change="loadRemote"
            @size-change="(size: number) => { remotePageSize = size; loadRemote(1) }"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="本地设备库" name="local">
        <el-card shadow="never">
          <div class="toolbar">
            <el-input
              v-model="localQuery"
              placeholder="本地设备名称/编号搜索"
              clearable
              style="width: 260px"
              :prefix-icon="Search"
              @keyup.enter="loadLibrary"
              @clear="loadLibrary"
            />
            <el-checkbox v-model="localSelectedOnly" @change="loadLibrary">只看报告优先</el-checkbox>
            <el-button @click="loadLibrary">刷新</el-button>
            <span class="hint">“报告优先”仅表示优先；报告生成时仍要求设备在用且当天使用少于10次。</span>
          </div>
          <el-table v-loading="localLoading" :data="local" row-key="id" border stripe>
            <el-table-column prop="name" label="设备名称" min-width="170" show-overflow-tooltip />
            <el-table-column prop="category_code" label="受控编号" width="115" />
            <el-table-column prop="model" label="规格型号" width="130" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="75" />
            <el-table-column prop="department" label="管理部门" width="120" show-overflow-tooltip />
            <el-table-column prop="last_check_date" label="最近检定" width="105" />
            <el-table-column prop="cert_no" label="检定证书编号" min-width="155" show-overflow-tooltip />
            <el-table-column label="报告优先" width="105" fixed="right">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.selected"
                  @update:model-value="(v: string | number | boolean) => toggleSelected(row, Boolean(v))"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="removeLocal(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="local-total">本地设备库共 {{ localTotal }} 台</div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.equipment-page {
  padding: 16px;
  height: 100%;
  overflow: auto;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
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
.status-card {
  margin-bottom: 12px;
}
.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.status-title {
  font-size: 17px;
  font-weight: 600;
}
.status-sub {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  word-break: break-all;
}
.status-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.login-box {
  margin-top: 14px;
}
.login-form {
  margin-top: 12px;
}
.captcha-img {
  height: 32px;
  margin: 0 6px;
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
}
.equipment-tabs {
  margin-top: 4px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.local-total {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
