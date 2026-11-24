<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FolderOpened, Plus, Refresh, Warning } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { DshPluginsStatus, ExternalPluginStatus } from '@/api/types'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()
const loading = ref(false)
const status = ref<ExternalPluginStatus>({ roots: [], records: [], loaded: 0, errors: 0 })
const dsh = ref<DshPluginsStatus | null>(null)
const roots = ref<string[]>([])
const newRoot = ref('')

const records = computed(() => status.value.records)
const builtinCount = computed(() => store.plugins.filter((p) => !p.external).length)
const externalCount = computed(() => store.plugins.filter((p) => p.external).length)

async function load() {
  loading.value = true
  try {
    const [external, dshStatus] = await Promise.all([
      api.getExternalPlugins(),
      api.getDshPlugins(),
    ])
    status.value = external
    dsh.value = dshStatus
    roots.value = [...(status.value.roots || [])]
    if (!store.plugins.length) await store.loadPlugins()
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

function addRoot() {
  const path = newRoot.value.trim()
  if (!path) return
  if (!roots.value.includes(path)) roots.value.push(path)
  newRoot.value = ''
}

async function saveRoots() {
  loading.value = true
  try {
    status.value = await api.saveExternalPluginSources(roots.value)
    roots.value = [...status.value.roots]
    await Promise.all([store.loadPlugins(), store.loadProject()])
    ElMessage.success('外部插件目录已保存并重新加载')
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function reload() {
  loading.value = true
  try {
    status.value = await api.reloadPlugins()
    await Promise.all([store.loadPlugins(), store.loadProject()])
    ElMessage.success(`插件已重新加载：外部 ${status.value.loaded} 个`)
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

function statusType(row: any): 'success' | 'danger' | 'warning' | 'info' {
  if (row.status === 'loaded') return 'success'
  if (row.status === 'error') return 'danger'
  if (row.status === 'missing') return 'warning'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="plugins-page" v-loading="loading">
    <header class="page-header">
      <div>
        <h2>插件管理</h2>
        <p>内置检测项目 + 外部插件目录，保存后无需重启后端即可重新加载。</p>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" @click="reload">重新加载全部插件</el-button>
      </div>
    </header>

    <el-alert
      type="warning"
      show-icon
      :closable="false"
      title="外部插件会执行本机 Python 代码，请只加载可信来源；纯 manifest 插件不执行代码。"
      description="外部目录结构：<目录>/<plugin_id>/plugin.json（必需），可选 plugin.py。plugin.json 的 source 为 manifest 或 python。"
      class="security-alert"
    />

    <el-card shadow="never" class="dsh-card">
      <template #header>
        <div class="card-head">
          <span>DSH 原生智能体能力</span>
          <div class="dsh-actions">
            <el-tag v-if="dsh" type="success" effect="plain">Agent 底座：DSH</el-tag>
            <el-button size="small" @click="router.push('/plugins/dsh')">DSH 插件市场管理</el-button>
          </div>
        </div>
      </template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="子智能体、网页搜索/获取、Agent 循环、终端、语音、授权审查、工作树和插件市场由 DSH 原生提供；本项目只做清单、入口与配置状态展示。"
        style="margin-bottom: 12px"
      />
      <div v-if="dsh" class="dsh-meta">
        <span>DSH GUI：{{ dsh.gui_url }}</span>
        <span>插件目录：{{ dsh.plugin_dir }}</span>
      </div>
      <div v-if="dsh" class="cap-grid">
        <div v-for="cap in dsh.capabilities" :key="cap.key" class="cap-card">
          <div class="cap-title">
            {{ cap.title }}
            <el-tag size="small" type="success">DSH</el-tag>
          </div>
          <div class="cap-desc">{{ cap.desc }}</div>
          <div class="cap-meta">{{ cap.surface }} · {{ cap.module }}</div>
        </div>
      </div>
      <div v-if="dsh" class="bundle-row">
        <span class="bundle-label">Profile bundles</span>
        <el-tag v-for="name in dsh.bundles" :key="name" size="small" effect="plain">{{ name }}</el-tag>
      </div>
      <div v-if="dsh" class="market-row">
        <span>{{ dsh.market_hint }}</span>
      </div>
    </el-card>

    <div class="stats">
      <div class="stat"><b>{{ builtinCount }}</b><span>内置插件</span></div>
      <div class="stat"><b>{{ externalCount }}</b><span>外部插件</span></div>
      <div class="stat"><b>{{ status.loaded }}</b><span>外部加载成功</span></div>
      <div class="stat" :class="{ bad: status.errors }"><b>{{ status.errors }}</b><span>加载失败</span></div>
    </div>

    <el-card shadow="never" class="source-card">
      <template #header>
        <div class="card-head">
          <span>外部插件目录</span>
          <span class="hint">支持绝对路径；目录不存在时保存会自动创建</span>
        </div>
      </template>
      <div class="source-add">
        <el-input v-model="newRoot" placeholder="例如 D:\structural-plugins 或 C:\...\plugins\external" clearable @keyup.enter="addRoot" />
        <el-button :icon="Plus" @click="addRoot">添加目录</el-button>
        <el-button type="primary" @click="saveRoots">保存并重载</el-button>
      </div>
      <div v-if="roots.length" class="root-list">
        <el-tag
          v-for="(root, index) in roots"
          :key="root"
          closable
          type="info"
          size="large"
          @close="roots.splice(index, 1)"
        >
          {{ root }}
        </el-tag>
      </div>
      <el-empty v-else description="尚未配置外部插件目录" :image-size="60" />
    </el-card>

    <el-card shadow="never" class="records-card">
      <template #header>
        <div class="card-head">
          <span>外部插件加载记录</span>
          <span class="hint">只显示外部目录；内置插件由 modules/ 自动发现</span>
        </div>
      </template>
      <el-table :data="records" border stripe row-key="path" empty-text="暂无外部插件">
        <el-table-column prop="id" label="插件 ID" width="170" show-overflow-tooltip />
        <el-table-column prop="name" label="名称" min-width="190" show-overflow-tooltip />
        <el-table-column prop="source" label="类型" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="插件目录" min-width="300" show-overflow-tooltip />
        <el-table-column label="错误 / 提示" min-width="260">
          <template #default="{ row }">
            <div v-if="row.errors?.length" class="error-text">
              <el-icon><Warning /></el-icon>{{ row.errors.join('；') }}
            </div>
            <div v-else-if="row.warnings?.length" class="warn-text">{{ row.warnings.join('；') }}</div>
            <span v-else class="ok-text">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="builtin-card">
      <template #header>
        <div class="card-head">
          <span>当前已加载检测项目</span>
          <el-button text :icon="FolderOpened" @click="load">刷新</el-button>
        </div>
      </template>
      <div class="plugin-tags">
        <el-tag
          v-for="p in store.plugins"
          :key="p.id"
          :type="p.external ? 'warning' : 'info'"
          effect="plain"
          size="large"
        >
          {{ p.name }}
          <span class="plugin-source">{{ p.external ? '外部' : '内置' }}</span>
        </el-tag>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.plugins-page {
  padding: 18px 22px 30px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.page-header h2 {
  margin: 0 0 5px;
  font-size: 22px;
}
.page-header p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.security-alert {
  margin-bottom: 14px;
}
.dsh-card {
  margin-bottom: 14px;
}
.dsh-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsh-meta {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 12px;
}
.cap-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.cap-card {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}
.cap-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 13px;
}
.cap-desc {
  margin-top: 5px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.55;
}
.cap-meta {
  margin-top: 5px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  font-family: Consolas, monospace;
}
.bundle-row,
.market-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.bundle-label {
  font-weight: 600;
}
.market-row {
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.stat {
  padding: 13px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
}
.stat b {
  display: block;
  font-size: 24px;
  color: var(--el-color-primary);
}
.stat span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.stat.bad b {
  color: var(--el-color-danger);
}
.source-card,
.records-card,
.builtin-card {
  margin-bottom: 14px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.source-add {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.source-add .el-input {
  flex: 1;
  min-width: 320px;
}
.root-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.error-text {
  color: var(--el-color-danger);
  font-size: 12px;
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.warn-text {
  color: var(--el-color-warning);
  font-size: 12px;
}
.ok-text {
  color: var(--el-text-color-placeholder);
}
.plugin-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.plugin-source {
  margin-left: 6px;
  opacity: 0.7;
  font-size: 11px;
}
</style>
