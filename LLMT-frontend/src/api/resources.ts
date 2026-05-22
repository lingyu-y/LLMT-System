import { get, type ApiMessage, unwrap } from '@/api/http'

export interface GpuInfo {
  index: number
  name: string
  utilization_pct: number
  memory_used_mb: number
  memory_total_mb: number
  temperature_c: number
  power_w: number
  processes: number
}

export interface GpuNode {
  node_id: string
  hostname: string
  gpus: GpuInfo[]
}

export interface GpuStatus {
  nodes: GpuNode[]
  summary: {
    total_gpus: number
    used_gpus: number
    available_gpus: number
    total_memory_mb: number
    used_memory_mb: number
  }
}

export const getGpuStatus = async () => unwrap(await get<ApiMessage<GpuStatus>>('/resources/gpu/status'))
