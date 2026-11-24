<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, ChatDotRound, Delete, EditPen, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { api } from '@/api'
import type { WikiCategory, WikiPage, WikiPageSummary, WikiStatus } from '@/api/types'
import { renderMarkdown } from '@/utils/markdown'

const router = useRouter()

const status = ref<WikiStatus | null>(null)
const categories = ref<WikiCategory[]>([])
const pages = ref<WikiPageSummary[]>([])
const total = ref(0)
const loading = ref(false)
const selected = ref<WikiPage | null>(null)
const detailLoading = ref(false)
const query = ref('')
const category = ref('')

const editorVisible = ref(false)
const saving = ref(false)
const form = reactive({
  id: '',
  title: '',
  category: '未分类',
  summary: '',
  content: '',
  tagsText: '',
  itemsText: '',
})

const importVisible = ref(false)
const importing = ref(false)
const importCategory = ref('未分类')
const importItems = ref('')
const importFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement>()

const categoryOptions = computed(() => {
  const names = new Set(categories.value.map((c) => c.name))
  names.add('未分类')
  return [...names]
})

const previewHtml = computed(() => renderMarkdown(form.content))

async function loadStatus() {
  try {
    status.value = await api.wikiStatus()
  } catch {
    /* api 层已提示 */
  }
}

async function loadCategories() {
  try {
    categories.value = await api.wikiCategories()
  } catch {
    /* api 层已提示 */
  }
}

async function loadPages() {
  loading.value = true
  try {
    const data = await api.listWikiPages({
      category: category.value,
      query: query.value.trim(),
      limit: 200,
    })
    pages.value = data.items
    total.value = data.total
    const currentId = selected.value?.id
    if (!pages.value.some((p) => p.id === currentId)) {
      if (pages.value.length) {
        await openPage(pages.value[0].id)
      } else {
        selected.value = null
      }
    }
  } catch {
    /* api 层已提示 */
  } finally {
    loading.value = false
  }
}

async function openPage(id: string) {
  detailLoading.value = true
  try {
    selected.value = await api.getWikiPage(id)
  } catch {
    /* api 层已提示 */
  } finally {
    detailLoading.value = false
  }
}

function selectCategory(name: string) {
  category.value = category.value === name ? '' : name
  void loadPages()
}

function onSearch() {
  void loadPages()
}

function openNew() {
  form.id = ''
  form.title = ''
  form.category = category.value || '未分类'
  form.summary = ''
  form.content = ''
  form.tagsText = ''
  form.itemsText = ''
  editorVisible.value = true
}

function openEdit() {
  if (!selected.value) return
  form.id = selected.value.id
  form.title = selected.value.title
  form.category = selected.value.category
  form.summary = selected.value.summary
  form.content = selected.value.content
  form.tagsText = (selected.value.tags || []).join('、')
  form.itemsText = (selected.value.detection_items || []).join('、')
  editorVisible.value = true
}

function splitList(text: string): string[] {
  return String(text || '')
    .split(/[、,，;；\n]/)
    .map((x) => x.trim())
    .filter(Boolean)
}

async function savePage() {
  if (!form.title.trim()) {
    ElMessage.warning('请填写页面标题')
    return
  }
  if (!form.content.trim()) {
    ElMessage.warning('请填写页面正文')
    return
  }
  saving.value = true
  try {
    const saved = await api.saveWikiPage({
      id: form.id || undefined,
      title: form.title.trim(),
      category: form.category.trim() || '未分类',
      summary: form.summary.trim(),
      content: form.content,
      tags: splitList(form.tagsText),
      detection_items: splitList(form.itemsText),
    })
    selected.value = saved
    editorVisible.value = false
    ElMessage.success('知识库页面已保存')
    await Promise.all([loadStatus(), loadCategories(), loadPages()])
  } catch {
    /* api 层已提示 */
  } finally {
    saving.value = false
  }
}

async function deletePage() {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除 Wiki 页面《${selected.value.title}》吗？此操作不可恢复。`,
      '删除页面',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.deleteWikiPage(selected.value.id)
    selected.value = null
    ElMessage.success('页面已删除')
    await Promise.all([loadStatus(), loadCategories(), loadPages()])
  } catch {
    /* api 层已提示 */
  }
}

function pickFiles() {
  fileInput.value?.click()
}

function onFilesChange(event: Event) {
  const input = event.target as HTMLInputElement
  importFiles.value = Array.from(input.files ?? [])
  input.value = ''
}

function openImport() {
  importFiles.value = []
  importCategory.value = category.value || '未分类'
  importItems.value = ''
  importVisible.value = true
}

async function doImport() {
  if (!importFiles.value.length) {
    ElMessage.warning('请选择 .md / .txt / .docx 知识文件')
    return
  }
  importing.value = true
  try {
    const result = await api.importWiki(
      importFiles.value,
      importCategory.value || '未分类',
      splitList(importItems.value),
    )
    const parts = [`导入 ${result.total} 个页面`]
    if (result.skipped.length) parts.push(`跳过 ${result.skipped.length} 个`)
    if (result.errors.length) parts.push(`${result.errors.length} 个失败`)
    ElMessage.success(parts.join('，'))
    importVisible.value = false
    await Promise.all([loadStatus(), loadCategories(), loadPages()])
  } catch {
    /* api 层已提示 */
  } finally {
    importing.value = false
  }
}

function askHarness(question: string) {
  router.push({ path: '/harness', query: { ask: question } })
}

function formatTime(value?: string): string {
  return value ? value.slice(0, 16) : ''
}

onMounted(async () => {
  await Promise.all([loadStatus(), loadCategories()])
  await loadPages()
})
</script>

<template>
  <div class="wiki-view">
    <header class="page-header">
      <div class="page-title">
        <el-button :icon="Back" text @click="router.push('/library')">返回资料库</el-button>
        <h2>LLM Wiki 知识库</h2>
        <el-tag v-if="status" type="success" size="small">{{ status.pages }} 页</el-tag>
        <el-tag v-if="status" type="info" size="small" effect="plain">{{ status.categories }} 个分类</el-tag>
      </div>
      <div class="page-actions">
        <el-input
          v-model="query"
          size="small"
          clearable
          placeholder="搜索页面标题 / 正文 / 标签"
          :prefix-icon="Search"
          class="search-input"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-button size="small" :icon="Refresh" :loading="loading" @click="loadPages">刷新</el-button>
        <el-button size="small" :icon="Search" @click="onSearch">搜索</el-button>
        <el-button size="small" :icon="Upload" @click="openImport">导入知识</el-button>
        <el-button size="small" type="primary" :icon="Plus" @click="openNew">新建页面</el-button>
      </div>
    </header>

    <div class="wiki-body">
      <aside class="category-pane">
        <div class="pane-title">分类</div>
        <div
          class="category-item"
          :class="{ active: !category }"
          @click="selectCategory('')"
        >
          <span>全部</span>
          <span class="category-count">{{ total }}</span>
        </div>
        <div
          v-for="item in categories"
          :key="item.name"
          class="category-item"
          :class="{ active: category === item.name }"
          @click="selectCategory(item.name)"
        >
          <span>{{ item.name }}</span>
          <span class="category-count">{{ item.count }}</span>
        </div>
        <div v-if="status" class="db-hint">
          <div class="db-hint-title">知识库数据库</div>
          <div class="db-hint-path">{{ status.db_path }}</div>
        </div>
      </aside>

      <section class="list-pane">
        <div class="pane-title">
          <span>页面</span>
          <span class="pane-sub">{{ pages.length }} / {{ total }}</span>
        </div>
        <el-scrollbar class="list-scroll">
          <el-empty v-if="!pages.length && !loading" :image-size="60" description="暂无页面" />
          <div
            v-for="page in pages"
            :key="page.id"
            class="page-item"
            :class="{ active: selected?.id === page.id }"
            @click="openPage(page.id)"
          >
            <div class="page-item-title">{{ page.title }}</div>
            <div class="page-item-summary">{{ page.summary || '（无摘要）' }}</div>
            <div class="page-item-meta">
              <el-tag size="small" effect="plain">{{ page.category }}</el-tag>
              <span v-if="page.builtin" class="builtin-tag">内置</span>
              <span class="page-time">{{ formatTime(page.updated_at) }}</span>
            </div>
          </div>
        </el-scrollbar>
      </section>

      <section class="detail-pane" v-loading="detailLoading">
        <el-empty
          v-if="!selected"
          :image-size="80"
          description="选择左侧页面查看内容，或新建/导入知识"
        >
          <el-button type="primary" :icon="ChatDotRound" @click="askHarness('知识库里有哪些检测方法和操作步骤？')">
            让 Harness 回答
          </el-button>
        </el-empty>
        <template v-else>
          <div class="detail-head">
            <div>
              <h3>{{ selected.title }}</h3>
              <div class="detail-meta">
                <el-tag size="small" effect="plain">{{ selected.category }}</el-tag>
                <el-tag v-if="selected.builtin" size="small" type="info">内置</el-tag>
                <span v-for="tag in selected.tags" :key="tag" class="tag-chip">#{{ tag }}</span>
                <span class="detail-time">更新于 {{ formatTime(selected.updated_at) }}</span>
              </div>
            </div>
            <div class="detail-actions">
              <el-button size="small" :icon="ChatDotRound" @click="askHarness(`请解释知识库《${selected.title}》的内容要点`)">
                问 Harness
              </el-button>
              <el-button size="small" :icon="EditPen" @click="openEdit">编辑</el-button>
              <el-button size="small" type="danger" plain :icon="Delete" @click="deletePage">删除</el-button>
            </div>
          </div>
          <div v-if="selected.summary" class="detail-summary">{{ selected.summary }}</div>
          <div class="markdown-body" v-html="renderMarkdown(selected.content)" />
        </template>
      </section>
    </div>

    <el-dialog
      v-model="editorVisible"
      :title="form.id ? '编辑知识页面' : '新建知识页面'"
      width="min(920px, 92vw)"
      :close-on-click-modal="false"
    >
      <el-form label-width="92px" class="editor-form">
        <el-row :gutter="12">
          <el-col :span="14">
            <el-form-item label="标题">
              <el-input v-model="form.title" placeholder="如：回弹法测区布置要求" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="分类">
              <el-select v-model="form.category" filterable allow-create default-first-option style="width: 100%">
                <el-option v-for="name in categoryOptions" :key="name" :label="name" :value="name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" placeholder="一句话说明页面内容" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="标签">
              <el-input v-model="form.tagsText" placeholder="用顿号或逗号分隔，如：回弹法、测区" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="检测项目">
              <el-input v-model="form.itemsText" placeholder="如：回弹法检测、钻芯法检测" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="正文 Markdown">
              <el-input v-model="form.content" type="textarea" :rows="18" placeholder="# 标题&#10;&#10;正文…" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <div class="preview-label">预览</div>
            <div class="markdown-body preview-body" v-html="previewHtml" />
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePage">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="导入知识文件" width="560px">
      <el-form label-width="92px">
        <el-form-item label="文件">
          <input ref="fileInput" type="file" multiple accept=".md,.markdown,.txt,.docx" hidden @change="onFilesChange" />
          <el-button :icon="Upload" @click="pickFiles">选择文件</el-button>
          <span class="import-files">{{ importFiles.length ? `${importFiles.length} 个文件` : '支持 .md / .txt / .docx' }}</span>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="importCategory" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="name in categoryOptions" :key="name" :label="name" :value="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="检测项目">
          <el-input v-model="importItems" placeholder="可选，如：回弹法检测、钻芯法检测" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.wiki-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 14px 16px 16px;
  gap: 10px;
  overflow: hidden;
}
.page-header {
  flex: none;
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
  font-size: 18px;
}
.page-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.search-input {
  width: 240px;
}
.wiki-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 200px 330px minmax(0, 1fr);
  gap: 10px;
}
.category-pane,
.list-pane,
.detail-pane {
  min-height: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.category-pane {
  padding: 8px;
}
.pane-title {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.pane-sub {
  font-weight: 400;
  color: var(--el-text-color-placeholder);
}
.category-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 9px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 12.5px;
  color: var(--el-text-color-regular);
}
.category-item:hover {
  background: var(--el-fill-color-light);
}
.category-item.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.category-count {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.db-hint {
  margin-top: auto;
  padding: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
  font-size: 10.5px;
  color: var(--el-text-color-secondary);
}
.db-hint-title {
  font-weight: 600;
  margin-bottom: 3px;
}
.db-hint-path {
  word-break: break-all;
  line-height: 1.5;
}
.list-scroll {
  flex: 1;
  min-height: 0;
  padding: 2px 8px 8px;
}
.page-item {
  padding: 8px 9px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
}
.page-item:hover {
  background: var(--el-fill-color-light);
}
.page-item.active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.page-item-title {
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.page-item-summary {
  margin: 3px 0 5px;
  color: var(--el-text-color-secondary);
  font-size: 11.5px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.page-item-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  color: var(--el-text-color-secondary);
}
.builtin-tag {
  color: var(--el-color-warning);
}
.page-time {
  margin-left: auto;
}
.detail-pane {
  padding: 14px 18px;
  overflow: auto;
}
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.detail-head h3 {
  margin: 0 0 6px;
  font-size: 18px;
}
.detail-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}
.detail-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.tag-chip {
  color: var(--el-color-primary);
}
.detail-time {
  margin-left: 4px;
}
.detail-summary {
  margin: 10px 0;
  padding: 8px 10px;
  border-radius: 7px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  font-size: 12.5px;
  line-height: 1.6;
}
.markdown-body {
  font-size: 13.5px;
  line-height: 1.85;
  color: var(--el-text-color-regular);
  word-break: break-word;
}
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  color: var(--el-text-color-primary);
  margin: 14px 0 6px;
}
.markdown-body :deep(h2) { font-size: 19px; }
.markdown-body :deep(h3) { font-size: 16px; }
.markdown-body :deep(h4) { font-size: 14px; }
.markdown-body :deep(p) { margin: 6px 0; }
.markdown-body :deep(ul) { padding-left: 22px; }
.markdown-body :deep(li) { margin: 3px 0; }
.markdown-body :deep(code) {
  background: var(--el-fill-color-light);
  padding: 1px 4px;
  border-radius: 4px;
  font-family: Consolas, monospace;
  font-size: 12px;
}
.markdown-body :deep(.wiki-code) {
  background: #0f1720;
  color: #d7e3ee;
  padding: 10px 12px;
  border-radius: 7px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
}

.markdown-body :deep(.wiki-code code) {
  background: transparent;
  color: inherit;
  padding: 0;
}
.preview-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.preview-body {
  height: 380px;
  overflow: auto;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12.5px;
}
.editor-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
.import-files {
  margin-left: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
@media (max-width: 1100px) {
  .wiki-body {
    grid-template-columns: 170px 280px minmax(0, 1fr);
  }
}
@media (max-width: 820px) {
  .wiki-body {
    grid-template-columns: 1fr;
    grid-template-rows: auto 220px minmax(0, 1fr);
  }
  .category-pane {
    max-height: 160px;
    overflow: auto;
  }
  .search-input {
    width: 180px;
  }
}
</style>
