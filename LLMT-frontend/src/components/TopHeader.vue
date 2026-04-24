<template>
  <header class="header">
    <div class="breadcrumb">
      <span class="muted">离线大数据训练与应用系统</span>
      <el-icon><ArrowRight /></el-icon>
      <strong>{{ pageTitle }}</strong>
    </div>

    <div class="header-right">
      <el-input v-model="keyword" class="search" placeholder="搜索功能、模型、数据..." :prefix-icon="Search" clearable />
      <el-button :icon="Bell" circle />
      <el-button :icon="QuestionFilled" circle />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight, Bell, QuestionFilled, Search } from '@element-plus/icons-vue'

const route = useRoute()
const keyword = ref('')
const pageTitle = computed(() => String(route.meta.title ?? '仪表盘'))
</script>

<style scoped>
.header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 73px;
  padding: 16px 32px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
}

.breadcrumb,
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.breadcrumb {
  color: var(--text-primary);
  font-size: 14px;
}

.search {
  width: 280px;
}
</style>
