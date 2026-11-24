<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Connection, Delete, Download, Plus, Refresh } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { DshBundle, DshHostStatus, DshMarketIndex } from '@/api/types'

const router = useRouter()
const loading = ref(false)
const connecting = ref(false)
const status = ref<DshHostStatus | null>(null)
const baseUrl = ref('')
const token = ref('')
const bundles = ref<DshBundle[]>([])
const indexes = ref<DshMarketIndex[]>([])
const marketError = ref('')
const newIndex = ref('')
const spec = ref('')
const inspection = ref<any>(null)
const installing = ref(false)

const connected = computed(() => Boolean(status.value?.token_configured))

async function loadStatus() {
  try {
    status.value = await api.getDshHostStatus()
    baseUrl.value = status.value.base_url || ''
  } catch {
    /* api 层已提示 */
  }
}

async function loadBundles() {
  if (!connected.value) return
  try {
    bundles.value = await api.getDshBundles()
  } catch (error) {
    ElMessage.error((error as Error).message || '读取 DSH 插件失败')
  }
}

async function loadIndexes() {
  marketError.value = ''
  if (!connected.value) return
  try {
    indexes.value = await api.getDshIndexes()
  } catch (error) {
    marketError.value = (error as Error).message || '当前 profile 未启用插件市场'
  }
}

async function connect() {
  connecting.value = true
  try {
    const result = await api.saveDshHost(baseUrl.value.trim(), token.value.trim())
    status.value = result.status
    token.value = ''
    ElMessage.success(`DSH Host 已连接，共 ${result.bundle_count} 个 bundle`)
    await Promise.all([loadBundles(), loadIndexes()])
  } catch {
    /* api 层已提示 */
  } finally {
    connecting.value = false
  }
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadBundles(), loadIndexes()])
  } finally {
    loading.value = false
  }
}

async function addIndex() {
  const url = newIndex.value.trim()
  if (!url) return
  const urls = [...indexes.value.map((item) => item.url), url]
  loading.value = true
  try {
    indexes.value = await api.saveDshIndexes(urls)
    newIndex.value = ''
    ElMessage.success('索引源已保存')
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function removeIndex(url: string) {
  try {
    await ElMessageBox.confirm(`移除索引源？\n${url}`, '移除索引源', { type: 'warning' })
  } catch {
    return
  }
  loading.value = true
  try {
    indexes.value = await api.saveDshIndexes(indexes.value.filter((item) => item.url !== url).map((item) => item.url))
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function toggleBundle(row: any, value: boolean) {
  try {
    await ElMessageBox.confirm(
      `${value ? '启用' : '停用'}插件 ${row.name}？\n该变更影响当前 DSH profile，可能要求重启。`,
      '确认变更',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.toggleDshBundle(row.name, value)
    ElMessage.success('插件状态已更新')
    await loadBundles()
  } catch {
    row.enabled = !value
  }
}

async function removeBundle(row: any) {
  try {
    await ElMessageBox.confirm(
      `删除插件 ${row.name}？\n删除后重新安装才能恢复。`,
      '删除插件',
      { type: 'error', confirmButtonText: '删除' },
    )
  } catch {
    return
  }
  try {
    await api.removeDshBundle(row.name)
    ElMessage.success('插件已删除')
    await loadBundles()
  } catch {
    /* api 层已提示 */
  }
}

async function inspectSpec() {
  if (!spec.value.trim()) return
  loading.value = true
  inspection.value = null
  try {
    inspection.value = await api.inspectDshPlugin(spec.value.trim())
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function installSpec() {
  if (!spec.value.trim()) return
  const result = inspection.value
  if (!result || result.status !== 'accepted') {
    ElMessage.warning('请先检查插件包，确认可安装')
    return
  }
  const version = result.version || ''
  try {
    await ElMessageBox.confirm(
      `安装 ${result.name || spec.value} ${version ? '@' + version : ''}？\n插件代码会进入当前 DSH profile。`,
      '确认安装',
      { type: 'warning', confirmButtonText: '安装' },
    )
  } catch {
    return
  }
  installing.value = true
  try {
    await api.installDshPlugin(spec.value.trim(), result.name && version
      ? { name: result.name, version }
      : undefined)
    ElMessage.success('插件安装完成')
    inspection.value = null
    spec.value = ''
    await loadBundles()
  } catch {
    /* api 层已提示 */
  } finally {
    installing.value = false
  }
}

function titleOf(value: any): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  return String(value.zh || value.en || Object.values(value)[0] || '')
}

onMounted(async () => {
  loading.value = true
  await loadStatus()
  await Promise.all([loadBundles(), loadIndexes()])
  loading.value = false
})
</script>

<template>
  <div class="dsh-host-page" v-loading="loading">
    <header class="page-header">
      <div>
        <el-button text :icon="Back" @click="router.push('/plugins')">返回插件中心</el-button>
        <h2>DSH 插件市场 / Host API</h2>
        <p>直接调用 DSH Host 的 pluginManager / pluginMarket 接口，安装到当前 DSH profile。</p>
      </div>
      <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
    </header>

    <el-alert type="warning" :closable="false" show-icon class="tip"
      title="Host token 等同 DSH 本机控制权限，只保存在本机 data/dsh_host.json，不会回传浏览器。"
      description="从 DSH 启动 URL 的 ?token=... 复制；base URL 要与该 DSH 实例一致（例如 127.0.0.1:6602）。" />

    <el-card shadow="never" class="connect-card">
      <template #header>
        <div class="card-head">
          <span><el-icon><Connection /></el-icon> Host 连接</span>
          <el-tag v-if="status?.token_configured" type="success" size="small">已配置 token</el-tag>
          <el-tag v-else type="info" size="small">未连接</el-tag>
        </div>
      </template>
      <div class="connect-form">
        <el-input v-model="baseUrl" placeholder="http://127.0.0.1:6602" />
        <el-input v-model="token" type="password" show-password
          placeholder="粘贴 DSH 启动 URL 的 token（留空则保留已保存 token）" />
        <el-button type="primary" :loading="connecting" @click="connect">连接 / 保存</el-button>
      </div>
      <div v-if="status?.last_error" class="error-text">{{ status.last_error }}</div>
    </el-card>

    <div class="two-col">
      <el-card shadow="never">
        <template #header>
          <div class="card-head">
            <span>已安装 Bundle（{{ bundles.length }}）</span>
            <el-button text :icon="Refresh" @click="loadBundles">刷新</el-button>
          </div>
        </template>
        <el-table :data="bundles" border stripe height="420" empty-text="暂无 bundle">
          <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
          <el-table-column prop="version" label="版本" width="120" />
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch :model-value="!!row.enabled" size="small"
                :disabled="row.readOnlyReason === 'management-required'"
                @change="(v: any) => toggleBundle(row, Boolean(v))" />
            </template>
          </el-table-column>
          <el-table-column label="来源" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.official ? 'success' : 'info'">
                {{ row.official ? '官方' : (row.installed ? '外部' : '随 DSH') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button v-if="row.removable" text type="danger" :icon="Delete"
                @click="removeBundle(row)" />
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-head"><span>安装外部插件</span></div>
        </template>
        <p class="hint">支持 npm 包名、绝对路径、Git 地址或 tarball；安装前先检查。</p>
        <el-input v-model="spec" placeholder="例如 @scope/my-dsh-plugin 或 D:\my-plugin" clearable />
        <div class="install-actions">
          <el-button :icon="Download" :loading="loading" @click="inspectSpec">检查</el-button>
          <el-button type="primary" :icon="Plus" :loading="installing"
            :disabled="inspection?.status !== 'accepted'" @click="installSpec">安装</el-button>
        </div>
        <div v-if="inspection" class="inspect-result">
          <el-tag :type="inspection.status === 'accepted' ? 'success' : 'danger'">
            {{ inspection.status }}
          </el-tag>
          <div v-if="inspection.name" class="inspect-name">
            {{ inspection.name }} <span v-if="inspection.version">@{{ inspection.version }}</span>
          </div>
          <div v-if="inspection.description" class="inspect-desc">{{ inspection.description }}</div>
          <div v-if="inspection.reason" class="error-text">{{ inspection.reason }}</div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="index-card">
      <template #header>
        <div class="card-head">
          <span>插件市场索引源</span>
          <el-tag v-if="marketError" type="warning" size="small">市场服务不可用</el-tag>
        </div>
      </template>
      <el-alert v-if="marketError" type="warning" :closable="false" show-icon
        :title="marketError"
        description="当前 DSH profile 可能未启用 plugin-market bundle；可先在右侧安装 @deepseek-ai/dsh-experimental-plugin-market-bundle，或在 DSH 原生插件页添加索引。" />
      <template v-else>
        <div class="index-add">
          <el-input v-model="newIndex" placeholder="https://example.com/plugin-market.json" clearable
            @keyup.enter="addIndex" />
          <el-button :icon="Plus" @click="addIndex">添加索引源</el-button>
        </div>
        <div v-if="indexes.length" class="index-list">
          <div v-for="item in indexes" :key="item.url" class="index-row">
            <div class="index-main">
              <b>{{ titleOf(item.title) || item.url }}</b>
              <span>{{ item.url }}</span>
              <em v-if="item.error" class="error-text">{{ item.error }}</em>
            </div>
            <el-button text type="danger" :icon="Delete" @click="removeIndex(item.url)" />
          </div>
        </div>
        <el-empty v-else description="尚未配置索引源" :image-size="50" />
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.dsh-host-page { padding: 18px 22px 30px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.page-header h2 { margin: 4px 0 5px; font-size: 22px; }
.page-header p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.tip { margin-bottom: 14px; }
.connect-card, .index-card { margin-bottom: 14px; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.card-head span { display: inline-flex; align-items: center; gap: 5px; }
.connect-form { display: flex; gap: 8px; flex-wrap: wrap; }
.connect-form .el-input:first-child { flex: 0 0 300px; }
.connect-form .el-input:nth-child(2) { flex: 1; min-width: 300px; }
.two-col { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(340px, 0.8fr); gap: 14px; margin-bottom: 14px; }
.hint { margin: 0 0 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.install-actions { display: flex; gap: 8px; margin-top: 10px; }
.inspect-result { margin-top: 12px; padding: 10px; border-radius: 8px; background: var(--el-fill-color-lighter); }
.inspect-name { margin-top: 6px; font-weight: 600; }
.inspect-desc { margin-top: 5px; font-size: 12px; color: var(--el-text-color-regular); }
.index-add { display: flex; gap: 8px; }
.index-add .el-input { flex: 1; }
.index-list { display: grid; gap: 8px; margin-top: 12px; }
.index-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; }
.index-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.index-main span { color: var(--el-text-color-secondary); font-size: 12px; word-break: break-all; }
.index-main em { font-style: normal; }
.error-text { color: var(--el-color-danger); font-size: 12px; margin-top: 6px; }
@media (max-width: 900px) {
  .two-col { grid-template-columns: 1fr; }
  .connect-form .el-input:first-child, .connect-form .el-input:nth-child(2) { flex: 1 1 100%; }
}
</style>
