<template>
  <div>
    <div class="page-header dashboard-header">
      <div>
        <h1 class="page-title">训练监控仪表盘</h1>
        <p class="page-description">实时监控离线训练资源、通信链路和任务状态</p>
      </div>
      <StatusBadge label="训练中" type="success" />
    </div>

    <div class="dashboard-grid">
      <section class="dashboard-main">
        <div class="resource-row">
          <div v-for="item in dashboardMetrics" :key="item.title" class="resource-compact">
            <span class="resource-icon" :style="{ background: item.bg, color: item.color }">
              <el-icon><Cpu /></el-icon>
            </span>
            <div class="resource-info">
              <span class="resource-label">{{ item.title }}</span>
              <strong>{{ item.value }}</strong>
            </div>
            <div class="progress-mini">
              <div class="progress-fill" :style="{ width: `${item.progress}%`, background: item.color }"></div>
            </div>
          </div>
        </div>

        <ChartCard title="实时训练损失曲线" :icon="TrendCharts" :option="lossOption" height="260px">
          <template #extra><StatusBadge label="训练中" type="success" /></template>
        </ChartCard>

        <div class="grid-2">
          <ChartCard title="显存趋势" :icon="Histogram" :option="gpuOption" height="210px" />
          <ChartCard title="延迟分布" :icon="Connection" :option="latencyOption" height="210px" />
        </div>
      </section>

      <aside class="card side-card">
        <div class="card-header">
          <h3 class="card-title">当前训练任务</h3>
        </div>
        <div class="card-body">
          <div class="task-list">
            <div v-for="task in trainingTasks" :key="task.name" class="task-item">
              <div class="task-icon"><el-icon><DataAnalysis /></el-icon></div>
              <div class="task-content">
                <div class="task-name">{{ task.name }}</div>
                <div class="task-meta">{{ task.meta }}</div>
                <div v-if="task.progress" class="progress-mini task-progress">
                  <div class="progress-fill blue" :style="{ width: `${task.progress}%` }"></div>
                </div>
              </div>
              <StatusBadge :label="task.type === 'warning' ? '排队' : '训练中'" :type="task.type" />
            </div>
          </div>

          <h4 class="activity-title">最近活动</h4>
          <div class="activity-list">
            <div v-for="item in recentActivities" :key="item.text" class="activity-item">
              <span class="activity-dot" :style="{ background: item.color }"></span>
              <span class="activity-text">{{ item.text }}</span>
              <span class="activity-time">{{ item.time }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, onBeforeUnmount, ref } from 'vue'
import { Connection, Cpu, DataAnalysis, Histogram, TrendCharts } from '@element-plus/icons-vue'

import ChartCard from '@/components/ChartCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import {
  dashboardMetrics,
  gpuSeries,
  latencySeries,
  lossSeries,
  recentActivities,
  trainingTasks,
} from '@/mock/dashboard'

const ticks = ref(['10:01', '10:02', '10:03', '10:04', '10:05', '10:06', '10:07', '10:08', '10:09', '10:10'])
const losses = ref([...lossSeries])
const gpu = ref([...gpuSeries])
const latency = ref([...latencySeries])

const baseGrid = { top: 24, right: 20, bottom: 28, left: 42 }
const lineStyle = { width: 3 }

const lossOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: baseGrid,
  xAxis: { type: 'category', data: ticks.value, boundaryGap: false },
  yAxis: { type: 'value', min: 0 },
  series: [{ type: 'line', data: losses.value, smooth: true, lineStyle, areaStyle: { opacity: 0.12 }, color: '#2563eb' }],
}))

const gpuOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: baseGrid,
  xAxis: { type: 'category', data: ticks.value, boundaryGap: false },
  yAxis: { type: 'value', min: 40, max: 100 },
  series: [{ type: 'line', data: gpu.value, smooth: true, lineStyle, color: '#f59e0b', areaStyle: { opacity: 0.12 } }],
}))

const latencyOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: baseGrid,
  xAxis: { type: 'category', data: ticks.value },
  yAxis: { type: 'value' },
  series: [{ type: 'bar', data: latency.value, color: '#06b6d4', barWidth: 18 }],
}))

const timer = window.setInterval(() => {
  const next = new Date()
  ticks.value = [...ticks.value.slice(1), `${String(next.getHours()).padStart(2, '0')}:${String(next.getMinutes()).padStart(2, '0')}`]
  losses.value = [...losses.value.slice(1), Math.max(0.01, losses.value.at(-1)! * (0.88 + Math.random() * 0.18))]
  gpu.value = [...gpu.value.slice(1), Math.round(70 + Math.random() * 18)]
  latency.value = [...latency.value.slice(1), Number((1.8 + Math.random() * 1.2).toFixed(1))]
}, 3000)

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<style scoped>
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 20px;
}

.dashboard-main {
  min-width: 0;
}

.resource-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.resource-compact,
.task-item,
.activity-item {
  display: flex;
  align-items: center;
}

.resource-compact {
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--card-bg);
}

.resource-icon,
.task-icon {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 8px;
}

.resource-icon {
  width: 36px;
  height: 36px;
}

.resource-info {
  flex: 1;
  min-width: 0;
}

.resource-label,
.task-meta {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.side-card {
  align-self: start;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-item {
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-color);
}

.task-icon {
  width: 32px;
  height: 32px;
  background: var(--primary-light);
  color: var(--primary-color);
}

.task-content {
  flex: 1;
  min-width: 0;
}

.task-name {
  font-size: 13px;
  font-weight: 700;
}

.task-progress {
  margin-top: 7px;
}

.activity-title {
  margin: 18px 0 12px;
  font-size: 13px;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.activity-item {
  gap: 10px;
  padding: 9px 10px;
  border-radius: 6px;
  background: var(--bg-color);
}

.activity-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.activity-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.activity-time {
  color: var(--text-muted);
  font-size: 11px;
}
</style>
