import { get, post, put, type ApiMessage, type PageResult, unwrap } from '@/api/http'

export interface BackendModel {
  id: number
  model_name: string
  model_code: string
  version: string
  tag?: string | null
  description?: string | null
  framework?: string | null
  dataset_version?: string | null
  metrics_json?: Record<string, unknown>
  hyperparams_json?: Record<string, unknown>
  is_current: boolean
  created_at: string
  updated_at?: string
  metrics?: Record<string, unknown>
  training_metadata?: Record<string, unknown>
  storage_path?: string
}

export interface ModelRateLimit {
  model_code: string
  enabled: boolean
  limits: {
    requests_per_minute: number
    requests_per_hour: number
    requests_per_day: number
    concurrent: number
    max_tokens_per_request: number
  }
  updated_at?: string | null
}

export interface SecurityReport {
  scan_id: string
  model_code: string
  version: string
  status: string
  score?: number
  summary?: string
  vulnerabilities: unknown[]
  scanned_at?: string
}

export const listModels = (params?: { page?: number; page_size?: number; keyword?: string }) =>
  get<PageResult<BackendModel>>('/models', params)

export const getModel = async (modelCode: string) => unwrap(await get<ApiMessage<BackendModel>>(`/models/${modelCode}`))

export const getModelVersions = async (modelCode: string) =>
  unwrap(await get<ApiMessage<BackendModel[]>>(`/models/${modelCode}/versions`))

export const getModelVersion = async (modelCode: string, version: string) =>
  unwrap(await get<ApiMessage<BackendModel>>(`/models/${modelCode}/versions/${encodeURIComponent(version)}`))

export const rollbackModelVersion = async (modelCode: string, version: string) =>
  unwrap(await post<ApiMessage<BackendModel>>(`/models/${modelCode}/versions/${encodeURIComponent(version)}/rollback`))

export const compareModelVersions = async (modelCode: string, v1: string, v2: string) =>
  unwrap(await get<ApiMessage<Record<string, unknown>>>(`/models/${modelCode}/versions/compare`, { v1, v2 }))

export const getModelDownloadUrl = (modelCode: string, version: string) =>
  `/api/v1/models/${modelCode}/versions/${encodeURIComponent(version)}/download`

export const createModel = async (file: File, metadata: Record<string, unknown>) => {
  const form = new FormData()
  form.append('file', file)
  form.append('metadata', JSON.stringify(metadata))
  return unwrap(await post<ApiMessage<BackendModel>>('/models', form))
}

export const importModel = async (payload: Record<string, unknown>) =>
  unwrap(await post<ApiMessage<BackendModel>>('/models/repository/import', payload))

export const exportModel = async (payload: { model_code: string; version: string; target_path: string }) =>
  unwrap(await post<ApiMessage<{ exported: number; target_path: string }>>('/models/repository/export', payload))

export const createModelVersion = async (modelCode: string, payload: Record<string, unknown>) =>
  unwrap(await post<ApiMessage<BackendModel>>(`/models/${modelCode}/versions`, payload))

export const triggerSecurityScan = async (modelCode: string) =>
  unwrap(await post<ApiMessage<Record<string, unknown>>>(`/models/${modelCode}/security/scan`))

export const getSecurityReports = async (modelCode: string) =>
  unwrap(await get<ApiMessage<SecurityReport[]>>(`/models/${modelCode}/security/reports`))

export const getModelRateLimit = async (modelCode: string) =>
  unwrap(await get<ApiMessage<ModelRateLimit>>(`/models/${modelCode}/rate-limit`))

export const updateModelRateLimit = async (modelCode: string, payload: Partial<ModelRateLimit['limits']> & { enabled?: boolean }) =>
  unwrap(await put<ApiMessage<ModelRateLimit>>(`/models/${modelCode}/rate-limit`, payload))
