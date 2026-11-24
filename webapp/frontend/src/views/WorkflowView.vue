<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, CircleCheck, DataAnalysis, Document, Files, Monitor, Refresh } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { WorkflowStatus, WorkflowStep } from '@/api/types'

const router = useRouter()
const loading = ref(false)
const status = ref<WorkflowStatus | null>(null)

const steps = computed<WorkflowStep[]>(() => status.value?.steps ?? [])
const progress = computed(() => {
  if (!status.value) return 0
  return Math.round((status.value.done_count / status.value.total_steps) * 100)
})
const nextStep = computed(() => status.value?.next_step)
const iconOf = (key: string) => {
  const map: Record<string, unknown> = {
    project: Files,
    collect: DataAnalysis,
    assess: CircleCheck,
    equipment: Monitor,
    template: Document,
    report: Document,
  }
  return map[key] ?? Document
}

async function load() {
  loading.value = true
  try {
    status.value = await api.getWorkflowStatus()
  } catch {
    /* 请求层已提示 */
  } finally {
    loading.value = false
  }
}

function go(route: string) {
  router.push(route)
}

onMounted(load)
</script>

<template>
  <div class="workflow-page" v-loading="loading">
    <section class="hero">
      <div>
        <div class="eyebrow">工程检测harness · 全流程</div>
        <h1>{{ status?.project_name || '检测项目' }}</h1>
        <p class="hero-sub">
          数据采集 → 检测评定 → 设备选用 → 报告生成 → 复核修改，所有环节按实际状态推进。
        </p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="go(nextStep?.route || '/project')">
            {{ nextStep?.key === 'report' ? '进入流式生成' : `继续：${nextStep?.title || '下一步'}` }}
            <el-icon class="el-icon--right"><ArrowRight /></el-icon>
          </el-button>
          <el-button :icon="Refresh" @click="load">刷新状态</el-button>
          <el-button text @click="go('/harness')">用 Harness 继续</el-button>
          <el-tag v-if="status?.report_ready" type="success" effect="dark">报告已可生成</el-tag>
        </div>
      </div>
      <div class="progress-ring">
        <el-progress type="dashboard" :percentage="progress" :width="138" :stroke-width="10">
          <template #default>
            <div class="ring-value">{{ progress }}%</div>
            <div class="ring-label">流程完成</div>
          </template>
        </el-progress>
      </div>
    </section>

    <section class="stat-row">
      <div class="stat-card">
        <div class="stat-value">{{ status?.checked_count ?? 0 }}</div>
        <div class="stat-label">已勾选检测项</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ status?.total_rows ?? 0 }}</div>
        <div class="stat-label">已录入数据行</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ status?.assessed_count ?? 0 }}/{{ status?.checked_count ?? 0 }}</div>
        <div class="stat-label">已完成评定</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ status?.equipment_count ?? 0 }}</div>
        <div class="stat-label">报告选用设备</div>
      </div>
    </section>

    <section class="flow-section">
      <div class="section-head">
        <h2>流程步骤</h2>
        <span class="section-hint">状态由后端实时计算，点击卡片进入对应页面</span>
      </div>
      <div class="flow-grid">
        <div
          v-for="(step, index) in steps"
          :key="step.key"
          class="flow-card"
          :class="[step.status, { active: nextStep?.key === step.key }]"
          @click="go(step.route)"
        >
          <div class="flow-card-top">
            <span class="flow-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <el-icon class="flow-icon"><component :is="iconOf(step.key)" /></el-icon>
          </div>
          <div class="flow-title">{{ step.title }}</div>
          <div class="flow-detail">{{ step.detail }}</div>
          <div class="flow-card-bottom">
            <el-tag
              size="small"
              :type="step.status === 'done' ? 'success' : step.status === 'ready' ? 'primary' : step.status === 'progress' ? 'warning' : 'info'"
            >
              {{ step.status === 'done' ? '已完成' : step.status === 'ready' ? '可生成' : step.status === 'progress' ? '进行中' : '待开始' }}
            </el-tag>
            <span v-if="nextStep?.key === step.key" class="next-mark">下一步</span>
            <el-icon class="go-icon"><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </section>

    <section class="tips">
      <div class="tip-item">
        <b>数据采集</b>
        <span>左侧检测项目树勾选项目，右侧表格录入或导入 Excel；所有修改自动保存。</span>
      </div>
      <div class="tip-item">
        <b>检测评定</b>
        <span>在数据采集页的“评定 / 结论”中运行；报告结论优先使用评定结果。</span>
      </div>
      <div class="tip-item">
        <b>报告生成</b>
        <span>报告页点击“流式生成报告”，实时显示后端组装日志，生成后可直接修改。</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.workflow-page {
  padding: 18px 20px 28px;
}
.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 26px 30px;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(120deg, #17324d 0%, #1d4d72 55%, #2f6f8f 100%);
  box-shadow: 0 10px 30px rgba(23, 50, 77, 0.18);
}
.eyebrow {
  font-size: 12px;
  letter-spacing: 2px;
  opacity: 0.72;
}
.hero h1 {
  margin: 8px 0 6px;
  font-size: 27px;
  font-weight: 600;
}
.hero-sub {
  margin: 0 0 16px;
  opacity: 0.82;
  font-size: 13px;
}
.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.progress-ring {
  flex: none;
  align-self: center;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 50%;
}
.progress-ring :deep(.el-progress__text) {
  color: #fff;
}
.ring-value {
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}
.ring-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
  margin-top: 2px;
}
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.stat-card {
  padding: 14px 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.stat-label {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 4px 0 10px;
}
.section-head h2 {
  margin: 0;
  font-size: 17px;
}
.section-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.flow-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.flow-card {
  position: relative;
  padding: 15px 16px 13px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
  cursor: pointer;
  transition: transform 0.18s, box-shadow 0.18s, border-color 0.18s;
}
.flow-card:hover {
  transform: translateY(-2px);
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 8px 20px rgba(30, 60, 90, 0.1);
}
.flow-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
}
.flow-card.done .flow-icon {
  color: var(--el-color-success);
}
.flow-card.ready .flow-icon,
.flow-card.active .flow-icon {
  color: var(--el-color-primary);
}
.flow-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.flow-index {
  font-family: Consolas, monospace;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.flow-icon {
  font-size: 22px;
  color: var(--el-text-color-secondary);
}
.flow-title {
  margin-top: 12px;
  font-size: 16px;
  font-weight: 600;
}
.flow-detail {
  min-height: 34px;
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.flow-card-bottom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.go-icon {
  margin-left: auto;
  color: var(--el-text-color-placeholder);
}
.next-mark {
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 600;
}
.tips {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.tip-item {
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}
.tip-item b {
  display: block;
  margin-bottom: 3px;
  color: var(--el-text-color-primary);
}
@media (max-width: 1000px) {
  .stat-row,
  .flow-grid,
  .tips {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 680px) {
  .hero {
    flex-direction: column;
  }
  .stat-row,
  .flow-grid,
  .tips {
    grid-template-columns: 1fr;
  }
}
</style>
