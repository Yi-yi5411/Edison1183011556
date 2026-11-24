/**
 * API 数据类型定义 —— 依据 webapp/API_CONTRACT.md
 * 后端统一响应：{ ok: boolean, data: T, message: string }
 */

/** 工作表列定义（插件与工作表共用） */
export interface ColumnDef {
  key: string
  label: string
  /** text | number | int | ... */
  type?: string
  width?: number
  /** false = 只读计算列 */
  editable?: boolean
  /** 是否为后端自动计算列 */
  calc?: boolean
  /** 插件列所属检测项目（/api/plugins 返回） */
  sub_item?: string
}

/** 检测插件（一个检测项目） */
export interface PluginInfo {
  id: string
  name: string
  structure_type: string
  /** 同结构类型内的菜单排序 */
  tree_order?: number
  requires_setup: boolean
  columns: ColumnDef[]
  calc_rules?: Record<string, unknown>
  /** 勾选时需要参数设置的检测项目名（如钻芯法检测） */
  setup_items?: string[]
  /** 检测项目树目录：{项目名: [构件,...]} */
  tree?: Record<string, string[]>
  /** 子检测项分组 [{name, columns}] */
  sub_items?: { name: string; columns: string[] }[]
  /** builtin / external */
  source?: string
  external?: boolean
}

/** 单元格值 */
export type CellValue = string | number | null

/** 行数据（后端存储形态：按列顺序的数组） */
export type SheetRow = CellValue[]

/** 后端可能返回对象形态的行（容错） */
export type SheetRowLike = SheetRow | Record<string, CellValue>

/** 合并区域（行列索引由后端给定） */
export interface MergeRange {
  start_row: number
  end_row: number
  start_col: number
  end_col: number
}

/** 工作表数据 */
export interface SheetData {
  columns: ColumnDef[] | string[]
  /** 基础检测项目名（如“回弹法检测(主要来源为仪器数据，可选用)”），用于原始记录模板匹配 */
  base_item?: string
  component?: string | null
  rows: SheetRowLike[]
  merges: MergeRange[]
  params?: Record<string, unknown>
  assessment?: {
    options?: AssessmentOptions
    result?: AssessmentResult | null
  }
}

/* ===== 检测评定 ===== */

export interface AssessmentField {
  key: string
  label: string
  type?: string
  required?: boolean
  note?: string
}

export interface AssessmentSpec {
  id: string
  name: string
  family: string
  implemented: boolean
  needs_raw_input: boolean
  component_label?: string
  project_label?: string
  base_items?: string[]
  required_fields?: AssessmentField[]
  thresholds?: Record<string, unknown>
  description?: string
  [key: string]: unknown
}

export interface AssessmentOptions {
  no_drawing?: boolean
  table_no?: string
  include_component_stats?: boolean
}

export interface AssessmentResult {
  ok: boolean
  sheet_key?: string
  base_item?: string
  spec_id?: string
  family?: string
  conclusion_type?: string
  conclusion?: string
  errors?: string[]
  warnings?: string[]
  summary?: Record<string, unknown>
  details?: Record<string, unknown>[]
  [key: string]: unknown
}

/* ===== 应用内智能助手 ===== */

export interface AgentToolCall {
  name: string
  arguments: Record<string, unknown>
  result: {
    ok?: boolean
    data?: unknown
    message?: string
    requires_confirmation?: boolean
  }
  write?: boolean
}

export interface AgentChatResult {
  reply: string
  tool_calls: AgentToolCall[]
  model?: string
  rounds?: number
  error?: boolean
}

export interface AgentStatus {
  api_base: string
  ollama_base_url: string
  model: string
  model_configured: boolean
  model_reachable: boolean
  backend_ok: boolean
  note?: string
  tool_count: number
}

export interface AssessmentDetail {
  sheet_key: string
  base_item: string
  component?: string | null
  spec: AssessmentSpec
  options: AssessmentOptions
  input?: Record<string, unknown> | null
  result?: AssessmentResult | null
  columns: string[]
  row_count: number
}

/** 报告/原始记录模板选择（随项目保存） */
export interface TemplateSelection {
  report_template_id: string
  original_template_map: Record<string, string>
}

/** 项目数据（GET /api/project） */
export interface ProjectData {
  project_name: string
  checked_items: string[]
  sheets: Record<string, SheetData>
  report_info?: ReportInfo
  template_selection?: TemplateSelection
  autosave?: {
    enabled: boolean
    autosaved_at?: string | null
    restored?: boolean
  }
}

/** 历史工程条目（GET /api/project/history） */
export interface ProjectHistoryItem {
  filepath: string
  name: string
  source: string
  modified: string
  size_kb: number
  checked_count: number
  sheet_count: number
}

/** 报告抬头（11 字段，键值对；容忍后端扩展字段） */
export type ReportInfo = Record<string, string>

export interface ReportAutoContent {
  sheet_key: string
  item: string
  component: string
  rows: number
  columns?: string[]
  status?: string
  conclusion?: string
}

export interface ReportAutoInfo {
  report_info: ReportInfo
  overview_template: string
  template: { id: string; name: string; auto: boolean }
  basis: string[]
  equipment: Array<Record<string, string>>
  content: ReportAutoContent[]
  content_text: string
  results: ReportAutoContent[]
  counts: { checked: number; filled: number; assessed: number; items?: number }
  warnings: string[]
  missing: string[]
}

/** 报告生成结果（POST /api/report/generate） */
export interface ReportGenerateResult {
  filepath: string
  engine: 'agent' | 'direct'
  /** 数据表数量（后端可能返回数组），展示时统一格式化 */
  tables?: number | string[]
  skipped?: number
  warnings?: string[]
  model?: string
  fallback_reason?: string
  template_id?: string
  template_name?: string
  record_id?: string | null
  draft?: boolean
  skipped_items?: Array<{ sheet_key: string; reason: string }>
}

/** 报告生成任务参数 */
export interface ReportGeneratePayload {
  output_path?: string
  template_id?: string
  /** 草稿：只生成数据、模板、评定都就绪的检测项 */
  draft?: boolean
  /** 措辞覆盖：overview 字符串 / basis 字符串数组 / conclusions 带编号结论句 */
  narrative?: {
    overview?: string
    basis?: string[]
    conclusions?: string[]
  }
}

/** 报告生成历史条目 */
/** 采集文件识别候选（GET /api/ingest/recognize） */
export interface IngestParamSpec {
  key: string
  label?: string
  type?: 'string' | 'int' | 'float' | 'bool' | 'enum'
  required?: boolean
  default?: unknown
  options?: unknown[]
  note?: string
  min?: number
  max?: number
}

export interface IngestCandidate {
  item: string
  structure_type: string
  sheet_key: string
  component: string
  component_guess: string
  matched: number
  total_columns: number
  score: number
  header_index: number
  missing_columns: string[]
  requires_setup: boolean
  param_specs: IngestParamSpec[]
  components?: string[]
  sheet_keys?: string[]
}

export interface IngestRecognizeResult {
  filepath: string
  format: string
  kind: 'table' | 'scan' | 'knowledge'
  converted_from: string
  warnings: string[]
  table?: { rows: number; columns: number; sheet_name: string }
  header?: string[]
  preview?: string[][]
  candidates?: IngestCandidate[]
  suggested_sheet_key?: string
  assessment_family?: string
  preview_text?: string
  next?: { tool: string; hint: string }
}

export interface IngestImportResult {
  sheet_key: string
  imported: number
  matched_columns: number
  rows: number
  merges: unknown[]
  recalc_error: string
  warnings: string[]
  requires_setup: boolean
  assessment: AssessmentResult | null
  ready: boolean
}

export interface ReportHistoryItem {
  id?: string
  filepath: string
  report_no?: string
  engine: 'agent' | 'direct'
  tables?: number | string[]
  skipped?: number
  warnings?: string[]
  model?: string
  fallback_reason?: string
  template_id?: string
  template_name?: string
  project_name?: string
  generated_at: string
  /** 后端视图附加：文件是否仍存在 */
  exists: boolean
}

/* ===== 模板库 ===== */

/** 报告模板摘要 */
export interface ReportTemplateInfo {
  id: string
  name: string
  description?: string
  builtin: boolean
  is_default: boolean
  available: boolean
  missing?: string[]
  chapter_count?: number
  table_count?: number
  created_at?: string
  updated_at?: string
  manifest?: Record<string, unknown>
}

/** 原始记录模板 */
export interface OriginalTemplateInfo {
  id: string
  name: string
  code?: string
  engine: 'native_docx' | 'docx_import' | 'doc_archive'
  fillable: boolean
  available: boolean
  builtin: boolean
  detection_items: string[]
  default_for: string[]
  reference_doc?: string
  reference_available?: boolean
  config?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

export interface OriginalTemplateList {
  templates: OriginalTemplateInfo[]
  defaults: Record<string, string>
}

/* ===== 原始记录生成 ===== */

export interface OriginalRecordFile {
  sheet_key: string
  template_id: string
  template_name: string
  filepath: string
  warnings: string[]
  record_id?: string | null
}

export interface OriginalRecordResult {
  files: OriginalRecordFile[]
  warnings: string[]
}

export interface OriginalRecordHistoryItem {
  id?: string
  filepath: string
  sheet_key: string
  base_item?: string
  template_id: string
  template_name: string
  rows: number
  project_name?: string
  generated_at: string
  exists: boolean
  has_snapshot?: boolean
}

/* ===== 报告修改 ===== */

export interface DocParagraph {
  index: number
  text: string
  style?: string
  heading?: boolean
  alignment?: string
  size?: number | null
  bold?: boolean | null
}

export interface DocCell {
  row: number
  col: number
  text: string
  colspan?: number
  rowspan?: number
  merged?: boolean
}

export interface DocTable {
  index: number
  rows: DocCell[][]
}

export interface DocBlock {
  type: 'paragraph' | 'table'
  index: number
}

export interface ReportDocument {
  filepath: string
  filename: string
  size: number
  modified_at: string
  paragraphs: DocParagraph[]
  tables: DocTable[]
  blocks: DocBlock[]
  paragraph_count: number
  table_count: number
}

export interface SaveReportDocumentPayload {
  filepath: string
  paragraphs?: { index: number; text: string }[]
  cells?: { table: number; row: number; col: number; text: string }[]
  output_path?: string
  overwrite?: boolean
}

export interface SaveReportDocumentResult {
  filepath: string
  saved: boolean
  changed_paragraphs?: number
  changed_cells?: number
  replacements?: number
  backup?: string
  message?: string
}

/* ===== 规范问答 ===== */

/** 规范清单条目（GET /api/normqa/status 的 codes） */
export interface NormCodeStat {
  code: string
  code_name: string
  count: number
}

export interface NormQaStatus {
  total: number
  codes: NormCodeStat[]
  db_path?: string
  exists?: boolean
}

export interface NormQaImportResult {
  total: number
  imported: number
  files: string[]
}

/** 规范条文（clauses 表行：id/code/code_name/chapter/title/body/...） */
export interface NormClause {
  id?: number
  code: string
  code_name?: string
  chapter: string
  title: string
  body: string
  category?: string
  chapter_path?: string
  source_file?: string
  score?: number
  [key: string]: unknown
}

/** 术语候选（未命中时给出，term 可点击重查） */
export interface NormCandidate {
  term: string
  count: number
  label?: string
}

export interface NormQaQueryResult {
  type: 'exact' | 'search' | 'candidates' | 'empty'
  clauses?: NormClause[]
  candidates?: NormCandidate[]
  query?: string
}

export interface NormQaExplainResult {
  answer: string
}

/* ===== 批量审查 ===== */

/** 审查候选意见（与后端 extract_candidates/export_review_docx 键名一一对应） */
export interface ReviewCandidate {
  location?: string
  excerpt?: string
  category?: string
  description?: string
  suggestion?: string
  basis?: string
  [key: string]: unknown
}

export interface ReviewRunResult {
  candidates: ReviewCandidate[]
  chunks: number
  files: string[]
  model?: string
}

/* ===== 扫描识别 ===== */

/** 单文件识别结果（POST /api/scan/run 的 files 元素） */
export interface ScanFileResult {
  filename: string
  error?: string
  doc_id?: string | number
  detection_item?: string
  sub_item?: string
  /** 对齐后的列头（识别目标检测项目的列） */
  columns: string[]
  /** 对齐行 [[单元格,...], ...]，可直接作为 scan/fill 的 records */
  rows: SheetRow[]
  structured?: Record<string, unknown>[]
  normalized?: Record<string, unknown>[]
  field_warnings: string[]
  classification?: unknown
  repair?: unknown
  ocr_stats?: Record<string, unknown>
  [key: string]: unknown
}

export interface ScanRunResult {
  files: ScanFileResult[]
  field_warnings: string[]
}

/** 识别历史记录（GET /api/scan/history） */
export interface ScanHistoryItem {
  id?: string | number
  detection_item?: string
  sub_item?: string
  source_path?: string
  stored_path?: string
  created_at?: string
  status?: string
  [key: string]: unknown
}


/** 异步扫描识别作业（POST /api/scan/submit、GET /api/scan/job/{id}） */
export interface ScanJobResult {
  detection_item?: string
  sub_item?: string
  columns?: string[]
  rows?: SheetRow[]
  field_warnings?: string[]
  classification?: {
    sub_item?: string
    confidence?: number
    candidates?: string[]
    mode?: string
    raw_reply?: string
  }
  repair?: unknown
  ocr_stats?: Record<string, unknown>
  [key: string]: unknown
}

export interface ScanJob {
  id: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'interrupted'
  filepath?: string
  detection_item?: string
  submitted_at?: string
  finished_at?: string
  error?: string
  duration_ms?: number
  result?: ScanJobResult
}

/** 一个可写入的采集工作表（GET /api/scan/targets） */
export interface ScanTarget {
  sheet_key: string
  component?: string
  columns: string[]
  exists: boolean
  rows: number
  checked: boolean
}

/** 扫描识别出的检测项目与目标表候选 */
export interface ScanPlan {
  detection_item: string
  input_item?: string
  components: string[]
  requires_setup: boolean
  param_specs: IngestParamSpec[]
  columns: string[]
  candidates: string[]
  targets: ScanTarget[]
  suggested_sheet_key: string
}

/** 扫描结果写入工程的返回（POST /api/scan/commit） */
export interface ScanCommitResult {
  sheet_key: string
  imported: number
  rows: number
  matched_columns: number
  target_columns: string[]
  merges?: unknown[]
  recalc_error?: string
  warnings?: string[]
  requires_setup?: boolean
  assessment?: {
    ok?: boolean
    conclusion?: string
    errors?: string[]
    warnings?: string[]
    [key: string]: unknown
  } | null
  ready: boolean
  checked_items: string[]
}

/** 视觉模型列表（GET /api/scan/vision_models） */
export interface VisionModelsResult {
  models: string[]
  base_url: string
}

/* ===== 配置 ===== */

export type AppConfigData = Record<string, Record<string, unknown>>


/* ===== 设备库（对接设备管理系统） ===== */

export interface EquipmentStatus {
  base_url: string
  username: string
  logged_in: boolean
  expires_at: string
  local_count: number
}

export interface EquipmentCaptcha {
  key: string
  image: string
}

/** 设备管理系统原始记录（字段随接口返回，常用字段如下） */
export interface EquipmentRemoteRecord {
  id: string
  equipmentName?: string
  equipmentId1?: string
  equipmentId2?: string
  equipmentId3?: string
  equipmentId5_dictText?: string
  equipmentType1?: string
  equipmentManufactor?: string
  code?: string
  codeone?: string
  codetwo?: string
  equipmentDate?: string
  equipmentPlace?: string
  equipmentPlace2_dictText?: string
  codes?: string
  [key: string]: unknown
}

export interface EquipmentRemotePage {
  records: EquipmentRemoteRecord[]
  total: number
  page_no: number
  page_size: number
}

/** 本地设备库记录 */
export interface EquipmentLocal {
  id: string
  remote_id: string
  name: string
  category_code: string
  cert_no: string
  last_check_date: string
  next_check_date: string
  model: string
  manufacturer: string
  status: string
  owner: string
  department: string
  location: string
  selected: boolean
  synced_at?: string
  [key: string]: unknown
}


/** 报告流式生成事件（SSE） */
export interface ReportStreamEvent {
  event: 'log' | 'result' | 'error' | 'done'
  data: Record<string, unknown>
}


/** 检测流程总览 */
export interface WorkflowStep {
  key: string
  title: string
  status: 'done' | 'progress' | 'pending' | 'ready'
  detail: string
  route: string
}

export interface WorkflowStatus {
  project_name: string
  checked_count: number
  filled_count: number
  total_rows: number
  assessed_count: number
  equipment_count: number
  template_name: string
  report_ready: boolean
  done_count: number
  total_steps: number
  steps: WorkflowStep[]
  next_step: WorkflowStep
  report_dir: string
}

/* ===== Harness 会话 ===== */

export type HarnessEventType =
  | 'boot'
  | 'message'
  | 'tool_call'
  | 'tool_result'
  | 'intent'
  | 'navigation'
  | 'artifact'
  | 'assistant'
  | 'task'
  | 'agent'
  | 'error'
  | 'done'

export interface HarnessIntent {
  category: string
  items: string[]
  components: string[]
  sheet_keys: string[]
  next_page: string
  confidence: number
  reason?: string
  summary: string
  source?: string
}

export interface HarnessNavigation {
  route: string
  label: string
  sheet_keys: string[]
  category: string
  auto: boolean
}

export interface HarnessToolCallLog {
  call_id: string
  name: string
  arguments: Record<string, unknown>
  ok: boolean
  summary: string
  write: boolean
  stage: string
  simulated: boolean
  duration_ms: number
}

export interface HarnessMessage {
  id: number
  session_id: string
  turn_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_calls: Record<string, unknown>[]
  meta: Record<string, unknown>
  created_at: string
}

export interface HarnessSession {
  id: string
  title: string
  mode: string
  status: string
  provider: string
  model: string
  project_name: string
  intent: HarnessIntent | Record<string, never>
  context: Record<string, unknown>
  current_stage: string
  current_route: string
  boot_done: boolean
  created_at: string
  updated_at: string
  last_active_at: string
}

export interface HarnessEvent {
  id: number
  session_id: string
  seq: number
  turn_id: string
  type: HarnessEventType
  stage: string
  tool_name: string
  payload: Record<string, unknown>
  created_at: string
}

export interface HarnessStage {
  key: string
  title: string
}

export interface HarnessSessionDetail {
  session: HarnessSession
  messages: HarnessMessage[]
  events: HarnessEvent[]
  stages?: HarnessStage[]
}

export interface HarnessUploadTable {
  name: string
  columns: string[]
  rows: Record<string, string>[]
  row_count: number
  preview: Record<string, string>[]
  truncated: boolean
}

export interface HarnessUploadedFile {
  file_id: string
  filename: string
  kind: 'excel' | 'csv' | 'word'
  table_count: number
  row_count: number
  summary: string
  tables: HarnessUploadTable[]
}

export interface HarnessUploadResult {
  message: HarnessMessage
  files: HarnessUploadedFile[]
  warnings: string[]
}

export interface HarnessStatus {
  available: boolean
  mode: 'llm' | 'rules'
  provider: string
  base_url: string
  model: string
  note: string
  tools_supported: boolean
  checked_at: string
  wiki_pages: number
  tool_count: number
  db_tool_count?: number
  sessions?: number
  runtime?: 'dsh' | 'python'
  dsh_available?: boolean
}

export interface HarnessChatResult {
  reply: string
  intent: HarnessIntent | Record<string, never>
  navigation: HarnessNavigation | null
  tool_calls: HarnessToolCallLog[]
  events: HarnessEvent[]
  model: string
  provider: string
  rounds: number
  error: boolean
  simulated: boolean
  cancelled?: boolean
}

export interface HarnessStreamEvent {
  event: string
  data: Record<string, unknown>
}

/* ===== LLM Wiki ===== */

export interface WikiPageSummary {
  id: string
  slug?: string
  title: string
  category: string
  summary: string
  tags: string[]
  detection_items: string[]
  source?: string
  builtin: boolean
  created_at?: string
  updated_at?: string
}

export interface WikiPage extends WikiPageSummary {
  content: string
  revision_count?: number
}

export interface WikiStatus {
  pages: number
  categories: number
  db_path: string
  exists: boolean
  seed_version?: number
}

export interface WikiCategory {
  name: string
  count: number
}

export interface WikiSearchHit {
  id: string
  title: string
  category: string
  summary: string
  snippet: string
  score: number
}

/* ===== 记录库 / 数据库状态 ===== */

export interface ReportRecord {
  id: string
  report_no: string
  project_name: string
  filepath: string
  filename: string
  engine: string
  template_id: string
  template_name: string
  tables: unknown
  skipped: unknown[]
  warnings: string[]
  model?: string
  fallback_reason?: string
  report_info?: Record<string, string>
  assessment_results?: Record<string, unknown>
  assessed_count: number
  file_size: number
  generated_at: string
  created_at: string
  exists: boolean
}

export interface OriginalRecord {
  id: string
  sheet_key: string
  base_item: string
  template_id: string
  template_name: string
  project_name: string
  filepath: string
  filename: string
  rows_count: number
  warnings: string[]
  has_snapshot: boolean
  snapshot_size: number
  generated_at: string
  created_at: string
  exists: boolean
}

export interface RecordList<T> {
  items: T[]
  total: number
}

export interface RecordsStats {
  report: { total: number; this_month: number }
  original: { total: number; this_month: number; with_snapshot: number }
  latest: string
  db_path: string
}

export interface Personnel {
  id: string
  name: string
  role: string
  cert_no: string
  phone: string
  organization: string
  note: string
  active: boolean
  created_at: string
  updated_at: string
}

export interface PersonnelList {
  items: Personnel[]
  total: number
}

export interface PersonnelStatus {
  total: number
  active: number
  roles: Record<string, number>
  db_path: string
  error?: string
}

export interface LibraryStatus {
  project: {
    name: string
    checked_items: number
    filled_items: number
    total_rows: number
    assessed_items: number
    autosave_path: string
  }
  templates: {
    report_templates: number
    original_templates: number
    default_report_template: string
    db_path: string
    error?: string
  }
  equipment: { total: number; selected: number; db_path: string; error?: string }
  records: RecordsStats & { error?: string }
  wiki: WikiStatus & { error?: string }
  personnel: PersonnelStatus
  norms: { total: number; codes: number; db_path: string; error?: string }
}


/* ===== 外部插件 ===== */

export interface ExternalPluginRecord {
  id: string
  name: string
  source: string
  status: 'loaded' | 'error' | 'missing' | string
  root: string
  path: string
  errors?: string[]
  warnings?: string[]
}

export interface ExternalPluginStatus {
  roots: string[]
  records: ExternalPluginRecord[]
  loaded: number
  errors: number
}


/* ===== DSH 原生能力 ===== */

export interface DshCapability {
  key: string
  title: string
  module: string
  desc: string
  surface: string
  available: boolean
  source: string
  note: string
}

export interface DshProfile {
  id: string
  name: string
  path: string
  exists: boolean
  bundles: string[]
  dependencies: Record<string, string>
  cordis_path: string
  cordis_exists: boolean
}

export interface DshPluginsStatus {
  gui_url: string
  profiles: DshProfile[]
  bundles: string[]
  capabilities: DshCapability[]
  plugin_dir: string
  market_hint: string
  agent_surface: string
}


/* ===== DSH Host API ===== */

export interface DshHostStatus {
  base_url: string
  token_configured: boolean
  authed: boolean
  last_error?: string
}

export interface DshMarketIndex {
  url: string
  title?: string | Record<string, string>
  description?: string | Record<string, string>
  error?: string
}

export interface DshBundle {
  name: string
  version?: string
  enabled?: boolean
  installed?: boolean
  official?: boolean
  optional?: boolean
  removable?: boolean
  availability?: string
  description?: string
  [key: string]: any
}

export interface DshSearchResult {
  total?: number
  plugins?: any[]
  [key: string]: any
}
