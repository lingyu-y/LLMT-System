import { del, get, post, put, type ApiMessage, type PageResult, unwrap } from '@/api/http'

// 上传进度需要直接使用 XMLHttpRequest，因此这里单独保留 API_BASE 和 TOKEN_KEY。
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const TOKEN_KEY = 'llmt_token'

// 数据集拥有者信息，通常用于页面展示上传者/创建者。
export interface DatasetOwner {
  id: number
  username: string
  real_name?: string | null
}

// 后端数据集原始结构。页面会在 DataProcessing.vue 中映射成 DatasetView。
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

// 数据集统计信息，用于数据处理页面顶部统计卡片。
export interface DatasetStats {
  total_datasets: number
  total_size: number
  completed: number
  processing: number
  by_type: Record<string, number>
}

// 后端处理任务结构，主要包括预处理任务的进度、输出位置和错误信息。
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

// 数据质量报告。字段比较多，对应完整性、一致性、时效性、准确性和异常建议。
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

// 数据血缘报告，包含来源、转换记录、上游和下游依赖。
export interface Lineage {
  dataset_id: number
  dataset_name: string
  source?: string | null
  transformations: LineageTransformation[]
  upstream: unknown[]
  downstream: unknown[]
}

// 单条血缘转换记录。
export interface LineageTransformation {
  rule?: string
  description?: string
  timestamp?: string | null
  version_before?: string | null
  version_after?: string | null
  operator?: string | null
}

// 影响分析结果，用于判断当前数据集变更会影响哪些模型、任务和下游数据集。
export interface LineageImpact {
  dataset_id: number
  affected_models: string[]
  affected_tasks: string[]
  affected_datasets: string[]
  risk?: {
    level?: string
    message?: string
    affected_task_count?: number
  } | null
}

// 质量修复接口返回结果。
export interface QualityRepairResult {
  status: string
  fixed_anomalies: string[]
}

// 创建数据集入参。创建后通常再调用上传接口写入文件。
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

// 更新数据集时允许只传部分字段。
export type DatasetUpdatePayload = Partial<DatasetCreatePayload>

// 获取数据集统计。
export const getDatasetStats = async () => unwrap(await get<ApiMessage<DatasetStats>>('/datasets/stats'))

// 分页查询数据集列表，支持关键词、类型和质量状态筛选。
export const listDatasets = (params?: { page?: number; page_size?: number; keyword?: string; data_type?: string; quality_status?: string }) =>
  get<PageResult<BackendDataset>>('/datasets', params)

// 创建数据集元信息，不包含文件内容。
export const createDataset = async (payload: DatasetCreatePayload) =>
  unwrap(await post<ApiMessage<BackendDataset>>('/datasets', payload))

// 更新数据集元信息。
export const updateDataset = async (datasetId: number, payload: DatasetUpdatePayload) =>
  unwrap(await put<ApiMessage<BackendDataset>>(`/datasets/${datasetId}`, payload))

// 删除数据集。
export const deleteDataset = async (datasetId: number) => await del<ApiMessage>(`/datasets/${datasetId}`)

// 普通单文件上传，不返回上传进度；页面更常用 uploadDatasetFileWithProgress。
export const uploadDatasetFile = async (datasetId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return unwrap(await post<ApiMessage<{ filename: string; content_type: string }>>('/datasets/upload', form, { dataset_id: datasetId }))
}

// 带上传进度的底层封装。fetch 无法稳定拿到 upload progress，所以这里使用 XMLHttpRequest。
const uploadWithProgress = <T>(path: string, form: FormData, params: Record<string, string | number>, onProgress?: (percent: number) => void) =>
  new Promise<T>((resolve, reject) => {
    const url = new URL(`${API_BASE}${path}`, window.location.origin)
    Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, String(value)))

    const xhr = new XMLHttpRequest()
    xhr.open('POST', url.toString())
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    // 上传阶段最多推进到 95%，剩余 5% 留给后端写入存储和返回结果。
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.min(95, Math.round((event.loaded / event.total) * 95)))
      }
    }
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText || '{}') as ApiMessage<T> & { detail?: string }
        if (xhr.status >= 200 && xhr.status < 300) {
          // 后端响应成功后才认为整个上传完成。
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

// 单文件上传并回传进度给页面。
export const uploadDatasetFileWithProgress = async (datasetId: number, file: File, onProgress?: (percent: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return uploadWithProgress<{ filename: string; content_type: string }>('/datasets/upload', form, { dataset_id: datasetId }, onProgress)
}

// 批量上传，不返回上传进度。
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

// 批量上传并回传整体进度给页面。
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

// 断点续传状态查询/恢复接口。目前页面有入口，但完整分片续传流程还未在 DataProcessing.vue 接入。
export const resumeUpload = async (uploadId: string) =>
  unwrap(await post<ApiMessage<{ upload_id: string; filename: string; total_size: number; offset: number; resumed: boolean }>>(`/datasets/upload/${uploadId}/resume`))

// 从外部路径或地址导入数据集，由后端负责拉取文件。
export const importExternalDataset = async (payload: {
  name: string
  data_type: string
  source_type: string
  source_path: string
  description?: string
  version?: string
}) =>
  unwrap(await post<ApiMessage<{ dataset: BackendDataset; imported_files: number; total_size: number; errors: string[] }>>('/datasets/import/external', payload))

// 启动数据预处理任务；shardSizeMb > 0 时作为 query 参数传给后端。
export const startPreprocess = async (datasetId: number, shardSizeMb?: number) => {
  const params: Record<string, string | number> = {}
  if (shardSizeMb != null && shardSizeMb > 0) params.shard_size_mb = shardSizeMb
  return unwrap(await post<ApiMessage<ProcessingJob>>(`/datasets/${datasetId}/preprocess`, undefined, params))
}

// 查询处理任务列表。
export const listProcessingJobs = (params?: { page?: number; page_size?: number }) =>
  get<PageResult<ProcessingJob>>('/datasets/processing-jobs', params)

// 查询单个处理任务详情。
export const getProcessingJob = async (jobId: string) => unwrap(await get<ApiMessage<ProcessingJob>>(`/datasets/processing-jobs/${jobId}`))

// 获取最近一次或当前数据集质量报告。
export const getQualityReport = async (datasetId: number) =>
  unwrap(await get<ApiMessage<QualityReport>>(`/datasets/${datasetId}/quality`))

// 触发数据质量校验。
export const triggerQualityCheck = async (datasetId: number) =>
  unwrap(await post<ApiMessage<QualityReport>>(`/datasets/${datasetId}/quality/check`))

// 触发质量修复或标记修复。
export const triggerQualityRepair = async (datasetId: number) =>
  unwrap(await post<ApiMessage<QualityRepairResult>>(`/datasets/${datasetId}/quality/repair`))

// 查询数据血缘链路。
export const getLineage = async (datasetId: number) => unwrap(await get<ApiMessage<Lineage>>(`/datasets/${datasetId}/lineage`))

// 查询数据集变更影响范围。
export const getLineageImpact = async (datasetId: number) =>
  unwrap(await get<ApiMessage<LineageImpact>>(`/datasets/${datasetId}/lineage/impact`))
