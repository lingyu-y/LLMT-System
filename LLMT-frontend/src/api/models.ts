import { get, post, type ApiMessage, type PageResult, unwrap } from '@/api/http'

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
