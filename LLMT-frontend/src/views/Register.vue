<template>
  <main class="register-page">
    <section class="register-panel">
      <div class="panel-head">
        <h1>离线大数据训练与应用系统</h1>
        <h2>注册普通用户</h2>
      </div>

      <el-form :model="form" label-position="top" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="form.username" size="large" placeholder="请输入用户名，至少 2 位" :prefix-icon="User" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.realName" size="large" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" size="large" placeholder="可选" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            size="large"
            placeholder="请输入密码，至少 6 位"
            show-password
            type="password"
            :prefix-icon="Lock"
          />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input
            v-model="confirmPassword"
            size="large"
            placeholder="请再次输入密码"
            show-password
            type="password"
            :prefix-icon="Lock"
            @keyup.enter="handleRegister"
          />
        </el-form-item>
        <el-button class="register-button" type="primary" size="large" :loading="loading" @click="handleRegister">
          注册并登录
        </el-button>
      </el-form>

      <div class="panel-link">
        已有账号？
        <RouterLink to="/login">返回登录</RouterLink>
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
const confirmPassword = ref('')
const form = reactive({
  username: '',
  realName: '',
  email: '',
  password: '',
})

const handleRegister = async () => {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (form.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  if (form.password !== confirmPassword.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    const result = await authStore.register({
      username: form.username.trim(),
      password: form.password,
      realName: form.realName.trim() || undefined,
      email: form.email.trim() || undefined,
    })
    ElMessage.success(`注册成功，欢迎 ${result.user.realName}`)
    await router.push('/dashboard')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
  background: var(--bg-color);
}

.register-panel {
  width: min(100%, 460px);
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

.register-button {
  width: 100%;
}

.panel-link {
  margin-top: 18px;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
}

.panel-link a {
  color: var(--primary-color);
  font-weight: 700;
  text-decoration: none;
}
</style>
