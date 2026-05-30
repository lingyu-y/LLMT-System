<template>
  <!-- 通用指标卡片：用于仪表盘等页面展示单个统计指标。 -->
  <div class="metric-card">
    <div class="metric-head">
      <span>{{ title }}</span>
      <!-- 图标和颜色由父组件传入，方便不同指标使用不同视觉标识。 -->
      <span class="metric-icon" :style="{ background: colorBg, color }">
        <el-icon><component :is="icon" /></el-icon>
      </span>
    </div>
    <div class="metric-value">{{ value }}</div>
    <!-- change 可选，用于展示同比、环比、状态变化等补充信息。 -->
    <div v-if="change" class="metric-change" :class="changeType">{{ change }}</div>
  </div>
</template>

<script setup lang="ts">
// 纯展示组件：不请求接口，只渲染父组件传入的指标标题、数值、图标和变化趋势。
defineProps<{
  title: string
  value: string | number
  icon?: unknown
  color?: string
  colorBg?: string
  change?: string
  // up/down 只控制变化文案颜色，不做数值计算。
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
