<template>
  <div class="dashboard-page">
    <div class="page-header dashboard-header">
      <div>
        <h1 class="page-title">训练监控仪表盘</h1>
        <p class="page-description">实时监控离线训练资源、通信链路和任务状态</p>
      </div>
      <StatusBadge :label="dashboardStatus.label" :type="dashboardStatus.type" />
    </div>
    <el-alert
      v-if="dashboardError"
      class="dashboard-alert"
      :title="dashboardError"
      type="error"
      show-icon
      :closable="false"
    />

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
          <template #extra><StatusBadge :label="dashboardStatus.label" :type="dashboardStatus.type" /></template>
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
          <div class="side-section task-list">
            <el-empty v-if="!trainingTasks.length" description="暂无训练任务" />
            <div v-for="task in trainingTasks" v-else :key="task.name" class="task-item">
              <div class="task-icon"><el-icon><DataAnalysis /></el-icon></div>
              <div class="task-content">
                <div class="task-name">{{ task.name }}</div>
                <div class="task-meta">{{ task.meta }}</div>
                <div v-if="task.progress" class="progress-mini task-progress">
                  <div class="progress-fill blue" :style="{ width: `${task.progress}%` }"></div>
                </div>
              </div>
              <StatusBadge :label="task.statusLabel" :type="task.type" />
            </div>
          </div>

          <h4 class="activity-title">最近活动</h4>
          <div class="side-section activity-list">
            <el-empty v-if="!recentActivities.length" description="暂无活动记录" />
            <div v-for="item in recentActivities" v-else :key="item.text" class="activity-item">
              <span class="activity-dot" :style="{ background: item.color }"></span>
              <span class="activity-text">{{ item.text }}</span>
              <span class="activity-time">{{ item.time }}</span>
            </div>
          </div>

          <h4 class="activity-title">告警事件</h4>
          <div class="side-section activity-list">
            <el-empty v-if="!alerts.length" description="暂无告警事件" />
            <div v-for="item in alerts" v-else :key="item.text" class="activity-item">
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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Connection, Cpu, DataAnalysis, Histogram, TrendCharts } from '@element-plus/icons-vue'

import {
  getDashboardActivities,
  getDashboardAlerts,
  getDashboardMetrics,
  getDashboardSummary,
  getDashboardTrainingTasks,
  type DashboardAlert,
  type DashboardActivity,
  type DashboardSummary,
  type DashboardTrainingTask,
} from '@/api/dashboard'
import ChartCard from '@/components/ChartCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'

interface ResourceMetric {
  title: string
  value: string
  progress: number
  color: string
  bg: string
}

interface TaskItem {
  name: string
  meta: string
  progress: number
  type: 'success' | 'warning' | 'info'
  statusLabel: string
}

interface ActivityItem {
  text: string
  time: string
  color: string
}

interface DashboardStatus {
  label: string
  type: 'success' | 'warning' | 'danger' | 'info'
}

const lossTicks = ref<string[]>([])
const gpuTicks = ref<string[]>([])
const latencyTicks = ref<string[]>([])
const losses = ref<number[]>([])
const gpu = ref<number[]>([])
const latency = ref<number[]>([])
const summaryGpuSeries = ref<{ timestamp: string; value: number }[]>([])
const dashboardMetrics = ref<ResourceMetric[]>([
  { title: 'GPU显存', value: '0.0%', progress: 0, color: '#f59e0b', bg: '#fed7aa' },
  { title: '通信延迟', value: '0.0ms', progress: 0, color: '#10b981', bg: '#d1fae5' },
  { title: '训练进度', value: '0.0%', progress: 0, color: '#2563eb', bg: '#dbeafe' },
  { title: '运行任务', value: '0', progress: 0, color: '#8b5cf6', bg: '#e9d5ff' },
])
const trainingTasks = ref<TaskItem[]>([])
const recentActivities = ref<ActivityItem[]>([])
const alerts = ref<ActivityItem[]>([])
const stream = ref<WebSocket>()
let refreshTimer: number | undefined
const dashboardError = ref('')
const dashboardStatus = ref<DashboardStatus>({ label: '未运行', type: 'info' })

const baseGrid = { top: 24, right: 20, bottom: 28, left: 42 }
const lineStyle = { width: 3 }

const emptyChartOption = (text: string): EChartsOption => ({
  grid: baseGrid,
  xAxis: { type: 'category', data: [], axisLine: { show: false }, axisTick: { show: false } },
  yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
  series: [],
  graphic: {
    type: 'text',
    left: 'center',
    top: 'middle',
    style: {
      text,
      fill: '#94a3b8',
      fontSize: 13,
      fontWeight: 500,
    },
  },
})

const lossOption = computed<EChartsOption>(() => ({
  ...(losses.value.length ? {} : emptyChartOption('暂无训练损失数据')),
  tooltip: { trigger: 'axis' },
  grid: baseGrid,
  xAxis: { type: 'category', data: lossTicks.value, boundaryGap: false },
  yAxis: { type: 'value', min: 0 },
  series: [{ type: 'line', data: losses.value, smooth: true, lineStyle, areaStyle: { opacity: 0.12 }, color: '#2563eb' }],
}))

const gpuOption = computed<EChartsOption>(() => ({
  ...(gpu.value.length ? {} : emptyChartOption('暂无显存趋势数据')),
  tooltip: { trigger: 'axis' },
  grid: baseGrid,
  xAxis: { type: 'category', data: gpuTicks.value, boundaryGap: false },
  yAxis: { type: 'value', min: 0, max: 100 },
  series: [{ type: 'line', data: gpu.value, smooth: true, showSymbol: true, lineStyle, color: '#f59e0b', areaStyle: { opacity: 0.12 } }],
}))

const latencyOption = computed<EChartsOption>(() => ({
  ...(latency.value.length ? {} : emptyChartOption('暂无延迟分布数据')),
  tooltip: { trigger: 'axis' },
  grid: baseGrid,
  xAxis: { type: 'category', data: latencyTicks.value },
  yAxis: { type: 'value' },
  series: [{ type: 'bar', data: latency.value, color: '#06b6d4', barWidth: 18 }],
}))

const formatTimeLabel = (timestamp: string) => {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp.slice(11, 16) || timestamp
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

const relativeTime = (timestamp: string) => {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ''
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  return `${Math.floor(minutes / 60)}小时前`
}

const statusType = (status: string): TaskItem['type'] => {
  if (status === 'running') return 'success'
  if (status === 'paused') return 'info'
  return 'warning'
}

const statusLabel = (status: string) => {
  const map: Record<string, string> = {
    running: '训练中',
    paused: '已暂停',
    queued: '排队',
    created: '待提交',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] ?? status
}

const buildMetrics = (summary: DashboardSummary): ResourceMetric[] => {
  const memoryPercent = summary.gpu_memory_total > 0 ? (summary.gpu_memory_used / summary.gpu_memory_total) * 100 : 0
  return [
    { title: 'GPU显存', value: summary.gpu_memory_total > 0 ? `${memoryPercent.toFixed(1)}%` : '暂无数据', progress: memoryPercent, color: '#f59e0b', bg: '#fed7aa' },
    { title: '通信延迟', value: `${summary.communication_latency_ms.toFixed(1)}ms`, progress: Math.min(100, summary.communication_latency_ms), color: '#10b981', bg: '#d1fae5' },
    { title: '训练进度', value: `${summary.training_progress.toFixed(1)}%`, progress: summary.training_progress, color: '#2563eb', bg: '#dbeafe' },
    { title: '运行任务', value: String(summary.running_tasks), progress: Math.min(100, summary.running_tasks * 20), color: '#8b5cf6', bg: '#e9d5ff' },
  ]
}

const buildDashboardStatus = (summary: DashboardSummary): DashboardStatus => {
  if (summary.alert_count > 0) return { label: '有告警', type: 'warning' }
  if (summary.running_tasks > 0) return { label: '训练中', type: 'success' }
  if (summary.paused_tasks > 0) return { label: '已暂停', type: 'info' }
  return { label: '未运行', type: 'info' }
}

const buildTaskItem = (task: DashboardTrainingTask): TaskItem => ({
  name: task.task_name,
  meta: `Epoch ${task.current_epoch}/${task.max_epoch ?? '-'} · Loss: ${task.loss ?? '-'}`,
  progress: task.progress,
  type: statusType(task.status),
  statusLabel: statusLabel(task.status),
})

const buildActivityItem = (item: DashboardActivity): ActivityItem => ({
  text: item.detail || `${item.username} ${item.action}`,
  time: relativeTime(item.created_at),
  color: item.action.includes('error') || item.action.includes('alert') ? '#f59e0b' : '#2563eb',
})

const buildAlertItem = (item: DashboardAlert): ActivityItem => ({
  text: item.message,
  time: relativeTime(item.created_at),
  color: item.level === 'critical' ? '#ef4444' : item.level === 'warning' ? '#f59e0b' : '#2563eb',
})

const appendGpuPoint = (point?: { timestamp: string; value: number }) => {
  if (!point) return
  const last = summaryGpuSeries.value.at(-1)
  if (last?.timestamp === point.timestamp && last.value === point.value) return
  summaryGpuSeries.value = [...summaryGpuSeries.value, point].slice(-10)
}

const buildSummaryGpuPoint = (summary?: DashboardSummary) => {
  if (!summary || summary.gpu_memory_total <= 0) return undefined
  return {
    timestamp: summary.updated_at,
    value: Number(((summary.gpu_memory_used / summary.gpu_memory_total) * 100).toFixed(2)),
  }
}

const updateMetricSeries = (metrics: {
  loss?: { timestamp: string; value: number }[]
  gpu_utilization?: { timestamp: string; value: number }[]
  gpu_memory?: { timestamp: string; value: number }[]
  latency?: { timestamp: string; value: number }[]
}, summary?: DashboardSummary) => {
  if ((metrics.gpu_memory?.length ?? 0) <= 1) appendGpuPoint(metrics.gpu_memory?.[0] ?? buildSummaryGpuPoint(summary))
  const gpuMemorySeries = (metrics.gpu_memory?.length ?? 0) > 1 ? metrics.gpu_memory! : summaryGpuSeries.value
  const gpuSeries = gpuMemorySeries.length ? gpuMemorySeries : metrics.gpu_utilization ?? []
  const latencySeries = metrics.latency ?? []

  lossTicks.value = (metrics.loss ?? []).map((item) => formatTimeLabel(item.timestamp)).slice(-10)
  losses.value = (metrics.loss ?? []).map((item) => item.value).slice(-10)
  gpuTicks.value = gpuSeries.map((item) => formatTimeLabel(item.timestamp)).slice(-10)
  gpu.value = gpuSeries.map((item) => item.value).slice(-10)
  latencyTicks.value = latencySeries.map((item) => formatTimeLabel(item.timestamp)).slice(-10)
  latency.value = latencySeries.map((item) => item.value).slice(-10)
}

const loadDashboard = async () => {
  try {
    dashboardError.value = ''
    const [summary, metrics, tasks, activities, alertItems] = await Promise.all([
      getDashboardSummary(),
      getDashboardMetrics('1h'),
      getDashboardTrainingTasks(),
      getDashboardActivities(8),
      getDashboardAlerts(5),
    ])

    dashboardMetrics.value = buildMetrics(summary)
    dashboardStatus.value = buildDashboardStatus(summary)
    trainingTasks.value = tasks.map(buildTaskItem)
    recentActivities.value = activities.map(buildActivityItem)
    alerts.value = alertItems.map(buildAlertItem)

    updateMetricSeries(metrics, summary)
  } catch (error) {
    dashboardError.value = error instanceof Error ? error.message : '加载仪表盘接口失败'
    dashboardStatus.value = { label: '连接异常', type: 'danger' }
    console.warn('加载仪表盘接口失败', error)
  }
}

const connectDashboardStream = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
  const wsBase = base.startsWith('http') ? base.replace(/^http/, 'ws') : `${protocol}://${window.location.host}${base}`
  const socket = new WebSocket(`${wsBase}/dashboard/stream`)
  stream.value = socket
  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.summary) {
        dashboardMetrics.value = buildMetrics(payload.summary)
        dashboardStatus.value = buildDashboardStatus(payload.summary)
      }
      if (payload.training_tasks) trainingTasks.value = payload.training_tasks.map(buildTaskItem)
      if (payload.metrics) updateMetricSeries(payload.metrics, payload.summary)
    } catch (error) {
      console.warn('仪表盘流数据解析失败', error)
    }
  }
  socket.onerror = () => socket.close()
}

onMounted(() => {
  void loadDashboard()
  connectDashboardStream()
  refreshTimer = window.setInterval(() => {
    void loadDashboard()
  }, 5000)
})
onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  stream.value?.close()
})
</script>

<style scoped>
.dashboard-page {
  min-height: calc(100vh - 131px);
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dashboard-alert {
  margin-bottom: 16px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  align-items: stretch;
  gap: 20px;
}

.dashboard-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 20px;
}

.dashboard-main :deep(.chart-card) {
  margin-bottom: 0;
}

.dashboard-main .grid-2 {
  align-items: stretch;
}

.resource-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 0;
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
  align-self: stretch;
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  margin-bottom: 0;
}

.side-card .card-header {
  flex: 0 0 auto;
}

.side-card .card-body {
  display: flex;
  flex: 1 1 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.side-card :deep(.el-empty) {
  padding: 10px 0;
}

.side-card :deep(.el-empty__image) {
  display: none;
}

.side-section {
  min-height: 0;
  overflow-y: auto;
}

.task-list {
  display: flex;
  flex: 1.25 1 0;
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
  flex: 0 0 auto;
  margin: 14px 0 10px;
  font-size: 13px;
}

.activity-list {
  display: flex;
  flex: 1 1 0;
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

@media (max-width: 1180px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .side-card {
    height: auto;
    max-height: none;
  }
}
</style>
