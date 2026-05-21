import { get, post, type ApiMessage, type PageResult, unwrap } from '@/api/http'

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
  started_at?: string | null
  finished_at?: string | null
}

export interface QualityReport {
  dataset_id: number
  dataset_name: string
  overall_score: number
  completeness: boolean
  consistency: boolean
  timeliness: boolean
  anomalies: Record<string, unknown>[]
  checked_at?: string | null
}

export interface Lineage {
  dataset_id: number
  dataset_name: string
  source?: string | null
  transformations: string[]
  upstream: string[]
  downstream: string[]
}

export interface LineageImpact {
  dataset_id: number
  affected_models: string[]
  affected_tasks: string[]
  affected_datasets: string[]
}

export interface QualityRepairResult {
  status: string
  fixed_anomalies: Record<string, unknown>[]
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

export const getDatasetStats = async () => unwrap(await get<ApiMessage<DatasetStats>>('/datasets/stats'))

export const listDatasets = (params?: { page?: number; page_size?: number; keyword?: string; data_type?: string; quality_status?: string }) =>
  get<PageResult<BackendDataset>>('/datasets', params)

export const createDataset = async (payload: DatasetCreatePayload) =>
  unwrap(await post<ApiMessage<BackendDataset>>('/datasets', payload))

export const uploadDatasetFile = async (datasetId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap(await post<ApiMessage<{ filename: string; content_type: string }>>('/datasets/upload', form, { dataset_id: datasetId }))
}

export const startPreprocess = async (datasetId: number) =>
  unwrap(await post<ApiMessage<ProcessingJob>>(`/datasets/${datasetId}/preprocess`))

export const listProcessingJobs = (params?: { page?: number; page_size?: number }) =>
  get<PageResult<ProcessingJob>>('/datasets/processing-jobs', params)

export const getQualityReport = async (datasetId: number) =>
  unwrap(await get<ApiMessage<QualityReport>>(`/datasets/${datasetId}/quality`))

export const triggerQualityCheck = async (datasetId: number) =>
  unwrap(await post<ApiMessage<QualityReport>>(`/datasets/${datasetId}/quality/check`))

export const triggerQualityRepair = async (datasetId: number) =>
  unwrap(await post<ApiMessage<QualityRepairResult>>(`/datasets/${datasetId}/quality/repair`))

export const getLineage = async (datasetId: number) => unwrap(await get<ApiMessage<Lineage>>(`/datasets/${datasetId}/lineage`))

export const getLineageImpact = async (datasetId: number) =>
  unwrap(await get<ApiMessage<LineageImpact>>(`/datasets/${datasetId}/lineage/impact`))
