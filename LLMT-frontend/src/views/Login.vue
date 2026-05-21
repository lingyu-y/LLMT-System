<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="panel-head">
        <h1>离线大数据训练与应用系统</h1>
        <h2>登录系统</h2>
      </div>

      <el-form :model="form" label-position="top" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="form.username" size="large" placeholder="请输入用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            size="large"
            placeholder="请输入密码"
            show-password
            type="password"
            :prefix-icon="Lock"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-button class="login-button" type="primary" size="large" :loading="loading" @click="handleLogin">
          登录
        </el-button>
      </el-form>

      <div class="panel-link">
        还没有账号？
        <RouterLink to="/register">注册普通用户</RouterLink>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})

const handleLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }

  loading.value = true
  try {
    const result = await authStore.login(form)
    ElMessage.success(`欢迎回来，${result.user.realName}`)
    const redirect = router.currentRoute.value.query.redirect
    await router.push(typeof redirect === 'string' ? redirect : '/dashboard')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
  background: var(--bg-color);
}

.login-panel {
  width: min(100%, 420px);
  padding: 34px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--card-bg);
  box-shadow: 0 16px 42px rgb(15 23 42 / 8%);
}

.panel-head {
  margin-bottom: 26px;
  text-align: center;
}

.panel-head h1 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 20px;
  font-weight: 800;
}

.panel-head h2 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 500;
}

.login-button {
  width: 100%;
}

.panel-link {
  margin-top: 16px;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
}

.panel-link a {
  color: var(--primary-color);
  font-weight: 700;
  text-decoration: none;
}

@media (max-width: 980px) {
  .login-panel {
    padding: 28px 22px;
  }
}
</style>
