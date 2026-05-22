import { get, post, type ApiMessage, type PageResult, unwrap } from '@/api/http'

export interface SelectOption<T = string | number> {
  value: T
  label: string
}

export interface TrainingConfig {
  model_type?: string
  vocab_size?: number
  hidden_size?: number
  num_layers?: number
  num_attention_heads?: number
  seq_length?: number
  batch_size?: number
  learning_rate?: number
  weight_decay?: number
  max_epochs?: number
  max_steps?: number | null
  warmup_steps?: number
  max_grad_norm?: number
  gradient_accumulation_steps?: number
  optimizer?: string
  scheduler?: string
  precision?: string
  min_lr?: number
  beta1?: number
  beta2?: number
  dataset_path?: string | null
  dataset_format?: string
  train_split?: number
  seed?: number
  num_gpus?: number
  num_nodes?: number
  tensor_model_parallel_size?: number
  pipeline_model_parallel_size?: number
  save_interval?: number
  eval_interval?: number
  max_checkpoints?: number
  upload_to_minio?: boolean
}

export interface TrainingTask {
  id: number | string
  task_name?: string
  taskName?: string
  task_code?: string
  taskCode?: string
  description?: string | null
  status: string
  framework?: string | null
  parallel_strategy?: string | null
  parallelStrategies?: string[]
  config_json?: Record<string, unknown>
  configJson?: Record<string, unknown>
  current_epoch?: number
  currentEpoch?: number
  current_step?: number
  currentStep?: number
  max_epoch?: number | null
  maxEpoch?: number | null
  dataset_id?: number
  datasetId?: number
  checkpoint_path?: string | null
  checkpointPath?: string | null
  error_message?: string | null
  errorMessage?: string | null
  started_at?: string | null
  startedAt?: string | null
  ended_at?: string | null
  endedAt?: string | null
  created_at?: string
  createdAt?: string
  model?: string
  gpu?: string
  progress?: number
  loss?: number | null
  latency?: number | null
}

export interface TrainingTaskCreatePayload {
  task_name: string
  description?: string
  dataset_id: number
  framework: 'pytorch' | 'deepspeed' | 'megatron'
  parallel_strategy: 'ddp' | 'zero1' | 'zero2' | 'zero3' | 'zero3_offload' | 'tp' | 'pp' | '3d'
  config: TrainingConfig
}

export interface TrainingMetrics {
  task_id?: number
  task_name?: string
  series?: Array<Record<string, unknown>>
  summary?: Record<string, unknown>
  [key: string]: unknown
}

export interface TrainingOptions {
  models: SelectOption[]
  datasets: SelectOption<number>[]
  frameworks: SelectOption[]
  gpu_options: SelectOption[]
  parallel_strategies: SelectOption[]
}

export const listTrainingTasks = (params?: { page?: number; page_size?: number; keyword?: string; status?: string; framework?: string }) =>
  get<PageResult<TrainingTask>>('/training/tasks', params)

export const getTrainingTask = async (taskId: number | string) =>
  unwrap(await get<ApiMessage<TrainingTask>>(`/training/tasks/${taskId}`))

export const createTrainingTask = async (payload: TrainingTaskCreatePayload) =>
  unwrap(await post<ApiMessage<TrainingTask>>('/training/tasks', payload))

export const submitTrainingTask = async (taskCode: string) =>
  unwrap(await post<ApiMessage<TrainingTask>>('/training/tasks/submit', { task_code: taskCode }))

export const pauseTrainingTask = async (taskId: number | string) =>
  unwrap(await post<ApiMessage<TrainingTask>>(`/training/tasks/${taskId}/pause`))

export const resumeTrainingTask = async (taskId: number | string) =>
  unwrap(await post<ApiMessage<TrainingTask>>(`/training/tasks/${taskId}/resume`))

export const cancelTrainingTask = async (taskId: number | string) =>
  unwrap(await post<ApiMessage<TrainingTask>>(`/training/tasks/${taskId}/cancel`))

export const scaleTrainingTask = async (taskId: number | string, payload: { gpu_count: number; parallel_strategy?: string }) =>
  unwrap(await post<ApiMessage<TrainingTask>>(`/training/tasks/${taskId}/scale`, payload))

export const getTrainingMetrics = async (taskId: number | string, params?: { metric_type?: string; start_time?: string; stop_time?: string; window?: string }) =>
  unwrap(await get<ApiMessage<TrainingMetrics>>(`/training/tasks/${taskId}/metrics`, params))

export const getTrainingCheckpoints = async (taskId: number | string) =>
  unwrap(await get<ApiMessage<unknown>>(`/training/tasks/${taskId}/checkpoints`))

export const getTrainingLogs = async (taskId: number | string, params?: { level?: string; keyword?: string; lines?: number }) =>
  unwrap(await get<ApiMessage<unknown>>(`/training/tasks/${taskId}/logs`, params))

export const getTrainingOptions = async () => unwrap(await get<ApiMessage<TrainingOptions>>('/training/options'))

export const validateTrainingConfig = async (payload: TrainingTaskCreatePayload) =>
  unwrap(await post<ApiMessage<Record<string, unknown>>>('/training/validate-config', payload))
