<script setup lang="ts">
import { computed, nextTick, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TabPaneName, TreeInstance } from 'element-plus'
import {
  ChatDotRound,
  Clock,
  Collection,
  Document,
  DocumentChecked,
  Download,
  FolderOpened,
  Grid,
  Moon,
  Plus,
  Promotion,
  Refresh,
  Search,
  Sunny,
  SwitchButton,
} from '@element-plus/icons-vue'
import { api } from '@/api'
import type { ProjectHistoryItem } from '@/api/types'
import { logout } from '@/auth'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

async function onLogout() {
  await logout()
  void router.replace('/login')
}

/* ===== 顶部导航 ===== */
const navItems = [
  { path: '/harness', label: '对话', icon: ChatDotRound },
  { path: '/project', label: '数据采集', icon: Grid },
  { path: '/report', label: '报告生成', icon: Document },
  { path: '/library', label: '资料与工具', icon: Collection },
  { path: '/plugins', label: '插件', icon: Collection },
]

const LIBRARY_PATHS = [
  '/library', '/wiki', '/templates', '/records', '/equipment', '/personnel',
  '/internal', '/workflow', '/report-edit', '/scan', '/review', '/normqa', '/settings',
]

const activeNav = computed(() => {
  if (LIBRARY_PATHS.includes(route.path)) return '/library'
  return route.path
})

/* ===== 左侧检测项目树（按结构类型分组，叶子节点 id = 后端 sheet_key：
   无构件为“项目名”，有构件为“项目名（构件名）”） ===== */
interface TreeNode {
  id: string
  label: string
  children?: TreeNode[]
}

/** 由检测项目名与构件名构造 sheet_key（与后端 _make_sheet_key 一致） */
function sheetKeyOf(item: string, comp?: string): string {
  return comp ? `${item}（${comp}）` : item
}

/** sheet_key 的基础项目名（去掉构件后缀） */
function baseItemOf(key: string): string {
  const i = key.indexOf('（')
  return i > 0 ? key.slice(0, i) : key
}

const treeRef = ref<TreeInstance>()
const asideVisible = ref(false)

const STRUCTURE_ORDER: Record<string, number> = {
  混凝土结构: 0,
  砖混结构: 1,
  钢结构: 2,
  木结构: 3,
}

const treeData = computed<TreeNode[]>(() => {
  const groups = new Map<string, TreeNode[]>()
  const plugins = [...store.plugins].sort(
    (a, b) => (STRUCTURE_ORDER[a.structure_type] ?? 9)
      - (STRUCTURE_ORDER[b.structure_type] ?? 9)
      || (a.tree_order ?? 0) - (b.tree_order ?? 0)
      || a.name.localeCompare(b.name, 'zh'),
  )
  for (const p of plugins) {
    const type = p.structure_type || '其他'
    const list = groups.get(type) ?? []
    const entries = Object.entries(p.tree ?? {})
    if (!entries.length) {
      groups.set(type, list)
      continue
    }
    const children: TreeNode[] = entries.map(([item, comps]) => {
      if (comps?.length) {
        return {
          id: sheetKeyOf(item),
          label: item,
          children: comps.map((c) => ({ id: sheetKeyOf(item, c), label: c })),
        }
      }
      return { id: sheetKeyOf(item), label: item }
    })
    // 单项且与类别同名（如化学植筋）时不再重复一层，直接作为叶子
    if (entries.length === 1 && entries[0][0] === p.name && !(entries[0][1]?.length)) {
      list.push(children[0])
    } else {
      list.push({ id: `cat:${p.id}`, label: p.name, children })
    }
    groups.set(type, list)
  }
  return [...groups.entries()].map(([type, children]) => ({ id: `group:${type}`, label: type, children }))
})

/* ===== 树搜索：输入即按 label 模糊过滤 ===== */
const treeFilter = ref('')

function filterNode(value: string, data: { label?: unknown }): boolean {
  const q = String(value ?? '').trim().toLowerCase()
  if (!q) return true
  return String(data?.label ?? '').toLowerCase().includes(q)
}

/* 默认展开：混凝土结构 + 其下各检测类别；检测项目/构件按需展开 */
const DEFAULT_EXPANDED_STRUCTURES = ['混凝土结构']
const GROUP_KEY_PREFIX = 'group:'
const CATEGORY_KEY_PREFIX = 'cat:'

const defaultExpandedKeys = computed(() => {
  const keys: string[] = []
  for (const g of treeData.value) {
    if (!DEFAULT_EXPANDED_STRUCTURES.includes(g.label)) continue
    keys.push(g.id)
    for (const category of g.children ?? []) {
      keys.push(category.id)
      for (const item of category.children ?? []) {
        if (item.children?.length) keys.push(item.id)
      }
    }
  }
  return keys
})

/** default-expanded-keys 对异步加载的树数据可能不生效，直接设置内部 store 的展开状态 */
type TreeStoreLike = { nodesMap: Record<string, { expanded?: boolean }> }

function applyExpansion(keys: string[]) {
  const tree = treeRef.value as unknown as { store?: TreeStoreLike } | undefined
  const nodesMap = tree?.store?.nodesMap
  if (!nodesMap) return
  for (const key of Object.keys(nodesMap)) {
    if (key.startsWith(GROUP_KEY_PREFIX) || key.startsWith(CATEGORY_KEY_PREFIX)
      || keys.includes(key)) {
      nodesMap[key].expanded = keys.includes(key)
    }
  }
}

watch(
  treeData,
  async () => {
    await nextTick()
    applyExpansion(defaultExpandedKeys.value)
  },
  { immediate: true },
)

watch(treeFilter, (val) => {
  treeRef.value?.filter(val)
  // 清空搜索后恢复默认展开状态
  if (!val) applyExpansion(defaultExpandedKeys.value)
})

/** 叶子节点对应插件的列数（hover 提示用） */
function columnCountOf(key: string): number {
  const direct = store.pluginMap.get(key)
  if (direct?.columns?.length) return direct.columns.length
  const base = baseItemOf(key)
  const owner = store.plugins.find((p) => !!p.tree && base in p.tree)
  return owner?.columns?.length ?? 0
}

/** 是否需要设置检测参数（插件 setup_items 声明，如钻芯法检测） */
function isSetupItem(key: string): boolean {
  const base = baseItemOf(key)
  return store.plugins.some((p) => p.setup_items?.some((s) => s === base))
}

// 项目重载后同步树勾选状态（同步期间忽略 check 事件，避免误删数据）
let syncingChecks = false

watch(
  () => store.checkedItems,
  async (keys) => {
    syncingChecks = true
    treeRef.value?.setCheckedKeys(keys)
    await nextTick()
    syncingChecks = false
  },
)

function hasSheetData(key: string): boolean {
  const sheet = store.sheets[key]
  return (sheet?.rows ?? []).some((row) => {
    if (Array.isArray(row)) {
      return row.some((v) => String(v ?? '').trim() !== '')
    }
    return Object.values(row as Record<string, unknown>)
      .some((v) => String(v ?? '').trim() !== '')
  })
}

async function onTreeCheck() {
  const tree = treeRef.value
  if (!tree || syncingChecks) return
  const checkedKeys = tree.getCheckedKeys(true).map(String)
  const current = store.checkedItems
  const removed = current.filter((k) => !checkedKeys.includes(k))
  const added = checkedKeys.filter((k) => !current.includes(k))
  if (removed.length) {
    const withData = removed.filter(hasSheetData)
    if (withData.length) {
      try {
        await ElMessageBox.confirm(
          `取消勾选将删除以下检测项已录入的数据：${withData.slice(0, 5).join('、')}` +
            `${withData.length > 5 ? ' 等' : ''}。确定继续吗？`,
          '确认删除数据',
          {
            type: 'warning',
            confirmButtonText: '删除并取消勾选',
            cancelButtonText: '保留数据',
          },
        )
      } catch {
        syncingChecks = true
        for (const key of removed) tree.setChecked(key, true, false)
        await nextTick()
        syncingChecks = false
        return
      }
    }
  }
  for (const key of removed) {
    try {
      await store.checkItem(key, false)
    } catch {
      tree.setChecked(key, true, false) // 提交失败还原勾选状态
    }
  }
  for (const key of added) {
    if (isSetupItem(key)) {
      pendingQueue.value.push(key)
    } else {
      try {
        await store.checkItem(key, true)
      } catch {
        tree.setChecked(key, false, false) // 提交失败还原勾选状态
      }
    }
  }
  if (pendingQueue.value.length && !setupVisible.value) openSetup()
}

/* ===== requires_setup 检测参数对话框（键名与后端 sheet_logic.build_* 严格一致） ===== */
interface SetupField {
  key: string
  label: string
  type?: 'number'
  min?: number
  default?: string | number
}

/* 钻芯法检测参数（后端 sheet_logic.build_core_drilling）
 * 默认值与桌面端 CoreDrillingInputDialog 保持一致：
 * 1# 楼、13 个构件、每构件 2 个芯样、编号从 1 开始、C40、芯样直径 75mm。 */
const DRILL_FIELDS: SetupField[] = [
  { key: 'building', label: '楼栋', default: '1#' },
  { key: 'components', label: '构件数', type: 'number', min: 1, default: 13 },
  { key: 'samples_per_component', label: '每构件芯样数', type: 'number', min: 1, default: 2 },
  { key: 'sample_start', label: '起始编号', type: 'number', min: 1, default: 1 },
  { key: 'grade', label: '设计等级', default: 'C40' },
  { key: 'diameter', label: '直径(mm)', type: 'number', min: 1, default: 75 },
]

/* 回弹钻芯修正法检测参数（后端 sheet_logic.build_rebound_core_drilling）
 * 默认值与桌面端 ReboundCoreDrillingInputDialog 保持一致：
 * 1# 楼、1 批、每批 5 个构件、每构件 3 个测区、C40、芯样直径 100mm。 */
const RCD_FIELDS: SetupField[] = [
  { key: 'building', label: '楼栋', default: '1#' },
  { key: 'batches', label: '批数', type: 'number', min: 1, default: 1 },
  { key: 'components_per_batch', label: '每批构件数', type: 'number', min: 1, default: 5 },
  { key: 'zones_per_component', label: '每构件测区数', type: 'number', min: 1, default: 3 },
  { key: 'grade', label: '设计等级', default: 'C40' },
  { key: 'diameter', label: '直径(mm)', type: 'number', min: 1, default: 100 },
]

/* 砖回弹法参数：1 个批次、10 个构件、每构件 10 个测区（每测区 5 个回弹值） */
const BRICK_FIELDS: SetupField[] = [
  { key: 'batch', label: '批次', default: '1' },
  { key: 'components', label: '构件数', type: 'number', min: 1, default: 10 },
  { key: 'zones_per_component', label: '每构件测区数', type: 'number', min: 1, default: 10 },
]

function setupFieldsFor(key: string): SetupField[] {
  const base = baseItemOf(key)
  if (base.startsWith('砖强度检测')) return BRICK_FIELDS
  return base.startsWith('回弹钻芯修正法') ? RCD_FIELDS : DRILL_FIELDS
}

const pendingQueue = ref<string[]>([])
const setupVisible = ref(false)
const pendingKey = ref('')
let confirmed = false
const setupText = reactive<Record<string, string>>({})
const setupNums = reactive<Record<string, number | undefined>>({})

const currentSetupFields = computed(() => setupFieldsFor(pendingKey.value || ''))
const setupTitle = computed(() => baseItemOf(pendingKey.value || ''))
const setupHint = computed(() => baseItemOf(pendingKey.value || '').startsWith('砖强度检测')
  ? '已按常用默认值预填；请根据实际工程修改批次、构件数量和每构件测区数，确认后将按参数生成表格结构。'
  : '已按常用默认值预填；请根据实际工程修改构件数量、设计等级和芯样直径，确认后将按参数生成表格结构。')

function resetSetupForm() {
  for (const f of currentSetupFields.value) {
    if (f.type === 'number') {
      setupNums[f.key] = typeof f.default === 'number' ? f.default : undefined
    } else {
      setupText[f.key] = f.default === undefined ? '' : String(f.default)
    }
  }
}

function openSetup() {
  const next = pendingQueue.value.shift()
  if (!next) return
  pendingKey.value = next
  resetSetupForm()
  setupVisible.value = true
}

function onSetupClose() {
  if (!confirmed) treeRef.value?.setChecked(pendingKey.value, false, false)
  confirmed = false
  if (pendingQueue.value.length) openSetup()
  else pendingKey.value = ''
}

async function confirmSetup() {
  confirmed = true
  setupVisible.value = false
  const key = pendingKey.value
  const fields = currentSetupFields.value
  const params: Record<string, unknown> = {}
  for (const f of fields) {
    const value = f.type === 'number' ? setupNums[f.key] : setupText[f.key]
    if (value !== undefined && value !== '') params[f.key] = value
  }
  try {
    await store.checkItem(key, true, params)
  } catch {
    treeRef.value?.setChecked(key, false, false) // 提交失败还原勾选状态
  }
}

function cancelSetup() {
  setupVisible.value = false
}

/* ===== 工作表未保存标记（SheetView 注入上报，关闭标签前确认用） ===== */
const sheetDirtyMap = reactive<Record<string, boolean>>({})
provide('sheetDirtyMap', sheetDirtyMap)

/* ===== 工作表标签页 ===== */
function tabLabel(key: string): string {
  return store.pluginMap.get(key)?.name ?? key
}

async function onTabRemove(name: TabPaneName) {
  if (typeof name !== 'string') return
  if (sheetDirtyMap[name]) {
    try {
      await ElMessageBox.confirm(`「${tabLabel(name)}」有未保存的修改，确定关闭该检测项目吗？`, '关闭确认', {
        confirmButtonText: '关闭',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return // 用户取消关闭
    }
  }
  try {
    await store.checkItem(name, false)
    delete sheetDirtyMap[name]
  } catch {
    /* 关闭失败时保留未保存标记，等待重试 */
  }
}

/* ===== 顶栏操作 ===== */
/** 切换项目前的危险操作确认：已有勾选项目或表格数据时提示 */
async function confirmSwitchProject(): Promise<boolean> {
  if (!store.checkedItems.length && !Object.keys(store.sheets).length) return true
  try {
    await ElMessageBox.confirm('当前工程数据将被切换，是否继续？', '提示', {
      confirmButtonText: '继续',
      cancelButtonText: '取消',
      type: 'warning',
    })
    return true
  } catch {
    return false
  }
}

async function onNewProject() {
  try {
    await ElMessageBox.confirm(
      '新建工程会清空当前工程（原工程先自动备份，可在“历史工程”里重新打开）。是否继续？',
      '新建工程',
      {
        confirmButtonText: '新建工程',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  try {
    await flushAllSheets()
    const stamp = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const name = `新建工程 ${pad(stamp.getMonth() + 1)}-${pad(stamp.getDate())} ${pad(stamp.getHours())}:${pad(stamp.getMinutes())}`
    await api.newProject(name)
    await store.loadProject()
    await router.push('/project')
    ElMessage.success('已新建工程，原工程已自动备份到历史工程')
  } catch {
    /* api 层已提示 */
  }
}

const historyVisible = ref(false)
const historyLoading = ref(false)
const historyItems = ref<ProjectHistoryItem[]>([])
const historyQuery = ref('')

const filteredHistory = computed(() => {
  const q = historyQuery.value.trim().toLowerCase()
  if (!q) return historyItems.value
  return historyItems.value.filter((item) =>
    item.name.toLowerCase().includes(q)
    || item.source.toLowerCase().includes(q)
    || item.filepath.toLowerCase().includes(q))
})

async function loadProjectHistory() {
  historyLoading.value = true
  try {
    const data = await api.getProjectHistory()
    historyItems.value = data.items ?? []
  } catch {
    /* api 层已提示 */
  } finally {
    historyLoading.value = false
  }
}

function openProjectHistory() {
  historyVisible.value = true
  historyQuery.value = ''
  void loadProjectHistory()
}

async function openHistoryProject(item: unknown) {
  const project = item as ProjectHistoryItem
  if (!(await confirmSwitchProject())) return
  try {
    await flushAllSheets()
    await store.openProject(project.filepath)
    historyVisible.value = false
    store.setStatus(`已打开历史工程：${project.name}`)
  } catch {
    /* api 层已提示 */
  }
}

async function revealHistoryProject(item: unknown) {
  const project = item as ProjectHistoryItem
  try {
    await api.revealFile(project.filepath)
  } catch {
    /* api 层已提示 */
  }
}

async function openProjectByPath() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程文件完整路径', '按路径打开工程', {
      confirmButtonText: '打开',
      cancelButtonText: '取消',
      inputPlaceholder: '例如 D:\\data\\project.json',
    })
    if (!value || !value.trim()) return
    if (!(await confirmSwitchProject())) return
    await flushAllSheets()
    await store.openProject(value.trim())
    historyVisible.value = false
  } catch {
    /* 用户取消 */
  }
}

async function onOpenProject() {
  openProjectHistory()
}

async function onSaveProject() {
  await store.saveProject()
}

async function flushAllSheets() {
  const waits: Promise<void>[] = []
  window.dispatchEvent(new CustomEvent('dsh-flush-sheets', {
    detail: { wait: (p: Promise<void>) => waits.push(p) },
  }))
  await Promise.allSettled(waits)
}

async function onExportExcel() {
  if (!store.checkedItems.length) {
    ElMessage.warning('请先勾选要导出的检测项目')
    return
  }
  await flushAllSheets()
  const name = await api.exportProject(
    `${store.projectName || '检测项目'}_检测数据.xlsx`,
  )
  store.setStatus(`已导出 Excel：${name}（${store.checkedItems.length} 个已勾选项目）`)
}

async function onProjectNameChange() {
  const name = String(store.projectName || '').trim()
  if (!name) {
    ElMessage.warning('工程名称不能为空')
    await store.loadProject()
    return
  }
  try {
    await api.renameProject(name)
    await store.loadProject()
    store.setStatus('工程名称已保存，并同步到报告信息')
  } catch {
    await store.loadProject()
  }
}

/* ===== 采集进度 ===== */
const progressPercent = computed(() => {
  const total = store.checkedItems.length
  return total ? Math.round((store.filledItemCount / total) * 100) : 0
})

/* ===== 初始化 ===== */
watch(
  () => [store.initialized, store.checkedItems.length] as const,
  ([ready, count]) => {
    // 空工程默认展开检测项目树；已有数据的工程默认只显示表格
    if (ready && count === 0) asideVisible.value = true
  },
  { immediate: true },
)

onMounted(() => {
  if (!store.initialized) void store.init()
})
</script>

<template>
  <div class="main-layout">
    <!-- 顶栏 -->
    <header class="layout-header">
      <div class="brand">
        <div class="brand-mark">
          <img class="brand-logo" src="/brand/logo.svg" alt="工程检测harness" />
        </div>
        <div class="brand-text">
          <span class="brand-name">工程检测harness</span>
          <span class="brand-sub">数据管理平台</span>
        </div>
      </div>
      <el-menu mode="horizontal" router :default-active="activeNav" class="nav-menu">
        <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
      <div class="header-actions">
        <el-tooltip :content="asideVisible ? '隐藏检测项目' : '显示检测项目'" placement="bottom">
          <el-button
            :icon="Grid"
            :type="asideVisible ? 'primary' : 'default'"
            :plain="asideVisible"
            @click="asideVisible = !asideVisible"
          />
        </el-tooltip>
        <el-input
          v-model="store.projectName"
          class="project-name-input"
          placeholder="工程名称"
          clearable
          @change="onProjectNameChange"
        />
        <el-tooltip content="新建工程（原工程自动备份）" placement="bottom">
          <el-button :icon="Plus" @click="onNewProject">新建工程</el-button>
        </el-tooltip>
        <el-tooltip content="历史工程（文件与自动备份）" placement="bottom">
          <el-button :icon="Clock" @click="openProjectHistory">历史工程</el-button>
        </el-tooltip>
        <el-tooltip content="打开工程文件" placement="bottom">
          <el-button :icon="FolderOpened" @click="onOpenProject" />
        </el-tooltip>
        <el-tooltip content="保存工程" placement="bottom">
          <el-button :icon="DocumentChecked" @click="onSaveProject" />
        </el-tooltip>
        <el-tooltip content="导出全部已勾选检测项目" placement="bottom" :disabled="!!store.checkedItems.length">
          <span class="tooltip-btn">
            <el-button :icon="Download" :disabled="!store.checkedItems.length" @click="onExportExcel">
              导出
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip content="请先勾选检测项目" placement="bottom" :disabled="!!store.checkedItems.length">
          <span class="tooltip-btn">
            <el-button
              type="primary"
              :icon="Promotion"
              :disabled="!store.checkedItems.length"
              @click="router.push('/report')"
            >
              生成报告
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip :content="store.theme === 'dark' ? '切换为浅色' : '切换为深色'" placement="bottom">
          <el-button
            circle
            size="small"
            :icon="store.theme === 'dark' ? Sunny : Moon"
            @click="store.toggleTheme()"
          />
        </el-tooltip>
        <el-tooltip content="退出登录" placement="bottom">
          <el-button circle size="small" :icon="SwitchButton" @click="onLogout" />
        </el-tooltip>
      </div>
    </header>

    <div class="layout-body">
      <!-- 左侧检测项目树：默认收起，点击顶部“检测项目”按钮显示 -->
      <aside v-show="asideVisible" class="layout-aside">
        <div class="aside-header">
          <span>检测项目</span>
          <el-button link size="small" @click="asideVisible = false">收起</el-button>
        </div>
        <div class="aside-search">
          <el-input
            v-model="treeFilter"
            placeholder="搜索检测项目"
            clearable
            :prefix-icon="Search"
            size="small"
          />
        </div>
        <el-scrollbar class="aside-tree">
          <el-tree
            ref="treeRef"
            :data="treeData"
            node-key="id"
            show-checkbox
            check-on-click-node
            :default-expanded-keys="defaultExpandedKeys"
            :props="{ label: 'label', children: 'children' }"
            :filter-node-method="filterNode"
            :default-checked-keys="store.checkedItems"
            @check="onTreeCheck"
          >
            <template #default="{ data }">
              <el-tooltip
                v-if="!data.children"
                :content="`共 ${columnCountOf(data.id)} 列`"
                :disabled="!columnCountOf(data.id)"
                placement="right"
                :show-after="300"
              >
                <span class="tree-leaf-label">{{ data.label }}</span>
              </el-tooltip>
              <span v-else>{{ data.label }}</span>
            </template>
          </el-tree>
        </el-scrollbar>
        <div class="aside-footer">
          <div class="aside-progress-text">
            已勾选 {{ store.checkedItems.length }} 项 · 已录入 {{ store.filledItemCount }} 项 /
            {{ store.totalRowCount }} 行
          </div>
          <el-progress :percentage="progressPercent" :show-text="false" />
          <el-button size="small" type="primary" class="aside-report-btn" @click="router.push('/report')">
            生成报告
          </el-button>
        </div>
      </aside>

      <!-- 主区工作表 -->
      <main class="layout-main">
        <el-tabs
          v-if="store.checkedItems.length"
          v-model="store.activeTab"
          type="card"
          class="main-tabs"
          closable
          @tab-remove="onTabRemove"
        >
          <el-tab-pane v-for="key in store.checkedItems" :key="key" :name="key" :label="tabLabel(key)" lazy>
            <slot name="sheet" :sheet-key="key" />
          </el-tab-pane>
        </el-tabs>
        <el-empty v-else class="main-empty" description="点击顶部「检测项目」按钮，勾选检测项目开始录入" />
      </main>
    </div>

    <!-- 底部状态栏 -->
    <footer class="layout-statusbar">
      <span class="status-text">{{ store.statusMessage }}</span>
      <span v-if="store.autosavedAt" class="status-right">自动保存 {{ store.autosavedAt }}</span>
    </footer>

    <!-- 历史工程文件 -->
    <el-dialog v-model="historyVisible" title="历史工程文件" width="980px" top="5vh" destroy-on-close>
      <div class="history-toolbar">
        <el-input v-model="historyQuery" :prefix-icon="Search" clearable placeholder="搜索工程名称、来源或路径" style="width: 320px" />
        <el-button :icon="Refresh" :loading="historyLoading" @click="loadProjectHistory">刷新</el-button>
        <el-button :icon="FolderOpened" @click="openProjectByPath">按路径打开</el-button>
      </div>
      <el-table
        v-loading="historyLoading"
        :data="filteredHistory"
        size="small"
        border
        max-height="450"
        empty-text="暂无历史工程"
        @row-dblclick="openHistoryProject"
      >
        <el-table-column label="工程名称" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="history-name">{{ row.name }}</div>
            <div class="history-path">{{ row.filepath }}</div>
          </template>
        </el-table-column>
        <el-table-column label="数据" width="120">
          <template #default="{ row }">{{ row.checked_count }} 项 / {{ row.sheet_count }} 表</template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.source }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="modified" label="修改时间" width="150" />
        <el-table-column label="大小" width="85">
          <template #default="{ row }">{{ row.size_kb }} KB</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="openHistoryProject(row)">打开</el-button>
            <el-button link size="small" @click="revealHistoryProject(row)">定位</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="history-tip">
        这里展示的是历史工程文件/备份；按会话一一对应请使用“历史工程（会话）”。
      </div>
    </el-dialog>

    <!-- 检测参数设置对话框 -->
    <el-dialog
      v-model="setupVisible"
      :title="`设置检测参数 · ${setupTitle}`"
      width="440px"
      :close-on-click-modal="false"
      @close="onSetupClose"
    >
      <el-form label-width="110px">
        <el-form-item v-for="f in currentSetupFields" :key="f.key" :label="f.label">
          <el-input-number
            v-if="f.type === 'number'"
            v-model="setupNums[f.key]"
            :min="f.min ?? 0"
            controls-position="right"
            class="w-full"
          />
          <el-input v-else v-model="setupText[f.key]" :placeholder="`请输入${f.label}`" />
        </el-form-item>
      </el-form>
      <div class="setup-tip">
        {{ setupHint }}
      </div>
      <template #footer>
        <el-button text @click="resetSetupForm">恢复默认</el-button>
        <el-button @click="cancelSetup">取消</el-button>
        <el-button type="primary" @click="confirmSetup">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.main-layout {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 顶栏 */
.layout-header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 14px;
  height: 64px;
  padding: 0 18px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 1px 0 rgba(20, 49, 66, 0.03);
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  white-space: nowrap;
  flex: none;
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 19px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(31, 95, 118, 0.22);
}

.brand-logo {
  display: block;
  width: 36px;
  height: 36px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.brand-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  letter-spacing: 0.2px;
}

.brand-sub {
  font-size: 10px;
  color: var(--el-text-color-secondary);
  letter-spacing: 0.8px;
}

.nav-menu {
  flex: 1 1 auto;
  min-width: 0;
  border-bottom: none;
  height: 100%;
  overflow-x: auto;
  white-space: nowrap;
  background: transparent;
}

.nav-menu :deep(.el-menu-item) {
  height: 38px;
  line-height: 38px;
  margin: auto 1px;
  padding: 0 11px;
  border-radius: 8px;
  color: var(--el-text-color-regular);
  font-weight: 500;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.nav-menu :deep(.el-menu-item .el-icon) {
  margin-right: 5px;
  font-size: 15px;
}

.nav-menu :deep(.el-menu-item:hover) {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.nav-menu :deep(.el-menu-item.is-active) {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.nav-menu :deep(.el-sub-menu__title) {
  height: 38px;
  line-height: 38px;
  margin: auto 1px;
  border-radius: 8px;
}

.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.tooltip-btn {
  display: inline-flex;
}

.project-name-input {
  width: clamp(160px, 16vw, 220px);
}

.setup-tip {
  margin-top: 4px;
  padding: 9px 11px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.history-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.history-intro {
  flex: 1;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.history-name {
  font-size: 12.5px;
  font-weight: 600;
}

.history-path {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-tip {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
  line-height: 1.6;
}

/* 主体区域 */
.layout-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.layout-aside {
  flex: none;
  width: 264px;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
}

.aside-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 6px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  letter-spacing: 0.4px;
}

.aside-search {
  flex: none;
  padding: 0 10px 8px;
}

.aside-tree {
  flex: 1;
  min-height: 0;
}

.aside-footer {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 8px 10px 10px;
  padding: 10px 11px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
}

.aside-progress-text {
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.aside-report-btn {
  width: 100%;
  margin-top: 2px;
}

.tree-leaf-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.layout-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 14px;
  gap: 2px;
}

.main-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.main-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
}

.main-tabs :deep(.el-tabs__item) {
  font-size: 12.5px;
}

.main-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: var(--shadow-sm);
  padding: 10px 12px;
  overflow: hidden;
}

.main-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.main-empty {
  margin: auto;
  border-radius: 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  padding: 40px;
}

/* 底部状态栏 */
.layout-statusbar {
  flex: none;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-top: 1px solid var(--el-border-color-lighter);
}

.status-right {
  white-space: nowrap;
}

.w-full {
  width: 100%;
}
</style>
