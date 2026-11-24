<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Connection, Refresh, RefreshLeft, Switch as SwitchIcon } from '@element-plus/icons-vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()
const isDark = computed(() => store.theme === 'dark')

const loading = ref(false)
const saving = ref(false)
const showAdvanced = ref(false)
const config = ref<Record<string, Record<string, unknown>>>({})

/* ===== 可编辑项 ===== */
const ollamaBaseUrl = ref('')   // llm.ollama_base_url
const agentEnabled = ref(false) // report_agent.enabled

const harnessForm = ref({
  enabled: true,
  provider: 'auto',
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.2,
  max_rounds: 12,
  auto_navigate: false,
  wiki_top_k: 3,
})
const harnessKeyConfigured = ref(false)

interface SettingsSnapshot {
  url: string
  agent: boolean
  harness: Record<string, unknown>
}

/** 本次进入页面时加载的初始值（「恢复默认」的目标） */
const initialSnapshot = ref<SettingsSnapshot>({ url: '', agent: false, harness: {} })
/** 最近一次从后端加载/保存的值（脏标记基准） */
const savedSnapshot = ref<SettingsSnapshot>({ url: '', agent: false, harness: {} })

function harnessState(): Record<string, unknown> {
  return {
    enabled: harnessForm.value.enabled,
    provider: harnessForm.value.provider,
    base_url: harnessForm.value.base_url,
    model: harnessForm.value.model,
    temperature: harnessForm.value.temperature,
    max_rounds: harnessForm.value.max_rounds,
    auto_navigate: harnessForm.value.auto_navigate,
    wiki_top_k: harnessForm.value.wiki_top_k,
  }
}

function snapshot(): SettingsSnapshot {
  return {
    url: ollamaBaseUrl.value,
    agent: agentEnabled.value,
    harness: harnessState(),
  }
}

const dirty = computed(
  () => !loading.value
    && JSON.stringify(snapshot()) !== JSON.stringify(savedSnapshot.value),
)

function snapshotSaved() {
  savedSnapshot.value = snapshot()
}

/** 把后端 harness 配置写入表单（api_key 脱敏为 *** 时留空保持） */
function applyHarnessConfig(raw: Record<string, unknown>) {
  harnessForm.value.enabled = raw['enabled'] !== false
  harnessForm.value.provider = String(raw['provider'] ?? 'auto')
  harnessForm.value.base_url = String(raw['base_url'] ?? '')
  harnessForm.value.model = String(raw['model'] ?? '')
  harnessForm.value.temperature = Number(raw['temperature'] ?? 0.2)
  harnessForm.value.max_rounds = Number(raw['max_rounds'] ?? 12)
  harnessForm.value.auto_navigate = raw['auto_navigate'] === true
  harnessForm.value.wiki_top_k = Number(raw['wiki_top_k'] ?? 3)
  harnessKeyConfigured.value = raw['api_key'] === '***'
  harnessForm.value.api_key = harnessKeyConfigured.value ? '' : String(raw['api_key'] ?? '')
}

async function loadConfig() {
  loading.value = true
  try {
    const data = await api.getConfig()
    config.value = data ?? {}
    const llm = config.value['llm'] ?? {}
    const agent = config.value['report_agent'] ?? {}
    const harness = config.value['harness'] ?? {}
    ollamaBaseUrl.value = typeof llm['ollama_base_url'] === 'string' ? llm['ollama_base_url'] : ''
    agentEnabled.value = agent['enabled'] === true
    applyHarnessConfig(harness)
    const snap = snapshot()
    savedSnapshot.value = snap
    initialSnapshot.value = { ...snap, harness: { ...snap.harness } }
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

/** 保存：分别写入 llm / report_agent / harness 配置节（PUT /api/config） */
async function onSave() {
  saving.value = true
  try {
    await api.putConfig('llm', { ollama_base_url: ollamaBaseUrl.value.trim() })
    await api.putConfig('report_agent', { enabled: agentEnabled.value })
    const harnessValues: Record<string, unknown> = {
      enabled: harnessForm.value.enabled,
      provider: harnessForm.value.provider,
      base_url: harnessForm.value.base_url.trim(),
      model: harnessForm.value.model.trim(),
      temperature: Number(harnessForm.value.temperature),
      max_rounds: Number(harnessForm.value.max_rounds),
      auto_navigate: harnessForm.value.auto_navigate,
      wiki_top_k: Number(harnessForm.value.wiki_top_k),
    }
    // 留空表示保持已保存的 Key（后端也不会把空值当成清除）
    if (harnessForm.value.api_key.trim()) harnessValues['api_key'] = harnessForm.value.api_key.trim()
    await api.putConfig('harness', harnessValues)
    ElMessage.success('配置已保存')
    store.setStatus('系统配置已保存')
    snapshotSaved()
    await loadConfig()
  } catch {
    /* api 层已提示 */
  } finally {
    saving.value = false
  }
}

/** 恢复默认：把可编辑表单重置为本次进入页面时加载的值（需确认） */
async function onReset() {
  try {
    await ElMessageBox.confirm(
      '将把可编辑配置恢复为进入本页时加载的值，未保存的修改会丢失。是否继续？',
      '恢复默认',
      { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const initial = initialSnapshot.value
  ollamaBaseUrl.value = initial.url
  agentEnabled.value = initial.agent
  Object.assign(harnessForm.value, initial.harness)
  ElMessage.info('已恢复为页面加载时的值（尚未保存）')
}

/* ===== Ollama 地址软校验（非阻断）与后端连接测试 ===== */
const urlWarning = computed(() => {
  const u = ollamaBaseUrl.value.trim()
  if (!u) return ''
  if (!/^https?:\/\//i.test(u)) return 'Ollama 地址需以 http://（或 https://）开头，否则可能无法连接'
  return ''
})

const testing = ref(false)
const testState = ref<'idle' | 'ok' | 'fail'>('idle')

async function onTestConnection() {
  testing.value = true
  testState.value = 'idle'
  try {
    await api.getConfig()
    testState.value = 'ok'
  } catch {
    testState.value = 'fail'
  } finally {
    testing.value = false
  }
}

/* ===== Harness 模型测试 ===== */


/* ===== 其余配置节只读展示（llm / report_agent / harness 已单独编辑） ===== */
const SECTION_LABELS: Record<string, string> = {
  ocr: 'OCR 识别（ocr）',
  storage: '识别存储（storage）',
  normalizer: '数据规范化（normalizer）',
  agent: 'AI 自修复（agent）',
  memory: '识别记忆（memory）',
  matcher: '字段匹配（matcher）',
  server: '上传服务器（server）',
}
const EDITABLE_SECTIONS = new Set(['llm', 'report_agent', 'harness'])

/** 只读展示顺序：已知配置节在前，其余按字母序 */
const readonlySections = computed(() => {
  const order = Object.keys(SECTION_LABELS)
  const keys = Object.keys(config.value)
    .filter((k) => !EDITABLE_SECTIONS.has(k))
    .sort((a, b) => {
      const ia = order.indexOf(a)
      const ib = order.indexOf(b)
      if (ia >= 0 && ib >= 0) return ia - ib
      if (ia >= 0) return -1
      if (ib >= 0) return 1
      return a.localeCompare(b)
    })
  return keys.map((key) => ({
    key,
    label: SECTION_LABELS[key] ?? key,
    entries: Object.entries(config.value[key] ?? {}).map(([k, v]) => ({ key: k, text: fmtValue(v) })),
  }))
})

function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '（空）'
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function onToggleTheme() {
  store.toggleTheme()
}

onMounted(() => {
  void loadConfig()
})
</script>

<template>
  <div class="settings-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/internal')">返回工具</el-button>
        <h2>系统设置</h2>
      </div>
      <div class="page-actions">
        <el-tag v-if="dirty" type="warning" size="small">有未保存修改</el-tag>
        <el-button :icon="Refresh" :loading="loading" @click="loadConfig">重新加载</el-button>
        <el-button :icon="RefreshLeft" :disabled="saving || loading" @click="onReset">恢复默认</el-button>
        <el-button type="primary" :icon="SwitchIcon" :loading="saving" @click="onSave">
          保存配置{{ dirty ? ' *' : '' }}
        </el-button>
      </div>
    </header>

    <!-- AI 服务 -->
    <el-card shadow="never" v-loading="loading">
      <template #header>AI 服务</template>
      <el-form label-width="140px" class="edit-form">
        <el-form-item label="Ollama 地址">
          <el-input
            v-model="ollamaBaseUrl"
            clearable
            placeholder="如 http://172.16.42.7:11434（留空沿用 llm.base_url 推导）"
          >
            <template #append>
              <el-button :icon="Connection" :loading="testing" @click="onTestConnection">
                连接测试
              </el-button>
            </template>
          </el-input>
          <div v-if="urlWarning" class="field-warning">{{ urlWarning }}</div>
          <div class="field-tip">规范问答 AI 解释、批量审查、视觉识别均通过该 Ollama 服务调用</div>
          <el-alert
            v-if="testState === 'fail'"
            type="error"
            show-icon
            :closable="false"
            title="无法连接后端服务（localhost:8765），请确认后端已启动后重试"
            class="test-result"
          />
          <el-alert
            v-else-if="testState === 'ok'"
            type="success"
            show-icon
            :closable="false"
            title="后端服务连接正常"
            class="test-result"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Harness 助手 -->
    <el-card shadow="never" v-loading="loading">
      <template #header>Harness 助手</template>
      <el-form label-width="140px" class="edit-form">
        <el-form-item label="启用 Harness">
          <el-switch v-model="harnessForm.enabled" active-text="启用" inactive-text="停用" />
          <div class="field-tip">停用后 Harness 只保留规则模式（启动预演/意图/知识库检索仍可用）</div>
        </el-form-item>
        <el-form-item label="模型来源">
          <el-select v-model="harnessForm.provider" style="width: 280px">
            <el-option label="自动（本地 vLLM → Ollama，推荐）" value="auto" />
            <el-option label="本地 vLLM（llm 配置）" value="vllm" />
            <el-option label="本地 Ollama" value="ollama" />
            <el-option label="DeepSeek API（需 Key）" value="deepseek" />
            <el-option label="仅规则模式（不调用大模型）" value="off" />
          </el-select>
          <div class="field-tip">
            自动模式只探测本地服务，检测数据不会默认上传云端；选择 DeepSeek 才使用云端接口。
          </div>
        </el-form-item>
        <el-form-item label="服务地址">
          <el-input
            v-model="harnessForm.base_url"
            clearable
            placeholder="留空使用所选来源的默认地址（如 https://api.deepseek.com/v1）"
          />
        </el-form-item>
        <el-form-item label="模型名">
          <el-input v-model="harnessForm.model" clearable placeholder="留空自动探测（如 deepseek-chat / qwen3.6:35b）" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="harnessForm.api_key"
            type="password"
            show-password
            clearable
            :placeholder="harnessKeyConfigured ? '已配置；留空保持原 Key' : '本地模型通常无需 Key'"
          />
          <div class="field-tip">密钥只保存在本机配置文件，GET 配置接口会脱敏；留空不会清除已保存的 Key。</div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="温度">
              <el-input-number v-model="harnessForm.temperature" :min="0" :max="1" :step="0.1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大工具轮数">
              <el-input-number v-model="harnessForm.max_rounds" :min="1" :max="24" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="意图后自动跳转">
              <el-switch v-model="harnessForm.auto_navigate" active-text="自动" inactive-text="手动" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Wiki 引用页数">
              <el-input-number v-model="harnessForm.wiki_top_k" :min="1" :max="10" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="对话入口">
          <span class="field-tip">
            智能体对话已统一到 DeepSeek Harness（见左侧「AI 状态」页）；
            此处配置仅作为历史遗留，不再驱动应用内对话。
          </span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 报告 Agent -->
    <el-card shadow="never" v-loading="loading">
      <template #header>报告 Agent</template>
      <el-form label-width="140px" class="edit-form">
        <el-form-item label="Agent 开关">
          <el-switch v-model="agentEnabled" active-text="启用" inactive-text="停用" />
          <div class="field-tip">开启后报告生成由本地大模型分章节编排，失败自动回退</div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 主题说明卡 -->
    <el-card shadow="never">
      <template #header>界面主题</template>
      <div class="theme-row">
        <span>当前主题：</span>
        <el-tag :type="isDark ? 'info' : 'primary'" effect="plain">
          {{ isDark ? '深色' : '浅色' }}
        </el-tag>
        <el-switch
          :model-value="isDark"
          active-text="深色"
          inactive-text="浅色"
          @change="onToggleTheme"
        />
      </div>
      <div class="field-tip">
        主题切换开关位于页面顶栏（「浅 / 深」图标开关），点击即可在浅色与深色之间切换；
        偏好自动记忆在浏览器本地（localStorage），下次打开自动应用。
      </div>
    </el-card>

    <!-- 其他配置（只读） -->
    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="settings-card-head">
          <span>其他配置（只读）</span>
          <el-button size="small" text @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '收起' : '展开' }}
          </el-button>
        </div>
      </template>
      <template v-if="showAdvanced && readonlySections.length">
        <div v-for="section in readonlySections" :key="section.key" class="ro-group">
          <div class="group-title">{{ section.label }}</div>
          <el-descriptions :column="1" border size="small" class="ro-desc">
            <el-descriptions-item v-for="e in section.entries" :key="e.key" :label="e.key">
              <span class="ro-value">{{ e.text }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </template>
      <div v-else-if="!showAdvanced" class="empty-tip">
        扫描识别/OCR/规范化等底层参数，需要时再展开查看。
      </div>
      <div v-else class="empty-tip">暂无其他配置</div>
    </el-card>
  </div>
</template>

<style scoped>
.settings-view {
  height: 100%;
  overflow: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.settings-view > :deep(.el-card) {
  flex: 0 0 auto;
}

.settings-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.settings-view :deep(.el-card__body) {
  overflow: visible;
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

.page-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.edit-form {
  max-width: 720px;
}

.field-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  margin-top: 4px;
  width: 100%;
}

.field-warning {
  font-size: 12px;
  color: var(--el-color-warning);
  line-height: 1.6;
  margin-top: 4px;
  width: 100%;
}

.test-result {
  margin-top: 8px;
  width: 100%;
}

.harness-test-result {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.theme-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ro-group + .ro-group {
  margin-top: 14px;
}

.group-title {
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin: 4px 0 10px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
  line-height: 1.2;
}

.ro-desc {
  max-width: 960px;
}

.ro-value {
  word-break: break-all;
  line-height: 1.6;
}

.empty-tip {
  color: var(--el-text-color-secondary);
}
</style>
