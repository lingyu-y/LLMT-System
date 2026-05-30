<template>
  <!-- 通用状态标签：展示一个彩色圆点和状态文案。 -->
  <span class="status-badge" :class="type">
    <span class="status-dot"></span>
    {{ label }}
  </span>
</template>

<script setup lang="ts">
// 组件只负责展示，不负责把后端状态翻译成中文；状态文案和颜色类型由父组件传入。
defineProps<{
  label: string
  type?: 'success' | 'warning' | 'danger' | 'info'
}>()
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  /* 状态标签通常出现在表格或卡片中，保持单行避免撑高布局。 */
  white-space: nowrap;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.success {
  background: #d1fae5;
  color: #059669;
}

.status-badge.warning {
  background: #fed7aa;
  color: #d97706;
}

.status-badge.danger {
  background: #fee2e2;
  color: #dc2626;
}

.status-badge.info {
  background: #cffafe;
  color: #0891b2;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  /* 使用 currentColor，让圆点颜色自动跟随文字颜色。 */
  background: currentColor;
}
</style>
