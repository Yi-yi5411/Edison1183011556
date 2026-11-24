import { createRouter, createWebHistory } from 'vue-router'
import { ensureAuth } from '@/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录', public: true },
    },
    { path: '/', redirect: '/harness' },
    {
      path: '/harness',
      name: 'harness',
      component: () => import('@/views/ChatView.vue'),
      meta: { title: '对话' },
    },
    {
      // DSH 原生 GUI 的 iframe 调试入口：仅保留 URL 直达，产品导航不再链接。
      path: '/dsh',
      name: 'dsh',
      component: () => import('@/views/HarnessView.vue'),
      meta: { title: 'DSH 调试', debug: true },
    },
    {
      path: '/workflow',
      name: 'workflow',
      component: () => import('@/views/WorkflowView.vue'),
      meta: { title: '流程总览' },
    },
    {
      path: '/project',
      name: 'project',
      component: () => import('@/views/ProjectView.vue'),
      meta: { title: '检测项目' },
    },
    {
      path: '/report',
      name: 'report',
      component: () => import('@/views/ReportView.vue'),
      meta: { title: '报告生成' },
    },
    {
      path: '/library',
      name: 'library',
      component: () => import('@/views/LibraryView.vue'),
      meta: { title: '资料库' },
    },
    {
      path: '/wiki',
      name: 'wiki',
      component: () => import('@/views/WikiView.vue'),
      meta: { title: '知识库' },
    },
    {
      path: '/personnel',
      name: 'personnel',
      component: () => import('@/views/PersonnelView.vue'),
      meta: { title: '人员库' },
    },
    {
      path: '/records',
      name: 'records',
      component: () => import('@/views/RecordsView.vue'),
      meta: { title: '记录库' },
    },
    {
      path: '/internal',
      redirect: '/library',
    },
    {
      path: '/equipment',
      name: 'equipment',
      component: () => import('@/views/EquipmentView.vue'),
      meta: { title: '设备库' },
    },
    {
      path: '/plugins/dsh',
      name: 'plugins-dsh',
      component: () => import('@/views/DshHostView.vue'),
      meta: { title: 'DSH 插件市场' },
    },
    {
      path: '/plugins',
      name: 'plugins',
      component: () => import('@/views/PluginsView.vue'),
      meta: { title: '插件管理' },
    },
    {
      path: '/templates',
      name: 'templates',
      component: () => import('@/views/TemplatesView.vue'),
      meta: { title: '模板库' },
    },
    {
      path: '/report-edit',
      name: 'report-edit',
      component: () => import('@/views/ReportEditView.vue'),
      meta: { title: '报告修改' },
    },
    {
      path: '/scan',
      name: 'scan',
      component: () => import('@/views/ScanView.vue'),
      meta: { title: '扫描识别' },
    },
    {
      path: '/normqa',
      name: 'normqa',
      component: () => import('@/views/NormQaView.vue'),
      meta: { title: '规范问答' },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('@/views/ReviewView.vue'),
      meta: { title: '批量审查' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: '系统设置' },
    },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) {
    if (to.path === '/login' && await ensureAuth()) return '/harness'
    return true
  }
  if (!await ensureAuth()) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

router.onError((error, to) => {
  const message = String((error as Error)?.message || error)
  if (!/dynamically imported module|Importing a module script failed|Loading chunk/i.test(message)) return
  // 浏览器缓存了旧 index.html 时，旧懒加载 chunk 可能已不存在；强制整页刷新一次。
  const reloadKey = 'route-chunk-reload'
  if (sessionStorage.getItem(reloadKey)) return
  sessionStorage.setItem(reloadKey, '1')
  window.location.assign(to.fullPath)
})

router.afterEach((to) => {
  sessionStorage.removeItem('route-chunk-reload')
  const title = to.meta.title
  document.title = typeof title === 'string' && title
    ? `${title} · 工程检测harness`
    : '工程检测harness'
})

export default router
