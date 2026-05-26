import { get, post, del, type PageResult } from './http'

export interface ParticipantConfig {
  participant_id: string
  name: string
  weight: number
  data_size: number
  local_epochs: number
  local_batch_size: number
  local_learning_rate: number
  dataset_id?: number
}

export interface FederatedParticipant {
  id: number
  task_id: number
  participant_id: string
  name: string
  status: string
  weight: number
  data_size: number
  local_epochs: number
  local_batch_size: number
  local_learning_rate: number
  dataset_id?: number
  dataset_name?: string
  last_round_completed?: number
  last_loss?: number
  anomaly_score?: number
  anomaly_details?: Record<string, unknown>
}

/** Lightweight list item returned by GET /federated/tasks */
export interface FederatedTaskListItem {
  id: number
  task_name: string
  task_code: string
  status: string
  model_type: string
  num_rounds: number
  current_round: number
  aggregation_strategy: string
  enable_dp: boolean
  num_participants: number
  best_loss?: number
  started_at?: string
  created_at: string
}

/** Full task detail returned by GET /federated/tasks/:id */
export interface FederatedTask {
  id: number
  task_name: string
  task_code: string
  description?: string
  status: string
  model_type: string
  model_config_json: Record<string, unknown>
  num_rounds: number
  current_round: number
  aggregation_strategy: string
  convergence_threshold: number
  enable_dp: boolean
  dp_epsilon: number
  dp_delta: number
  dp_noise_multiplier: number
  dp_max_grad_norm: number
  config_json: Record<string, unknown>
  best_loss?: number
  final_model_path?: string
  result_json?: Record<string, unknown>
  started_at?: string
  ended_at?: string
  error_message?: string
  created_at: string
  participants: FederatedParticipant[]
}

export interface CreateFederatedTask {
  task_name: string
  description?: string
  model_type: string
  vocab_size: number
  hidden_size: number
  num_layers: number
  num_attention_heads: number
  seq_length: number
  dropout: number
  num_rounds: number
  min_participants: number
  aggregation_strategy: string
  convergence_threshold: number
  max_rounds_no_improve: number
  enable_dp: boolean
  dp_epsilon: number
  dp_delta: number
  dp_noise_multiplier: number
  dp_max_grad_norm: number
  fedprox_mu: number
  anomaly_threshold: number
  auto_remove_malicious: boolean
  checkpoint_dir: string
  save_every_n_rounds: number
  participants: ParticipantConfig[]
}

export const fetchFederatedTasks = (params?: Record<string, string | number>) =>
  get<PageResult<FederatedTaskListItem>>('/federated/tasks', params)

export const fetchFederatedTask = (id: number) =>
  get<{ message: string; data: FederatedTask }>(`/federated/tasks/${id}`)

export const createFederatedTask = (body: CreateFederatedTask) =>
  post<{ message: string; data: FederatedTask }>('/federated/tasks', body)

export const startFederatedTask = (id: number) =>
  post<{ message: string; data: FederatedTask }>(`/federated/tasks/${id}/start`)

export const cancelFederatedTask = (id: number) =>
  post<{ message: string; data: FederatedTask }>(`/federated/tasks/${id}/cancel`)

export const fetchFederatedMetrics = (id: number) =>
  get<{ message: string; data: Record<string, unknown> }>(`/federated/tasks/${id}/metrics`)

export const fetchFederatedLogs = (id: number) =>
  get<{ message: string; data: { task_id: number; logs: unknown[]; total: number } }>(`/federated/tasks/${id}/logs`)

export const addParticipant = (taskId: number, body: ParticipantConfig) =>
  post<{ message: string; data: FederatedParticipant }>(`/federated/tasks/${taskId}/participants`, body)

export const removeParticipant = (taskId: number, participantId: string) =>
  del<{ message: string }>(`/federated/tasks/${taskId}/participants/${participantId}`)

export const deleteFederatedTask = (taskId: number) =>
  del<{ message: string }>(`/federated/tasks/${taskId}`)

export interface DatasetOption {
  id: number
  name: string
  data_type: string
  file_count: number
}

export interface FederatedOptions {
  aggregation_strategies: { value: string; label: string }[]
  model_types: { value: string; label: string }[]
  dp_algorithms: { value: string; label: string }[]
  datasets: DatasetOption[]
}

export const fetchFederatedOptions = () =>
  get<{ message: string; data: FederatedOptions }>('/federated/options')
