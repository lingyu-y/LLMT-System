import { get, type ApiMessage, unwrap } from '@/api/http'

export interface DashboardSummary {
  gpu_memory_used: number
  gpu_memory_total: number
  communication_latency_ms: number
  training_progress: number
  running_tasks: number
  paused_tasks: number
  today_completed: number
  alert_count: number
  gpu_utilization: number
  cpu_utilization: number
  updated_at: string
}

export interface DashboardMetricPoint {
  timestamp: string
  value: number
}

export interface DashboardMetrics {
  loss: DashboardMetricPoint[]
  accuracy: DashboardMetricPoint[]
  gpu_utilization: DashboardMetricPoint[]
  gpu_memory: DashboardMetricPoint[]
  latency: DashboardMetricPoint[]
}

export interface DashboardTrainingTask {
  task_id: string
  task_name: string
  model: string
  status: string
  progress: number
  current_epoch: number
  current_step: number
  max_epoch?: number | null
  loss?: number | null
  gpu?: number | string
  framework?: string | null
  parallel_strategy?: string | null
}

export interface DashboardActivity {
  id: number
  username: string
  action: string
  resource: string
  detail: string
  created_at: string
}

export interface DashboardAlert {
  level: 'critical' | 'warning' | 'info' | string
  message: string
  source: string
  created_at: string
}

export const getDashboardSummary = async () => unwrap(await get<ApiMessage<DashboardSummary>>('/dashboard/summary'))

export const getDashboardMetrics = async (range = '1h') =>
  unwrap(await get<ApiMessage<DashboardMetrics>>('/dashboard/metrics', { range }))

export const getDashboardTrainingTasks = async () =>
  unwrap(await get<ApiMessage<DashboardTrainingTask[]>>('/dashboard/training-tasks'))

export const getDashboardActivities = async (limit = 10) =>
  unwrap(await get<ApiMessage<DashboardActivity[]>>('/dashboard/activities', { limit }))

export const getDashboardAlerts = async (limit = 10) =>
  unwrap(await get<ApiMessage<DashboardAlert[]>>('/dashboard/alerts', { limit }))
