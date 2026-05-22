<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">联邦学习</h1>
      <p class="page-description">分布式多方协作训练，通过参数交换实现模型训练，保护数据隐私</p>
    </div>

    <div class="grid-4 stats">
      <div v-for="item in statsData" :key="item.label" class="stat-tile">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <div class="card">
      <div class="card-body">
        <el-tabs v-model="activeTab">
          <!-- 任务列表 -->
          <el-tab-pane label="任务列表" name="list">
            <div class="tab-toolbar">
              <el-button type="primary" @click="showCreateDialog = true">新建联邦任务</el-button>
              <el-button @click="loadTasks">刷新</el-button>
            </div>
            <el-table :data="tasks" stripe v-loading="loading">
              <el-table-column prop="task_code" label="任务代码" width="210" />
              <el-table-column prop="task_name" label="任务名称" min-width="170" />
              <el-table-column prop="model_type" label="模型" width="100" />
              <el-table-column label="轮次" width="100">
                <template #default="{ row }">{{ row.current_round }} / {{ row.num_rounds }}</template>
              </el-table-column>
              <el-table-column label="参与方" width="90">
                <template #default="{ row }">{{ row.num_participants ?? row.participants?.length ?? 0 }}</template>
              </el-table-column>
              <el-table-column label="聚合策略" width="130">
                <template #default="{ row }">{{ strategyLabel(row.aggregation_strategy) }}</template>
              </el-table-column>
              <el-table-column label="差分隐私" width="100">
                <template #default="{ row }">
                  <StatusBadge :label="row.enable_dp ? '已启用' : '未启用'" :type="row.enable_dp ? 'success' : 'info'" />
                </template>
              </el-table-column>
              <el-table-column label="状态" width="120">
                <template #default="{ row }"><StatusBadge :label="statusLabel(row.status)" :type="statusType(row.status)" /></template>
              </el-table-column>
              <el-table-column label="操作" width="240" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" :disabled="row.status !== 'created'" @click="handleStart(row)">启动</el-button>
                  <el-button size="small" :disabled="row.status !== 'running'" type="danger" @click="handleCancel(row)">取消</el-button>
                  <el-button size="small" @click="openDetail(row)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 任务配置 -->
          <el-tab-pane label="创建任务" name="create">
            <div class="grid-2">
              <div class="card">
                <div class="card-header"><h3 class="card-title">模型配置</h3></div>
                <div class="card-body">
                  <el-form label-position="top">
                    <el-form-item label="任务名称">
                      <el-input v-model="form.task_name" placeholder="输入联邦学习任务名称" />
                    </el-form-item>
                    <el-form-item label="模型类型">
                      <el-select v-model="form.model_type" class="full">
                        <el-option label="GPT-2" value="gpt2" />
                        <el-option label="BERT" value="bert" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="隐藏层大小">
                      <el-input-number v-model="form.hidden_size" :min="128" :step="128" />
                    </el-form-item>
                    <el-form-item label="层数">
                      <el-input-number v-model="form.num_layers" :min="1" :max="48" />
                    </el-form-item>
                    <el-form-item label="注意力头数">
                      <el-input-number v-model="form.num_attention_heads" :min="1" :max="32" />
                    </el-form-item>
                    <el-form-item label="序列长度">
                      <el-input-number v-model="form.seq_length" :min="64" :step="128" />
                    </el-form-item>
                  </el-form>
                </div>
              </div>

              <div class="card">
                <div class="card-header"><h3 class="card-title">联邦配置</h3></div>
                <div class="card-body">
                  <el-form label-position="top">
                    <el-form-item label="训练轮数">
                      <el-input-number v-model="form.num_rounds" :min="1" :max="200" />
                    </el-form-item>
                    <el-form-item label="最少参与方">
                      <el-input-number v-model="form.min_participants" :min="1" :max="20" />
                    </el-form-item>
                    <el-form-item label="聚合策略">
                      <el-select v-model="form.aggregation_strategy" class="full">
                        <el-option label="加权 FedAvg (按数据量加权)" value="weighted_fedavg" />
                        <el-option label="FedAvg (均匀平均)" value="fedavg" />
                        <el-option label="FedProx (近端优化)" value="fedprox" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="收敛阈值">
                      <el-input-number v-model="form.convergence_threshold" :min="0.00001" :step="0.0001" :precision="5" />
                    </el-form-item>
                    <el-form-item label="异常检测阈值 (σ)">
                      <el-input-number v-model="form.anomaly_threshold" :min="1" :step="0.5" :precision="1" />
                    </el-form-item>
                    <el-form-item>
                      <el-checkbox v-model="form.auto_remove_malicious">自动移除恶意参与方</el-checkbox>
                    </el-form-item>
                  </el-form>
                </div>
              </div>
            </div>

            <!-- 差分隐私配置 -->
            <div class="card" style="margin-top: 18px">
              <div class="card-header">
                <h3 class="card-title">差分隐私配置</h3>
                <el-switch v-model="form.enable_dp" />
              </div>
              <div class="card-body" v-if="form.enable_dp">
                <div class="grid-2">
                  <el-form label-position="top">
                    <el-form-item label="隐私预算 ε">
                      <el-slider v-model="form.dp_epsilon" :min="0.1" :max="100" :step="0.1" show-input />
                    </el-form-item>
                    <el-form-item label="噪声乘数">
                      <el-slider v-model="form.dp_noise_multiplier" :min="0.1" :max="5" :step="0.1" show-input />
                    </el-form-item>
                  </el-form>
                  <el-form label-position="top">
                    <el-form-item label="隐私保证 δ">
                      <el-input-number v-model="form.dp_delta" :min="0" :max="1" :step="1e-6" :precision="7" />
                    </el-form-item>
                    <el-form-item label="梯度裁剪阈值">
                      <el-input-number v-model="form.dp_max_grad_norm" :min="0.1" :step="0.1" :precision="1" />
                    </el-form-item>
                  </el-form>
                </div>
                <div class="dp-note">
                  <strong>隐私保证说明：</strong>ε 越小隐私保护越强但模型精度越低；噪声乘数越大隐私保护越强但收敛越慢。
                  当前配置下，每轮训练消耗约 ε ≈ {{ dpPerRoundEstimate }} 的隐私预算。
                </div>
              </div>
            </div>

            <!-- 参与方配置 -->
            <div class="card" style="margin-top: 18px">
              <div class="card-header">
                <h3 class="card-title">参与方配置 ({{ form.participants.length }})</h3>
                <el-button type="primary" size="small" @click="addParticipantRow">添加参与方</el-button>
              </div>
              <div class="card-body">
                <div v-for="(p, idx) in form.participants" :key="idx" class="participant-row">
                  <div class="participant-header">
                    <strong>参与方 {{ idx + 1 }}: {{ p.name || p.participant_id }}</strong>
                    <el-button type="danger" size="small" text @click="form.participants.splice(idx, 1)">移除</el-button>
                  </div>
                  <div class="grid-4">
                    <el-form-item label="标识">
                      <el-input v-model="p.participant_id" placeholder="唯一ID" />
                    </el-form-item>
                    <el-form-item label="名称">
                      <el-input v-model="p.name" placeholder="参与方名称" />
                    </el-form-item>
                    <el-form-item label="数据集">
                      <el-select v-model="p.dataset_id" placeholder="选择数据集" clearable class="full" @change="(val: number | undefined) => onDatasetSelect(p, val)">
                        <el-option v-for="ds in datasetOptions" :key="ds.id" :label="ds.name" :value="ds.id" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="数据量">
                      <el-input-number v-model="p.data_size" :min="0" :step="100" />
                    </el-form-item>
                  </div>
                  <div class="grid-4">
                    <el-form-item label="权重">
                      <el-input-number v-model="p.weight" :min="0" :step="0.1" :precision="1" />
                    </el-form-item>
                    <el-form-item label="本地轮数">
                      <el-input-number v-model="p.local_epochs" :min="1" :max="20" />
                    </el-form-item>
                    <el-form-item label="批次大小">
                      <el-input-number v-model="p.local_batch_size" :min="1" :step="8" />
                    </el-form-item>
                    <el-form-item label="学习率">
                      <el-input-number v-model="p.local_learning_rate" :min="0.000001" :step="0.00001" :precision="7" />
                    </el-form-item>
                  </div>
                </div>
                <div v-if="form.participants.length === 0" class="empty-tip">请添加至少 2 个参与方</div>
              </div>
            </div>

            <div class="action-row" style="margin-top: 18px">
              <el-button type="primary" @click="handleCreate" :disabled="form.participants.length < 2">创建联邦任务</el-button>
              <el-button @click="resetForm">重置</el-button>
            </div>
          </el-tab-pane>

          <!-- 训练监控 -->
          <el-tab-pane label="训练监控" name="monitor" :disabled="!selectedTask">
            <template v-if="selectedTask">
              <div class="monitor-row">
                <div v-for="item in monitorItems" :key="item.label" class="monitor-item">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>

              <!-- 参与方状态 -->
              <div class="card" style="margin-top: 18px">
                <div class="card-header">
                  <h3 class="card-title">参与方状态</h3>
                  <el-button size="small" type="primary" @click="showAddParticipantDialog = true" :disabled="selectedTask.status !== 'running'">
                    动态加入
                  </el-button>
                </div>
                <div class="card-body">
                  <el-table :data="selectedTask.participants || []" stripe>
                    <el-table-column prop="participant_id" label="ID" width="120" />
                    <el-table-column prop="name" label="名称" width="140" />
                    <el-table-column label="数据集" width="140">
                      <template #default="{ row }">{{ row.dataset_name ?? (row.dataset_id ? `#${row.dataset_id}` : '-') }}</template>
                    </el-table-column>
                    <el-table-column label="数据量" width="100">
                      <template #default="{ row }">{{ row.data_size?.toLocaleString() }}</template>
                    </el-table-column>
                    <el-table-column prop="weight" label="权重" width="80" />
                    <el-table-column label="状态" width="100">
                      <template #default="{ row }">
                        <StatusBadge :label="row.status === 'active' ? '活跃' : row.status === 'malicious' ? '异常' : '离线'" :type="row.status === 'active' ? 'success' : row.status === 'malicious' ? 'danger' : 'info'" />
                      </template>
                    </el-table-column>
                    <el-table-column label="最近轮次" width="100">
                      <template #default="{ row }">{{ row.last_round_completed ?? '-' }}</template>
                    </el-table-column>
                    <el-table-column label="最近Loss" width="100">
                      <template #default="{ row }">{{ row.last_loss?.toFixed(4) ?? '-' }}</template>
                    </el-table-column>
                    <el-table-column label="异常分数" width="100">
                      <template #default="{ row }">{{ row.anomaly_score?.toFixed(2) ?? '-' }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="100">
                      <template #default="{ row }">
                        <el-button size="small" type="danger" text :disabled="row.status === 'inactive'" @click="handleRemoveParticipant(row)">移除</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>

              <!-- 训练指标图表 -->
              <div class="card" style="margin-top: 18px">
                <div class="card-header"><h3 class="card-title">训练指标</h3></div>
                <div class="card-body">
                  <div class="metrics-grid">
                    <div class="metric-chart" v-for="chart in metricCharts" :key="chart.title">
                      <h4>{{ chart.title }}</h4>
                      <div class="chart-values">
                        <div v-for="(val, i) in chart.values" :key="i" class="chart-bar-row">
                          <span class="chart-label">R{{ i + 1 }}</span>
                          <div class="chart-bar">
                            <div class="chart-fill" :style="{ width: val.percent + '%', background: chart.color }"></div>
                          </div>
                          <span class="chart-value">{{ val.value }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 训练日志 -->
              <div class="card" style="margin-top: 18px">
                <div class="card-header"><h3 class="card-title">训练日志</h3></div>
                <div class="card-body">
                  <div class="log-container">
                    <div v-for="(log, i) in trainingLogs" :key="i" class="log-entry" :class="log.level.toLowerCase()">
                      <span class="log-time">{{ formatTime(log.timestamp) }}</span>
                      <span class="log-level">{{ log.level }}</span>
                      <span class="log-msg">{{ log.message }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </el-tab-pane>

          <!-- 流程说明 -->
          <el-tab-pane label="流程说明" name="guide">
            <div class="card">
              <div class="card-body">
                <div class="flow-steps">
                  <div v-for="(step, i) in flowSteps" :key="i" class="flow-step">
                    <div class="flow-num">{{ i + 1 }}</div>
                    <div class="flow-content">
                      <h4>{{ step.title }}</h4>
                      <p>{{ step.desc }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 创建成功提示对话框 -->
    <el-dialog v-model="showCreateDialog" title="快速创建联邦学习任务" width="560px">
      <el-form label-position="top">
        <el-form-item label="任务名称">
          <el-input v-model="quickForm.task_name" placeholder="例如：多医院协作医疗模型训练" />
        </el-form-item>
        <el-form-item label="参与方数量">
          <el-input-number v-model="quickForm.num_participants" :min="2" :max="10" />
        </el-form-item>
        <el-form-item label="训练轮数">
          <el-input-number v-model="quickForm.num_rounds" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="聚合策略">
          <el-select v-model="quickForm.aggregation_strategy" class="full">
            <el-option label="加权 FedAvg" value="weighted_fedavg" />
            <el-option label="FedAvg" value="fedavg" />
            <el-option label="FedProx" value="fedprox" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="quickForm.enable_dp">启用差分隐私</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleQuickCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 动态加入参与方对话框 -->
    <el-dialog v-model="showAddParticipantDialog" title="动态加入参与方" width="480px">
      <el-form label-position="top">
        <el-form-item label="参与方标识">
          <el-input v-model="newParticipant.participant_id" placeholder="例如：hospital-D" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="newParticipant.name" placeholder="例如：D医院" />
        </el-form-item>
        <el-form-item label="数据集">
          <el-select v-model="newParticipant.dataset_id" placeholder="选择数据集" clearable class="full" @change="(val: number | undefined) => onDatasetSelect(newParticipant, val)">
            <el-option v-for="ds in datasetOptions" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据量">
          <el-input-number v-model="newParticipant.data_size" :min="0" :step="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddParticipantDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAddParticipant">加入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import StatusBadge from '@/components/StatusBadge.vue'
import {
  type CreateFederatedTask,
  type DatasetOption,
  type FederatedTask,
  type FederatedTaskListItem,
  type ParticipantConfig,
  fetchFederatedTasks,
  fetchFederatedTask,
  createFederatedTask,
  startFederatedTask,
  cancelFederatedTask,
  fetchFederatedMetrics,
  fetchFederatedLogs,
  addParticipant,
  removeParticipant,
  fetchFederatedOptions,
} from '@/api/federated'

// State
const activeTab = ref('list')
const loading = ref(false)
const tasks = ref<FederatedTaskListItem[]>([])
const selectedTask = ref<FederatedTask | null>(null)
const showCreateDialog = ref(false)
const showAddParticipantDialog = ref(false)
const trainingLogs = ref<{ timestamp: string; level: string; message: string }[]>([])
const datasetOptions = ref<DatasetOption[]>([])

// Form
const form = reactive<CreateFederatedTask & { min_participants: number; max_rounds_no_improve: number; fedprox_mu: number; anomaly_threshold: number; auto_remove_malicious: boolean; checkpoint_dir: string; save_every_n_rounds: number }>({
  task_name: '多医院协作医疗模型训练',
  description: '联邦学习分布式协作训练任务',
  model_type: 'gpt2',
  vocab_size: 50257,
  hidden_size: 768,
  num_layers: 12,
  num_attention_heads: 12,
  seq_length: 512,
  dropout: 0.1,
  num_rounds: 10,
  min_participants: 2,
  aggregation_strategy: 'weighted_fedavg',
  convergence_threshold: 0.0001,
  max_rounds_no_improve: 3,
  enable_dp: true,
  dp_epsilon: 8.0,
  dp_delta: 1e-5,
  dp_noise_multiplier: 1.1,
  dp_max_grad_norm: 1.0,
  fedprox_mu: 0.01,
  anomaly_threshold: 3.0,
  auto_remove_malicious: false,
  checkpoint_dir: './checkpoints/federated',
  save_every_n_rounds: 1,
  participants: [
    { participant_id: 'hospital-A', name: 'A医院', weight: 1.0, data_size: 5000, local_epochs: 2, local_batch_size: 32, local_learning_rate: 2e-5, dataset_id: undefined },
    { participant_id: 'hospital-B', name: 'B医院', weight: 1.0, data_size: 3000, local_epochs: 2, local_batch_size: 32, local_learning_rate: 2e-5, dataset_id: undefined },
    { participant_id: 'hospital-C', name: 'C医院', weight: 1.0, data_size: 4000, local_epochs: 2, local_batch_size: 32, local_learning_rate: 2e-5, dataset_id: undefined },
  ],
})

const quickForm = reactive({
  task_name: '联邦协作训练任务',
  num_participants: 3,
  num_rounds: 10,
  aggregation_strategy: 'weighted_fedavg',
  enable_dp: true,
})

const newParticipant = reactive<ParticipantConfig>({
  participant_id: '',
  name: '',
  weight: 1.0,
  data_size: 1000,
  local_epochs: 2,
  local_batch_size: 32,
  local_learning_rate: 2e-5,
  dataset_id: undefined,
})

// Computed
const statsData = computed(() => [
  { label: '运行任务', value: String(tasks.value.filter(t => t.status === 'running').length) },
  { label: '总任务数', value: String(tasks.value.length) },
  { label: '活跃参与方', value: String(tasks.value.filter(t => t.status === 'running').reduce((sum, t) => sum + (t.num_participants ?? 0), 0)) },
  { label: '差分隐私', value: tasks.value.some(t => t.enable_dp) ? '已启用' : '未启用' },
])

const monitorItems = computed(() => {
  if (!selectedTask.value) return []
  const t = selectedTask.value
  const progress = t.num_rounds > 0 ? Math.round((t.current_round / t.num_rounds) * 100) : 0
  return [
    { label: '当前轮次', value: `${t.current_round} / ${t.num_rounds}` },
    { label: '活跃参与方', value: String(t.participants?.filter(p => p.status === 'active').length ?? 0) },
    { label: '当前 Loss', value: t.best_loss?.toFixed(4) ?? '-' },
    { label: '训练进度', value: `${progress}%` },
  ]
})

const dpPerRoundEstimate = computed(() => {
  if (!form.enable_dp) return 0
  const n = form.dp_noise_multiplier
  if (n <= 0) return Infinity
  return Math.sqrt(2 * Math.log(1.25 / form.dp_delta)) / n
})

const metricCharts = computed(() => {
  if (!selectedTask.value?.result_json) return []
  const rounds = (selectedTask.value.result_json as Record<string, unknown>).round_results as Array<Record<string, unknown>> ?? []
  if (rounds.length === 0) return []
  const maxLoss = Math.max(...rounds.map((r: Record<string, unknown>) => (r.round_loss as number) ?? 0))

  return [
    {
      title: '每轮训练 Loss',
      color: '#3b82f6',
      values: rounds.map((r: Record<string, unknown>) => ({
        value: ((r.round_loss as number) ?? 0).toFixed(4),
        percent: Math.round(((r.round_loss as number) ?? 0) / maxLoss * 100),
      })),
    },
  ]
})

// Flow steps
const flowSteps = [
  { title: '创建全局模型', desc: '在内存中创建全局模型，耗时5至15秒，写入共享内存' },
  { title: '分发模型参数', desc: '主进程向各模拟参与方分发模型参数，通过共享内存传递' },
  { title: '加载模型', desc: '各模拟参与方加载全局模型，将模型加载至GPU显存' },
  { title: '本地训练', desc: '各模拟参与方串行执行本地训练，依次使用GPU完成前向、反向传播及差分隐私处理' },
  { title: '提交更新', desc: '各模拟参与方提交模型更新（Δw），写入共享内存' },
  { title: '联邦聚合', desc: '主进程收集所有更新，执行联邦聚合（加权平均），生成新全局模型' },
  { title: '更新全局模型', desc: '主进程更新全局模型，写入共享内存' },
  { title: '循环/结束', desc: '重复步骤3-8直到达到训练轮数或收敛条件，保存最终全局模型' },
]

// Methods
const loadTasks = async () => {
  loading.value = true
  try {
    const res = await fetchFederatedTasks()
    tasks.value = res.data ?? []
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  try {
    await createFederatedTask(form)
    ElMessage.success('联邦学习任务已创建')
    activeTab.value = 'list'
    await loadTasks()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '创建失败')
  }
}

const handleQuickCreate = async () => {
  const participants: ParticipantConfig[] = []
  for (let i = 0; i < quickForm.num_participants; i++) {
    const letter = String.fromCharCode(65 + i)
    participants.push({
      participant_id: `participant-${letter}`,
      name: `参与方 ${letter}`,
      weight: 1.0,
      data_size: 2000 + Math.floor(Math.random() * 3000),
      local_epochs: 2,
      local_batch_size: 32,
      local_learning_rate: 2e-5,
      dataset_id: undefined,
    })
  }
  const body: CreateFederatedTask = {
    task_name: quickForm.task_name,
    model_type: 'gpt2',
    vocab_size: 50257,
    hidden_size: 768,
    num_layers: 12,
    num_attention_heads: 12,
    seq_length: 512,
    dropout: 0.1,
    num_rounds: quickForm.num_rounds,
    min_participants: 2,
    aggregation_strategy: quickForm.aggregation_strategy,
    convergence_threshold: 0.0001,
    max_rounds_no_improve: 3,
    enable_dp: quickForm.enable_dp,
    dp_epsilon: 8.0,
    dp_delta: 1e-5,
    dp_noise_multiplier: 1.1,
    dp_max_grad_norm: 1.0,
    fedprox_mu: 0.01,
    anomaly_threshold: 3.0,
    auto_remove_malicious: false,
    checkpoint_dir: './checkpoints/federated',
    save_every_n_rounds: 1,
    participants,
  }
  try {
    await createFederatedTask(body)
    ElMessage.success('联邦学习任务已创建')
    showCreateDialog.value = false
    activeTab.value = 'list'
    await loadTasks()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '创建失败')
  }
}

const handleStart = async (task: FederatedTaskListItem) => {
  try {
    await startFederatedTask(task.id)
    ElMessage.success(`任务 ${task.task_code} 已启动`)
    await loadTasks()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '启动失败')
  }
}

const handleCancel = async (task: FederatedTaskListItem) => {
  try {
    await cancelFederatedTask(task.id)
    ElMessage.success(`任务 ${task.task_code} 已取消`)
    await loadTasks()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '取消失败')
  }
}

const openDetail = async (task: FederatedTaskListItem) => {
  selectedTask.value = task
  activeTab.value = 'monitor'
  try {
    const [detailRes, metricsRes, logsRes] = await Promise.all([
      fetchFederatedTask(task.id),
      fetchFederatedMetrics(task.id),
      fetchFederatedLogs(task.id),
    ])
    // Full task details (includes participants with runtime stats)
    if (detailRes.data) {
      selectedTask.value = detailRes.data as FederatedTask
    }
    // Overlay metrics & logs onto the selected task
    if (metricsRes.data) {
      selectedTask.value = { ...selectedTask.value, result_json: metricsRes.data as Record<string, unknown> }
    }
    if (logsRes.data) {
      trainingLogs.value = (logsRes.data as { logs: { timestamp: string; level: string; message: string }[] }).logs ?? []
    }
  } catch {
    // ignore
  }
}

const handleAddParticipant = async () => {
  if (!selectedTask.value) return
  try {
    await addParticipant(selectedTask.value.id, newParticipant)
    ElMessage.success('参与方已加入')
    showAddParticipantDialog.value = false
    // Re-fetch full task details so participant list is up to date
    const detailRes = await fetchFederatedTask(selectedTask.value.id)
    if (detailRes.data) {
      selectedTask.value = detailRes.data as FederatedTask
    }
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '加入失败')
  }
}

const handleRemoveParticipant = async (participant: { participant_id: string }) => {
  if (!selectedTask.value) return
  try {
    await removeParticipant(selectedTask.value.id, participant.participant_id)
    ElMessage.success('参与方已移除')
    // Re-fetch full task details so participant list is up to date
    const detailRes = await fetchFederatedTask(selectedTask.value.id)
    if (detailRes.data) {
      selectedTask.value = detailRes.data as FederatedTask
    }
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '移除失败')
  }
}

const onDatasetSelect = (p: ParticipantConfig, datasetId: number | undefined) => {
  if (!datasetId) return
  const ds = datasetOptions.value.find(d => d.id === datasetId)
  if (ds && ds.file_count > 0 && p.data_size === 0) {
    p.data_size = ds.file_count * 100  // rough estimate: file_count * 100 samples
  }
}

const addParticipantRow = () => {
  const idx = form.participants.length + 1
  form.participants.push({
    participant_id: `participant-${idx}`,
    name: `参与方 ${idx}`,
    weight: 1.0,
    data_size: 2000,
    local_epochs: 2,
    local_batch_size: 32,
    local_learning_rate: 2e-5,
    dataset_id: undefined,
  })
}

const resetForm = () => {
  form.participants = []
  form.num_rounds = 10
  form.aggregation_strategy = 'weighted_fedavg'
  form.enable_dp = true
}

const strategyLabel = (s: string) => {
  const map: Record<string, string> = { fedavg: 'FedAvg', weighted_fedavg: '加权FedAvg', fedprox: 'FedProx' }
  return map[s] ?? s
}

const statusLabel = (s: string) => {
  const map: Record<string, string> = { created: '已创建', initializing: '初始化', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  return map[s] ?? s
}

const statusType = (s: string): 'success' | 'warning' | 'danger' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = { created: 'info', initializing: 'warning', running: 'success', completed: 'success', failed: 'danger', cancelled: 'info' }
  return map[s] ?? 'info'
}

const formatTime = (ts: string) => {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString()
}

const loadDatasetOptions = async () => {
  try {
    const res = await fetchFederatedOptions()
    datasetOptions.value = res.data?.datasets ?? []
  } catch {
    datasetOptions.value = []
  }
}

onMounted(() => {
  loadTasks()
  loadDatasetOptions()
})
</script>

<style scoped>
.full { width: 100%; }

.stats { margin-bottom: 22px; }

.stat-tile,
.monitor-item,
.recommend-box {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.stat-tile span,
.monitor-item span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.stat-tile strong,
.monitor-item strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
}

.tab-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.monitor-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.grid-4 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.grid-4.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}

.dp-note {
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.participant-row {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.participant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.empty-tip {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.action-row {
  display: flex;
  gap: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Flow steps */
.flow-steps {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.flow-step {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.flow-num {
  display: grid;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary-color, #4f46e5), #3b82f6);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
}

.flow-content h4 {
  margin: 0 0 4px;
  font-size: 15px;
}

.flow-content p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

/* Metrics chart */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 18px;
}

.metric-chart h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--text-secondary);
}

.chart-bar-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.chart-label {
  width: 30px;
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 12px;
}

.chart-bar {
  flex: 1;
  height: 18px;
  border-radius: 4px;
  background: #f1f5f9;
  overflow: hidden;
}

.chart-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}

.chart-value {
  width: 60px;
  flex-shrink: 0;
  color: var(--text-primary);
  font-size: 12px;
  text-align: right;
}

/* Log container */
.log-container {
  max-height: 400px;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #1e293b;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.log-entry {
  display: flex;
  gap: 10px;
  padding: 2px 0;
}

.log-entry.info { color: #94a3b8; }
.log-entry.warn { color: #fbbf24; }
.log-entry.error { color: #f87171; }

.log-time {
  flex-shrink: 0;
  color: #64748b;
}

.log-level {
  width: 42px;
  flex-shrink: 0;
  font-weight: 700;
}

.log-msg {
  flex: 1;
}

@media (max-width: 900px) {
  .grid-2,
  .grid-4,
  .grid-4.stats,
  .monitor-row,
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .grid-2,
  .grid-4,
  .grid-4.stats,
  .monitor-row,
  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
