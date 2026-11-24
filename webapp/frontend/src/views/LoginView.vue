<script setup lang="ts">
/** 新 Web 产品登录页：复用项目账号库（admin/admin123 或手机号）。 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { login } from '@/auth'

const route = useRoute()
const router = useRouter()

const form = ref({ loginId: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.value.loginId.trim() || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const user = await login(form.value.loginId.trim(), form.value.password)
    ElMessage.success('欢迎，' + (user.real_name || user.username))
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/harness'
    router.replace(redirect)
  } catch (error) {
    ElMessage.error((error as Error).message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-brand">
      <div class="brand-row">
        <img class="brand-logo" src="/brand/logo.svg" alt="工程检测harness" />
        <div>
          <div class="brand-name">工程检测harness</div>
          <div class="brand-sub">数据管理平台</div>
        </div>
      </div>
      <h1>检测数据 · 对话 · 报告<br />一个工作台完成</h1>
      <p class="lead">对话识别意图，自动加载检测项、录入数据、评定并生成报告；报告可预览、可修改。</p>
      <ul class="features">
        <li>17 类检测项目 · 109 个工具</li>
        <li>原始记录导入 / 扫描识别 / 评定</li>
        <li>报告生成 · 在线预览 · 修改留痕</li>
      </ul>
    </section>

    <section class="login-panel">
      <el-card class="login-card" shadow="never">
        <h2>登录工作台</h2>
        <p class="hint">使用项目账号登录；管理员默认 admin / admin123。</p>
        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="用户名 / 手机号">
            <el-input v-model="form.loginId" :prefix-icon="User" size="large" placeholder="admin" autofocus />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              :prefix-icon="Lock"
              size="large"
              type="password"
              show-password
              placeholder="请输入密码"
              @keyup.enter="submit"
            />
          </el-form-item>
          <el-button class="submit" type="primary" size="large" :loading="loading" @click="submit">
            登录
          </el-button>
        </el-form>
      </el-card>
      <p class="foot">本地部署 · 数据保存在本机</p>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(380px, 0.85fr);
  background: #f6f8fb;
}
.login-brand {
  position: relative;
  padding: 64px 72px;
  color: #fff;
  background:
    radial-gradient(1100px 520px at -10% -20%, rgba(242, 184, 75, 0.22), transparent 60%),
    linear-gradient(140deg, #0e3a5c 0%, #12496f 55%, #0b2f4a 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.brand-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.brand-logo {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.25);
}
.brand-name {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.brand-sub {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 2px;
}
.login-brand h1 {
  margin: 54px 0 18px;
  font-size: 36px;
  line-height: 1.35;
  font-weight: 700;
}
.lead {
  max-width: 520px;
  font-size: 14px;
  line-height: 1.9;
  opacity: 0.82;
}
.features {
  margin: 28px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
  font-size: 13px;
  opacity: 0.85;
}
.features li::before {
  content: '·';
  color: #f2b84b;
  font-weight: 900;
  margin-right: 8px;
}
.login-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.login-card {
  width: 100%;
  max-width: 380px;
  border-radius: 16px;
  border: 1px solid #e6ebf2;
}
.login-card h2 {
  margin: 4px 0 6px;
  font-size: 22px;
  color: #0e3a5c;
}
.hint {
  margin: 0 0 22px;
  font-size: 12px;
  color: #8a94a6;
  line-height: 1.7;
}
.submit {
  width: 100%;
  margin-top: 6px;
}
.foot {
  margin-top: 18px;
  font-size: 12px;
  color: #9aa3b2;
}
@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .login-brand {
    padding: 40px 32px;
  }
  .login-brand h1 {
    font-size: 28px;
    margin-top: 30px;
  }
  .features {
    display: none;
  }
}
</style>
