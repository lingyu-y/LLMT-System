<template>
  <span class="status-badge" :class="type">
    <span class="status-dot"></span>
    {{ label }}
  </span>
</template>

<script setup lang="ts">
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
  background: currentColor;
}
</style>
