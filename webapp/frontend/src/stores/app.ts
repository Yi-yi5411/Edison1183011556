/**
 * 全局状态：项目 / 插件 / 勾选项 / 工作表 / 激活标签页 / 主题 / 状态栏消息
 */
import { defineStore } from 'pinia'
import { VxeUI } from 'vxe-pc-ui'
import { api } from '@/api'
import type {
  OriginalTemplateInfo,
  PluginInfo,
  ReportInfo,
  ReportTemplateInfo,
  SheetData,
  SheetRowLike,
  TemplateSelection,
} from '@/api/types'

export type ThemeName = 'light' | 'dark'

const THEME_KEY = 'wb-theme'

function rowHasValue(row: SheetRowLike | null | undefined): boolean {
  if (!row) return false
  if (Array.isArray(row)) return row.some((v) => String(v ?? '').trim() !== '')
  return Object.values(row).some((v) => String(v ?? '').trim() !== '')
}

function emptyTemplateSelection(): TemplateSelection {
  return { report_template_id: '', original_template_map: {} }
}

export const useAppStore = defineStore('app', {
  state: () => ({
    projectName: '',
    plugins: [] as PluginInfo[],
    checkedItems: [] as string[],
    sheets: {} as Record<string, SheetData>,
    activeTab: '',
    /** 项目版本号：每次从后端重载项目后自增，用于驱动表格刷新 */
    projectVersion: 0,
    reportInfo: null as ReportInfo | null,
    templateSelection: emptyTemplateSelection(),
    autosavedAt: '',
    autosaveRestored: false,
    reportTemplates: [] as ReportTemplateInfo[],
    originalTemplates: [] as OriginalTemplateInfo[],
    originalDefaults: {} as Record<string, string>,
    theme: (localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light') as ThemeName,
    statusMessage: '正在初始化…',
    initialized: false,
  }),

  getters: {
    pluginMap(state): Map<string, PluginInfo> {
      return new Map(state.plugins.map((p) => [p.id, p]))
    },
    /** 保持插件定义顺序的已勾选插件列表 */
    checkedPlugins(state): PluginInfo[] {
      return state.plugins.filter((p) => state.checkedItems.includes(p.id))
    },
    /** 已录入数据的检测项数量 */
    filledItemCount(state): number {
      return state.checkedItems.filter((key) =>
        (state.sheets[key]?.rows ?? []).some(rowHasValue),
      ).length
    },
    /** 非空数据行总数 */
    totalRowCount(state): number {
      return state.checkedItems.reduce(
        (sum, key) => sum + (state.sheets[key]?.rows ?? []).filter(rowHasValue).length,
        0,
      )
    },
  },

  actions: {
    setStatus(message: string) {
      this.statusMessage = message
    },

    applyTheme(theme: ThemeName) {
      this.theme = theme
      localStorage.setItem(THEME_KEY, theme)
      document.documentElement.classList.toggle('dark', theme === 'dark')
      try {
        VxeUI.setTheme(theme)
      } catch {
        /* vxe 主题切换失败不影响主流程 */
      }
    },

    toggleTheme() {
      this.applyTheme(this.theme === 'dark' ? 'light' : 'dark')
    },

    async init() {
      this.applyTheme(this.theme)
      // P0 后工程作用域由后端 autosave/打开工程决定，不再按 Harness 会话恢复
      localStorage.removeItem('harness-session-id')
      const results = await Promise.allSettled([this.loadPlugins(), this.loadProject()])
      if (results.every((r) => r.status === 'rejected')) {
        this.setStatus('后端服务不可用（localhost:8765），部分功能暂不可用')
      } else {
        this.setStatus('就绪')
      }
      this.initialized = true
    },

    async loadPlugins() {
      this.plugins = await api.listPlugins()
    },

    async loadProject() {
      const data = await api.getProject()
      this.projectName = data.project_name || '未命名项目'
      this.checkedItems = data.checked_items ?? []
      this.sheets = data.sheets ?? {}
      if (data.report_info) this.reportInfo = data.report_info
      this.templateSelection = data.template_selection ?? emptyTemplateSelection()
      if (!this.templateSelection.original_template_map) {
        this.templateSelection.original_template_map = {}
      }
      this.autosavedAt = data.autosave?.autosaved_at ?? ''
      this.autosaveRestored = !!data.autosave?.restored
      if (!this.activeTab || !this.checkedItems.includes(this.activeTab)) {
        this.activeTab = this.checkedItems[0] ?? ''
      }
      this.projectVersion += 1
    },

    async newProject(projectName: string) {
      const data = await api.newProject(projectName) as {
        backup_path?: string | null
      } | null
      await this.loadProject()
      this.setStatus(`已新建工程：${projectName}`)
      return data
    },

    async openProject(filepath: string) {
      await api.openProject(filepath)
      await this.loadProject()
      this.setStatus(`已打开工程：${filepath}`)
    },

    async saveProject(filepath?: string) {
      const data = await api.saveProject(filepath)
      this.setStatus(`工程已保存${data?.filepath ? `：${data.filepath}` : ''}`)
      return data
    },

    async checkItem(sheetKey: string, checked: boolean, params?: Record<string, unknown>) {
      await api.checkItem(sheetKey, checked, params)
      await this.loadProject()
      if (checked) this.activeTab = sheetKey
      const name = this.pluginMap.get(sheetKey)?.name ?? sheetKey
      this.setStatus(checked ? `已勾选检测项目：${name}` : `已取消检测项目：${name}`)
    },

    /** 本地回写某表行数据（保存/计算成功后同步，不触发版本号） */
    patchSheetRows(sheetKey: string, rows: SheetRowLike[]) {
      const sheet = this.sheets[sheetKey]
      if (sheet) sheet.rows = rows
    },

    /* ===== 模板库 ===== */
    async loadReportTemplates() {
      this.reportTemplates = await api.listReportTemplates()
    },

    async loadOriginalTemplates() {
      const data = await api.listOriginalTemplates()
      this.originalTemplates = data.templates ?? []
      this.originalDefaults = data.defaults ?? {}
    },

    /* ===== 模板选择 ===== */
    setReportTemplateId(templateId: string) {
      this.templateSelection.report_template_id = templateId
    },

    setOriginalTemplate(sheetKey: string, templateId: string) {
      if (templateId) this.templateSelection.original_template_map[sheetKey] = templateId
      else delete this.templateSelection.original_template_map[sheetKey]
    },

    async saveTemplateSelection() {
      this.templateSelection = await api.saveTemplateSelection({
        report_template_id: this.templateSelection.report_template_id,
        original_template_map: { ...this.templateSelection.original_template_map },
      })
      this.setStatus('模板选择已保存到当前项目')
    },
  },
})
