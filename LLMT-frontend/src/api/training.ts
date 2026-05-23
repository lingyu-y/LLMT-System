import { get, post, type PageResult } from './http'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TrainingConfigDict {
  model_type: string
  vocab_size: number
  hidden_size: number
  num_layers: number
  num_attention_heads: number
  seq_length: number
  batch_size: number
  learning_rate: number
  weight_decay: number
  max_epochs: number
  max_steps: number | null
  warmup_steps: number
  max_grad_norm: number
  gradient_accumulation_steps: number
  optimizer: string
  scheduler: string
  precision: string
  min_lr: number
  beta1: number
  beta2: number
  dataset_path: string | null
  dataset_format: string
  train_split: number
  seed: number
  num_gpus: number
  num_nodes: number
  tensor_model_parallel_size: number
  pipeline_model_parallel_size: number
  save_interval: number
  eval_interval: number
  max_checkpoints: number
  upload_to_minio: boolean
  deepspeed_overrides: Record<string, unknown> | null
  megatron_overrides: Record<string, unknown> | null
}

export interface TrainingTaskCreate {
  task_name: string
  description?: string
  dataset_id: number
  framework: 'pytorch' | 'deepspeed' | 'megatron'
  parallel_strategy: 'ddp' | 'zero1' | 'zero2' | 'zero3' | 'zero3_offload' | 'tp' | 'pp' | '3d'
  config: Partial<TrainingConfigDict>
}

export interface ScaleTaskRequest {
  gpu_count: number
  parallel_strategy?: string
}

export interface TrainingTask {
  id: number
  task_name: string
  task_code: string
  description?: string
  status: string
  framework?: string
  parallel_strategy?: string
  config_json: Record<string, unknown>
  current_epoch: number
  current_step: number
  max_epoch?: number
  dataset_id: number
  checkpoint_path?: string
  error_message?: string
  celery_task_id?: string
  started_at?: string
  ended_at?: string
  created_at: string
}

export interface TrainingTaskListItem {
  id: number
  task_name: string
  task_code: string
  status: string
  framework?: string
  parallel_strategy?: string
  current_epoch: number
  current_step: number
  max_epoch?: number
  dataset_id: number
  config_json: Record<string, unknown>
  created_at: string
  progress: number
  gpu_display: string
  error_message?: string
}

export interface OptionItem {
  value: string
  label: string
}

export interface DatasetOptionItem {
  value: number
  label: string
}

export interface TrainingOptions {
  models: OptionItem[]
  datasets: DatasetOptionItem[]
  frameworks: OptionItem[]
  gpu_options: OptionItem[]
  parallel_strategies: OptionItem[]
}

export interface TrainingLog {
  timestamp: string
  level: string
  message: string
  step?: number
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export const fetchTrainingTasks = (params?: Record<string, string | number>) =>
  get<PageResult<TrainingTaskListItem>>('/training/tasks', params)

export const fetchTrainingTask = (id: number) =>
  get<{ message: string; data: TrainingTask }>(`/training/tasks/${id}`)

export const createTrainingTask = (body: TrainingTaskCreate) =>
  post<{ message: string; data: TrainingTask }>('/training/tasks', body)

export const cancelTrainingTask = (id: number) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/cancel`)

export const pauseTrainingTask = (id: number) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/pause`)

export const resumeTrainingTask = (id: number) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/resume`)

export const scaleTrainingTask = (id: number, body: ScaleTaskRequest) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/scale`, body)

export const fetchTrainingMetrics = (id: number, params?: Record<string, string | number>) =>
  get<{ message: string; data: Record<string, unknown> }>(`/training/tasks/${id}/metrics`, params)

export const fetchTrainingCheckpoints = (id: number) =>
  get<{ message: string; data: Record<string, unknown> }>(`/training/tasks/${id}/checkpoints`)

export const fetchTrainingLogs = (id: number, params?: Record<string, string | number>) =>
  get<{ message: string; data: { task_id: number; logs: TrainingLog[]; total: number } }>(`/training/tasks/${id}/logs`, params)

export const fetchTrainingOptions = () =>
  get<{ message: string; data: TrainingOptions }>('/training/options')

export const fetchTrainingStats = () =>
  get<{ message: string; data: Record<string, number> }>('/training/stats')

export const validateTrainingConfig = (body: TrainingTaskCreate) =>
  post<{ message: string; data: ValidationResult }>('/training/validate-config', body)

export const promoteTrainingTask = (id: number) =>
  post<{ message: string; data: Record<string, unknown> }>(`/training/tasks/${id}/promote-to-model`)
