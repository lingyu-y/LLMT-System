import { del, get, post, put, type ApiMessage, type PageResult, unwrap } from '@/api/http'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const TOKEN_KEY = 'llmt_token'

export interface DatasetOwner {
  id: number
  username: string
  real_name?: string | null
}

export interface BackendDataset {
  id: number
  name: string
  description?: string | null
  data_type: string
  version: string
  source?: string | null
  storage_path?: string
  file_count: number
  total_size: number
  quality_status: string
  processing_status: string
  lineage_status: string
  owner?: DatasetOwner | null
  created_at: string
  updated_at?: string
}

export interface DatasetStats {
  total_datasets: number
  total_size: number
  completed: number
  processing: number
  by_type: Record<string, number>
}

export interface ProcessingJob {
  job_id: string
  dataset_id: number
  dataset_name: string
  job_type: string
  status: string
  progress: number
  output_path?: string
  record_count?: number
  processed_size?: number
  source_file_count?: number
  error?: string
  started_at?: string | null
  finished_at?: string | null
}

export interface QualityReport {
  report_id?: string
  dataset_id: number
  dataset_name: string
  overall_score: number
  passed?: boolean
  alerted?: boolean
  blocked_for_training?: boolean
  completeness: boolean
  consistency: boolean
  timeliness: boolean
  accuracy?: boolean
  duplicate_rows?: number
  range_violations?: number
  rule_violations?: number
  missing_rate_pct?: number
  format_rate_pct?: number
  data_age_days?: number
  capture_age_days?: number
  outlier_rate_pct?: number
  sample_rows?: number
  sample_cells?: number
  scores_detail?: Record<string, number>
  anomalies: Record<string, unknown>[]
  suggestions?: string[]
  skip_reason?: string | null
  great_expectations?: Record<string, unknown> | null
  checked_at?: string | null
}

export interface Lineage {
  dataset_id: number
  dataset_name: string
  source?: string | null
  transformations: LineageTransformation[]
  upstream: unknown[]
  downstream: unknown[]
}

export interface LineageTransformation {
  rule?: string
  description?: string
  timestamp?: string | null
  version_before?: string | null
  version_after?: string | null
}

export interface LineageImpact {
  dataset_id: number
  affected_models: string[]
  affected_tasks: string[]
  affected_datasets: string[]
}

export interface QualityRepairResult {
  status: string
  fixed_anomalies: string[]
}

export interface DatasetCreatePayload {
  name: string
  description?: string
  data_type: string
  version?: string
  source?: string
  storage_path?: string
  file_count?: number
  total_size?: number
}

export type DatasetUpdatePayload = Partial<DatasetCreatePayload>

export const getDatasetStats = async () => unwrap(await get<ApiMessage<DatasetStats>>('/datasets/stats'))

export const listDatasets = (params?: { page?: number; page_size?: number; keyword?: string; data_type?: string; quality_status?: string }) =>
  get<PageResult<BackendDataset>>('/datasets', params)

export const createDataset = async (payload: DatasetCreatePayload) =>
  unwrap(await post<ApiMessage<BackendDataset>>('/datasets', payload))

export const updateDataset = async (datasetId: number, payload: DatasetUpdatePayload) =>
  unwrap(await put<ApiMessage<BackendDataset>>(`/datasets/${datasetId}`, payload))

export const deleteDataset = async (datasetId: number) => await del<ApiMessage>(`/datasets/${datasetId}`)

export const uploadDatasetFile = async (datasetId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap(await post<ApiMessage<{ filename: string; content_type: string }>>('/datasets/upload', form, { dataset_id: datasetId }))
}

const uploadWithProgress = <T>(path: string, form: FormData, params: Record<string, string | number>, onProgress?: (percent: number) => void) =>
  new Promise<T>((resolve, reject) => {
    const url = new URL(`${API_BASE}${path}`, window.location.origin)
    Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, String(value)))

    const xhr = new XMLHttpRequest()
    xhr.open('POST', url.toString())
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.min(95, Math.round((event.loaded / event.total) * 95)))
      }
    }
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText || '{}') as ApiMessage<T> & { detail?: string }
        if (xhr.status >= 200 && xhr.status < 300) {
          onProgress?.(100)
          resolve(body.data as T)
        } else {
          reject(new Error(body.detail ?? body.message ?? `请求失败 (${xhr.status})`))
        }
      } catch {
        reject(new Error(`请求失败 (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('网络错误，文件上传未完成'))
    xhr.send(form)
  })

export const uploadDatasetFileWithProgress = async (datasetId: number, file: File, onProgress?: (percent: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return uploadWithProgress<{ filename: string; content_type: string }>('/datasets/upload', form, { dataset_id: datasetId }, onProgress)
}

export const uploadDatasetFilesBatch = async (datasetId: number, files: File[]) => {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return unwrap(
    await post<ApiMessage<{ total: number; uploaded: number; failed: number; files: Record<string, unknown>[] }>>(
      '/datasets/upload/batch',
      form,
      { dataset_id: datasetId },
    ),
  )
}

export const uploadDatasetFilesBatchWithProgress = async (datasetId: number, files: File[], onProgress?: (percent: number) => void) => {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return uploadWithProgress<{ total: number; uploaded: number; failed: number; files: Record<string, unknown>[] }>(
    '/datasets/upload/batch',
    form,
    { dataset_id: datasetId },
    onProgress,
  )
}

export const resumeUpload = async (uploadId: string) =>
  unwrap(await post<ApiMessage<{ upload_id: string; filename: string; total_size: number; offset: number; resumed: boolean }>>(`/datasets/upload/${uploadId}/resume`))

export const importExternalDataset = async (payload: {
  name: string
  data_type: string
  source_type: string
  source_path: string
  description?: string
  version?: string
}) =>
  unwrap(await post<ApiMessage<{ dataset: BackendDataset; imported_files: number; total_size: number; errors: string[] }>>('/datasets/import/external', payload))

export const startPreprocess = async (datasetId: number, shardSizeMb?: number) => {
  const params: Record<string, string | number> = {}
  if (shardSizeMb != null && shardSizeMb > 0) params.shard_size_mb = shardSizeMb
  return unwrap(await post<ApiMessage<ProcessingJob>>(`/datasets/${datasetId}/preprocess`, undefined, params))
}

export const listProcessingJobs = (params?: { page?: number; page_size?: number }) =>
  get<PageResult<ProcessingJob>>('/datasets/processing-jobs', params)

export const getProcessingJob = async (jobId: string) => unwrap(await get<ApiMessage<ProcessingJob>>(`/datasets/processing-jobs/${jobId}`))

export const getQualityReport = async (datasetId: number) =>
  unwrap(await get<ApiMessage<QualityReport>>(`/datasets/${datasetId}/quality`))

export const triggerQualityCheck = async (datasetId: number) =>
  unwrap(await post<ApiMessage<QualityReport>>(`/datasets/${datasetId}/quality/check`))

export const triggerQualityRepair = async (datasetId: number) =>
  unwrap(await post<ApiMessage<QualityRepairResult>>(`/datasets/${datasetId}/quality/repair`))

export const getLineage = async (datasetId: number) => unwrap(await get<ApiMessage<Lineage>>(`/datasets/${datasetId}/lineage`))

export const getLineageImpact = async (datasetId: number) =>
  unwrap(await get<ApiMessage<LineageImpact>>(`/datasets/${datasetId}/lineage/impact`))
