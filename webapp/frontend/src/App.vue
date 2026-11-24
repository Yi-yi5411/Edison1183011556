<script setup lang="ts">
import { onMounted } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useAppStore } from '@/stores/app'

const store = useAppStore()

// 应用启动即恢复主题偏好（与路由无关）
onMounted(() => {
  store.applyTheme(store.theme)
})
</script>

<template>
  <el-config-provider :locale="zhCn">
    <RouterView v-slot="{ Component }">
      <transition name="page-fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </RouterView>
  </el-config-provider>
</template>
