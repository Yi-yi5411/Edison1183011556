/**
 * Axios 实例 + API 契约全部端点的类型化封装
 * 统一约定：响应 { ok, data, message }；ok=false 或请求异常时 ElMessage.error 并 reject
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { AxiosResponse, AxiosRequestConfig } from 'axios'
import router from '@/router'
import { resetAuth } from '@/auth'
import type {
  AppConfigData,
  AssessmentDetail,
  AssessmentOptions,
  AssessmentResult,
  AssessmentSpec,
  EquipmentCaptcha,
  EquipmentLocal,
  EquipmentRemotePage,
  EquipmentStatus,
  ExternalPluginStatus,
  IngestImportResult,
  IngestRecognizeResult,
  DshBundle,
  DshHostStatus,
  DshMarketIndex,
  DshPluginsStatus,
  DshSearchResult,
  LibraryStatus,
  MergeRange,
  NormQaExplainResult,
  NormQaImportResult,
  NormQaQueryResult,
  NormQaStatus,
  OriginalRecord,
  OriginalRecordHistoryItem,
  OriginalRecordResult,
  OriginalTemplateInfo,
  OriginalTemplateList,
  Personnel,
  PersonnelList,
  PersonnelStatus,
  PluginInfo,
  ProjectHistoryItem,
  ProjectData,
  RecordList,
  ReportDocument,
  ReportGeneratePayload,
  ReportGenerateResult,
  ReportHistoryItem,
  ReportAutoInfo,
  ReportInfo,
  ReportRecord,
  ReportStreamEvent,
  ReportTemplateInfo,
  ReviewCandidate,
  ReviewRunResult,
  SaveReportDocumentPayload,
  SaveReportDocumentResult,
  ScanCommitResult,
  ScanHistoryItem,
  ScanJob,
  ScanPlan,
  ScanRunResult,
  SheetRow,
  TemplateSelection,
  VisionModelsResult,
  WikiCategory,
  WikiPage,
  WikiPageSummary,
  WikiSearchHit,
  WikiStatus,
  WorkflowStatus,
} from './types'

interface ApiEnvelope<T = unknown> {
  ok: boolean
  data: T
  message?: string
}

const http = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

/* ===== 401 统一处理：会话过期/未登录 → 清缓存并跳转登录页 ===== */
let handling401 = false

/** 统一处理 401：返回 true 表示本次错误源于登录态失效（已做跳转提示）。 */
function handle401(): boolean {
  resetAuth()
  if (handling401) return true
  handling401 = true
  ElMessage.error('登录已过期，请重新登录')
  if (router.currentRoute.value.path !== '/login') {
    void router.replace({
      path: '/login',
      query: { redirect: router.currentRoute.value.fullPath },
    })
  }
  window.setTimeout(() => {
    handling401 = false
  }, 1000)
  return true
}

/** axios 响应拦截：401 统一跳登录，其余错误交给调用方提示 */
http.interceptors.response.use(undefined, (error) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    handle401()
  }
  throw error
})

/** 从任意异常中提取后端中文 message */
function extractMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data: unknown = err.response?.data
    if (data && typeof data === 'object' && !(data instanceof Blob)) {
      const m = (data as Record<string, unknown>).message
      if (typeof m === 'string' && m) return m
    }
    if (err.code === 'ECONNABORTED') return '请求超时，请确认后端服务（localhost:8765）是否正在运行'
    if (!err.response) return '无法连接后端服务（localhost:8765），请先启动后端'
    return err.response.statusText
      ? `请求失败（${err.response.status} ${err.response.statusText}）`
      : `请求失败（${err.response.status}）`
  }
  return err instanceof Error ? err.message : '请求失败'
}

/** 发起请求并解包 { ok, data, message } 信封 */
async function request<T>(config: AxiosRequestConfig): Promise<T> {
  let resp: AxiosResponse<ApiEnvelope<T>>
  try {
    resp = await http.request<ApiEnvelope<T>>(config)
  } catch (err) {
    if (!(axios.isAxiosError(err) && err.response?.status === 401)) {
      ElMessage.error(extractMessage(err))
    }
    throw err
  }
  const body = resp.data
  if (body && typeof body === 'object' && 'ok' in body) {
    if (!body.ok) {
      const msg = body.message || '操作失败'
      ElMessage.error(msg)
      throw new Error(msg)
    }
    return body.data
  }
  // 非标准信封响应，原样返回
  return resp.data as T
}

/* ===== 文件下载 ===== */

function filenameFromDisposition(headers: AxiosResponse['headers']): string | null {
  const raw: unknown = (headers as Record<string, unknown>)?.['content-disposition']
  const cd = Array.isArray(raw) ? raw.join(';') : typeof raw === 'string' ? raw : ''
  if (!cd) return null
  const m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd)
  if (!m) return null
  try {
    return decodeURIComponent(m[1].replace(/"/g, ''))
  } catch {
    return m[1]
  }
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 把普通 JSON 对象作为文件下载（结构化数据导出等） */
export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  triggerDownload(blob, filename)
}

/** 二进制下载（失败时给出中文提示） */
async function download(
  url: string,
  fallbackName: string,
  method: 'get' | 'post' = 'get',
  data?: unknown,
): Promise<string> {
  try {
    const resp = await http.request<Blob>({ url, method, data, responseType: 'blob' })
    const name = filenameFromDisposition(resp.headers) || fallbackName
    triggerDownload(resp.data, name)
    return name
  } catch (err) {
    if (!(axios.isAxiosError(err) && err.response?.status === 401)) {
      ElMessage.error(extractMessage(err))
    }
    throw err
  }
}

/* ===== multipart ===== */

function toForm(files: File[], extra?: Record<string, string>): FormData {
  const fd = new FormData()
  for (const f of files) fd.append('files', f, f.name)
  if (extra) {
    for (const [k, v] of Object.entries(extra)) fd.append(k, v)
  }
  return fd
}

/** 单文件 + 表单字段（模板上传） */
function toSingleForm(file: File, extra?: Record<string, string>): FormData {
  const fd = new FormData()
  fd.append('file', file, file.name)
  if (extra) {
    for (const [k, v] of Object.entries(extra)) fd.append(k, v)
  }
  return fd
}

/* ===== API 封装 ===== */

export const api = {
  /* 1. 检测项目（插件） */
  listPlugins(): Promise<PluginInfo[]> {
    return request<PluginInfo[]>({ url: '/plugins', method: 'get' })
  },

  /* 2. 项目管理 */
  getProject(): Promise<ProjectData> {
    return request<ProjectData>({ url: '/project', method: 'get' })
  },
  newProject(projectName: string): Promise<unknown> {
    return request({ url: '/project/new', method: 'post', data: { project_name: projectName } })
  },
  openProject(filepath: string): Promise<unknown> {
    return request({ url: '/project/open', method: 'post', data: { filepath } })
  },
  getProjectHistory(): Promise<{ items: ProjectHistoryItem[]; total: number }> {
    return request({
      url: '/project/history',
      method: 'get',
    })
  },
  listProjects(): Promise<{ items: ProjectHistoryItem[]; total: number }> {
    return request({ url: '/project/list', method: 'get' })
  },
  currentProject(): Promise<Record<string, unknown>> {
    return request({ url: '/project/current', method: 'get' })
  },
  activateProject(filepath: string): Promise<unknown> {
    return request({ url: '/project/activate', method: 'post', data: { filepath } })
  },
  saveProject(filepath?: string): Promise<{ filepath?: string } | null> {
    return request<{ filepath?: string } | null>({
      url: '/project/save',
      method: 'post',
      data: filepath ? { filepath } : {},
    })
  },
  renameProject(projectName: string): Promise<unknown> {
    return request({
      url: '/project/name',
      method: 'put',
      data: { project_name: projectName },
    })
  },
  checkItem(sheetKey: string, checked: boolean, params?: Record<string, unknown>): Promise<unknown> {
    return request({
      url: '/project/check_item',
      method: 'post',
      data: { sheet_key: sheetKey, checked, ...(params ? { params } : {}) },
    })
  },
  ingestRecognize(filepath: string, sheetName = ''): Promise<IngestRecognizeResult> {
    return request<IngestRecognizeResult>({
      url: '/ingest/recognize',
      method: 'get',
      params: { filepath, ...(sheetName ? { sheet_name: sheetName } : {}) },
    })
  },
  ingestImport(payload: {
    filepath: string
    sheet_key: string
    sheet_name?: string
    append?: boolean
    auto_assess?: boolean
    params?: Record<string, unknown>
  }): Promise<IngestImportResult> {
    return request<IngestImportResult>({
      url: '/ingest/import',
      method: 'post',
      data: { auto_assess: true, ...payload },
    })
  },

  /* 3. 表格数据 */
  putSheetRows(sheetKey: string, rows: SheetRow[]): Promise<unknown> {
    return request({ url: `/sheet/${encodeURIComponent(sheetKey)}/rows`, method: 'put', data: { rows } })
  },
  importSheetExcel(
    sheetKey: string,
    file: File,
    append = false,
    sheetName = '',
  ): Promise<unknown> {
    return request({
      url: `/sheet/${encodeURIComponent(sheetKey)}/import_excel`,
      method: 'post',
      data: toSingleForm(file, {
        append: append ? 'true' : 'false',
        sheet_name: sheetName,
      }),
    })
  },
  calcSheet(sheetKey: string, rows: SheetRow[]): Promise<unknown> {
    return request({ url: `/sheet/${encodeURIComponent(sheetKey)}/calc`, method: 'post', data: { rows } })
  },
  mergeSheet(sheetKey: string, merges: MergeRange[], append = false): Promise<unknown> {
    return request({
      url: `/sheet/${encodeURIComponent(sheetKey)}/merge`,
      method: 'post',
      data: { merges, append },
    })
  },
  insertSheetRows(sheetKey: string, index: number, count = 1): Promise<unknown> {
    return request({
      url: `/sheet/${encodeURIComponent(sheetKey)}/rows/insert`,
      method: 'post',
      data: { index, count },
    })
  },
  deleteSheetRows(sheetKey: string, index: number, count = 1): Promise<unknown> {
    return request({
      url: `/sheet/${encodeURIComponent(sheetKey)}/rows/delete`,
      method: 'post',
      data: { index, count },
    })
  },
  smartMergeSheet(sheetKey: string, columns?: number[]): Promise<unknown> {
    return request({
      url: `/sheet/${encodeURIComponent(sheetKey)}/smart_merge`,
      method: 'post',
      data: columns && columns.length ? { columns } : undefined,
    })
  },
  fillDown(sheetKey: string, colKeys: string[], rowFrom: number, rowTo: number): Promise<unknown> {
    return request({
      url: `/sheet/${encodeURIComponent(sheetKey)}/fill_down`,
      method: 'post',
      data: { col_keys: colKeys, row_from: rowFrom, row_to: rowTo },
    })
  },
  exportProject(fallbackName: string): Promise<string> {
    return download('/project/export', fallbackName)
  },
  exportSheet(sheetKey: string, fallbackName: string): Promise<string> {
    return download(`/sheet/${encodeURIComponent(sheetKey)}/export`, fallbackName)
  },

  /* 4. 报告生成 */
  getReportInfo(): Promise<ReportInfo> {
    return request<ReportInfo>({ url: '/report/info', method: 'get' })
  },
  reportAutoInfo(): Promise<ReportAutoInfo> {
    return request<ReportAutoInfo>({ url: '/report/auto_info', method: 'post' })
  },
  reportPreviewUrl(filepath: string): string {
    return `/api/report/preview?filepath=${encodeURIComponent(filepath)}`
  },
  reportDownloadUrl(filepath: string): string {
    return `/api/report/download?filepath=${encodeURIComponent(filepath)}`
  },
  putReportInfo(reportInfo: ReportInfo): Promise<unknown> {
    return request({ url: '/report/info', method: 'put', data: { report_info: reportInfo } })
  },
  generateReport(payload: ReportGeneratePayload): Promise<ReportGenerateResult> {
    return request<ReportGenerateResult>({ url: '/report/generate', method: 'post', data: payload })
  },
  revealReport(filepath: string): Promise<unknown> {
    return request({ url: '/report/reveal', method: 'post', data: { filepath } })
  },
  /** 推算下一个报告编号（前缀-年份-序号，按生成历史最大序号递增） */
  getNextReportNo(): Promise<string> {
    return request<string>({ url: '/report/next_no', method: 'get' })
  },
  /** 报告生成历史（最近 50 条，倒序） */
  getReportHistory(): Promise<ReportHistoryItem[]> {
    return request<ReportHistoryItem[]>({ url: '/report/history', method: 'get' })
  },
  clearReportHistory(): Promise<unknown> {
    return request({ url: '/report/history/clear', method: 'post' })
  },
  /** 通用：在资源管理器中定位产物文件（审查意见表/导出 Excel 等） */
  revealFile(filepath: string): Promise<unknown> {
    return request({ url: '/utils/reveal', method: 'post', data: { filepath } })
  },

  /* 5. 规范问答 */
  normqaStatus(): Promise<NormQaStatus> {
    return request<NormQaStatus>({ url: '/normqa/status', method: 'get' })
  },
  normqaImport(files: File[], mode: 'append' | 'rebuild'): Promise<NormQaImportResult> {
    return request<NormQaImportResult>({
      url: '/normqa/import',
      method: 'post',
      data: toForm(files, { mode }),
    })
  },
  normqaQuery(question: string): Promise<NormQaQueryResult> {
    return request<NormQaQueryResult>({ url: '/normqa/query', method: 'post', data: { question } })
  },
  normqaExplain(question: string, clauses: Record<string, unknown>[]): Promise<NormQaExplainResult> {
    return request<NormQaExplainResult>({
      url: '/normqa/explain',
      method: 'post',
      data: { question, clauses },
    })
  },

  /* 6. 批量审查 */
  reviewRun(files: File[]): Promise<ReviewRunResult> {
    return request<ReviewRunResult>({ url: '/review/run', method: 'post', data: toForm(files) })
  },
  reviewExport(candidates: ReviewCandidate[], projectName: string): Promise<string> {
    return download('/review/export', '审查意见表.docx', 'post', { candidates, project_name: projectName })
  },

  /* 7. 扫描识别 */
  scanRun(files: File[], detectionItem?: string): Promise<ScanRunResult> {
    return request<ScanRunResult>({
      url: '/scan/run',
      method: 'post',
      data: toForm(files, detectionItem ? { detection_item: detectionItem } : undefined),
    })
  },
  /** 提交异步扫描识别作业，返回秒回的作业视图 */
  scanSubmit(filepath: string, detectionItem = ''): Promise<ScanJob> {
    return request<ScanJob>({
      url: '/scan/submit',
      method: 'post',
      data: { filepath, detection_item: detectionItem },
    })
  },
  /** 轮询异步扫描识别作业 */
  scanJob(jobId: string): Promise<ScanJob> {
    return request<ScanJob>({ url: '/scan/job/' + encodeURIComponent(jobId), method: 'get' })
  },
  /** 按识别出的检测项目查询可写入的采集表（含构件、参数要求） */
  scanTargets(detectionItem: string): Promise<ScanPlan> {
    return request<ScanPlan>({
      url: '/scan/targets',
      method: 'get',
      params: { detection_item: detectionItem },
    })
  },
  /** 把扫描结构化结果写入指定采集表，只勾选该表并自动评定 */
  scanCommit(payload: {
    job_id: string
    sheet_key: string
    append?: boolean
    params?: Record<string, unknown>
    auto_assess?: boolean
  }): Promise<ScanCommitResult> {
    return request<ScanCommitResult>({
      url: '/scan/commit',
      method: 'post',
      data: { auto_assess: true, ...payload },
    })
  },
  /** records 为匹配列后的对齐行 [[单元格,...], ...]，逐行追加到目标表末尾 */
  scanFill(sheetKey: string, records: SheetRow[]): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>({
      url: '/scan/fill',
      method: 'post',
      data: { sheet_key: sheetKey, records },
    })
  },
  scanHistory(): Promise<ScanHistoryItem[]> {
    return request<ScanHistoryItem[]>({ url: '/scan/history', method: 'get' })
  },
  scanVisionModels(): Promise<VisionModelsResult> {
    return request<VisionModelsResult>({ url: '/scan/vision_models', method: 'get' })
  },

  /* 8. 配置 */
  getConfig(): Promise<AppConfigData> {
    return request<AppConfigData>({ url: '/config', method: 'get' })
  },
  putConfig(section: string, values: Record<string, unknown>): Promise<unknown> {
    return request({ url: '/config', method: 'put', data: { section, values } })
  },

  /* 8.5 检测评定 */
  listAssessmentSpecs(): Promise<{ specs: AssessmentSpec[] }> {
    return request<{ specs: AssessmentSpec[] }>({ url: '/assessment/specs', method: 'get' })
  },
  getAssessment(sheetKey: string): Promise<AssessmentDetail> {
    return request<AssessmentDetail>({
      url: `/assessment/${encodeURIComponent(sheetKey)}`,
      method: 'get',
    })
  },
  runAssessment(
    sheetKey: string,
    payload: { input?: Record<string, unknown>; options?: AssessmentOptions },
  ): Promise<AssessmentResult> {
    return request<AssessmentResult>({
      url: `/assessment/${encodeURIComponent(sheetKey)}/run`,
      method: 'post',
      data: payload,
    })
  },
  saveAssessmentInput(
    sheetKey: string,
    payload: { input?: Record<string, unknown>; options?: AssessmentOptions },
  ): Promise<unknown> {
    return request({
      url: `/assessment/${encodeURIComponent(sheetKey)}/input`,
      method: 'put',
      data: payload,
    })
  },
  importAssessmentExcel(
    sheetKey: string,
    file: File,
    sheetName = '',
  ): Promise<{
    sheet_key: string
    input: Record<string, unknown>
    components?: number
    warnings: string[]
  }> {
    return request({
      url: `/assessment/${encodeURIComponent(sheetKey)}/import_excel`,
      method: 'post',
      data: toSingleForm(file, { sheet_name: sheetName }),
    })
  },
  runAllAssessments(sheetKeys?: string[]): Promise<{
    results: Record<string, AssessmentResult>
    warnings: string[]
  }> {
    return request({
      url: '/assessment/run_all',
      method: 'post',
      data: { sheet_keys: sheetKeys ?? [] },
    })
  },

  /* 8.7 检测项目插件 */
  getDshPlugins(): Promise<DshPluginsStatus> {
    return request<DshPluginsStatus>({ url: '/plugins/dsh', method: 'get' })
  },
  getDshHostStatus(): Promise<DshHostStatus> {
    return request<DshHostStatus>({ url: '/plugins/dsh/host', method: 'get' })
  },
  saveDshHost(base_url: string, token: string): Promise<{ status: DshHostStatus; bundle_count: number }> {
    return request<{ status: DshHostStatus; bundle_count: number }>({
      url: '/plugins/dsh/host', method: 'put', data: { base_url, token },
    })
  },
  getDshIndexes(): Promise<DshMarketIndex[]> {
    return request<DshMarketIndex[]>({ url: '/plugins/dsh/host/indexes', method: 'get' })
  },
  saveDshIndexes(urls: string[]): Promise<DshMarketIndex[]> {
    return request<DshMarketIndex[]>({
      url: '/plugins/dsh/host/indexes', method: 'put', data: { urls },
    })
  },
  getDshBundles(): Promise<DshBundle[]> {
    return request<DshBundle[]>({ url: '/plugins/dsh/host/bundles', method: 'get' })
  },
  searchDshPlugins(url: string, text: string): Promise<DshSearchResult> {
    return request<DshSearchResult>({
      url: '/plugins/dsh/host/search', method: 'post', data: { url, text, limit: 30 },
    })
  },
  inspectDshPlugin(spec: string): Promise<any> {
    return request<any>({ url: '/plugins/dsh/host/inspect', method: 'post', data: { spec } })
  },
  installDshPlugin(spec: string, expected?: { name: string; version: string }): Promise<any> {
    return request<any>({
      url: '/plugins/dsh/host/install', method: 'post',
      data: { spec, name: expected?.name || '', version: expected?.version || '', confirm: true },
    })
  },
  toggleDshBundle(name: string, enabled: boolean): Promise<any> {
    return request<any>({
      url: '/plugins/dsh/host/toggle', method: 'post', data: { name, enabled, confirm: true },
    })
  },
  removeDshBundle(name: string): Promise<any> {
    return request<any>({
      url: '/plugins/dsh/host/remove', method: 'post',
      data: { name, confirm: true, confirm_delete: true },
    })
  },
  getExternalPlugins(): Promise<ExternalPluginStatus> {
    return request<ExternalPluginStatus>({ url: '/plugins/external', method: 'get' })
  },
  reloadPlugins(): Promise<ExternalPluginStatus> {
    return request<ExternalPluginStatus>({ url: '/plugins/external/reload', method: 'post' })
  },
  saveExternalPluginSources(roots: string[]): Promise<ExternalPluginStatus> {
    return request<ExternalPluginStatus>({
      url: '/plugins/external/sources',
      method: 'put',
      data: { roots },
    })
  },

  /* 9. 模板库 */
  listReportTemplates(): Promise<ReportTemplateInfo[]> {
    return request<ReportTemplateInfo[]>({ url: '/templates/report', method: 'get' })
  },
  getReportTemplate(templateId: string): Promise<ReportTemplateInfo> {
    return request<ReportTemplateInfo>({
      url: `/templates/report/${encodeURIComponent(templateId)}`,
      method: 'get',
    })
  },
  uploadReportTemplate(file: File): Promise<{ template: ReportTemplateInfo; warnings: string[] }> {
    return request<{ template: ReportTemplateInfo; warnings: string[] }>({
      url: '/templates/report/upload',
      method: 'post',
      data: toSingleForm(file),
    })
  },
  setDefaultReportTemplate(templateId: string): Promise<ReportTemplateInfo> {
    return request<ReportTemplateInfo>({
      url: `/templates/report/${encodeURIComponent(templateId)}/default`,
      method: 'post',
    })
  },
  deleteReportTemplate(templateId: string): Promise<unknown> {
    return request({
      url: `/templates/report/${encodeURIComponent(templateId)}`,
      method: 'delete',
    })
  },
  exportReportTemplate(templateId: string, fallbackName: string): Promise<string> {
    return download(
      `/templates/report/${encodeURIComponent(templateId)}/export`,
      fallbackName,
    )
  },

  listOriginalTemplates(): Promise<OriginalTemplateList> {
    return request<OriginalTemplateList>({ url: '/templates/original', method: 'get' })
  },
  uploadOriginalTemplate(payload: {
    file: File
    name: string
    code?: string
    detection_items: string[]
    set_default?: boolean
  }): Promise<OriginalTemplateInfo> {
    const form = toSingleForm(payload.file, {
      name: payload.name,
      code: payload.code ?? '',
      detection_items: JSON.stringify(payload.detection_items ?? []),
      set_default: payload.set_default ? 'true' : 'false',
    })
    return request<OriginalTemplateInfo>({
      url: '/templates/original/upload',
      method: 'post',
      data: form,
    })
  },
  setOriginalDefaults(templateId: string, items: string[]): Promise<OriginalTemplateInfo> {
    return request<OriginalTemplateInfo>({
      url: `/templates/original/${encodeURIComponent(templateId)}/default`,
      method: 'post',
      data: { items },
    })
  },
  deleteOriginalTemplate(templateId: string): Promise<unknown> {
    return request({
      url: `/templates/original/${encodeURIComponent(templateId)}`,
      method: 'delete',
    })
  },
  previewOriginalTemplate(templateId: string): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>({
      url: `/templates/original/${encodeURIComponent(templateId)}/preview`,
      method: 'get',
    })
  },
  downloadOriginalTemplate(templateId: string, fallbackName: string): Promise<string> {
    return download(
      `/templates/original/${encodeURIComponent(templateId)}/download`,
      fallbackName,
    )
  },
  downloadReferenceDoc(templateId: string, fallbackName: string): Promise<string> {
    return download(
      `/templates/original/${encodeURIComponent(templateId)}/reference`,
      fallbackName,
    )
  },

  /* 10. 原始记录生成 */
  generateOriginalRecords(payload: {
    sheet_keys: string[]
    template_map: Record<string, string>
  }): Promise<OriginalRecordResult> {
    return request<OriginalRecordResult>({
      url: '/original-record/generate',
      method: 'post',
      data: payload,
    })
  },
  getOriginalRecordHistory(): Promise<OriginalRecordHistoryItem[]> {
    return request<OriginalRecordHistoryItem[]>({
      url: '/original-record/history',
      method: 'get',
    })
  },
  clearOriginalRecordHistory(): Promise<unknown> {
    return request({ url: '/original-record/history/clear', method: 'post' })
  },

  /* 11. 模板选择 */
  saveTemplateSelection(selection: TemplateSelection): Promise<TemplateSelection> {
    return request<TemplateSelection>({
      url: '/project/template_selection',
      method: 'put',
      data: selection,
    })
  },

  /* 12. 报告修改 */
  loadReportDocument(filepath: string): Promise<ReportDocument> {
    return request<ReportDocument>({
      url: '/report/document',
      method: 'get',
      params: { filepath },
    })
  },
  saveReportDocument(payload: SaveReportDocumentPayload): Promise<SaveReportDocumentResult> {
    return request<SaveReportDocumentResult>({
      url: '/report/document/save',
      method: 'post',
      data: payload,
    })
  },
  replaceReportText(payload: SaveReportDocumentPayload & {
    find: string
    replace: string
  }): Promise<SaveReportDocumentResult> {
    return request<SaveReportDocumentResult>({
      url: '/report/document/replace',
      method: 'post',
      data: payload,
    })
  },
  downloadReportDocument(filepath: string, fallbackName: string): Promise<string> {
    return download(
      `/report/document/download?filepath=${encodeURIComponent(filepath)}`,
      fallbackName,
    )
  },

  /* 13. 设备库（设备管理系统） */
  generateReportStream(
    payload: ReportGeneratePayload,
    onEvent: (event: ReportStreamEvent) => void,
  ): Promise<ReportGenerateResult> {
    return new Promise((resolve, reject) => {
      let finished = false
      fetch('/api/report/generate/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(payload),
      })
        .then(async (response) => {
          if (!response.ok || !response.body) {
            if (response.status === 401) {
              handle401()
              throw new Error('登录已过期，请重新登录')
            }
            const text = await response.text().catch(() => '')
            throw new Error(text || `报告生成服务返回 ${response.status}`)
          }
          const reader = response.body.getReader()
          const decoder = new TextDecoder('utf-8')
          let buffer = ''
          const handleBlock = (block: string) => {
            let event = 'message'
            const dataLines: string[] = []
            for (const line of block.split('\n')) {
              if (line.startsWith('event:')) event = line.slice(6).trim()
              if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
            }
            if (!dataLines.length) return
            let data: Record<string, unknown> = {}
            try {
              data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
            } catch {
              data = { message: dataLines.join('\n') }
            }
            onEvent({ event: event as ReportStreamEvent['event'], data })
            if (event === 'result') {
              finished = true
              const result = (data.data ?? data) as unknown as ReportGenerateResult
              resolve(result)
            } else if (event === 'error') {
              finished = true
              reject(new Error(String(data.message || '报告生成失败')))
            }
          }
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            let index = buffer.indexOf('\n\n')
            while (index >= 0) {
              handleBlock(buffer.slice(0, index))
              buffer = buffer.slice(index + 2)
              index = buffer.indexOf('\n\n')
            }
          }
          if (buffer.trim()) handleBlock(buffer)
          if (!finished) reject(new Error('报告生成流意外结束'))
        })
        .catch(reject)
    })
  },
  getWorkflowStatus(): Promise<WorkflowStatus> {
    return request<WorkflowStatus>({ url: '/workflow/status', method: 'get' })
  },
  equipmentStatus(): Promise<EquipmentStatus> {
    return request<EquipmentStatus>({ url: '/equipment/status', method: 'get' })
  },
  equipmentCaptcha(): Promise<EquipmentCaptcha> {
    return request<EquipmentCaptcha>({ url: '/equipment/captcha', method: 'get', timeout: 30000 })
  },
  equipmentLogin(payload: {
    username: string
    password: string
    captcha: string
    check_key: string
  }): Promise<EquipmentStatus> {
    return request<EquipmentStatus>({
      url: '/equipment/login',
      method: 'post',
      data: payload,
      timeout: 60000,
    })
  },
  equipmentLogout(): Promise<EquipmentStatus> {
    return request<EquipmentStatus>({ url: '/equipment/logout', method: 'post' })
  },
  equipmentRemote(params: {
    page_no?: number
    page_size?: number
    keyword?: string
    status?: string
    department?: string
  }): Promise<EquipmentRemotePage> {
    return request<EquipmentRemotePage>({
      url: '/equipment/remote',
      method: 'get',
      params,
      timeout: 60000,
    })
  },
  equipmentSync(ids: string[], all = false): Promise<{ synced: number; local_count: number }> {
    return request<{ synced: number; local_count: number }>({
      url: '/equipment/sync',
      method: 'post',
      data: { ids, all },
      timeout: 180000,
    })
  },
  equipmentLibrary(keyword = '', selectedOnly = false): Promise<{
    records: EquipmentLocal[]
    total: number
  }> {
    return request<{ records: EquipmentLocal[]; total: number }>({
      url: '/equipment/library',
      method: 'get',
      params: { keyword, selected_only: selectedOnly },
    })
  },
  equipmentSelect(ids: string[], selected = true): Promise<{ updated: number }> {
    return request<{ updated: number }>({
      url: '/equipment/library/select',
      method: 'post',
      data: { ids, selected },
    })
  },
  equipmentDelete(ids: string[]): Promise<{ deleted: number }> {
    return request<{ deleted: number }>({
      url: '/equipment/library/delete',
      method: 'post',
      data: { ids },
    })
  },

  /* ===== 14. 系统信息（对话入口 = /harness 嵌入原生 DSH） ===== */
  systemInfo(): Promise<{
    backend: string
    version: string
    agent_surface: string
    dsh_gui_url: string
    mcp_server_name: string
    architecture_doc: string
  }> {
    return request({ url: '/system/info', method: 'get' })
  },
  dshStatus(): Promise<{
    url: string
    reachable: boolean
    status: number
    auth_required: boolean
    error?: string
  }> {
    return request({ url: '/system/dsh', method: 'get' })
  },

  /* ===== 15. LLM Wiki ===== */
  wikiStatus(): Promise<WikiStatus> {
    return request<WikiStatus>({ url: '/wiki/status', method: 'get' })
  },
  wikiCategories(): Promise<WikiCategory[]> {
    return request<WikiCategory[]>({ url: '/wiki/categories', method: 'get' })
  },
  listWikiPages(params: { category?: string; query?: string; limit?: number; offset?: number } = {}): Promise<RecordList<WikiPageSummary>> {
    return request<RecordList<WikiPageSummary>>({
      url: '/wiki/pages',
      method: 'get',
      params,
    })
  },
  getWikiPage(pageId: string): Promise<WikiPage> {
    return request<WikiPage>({
      url: `/wiki/pages/${encodeURIComponent(pageId)}`,
      method: 'get',
    })
  },
  saveWikiPage(payload: {
    id?: string
    title: string
    category: string
    summary?: string
    content: string
    tags?: string[]
    detection_items?: string[]
    source?: string
  }): Promise<WikiPage> {
    return request<WikiPage>({ url: '/wiki/pages', method: 'post', data: payload })
  },
  deleteWikiPage(pageId: string): Promise<unknown> {
    return request({
      url: `/wiki/pages/${encodeURIComponent(pageId)}`,
      method: 'delete',
    })
  },
  importWiki(
    files: File[],
    category: string,
    detectionItems: string[] = [],
  ): Promise<{ imported: WikiPageSummary[]; skipped: string[]; errors: string[]; total: number }> {
    const form = new FormData()
    for (const f of files) form.append('files', f, f.name)
    form.append('category', category)
    form.append('detection_items', JSON.stringify(detectionItems))
    return request({
      url: '/wiki/import',
      method: 'post',
      data: form,
      timeout: 300000,
    })
  },
  searchWiki(payload: { question: string; top_k?: number; detection_items?: string[] }): Promise<{ items: WikiSearchHit[]; total: number; query: string }> {
    return request({
      url: '/wiki/search',
      method: 'post',
      data: payload,
    })
  },
  wikiContext(payload: { question: string; top_k?: number; detection_items?: string[] }): Promise<{ wiki: unknown[]; norms: unknown[]; text: string }> {
    return request({
      url: '/wiki/context',
      method: 'post',
      data: payload,
    })
  },

  /* ===== 16. 记录库 / 数据库状态 ===== */
  listReportRecords(params: { q?: string; project?: string; limit?: number; offset?: number } = {}): Promise<RecordList<ReportRecord>> {
    return request<RecordList<ReportRecord>>({
      url: '/records/report',
      method: 'get',
      params,
    })
  },
  listOriginalRecords(params: { q?: string; project?: string; limit?: number; offset?: number } = {}): Promise<RecordList<OriginalRecord>> {
    return request<RecordList<OriginalRecord>>({
      url: '/records/original',
      method: 'get',
      params,
    })
  },
  getReportRecord(id: string): Promise<ReportRecord> {
    return request<ReportRecord>({
      url: `/records/report/${encodeURIComponent(id)}`,
      method: 'get',
    })
  },
  getOriginalRecord(id: string): Promise<OriginalRecord> {
    return request<OriginalRecord>({
      url: `/records/original/${encodeURIComponent(id)}`,
      method: 'get',
    })
  },
  deleteReportRecord(id: string): Promise<unknown> {
    return request({
      url: `/records/report/${encodeURIComponent(id)}`,
      method: 'delete',
    })
  },
  deleteOriginalRecord(id: string): Promise<unknown> {
    return request({
      url: `/records/original/${encodeURIComponent(id)}`,
      method: 'delete',
    })
  },
  downloadOriginalSnapshot(id: string, fallbackName: string): Promise<string> {
    return download(
      `/records/original/${encodeURIComponent(id)}/snapshot`,
      fallbackName,
    )
  },
  listPersonnel(params: {
    q?: string
    role?: string
    active_only?: boolean
    limit?: number
    offset?: number
  } = {}): Promise<PersonnelList> {
    return request<PersonnelList>({ url: '/personnel', method: 'get', params })
  },
  createPersonnel(data: Partial<Personnel>): Promise<Personnel> {
    return request<Personnel>({ url: '/personnel', method: 'post', data })
  },
  updatePersonnel(id: string, data: Partial<Personnel>): Promise<Personnel> {
    return request<Personnel>({
      url: `/personnel/${encodeURIComponent(id)}`,
      method: 'put',
      data,
    })
  },
  deletePersonnel(id: string): Promise<unknown> {
    return request({ url: `/personnel/${encodeURIComponent(id)}`, method: 'delete' })
  },
  getPersonnelStatus(): Promise<PersonnelStatus> {
    return request<PersonnelStatus>({ url: '/personnel/status', method: 'get' })
  },
  importPersonnel(file: File): Promise<{
    created: number
    updated: number
    skipped: number
    total: number
    warnings: string[]
  }> {
    return request({
      url: '/personnel/import',
      method: 'post',
      data: toSingleForm(file),
    })
  },
  getLibrariesStatus(): Promise<LibraryStatus> {
    return request<LibraryStatus>({ url: '/libraries/status', method: 'get' })
  },
}
