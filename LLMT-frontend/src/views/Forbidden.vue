<template>
  <div class="forbidden-page">
    <div class="forbidden-card">
      <div class="code">403</div>
      <h1>无权访问</h1>
      <p>当前 mock 用户没有访问该页面的权限。</p>
      <el-button type="primary" @click="router.push('/dashboard')">返回仪表盘</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<style scoped>
.forbidden-page {
  display: grid;
  min-height: calc(100vh - 145px);
  place-items: center;
}

.forbidden-card {
  width: min(100%, 420px);
  padding: 34px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--card-bg);
  text-align: center;
}

.code {
  color: var(--primary-color);
  font-size: 52px;
  font-weight: 800;
}

.forbidden-card h1 {
  margin: 4px 0 10px;
  font-size: 24px;
}

.forbidden-card p {
  margin: 0 0 24px;
  color: var(--text-secondary);
}
</style>
