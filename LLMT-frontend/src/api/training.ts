import { del, get, post, unwrap, type ApiMessage, type PageResult } from './http'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// 训练配置字典。大部分字段会透传给后端训练服务，用于构造 PyTorch/DeepSpeed/Megatron 配置。
export interface TrainingConfigDict {
  vocab_size: number
  tokenizer_type: 'gpt2' | 'sentencepiece'
  tokenizer_path: string
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
  enable_dp: boolean
  dp_epsilon: number
  dp_delta: number
  dp_noise_mechanism: 'Gaussian' | 'Laplace'
  dp_noise_multiplier: number | null
  dp_max_grad_norm: number
  deepspeed_overrides: Record<string, unknown> | null
  megatron_overrides: Record<string, unknown> | null
}

// 创建训练任务入参。ModelTraining.vue 会通过 buildTrainingPayload() 组装这个结构。
export interface TrainingTaskCreate {
  task_name: string
  description?: string
  dataset_id: number
  framework: 'pytorch' | 'deepspeed' | 'megatron'
  parallel_strategy: 'ddp' | 'zero1' | 'zero2' | 'zero3' | 'zero3_offload' | 'tp' | 'pp' | '3d'
  config: Partial<TrainingConfigDict>
  base_model_version_id?: number
}

// 扩缩容入参：修改 GPU 数量和可选并行策略。
export interface ScaleTaskRequest {
  gpu_count: number
  parallel_strategy?: string
}

// 训练任务详情结构，比列表项更完整。
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

// 训练任务列表项，用于任务表格渲染。
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

// 通用下拉选项结构，例如训练框架、GPU 资源、并行策略。
export interface OptionItem {
  value: string
  label: string
}

// 数据集下拉选项，value 是后端数据集 id。
export interface DatasetOptionItem {
  value: number
  label: string
}

// 基础模型选项，用于“继续训练”；value 是 ModelVersion.id。
export interface BaseModelOption {
  value: number       // ModelVersion.id
  label: string       // "model_name (version)"
  model_code: string
  version: string
  model_name: string
  hyperparams_json: Record<string, unknown>
}

// 训练配置页需要的所有下拉选项。
export interface TrainingOptions {
  base_models: BaseModelOption[]
  datasets: DatasetOptionItem[]
  frameworks: OptionItem[]
  gpu_options: OptionItem[]
  parallel_strategies: OptionItem[]
}

// 训练日志结构，显示在 ModelTraining.vue 右侧日志面板。
export interface TrainingLog {
  timestamp: string
  level: string
  message: string
  step?: number
}

// 后端配置校验结果。
export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

// 查询训练任务列表。
export const fetchTrainingTasks = (params?: Record<string, string | number>) =>
  get<PageResult<TrainingTaskListItem>>('/training/tasks', params)

// 查询训练任务详情。
export const fetchTrainingTask = (id: number) =>
  get<{ message: string; data: TrainingTask }>(`/training/tasks/${id}`)

// 创建训练任务。
export const createTrainingTask = (body: TrainingTaskCreate) =>
  post<{ message: string; data: TrainingTask }>('/training/tasks', body)

// 取消训练任务。
export const cancelTrainingTask = (id: number) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/cancel`)

// 暂停训练任务。后端会保存 checkpoint，方便后续恢复。
export const pauseTrainingTask = (id: number) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/pause`)

// 恢复暂停中的训练任务。
export const resumeTrainingTask = (id: number) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/resume`)

// 扩缩容训练任务，后端会调整资源配置并重启/恢复任务。
export const scaleTrainingTask = (id: number, body: ScaleTaskRequest) =>
  post<{ message: string; data: TrainingTask }>(`/training/tasks/${id}/scale`, body)

// 获取训练指标，例如 loss、step、吞吐等。
export const fetchTrainingMetrics = (id: number, params?: Record<string, string | number>) =>
  get<{ message: string; data: Record<string, unknown> }>(`/training/tasks/${id}/metrics`, params)

// 获取训练任务 checkpoint 列表。
export const fetchTrainingCheckpoints = (id: number) =>
  get<{ message: string; data: Record<string, unknown> }>(`/training/tasks/${id}/checkpoints`)

// 获取训练日志，可带分页或过滤参数。
export const fetchTrainingLogs = (id: number, params?: Record<string, string | number>) =>
  get<{ message: string; data: { task_id: number; logs: TrainingLog[]; total: number } }>(`/training/tasks/${id}/logs`, params)

// 获取训练配置页下拉选项。
export const fetchTrainingOptions = async () =>
  unwrap(await get<ApiMessage<TrainingOptions>>('/training/options'))

// 获取训练任务状态统计。
export const fetchTrainingStats = async () =>
  unwrap(await get<ApiMessage<Record<string, number>>>('/training/stats'))

// 校验训练配置，不创建任务。
export const validateTrainingConfig = (body: TrainingTaskCreate) =>
  post<{ message: string; data: ValidationResult }>('/training/validate-config', body)

// 将完成的训练任务提升为模型版本，随后可在模型管理中查看。
export const promoteTrainingTask = (id: number) =>
  post<{ message: string; data: Record<string, unknown> }>(`/training/tasks/${id}/promote-to-model`)

// 删除训练任务。
export const deleteTrainingTask = (id: number) =>
  del<{ message: string }>(`/training/tasks/${id}`)
