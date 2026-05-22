import { get, post, type ApiMessage, unwrap } from '@/api/http'

export interface InferenceModel {
  model_code: string
  model_name: string
  version: string
  framework?: string | null
  tag?: string | null
}

export interface PredictResult {
  model_code: string
  output: string
  latency_ms: number
}

export interface InferenceJob {
  job_id: string
  model_code: string
  status: string
  input: string
  output?: string | null
  created_at: string
  finished_at?: string | null
}

export interface InferenceUsage {
  model_code: string
  total_calls: number
  remaining_calls: number
  limit_per_minute: number
  reset_at: string
}

export const listInferenceModels = async () => unwrap(await get<ApiMessage<InferenceModel[]>>('/inference/models'))

export const predict = async (modelCode: string, payload: { input: string; parameters?: Record<string, unknown> }) =>
  unwrap(await post<ApiMessage<PredictResult>>(`/inference/models/${modelCode}/predict`, payload))

export const createInferenceJob = async (payload: { model_code: string; input: string; parameters?: Record<string, unknown> }) =>
  unwrap(await post<ApiMessage<InferenceJob>>('/inference/jobs', payload))

export const getInferenceJob = async (jobId: string) => unwrap(await get<ApiMessage<InferenceJob>>(`/inference/jobs/${jobId}`))

export const cancelInferenceJob = async (jobId: string) => unwrap(await post<ApiMessage<unknown>>(`/inference/jobs/${jobId}/cancel`))

export const getInferenceUsage = async (modelCode?: string) =>
  unwrap(await get<ApiMessage<InferenceUsage[]>>('/inference/usage', { model_code: modelCode }))
