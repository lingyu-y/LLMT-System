<template>
  <div class="metric-card">
    <div class="metric-head">
      <span>{{ title }}</span>
      <span class="metric-icon" :style="{ background: colorBg, color }">
        <el-icon><component :is="icon" /></el-icon>
      </span>
    </div>
    <div class="metric-value">{{ value }}</div>
    <div v-if="change" class="metric-change" :class="changeType">{{ change }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  value: string | number
  icon?: unknown
  color?: string
  colorBg?: string
  change?: string
  changeType?: 'up' | 'down'
}>()
</script>

<style scoped>
.metric-card {
  padding: 20px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--card-bg);
}

.metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.metric-icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 8px;
}

.metric-value {
  margin-top: 12px;
  font-size: 28px;
  font-weight: 800;
}

.metric-change {
  margin-top: 6px;
  font-size: 12px;
}

.metric-change.up {
  color: var(--success-color);
}

.metric-change.down {
  color: var(--danger-color);
}
</style>
