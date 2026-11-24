<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Back,
  DataAnalysis,
  Document,
  DocumentChecked,
  Files,
  FolderOpened,
  Monitor,
  Reading,
  Refresh,
  Setting,
  Tools,
  User,
  View,
} from '@element-plus/icons-vue'
import { api } from '@/api'
import type { LibraryStatus } from '@/api/types'

const router = useRouter()
const status = ref<LibraryStatus | null>(null)
const loading = ref(false)

async function loadStatus() {
  loading.value = true
  try {
    status.value = await api.getLibrariesStatus()
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

const cards = computed(() => {
  const s = status.value
  return [
    {
      key: 'wiki',
      title: '知识库',
      desc: '标准规范、检测方法、操作指南和计算规则',
      count: s ? `${s.wiki.pages} 页` : '—',
      meta: s ? `${s.wiki.categories} 个分类` : '',
      route: '/wiki',
      icon: Reading,
      tone: 'teal',
    },
    {
      key: 'templates',
      title: '报告模板库',
      desc: '报告模板与原始记录模板，支持上传和默认模板设置',
      count: s ? `${s.templates.report_templates} 个报告模板` : '—',
      meta: s ? `${s.templates.original_templates} 个原始记录模板` : '',
      route: '/templates',
      icon: Document,
      tone: 'blue',
    },
    {
      key: 'personnel',
      title: '人员库',
      desc: '检测人员、报告编写/复核/审核/批准人员信息复用',
      count: s ? `${s.personnel.total} 人` : '—',
      meta: s ? `${Object.keys(s.personnel.roles || {}).length} 个岗位` : '',
      route: '/personnel',
      icon: User,
      tone: 'rose',
    },
    {
      key: 'records',
      title: '记录库',
      desc: '历史报告与原始记录，含数据快照、文件定位和再次修改',
      count: s ? `${s.records.report.total} 份报告 · ${s.records.original.total} 条原始记录` : '—',
      meta: s ? `含数据快照 ${s.records.original.with_snapshot} 条` : '',
      route: '/records',
      icon: FolderOpened,
      tone: 'green',
    },
    {
      key: 'equipment',
      title: '设备库',
      desc: '检测设备同步、检定信息与报告选用设备管理',
      count: s ? `${s.equipment.total} 台` : '—',
      meta: s ? `报告选用 ${s.equipment.selected} 台` : '',
      route: '/equipment',
      icon: Monitor,
      tone: 'violet',
    },
  ]
})

const tools = [
  { title: '流程总览', desc: '采集/评定/报告进度', route: '/workflow', icon: Files },
  { title: '插件管理', desc: '内置 / 外部检测项目插件', route: '/plugins', icon: Tools },
  { title: '报告修改', desc: '段落、表格、查找替换', route: '/report-edit', icon: DocumentChecked },
  { title: '规范问答', desc: '规范条文检索与解释', route: '/normqa', icon: Reading },
  { title: '原始记录扫描', desc: '扫描/拍照回填数据', route: '/scan', icon: View },
  { title: '批量审查', desc: '批量生成审查意见', route: '/review', icon: DataAnalysis },
  { title: '系统设置', desc: 'Harness 与识别配置', route: '/settings', icon: Setting },
]

function onProjectChanged() {
  void loadStatus()
}

onMounted(() => {
  void loadStatus()
  window.addEventListener('harness-project-changed', onProjectChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('harness-project-changed', onProjectChanged)
})
</script>

<template>
  <div class="library-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/project')">返回数据采集</el-button>
        <h2>资料与工具</h2>
        <el-tag size="small" effect="plain">统一入口</el-tag>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadStatus">刷新</el-button>
      </div>
    </header>

    <p class="library-intro">
      知识、模板、设备、人员、记录与流程工具集中在一个入口；数据采集和报告生成保持独立。
    </p>

    <div v-loading="loading" class="library-grid">
      <router-link
        v-for="card in cards"
        :key="card.key"
        :to="card.route"
        class="library-card"
        :class="`tone-${card.tone}`"
      >
        <div class="card-head">
          <div class="card-icon">
            <el-icon><component :is="card.icon" /></el-icon>
          </div>
          <span class="card-arrow"><el-icon><ArrowRight /></el-icon></span>
        </div>
        <div class="card-title">{{ card.title }}</div>
        <div class="card-desc">{{ card.desc }}</div>
        <div class="card-foot">
          <span class="card-count">{{ card.count }}</span>
          <span class="card-meta">{{ card.meta }}</span>
        </div>
      </router-link>
    </div>

    <div class="library-tip">
      资源管理不改变项目数据；流程工具保持独立入口，不再重复建设一级导航。
    </div>

    <section class="tools-panel">
      <div class="tools-head">
        <div>
          <h3>工具</h3>
          <p>流程辅助、专项检查与系统配置集中在这里，不再单独设置“工具”一级页面。</p>
        </div>
        <el-icon class="tools-icon"><Tools /></el-icon>
      </div>
      <div class="tools-grid">
        <router-link
          v-for="tool in tools"
          :key="tool.route"
          :to="tool.route"
          class="tool-link"
        >
          <el-icon><component :is="tool.icon" /></el-icon>
          <span>
            <strong>{{ tool.title }}</strong>
            <small>{{ tool.desc }}</small>
          </span>
          <el-icon class="tool-arrow"><ArrowRight /></el-icon>
        </router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.library-view {
  height: 100%;
  overflow: auto;
  padding: 18px 22px 30px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  max-width: 1180px;
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

.library-intro {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.library-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 2px;
}

.library-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 170px;
  padding: 15px 16px 13px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 13px;
  background: var(--el-bg-color);
  box-shadow: var(--shadow-sm);
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  transition: transform 0.16s, box-shadow 0.16s, border-color 0.16s;
}

.library-card:hover {
  transform: translateY(-2px);
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 9px 24px rgba(30, 60, 90, 0.1);
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.card-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 19px;
}

.tone-teal .card-icon { background: linear-gradient(135deg, #2f8fa8, #1f6479); }
.tone-blue .card-icon { background: linear-gradient(135deg, #4f7fc4, #315f9f); }
.tone-violet .card-icon { background: linear-gradient(135deg, #8a72c8, #6750a8); }
.tone-green .card-icon { background: linear-gradient(135deg, #4e9b7a, #2f7760); }
.tone-rose .card-icon { background: linear-gradient(135deg, #c46f8e, #9f4d6b); }

.card-arrow {
  display: inline-flex;
  align-items: center;
  color: var(--el-text-color-placeholder);
}

.card-title {
  margin-top: 10px;
  font-size: 15px;
  font-weight: 650;
  color: var(--el-text-color-primary);
}

.card-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.card-foot {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: auto;
  padding-top: 12px;
  flex-wrap: wrap;
}

.card-count {
  font-size: 15px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.card-meta {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.library-tip {
  padding: 10px 12px;
  border-radius: 9px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.tools-panel {
  margin-top: 4px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
}
.tools-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.tools-head h3 {
  margin: 0;
  font-size: 15px;
}
.tools-head p {
  margin: 3px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
}
.tools-icon {
  color: var(--el-text-color-placeholder);
  font-size: 20px;
}
.tools-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.tool-link {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-regular);
  text-decoration: none;
  transition: border-color 0.15s, background 0.15s;
}
.tool-link:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.tool-link > .el-icon:first-child {
  color: var(--el-color-primary);
  flex: none;
}
.tool-link span {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.tool-link strong {
  font-size: 12px;
  font-weight: 600;
}
.tool-link small {
  color: var(--el-text-color-secondary);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tool-arrow {
  margin-left: auto;
  flex: none;
  color: var(--el-text-color-placeholder);
}
@media (max-width: 800px) {
  .tools-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .tools-grid { grid-template-columns: 1fr; }
}

@media (max-width: 900px) {
  .library-view { padding: 14px; }
  .library-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 620px) {
  .library-grid { grid-template-columns: 1fr; }
}
</style>
