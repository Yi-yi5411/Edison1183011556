<script setup lang="ts">
/**
 * 对话入口（/harness，默认首页）。
 *
 * 交互完全交给 DSH：本页只保留一条 40px 的状态条，其余整屏都是原生 DSH Web GUI
 * ——会话列表、输入框、计划/子智能体/审批/技能全部是 DSH 自己的交互，不再套卡片面板。
 * 工程上下文与项目化预设放在 DSH 输入框上方的 dock 插件里（见 docs/DSH源码改造.md）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '@/api'
import { logout } from '@/auth'
import type { WorkflowStatus } from '@/api/types'

const router = useRouter()

interface SystemInfo {
  backend: string
  version: string
  agent_surface: string
  dsh_gui_url: string
  mcp_server_name: string
  architecture_doc: string
}

const system = ref<SystemInfo | null>(null)
const dsh = ref<{ url: string; reachable: boolean; status: number; auth_required: boolean } | null>(null)
const workflow = ref<WorkflowStatus | null>(null)
const frameKey = ref(0)
const frameLoaded = ref(false)

const embedUrl = computed(() => {
  const url = dsh.value?.url || system.value?.dsh_gui_url || ''
  return url ? url.replace(/\/$/, '') + '/' : ''
})

const hostMismatch = computed(() => {
  if (!embedUrl.value) return false
  try {
    return new URL(embedUrl.value).hostname !== window.location.hostname
  } catch {
    return false
  }
})

const healthy = computed(() => !!dsh.value?.reachable)

async function load() {
  try {
    const [info, dshInfo, flow] = await Promise.all([
      api.systemInfo(),
      api.dshStatus(),
      api.getWorkflowStatus(),
    ])
    system.value = info
    dsh.value = dshInfo
    workflow.value = flow
  } catch {
    /* api 层已提示 */
  }
}

function openDsh() {
  if (!embedUrl.value) return
  window.open(embedUrl.value, '_blank', 'noopener')
}

function reloadFrame() {
  frameKey.value += 1
  frameLoaded.value = false
  void load()
}

function go(path: string) {
  void router.push(path)
}

async function onLogout() {
  await logout()
  void router.replace('/login')
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="dsh-shell">
    <header class="dsh-bar">
      <span class="dot" :class="{ ok: healthy, warn: !healthy }" />
      <span class="brand">工程检测harness · DSH 调试</span>
      <span class="proj">{{ workflow?.project_name || '未命名工程' }}</span>
      <span class="meta">勾选 {{ workflow?.checked_count ?? 0 }} · 录入 {{ workflow?.filled_count ?? 0 }} · 评定 {{ workflow?.assessed_count ?? 0 }}</span>
      <span class="spacer" />
      <button class="link" type="button" @click="reloadFrame">刷新</button>
      <button class="link" type="button" @click="go('/project')">数据采集</button>
      <button class="link" type="button" @click="go('/report')">报告</button>
      <button class="link strong" type="button" @click="openDsh">新窗口</button>
      <button class="link" type="button" @click="onLogout">退出</button>
    </header>

    <div v-if="hostMismatch" class="banner">
      请用 <b>http://127.0.0.1:8765</b> 访问：DSH 登录 Cookie 绑定在 127.0.0.1，用 localhost 会要求重新登录。
    </div>

    <main class="dsh-main">
      <template v-if="embedUrl">
        <iframe
          :key="frameKey"
          :src="embedUrl"
          class="dsh-frame"
          title="DSH 对话"
          allow="clipboard-read; clipboard-write"
          @load="frameLoaded = true"
        />
        <div v-if="!frameLoaded" class="dsh-cover">
          <div class="cover-title">正在连接 DSH 原生 GUI</div>
          <p>调试入口：若一直空白，说明 DSH 未启动或需要登录。</p>
          <el-button type="primary" :icon="Refresh" @click="openDsh">在新窗口打开 DSH</el-button>
        </div>

      </template>
      <div v-else class="dsh-cover">
        <div class="cover-title">DSH 原生 GUI · 调试入口</div>
        <p>未配置 DSH 地址：在 config/structural.toml 的 [dsh].gui_url 填写，例如 http://127.0.0.1:3642</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.dsh-shell {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color, #fff);
}
.dsh-bar {
  flex: none;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
  font-size: 12px;
  color: var(--el-text-color-regular, #606266);
  background: var(--el-bg-color, #fff);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c0c4cc;
}
.dot.ok {
  background: #67c23a;
}
.dot.warn {
  background: #e6a23c;
}
.brand {
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.proj {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  color: var(--el-text-color-secondary, #909399);
}
.spacer {
  flex: 1;
}
.link {
  border: 0;
  background: transparent;
  padding: 2px 6px;
  border-radius: 5px;
  color: var(--el-text-color-regular, #606266);
  font-size: 12px;
  cursor: pointer;
}
.link:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--el-color-primary, #409eff);
}
.link.strong {
  color: var(--el-color-primary, #409eff);
}
.banner {
  flex: none;
  padding: 5px 12px;
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border-bottom: 1px solid #fde68a;
}
.dsh-main {
  position: relative;
  flex: 1;
  min-height: 0;
}
.dsh-frame {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
.dsh-cover {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 24px;
  background: var(--el-bg-color, #fff);
  color: var(--el-text-color-secondary, #909399);
  font-size: 13px;
}
.cover-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.login-tip {
  position: absolute;
  right: 12px;
  bottom: 12px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #92400e;
  font-size: 12px;
}
</style>
