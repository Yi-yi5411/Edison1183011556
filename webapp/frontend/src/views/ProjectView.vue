<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import MainLayout from '@/layouts/MainLayout.vue'
import SheetView from '@/components/SheetView.vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const route = useRoute()

const lastSheetNotice = ref('')

/** Harness 意图跳转：/project?sheet=项目（构件） → 定位工作表 */
function applySheetFromQuery() {
  const key = String(route.query.sheet || '').trim()
  if (!key) return
  // 项目尚未加载完成时不要提前提示“未勾选”
  if (!store.initialized || !store.projectVersion) return
  if (store.checkedItems.includes(key)) {
    store.activeTab = key
    return
  }
  if (lastSheetNotice.value === key) return
  lastSheetNotice.value = key
  ElMessage.info(`「${key}」尚未勾选，请点击顶部“检测项目”按钮勾选后再录入数据`)
}

watch(
  [() => route.query.sheet, () => store.projectVersion, () => store.initialized],
  () => applySheetFromQuery(),
  { immediate: true },
)
</script>

<template>
  <div class="project-view">
    <MainLayout>
      <template #sheet="{ sheetKey }">
        <SheetView :sheet-key="sheetKey" />
      </template>
    </MainLayout>
  </div>
</template>

<style scoped>
.project-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.project-view > :deep(.main-layout) {
  flex: 1;
  min-height: 0;
}
</style>
