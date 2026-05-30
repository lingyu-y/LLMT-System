<template>
  <div>
    <!-- 页面头部：说明训练模块的主要操作路径。 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">模型训练</h1>
        <p class="page-description">配置训练参数后直接启动，下方可查看任务进度和训练日志</p>
      </div>
    </div>

    <!-- 统计卡片：按任务状态展示运行、排队、完成、失败/取消数量。 -->
    <div class="grid-4 stats">
      <div v-for="item in trainingStats" :key="item.label" class="stat-tile" :class="item.cls">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <!-- 训练配置：左侧基础信息和超参数，右侧资源策略与操作按钮。 -->
    <div class="card config-card">
      <div class="card-header"><h3 class="card-title">训练配置</h3></div>
      <div class="card-body">
        <div class="config-grid">
          <!-- 左列：任务基本信息、基础模型、数据集和训练超参数。 -->
          <div>
            <el-form label-position="top">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="任务名称">
                    <el-input v-model="form.task_name" placeholder="输入训练任务名称" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="训练框架">
                    <el-select v-model="form.framework" class="full">
                      <el-option v-for="item in options.frameworks" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="基础模型">
                    <el-select
                      v-model="baseModelId"
                      class="full"
                      placeholder="选填，不选则从零训练"
                      clearable
                      @change="onBaseModelChange"
                    >
                      <el-option
                        v-for="item in options.base_models"
                        :key="item.value"
                        :label="item.label"
                        :value="item.value"
                      />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="训练数据集">
                    <el-select v-model="form.dataset_id" class="full" placeholder="选择数据集">
                      <el-option v-for="item in options.datasets" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
            <el-collapse style="margin-top:8px">
              <!-- 可折叠的训练超参数，避免主表单过长。 -->
              <el-collapse-item title="训练超参数（点击展开）" name="hp">
                <el-form label-position="top">
                  <el-row :gutter="12">
                    <el-col :span="8">
                      <el-form-item label="Batch Size">
                        <el-input-number v-model="form.config.batch_size" :min="1" :max="256" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="Learning Rate">
                        <el-input-number v-model="form.config.learning_rate" :min="1e-7" :max="1e-1" :step="1e-5" :precision="6" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="Seq Length">
                        <el-input-number v-model="form.config.seq_length" :min="64" :max="4096" :step="64" style="width:100%" />
                      </el-form-item>
                    </el-col>
                  </el-row>
                  <el-row :gutter="12">
                    <el-col :span="8">
                      <el-form-item label="Max Epochs">
                        <el-input-number v-model="form.config.max_epochs" :min="1" :max="1000" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="Max Steps（0=仅epoch）">
                        <el-input-number v-model="form.config.max_steps" :min="0" :max="100000" :step="100" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="Precision">
                        <el-select v-model="form.config.precision" style="width:100%">
                          <el-option label="FP16" value="fp16" />
                          <el-option label="BF16" value="bf16" />
                          <el-option label="FP32" value="fp32" />
                        </el-select>
                      </el-form-item>
                    </el-col>
                  </el-row>
                </el-form>
              </el-collapse-item>
              <!-- 差分隐私配置：启用后训练侧会尝试进行梯度裁剪和噪声注入。 -->
              <el-collapse-item title="差分隐私保护（点击展开）" name="dp">
                <div class="dp-header">
                  <span>启用后训练 Step 会执行梯度裁剪与噪声注入</span>
                  <el-switch v-model="form.config.enable_dp" />
                </div>
                <el-form v-if="form.config.enable_dp" label-position="top">
                  <el-row :gutter="12">
                    <el-col :span="8">
                      <el-form-item label="ε 隐私预算">
                        <el-input-number v-model="form.config.dp_epsilon" :min="0.01" :max="100" :step="0.1" :precision="2" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="δ 失败概率">
                        <el-input-number v-model="form.config.dp_delta" :min="1e-12" :max="1" :step="1e-6" :precision="8" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="噪声机制">
                        <el-select v-model="form.config.dp_noise_mechanism" style="width:100%">
                          <el-option label="Gaussian" value="Gaussian" />
                          <el-option label="Laplace" value="Laplace" />
                        </el-select>
                      </el-form-item>
                    </el-col>
                  </el-row>
                  <el-row :gutter="12">
                    <el-col :span="8">
                      <el-form-item label="梯度裁剪阈值">
                        <el-input-number v-model="form.config.dp_max_grad_norm" :min="0.1" :max="100" :step="0.1" :precision="1" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="噪声乘数">
                        <el-input-number v-model="form.config.dp_noise_multiplier" :min="0" :max="20" :step="0.1" :precision="2" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="预计每步ε消耗">
                        <el-input :model-value="dpStepEstimate" disabled />
                      </el-form-item>
                    </el-col>
                  </el-row>
                  <el-alert v-if="dpWarning" :title="dpWarning" type="warning" show-icon :closable="false" />
                </el-form>
              </el-collapse-item>
            </el-collapse>
          </div>

          <!-- 右列：GPU 资源、并行策略、推荐策略和提交动作。 -->
          <div>
            <el-form label-position="top">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="GPU 资源">
                    <el-select v-model="gpuOptionValue" class="full" placeholder="选择GPU数量">
                      <el-option v-for="item in options.gpu_options" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="并行策略">
                    <el-select v-model="form.parallel_strategy" class="full" placeholder="选择并行策略">
                      <el-option v-for="item in options.parallel_strategies" :key="item.value" :label="item.label" :value="item.value" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
            <div class="recommend-box">
              <span>系统推荐</span>
              <strong>{{ recommendedStrategy }}</strong>
              <p>{{ resourceAdvice }}</p>
            </div>
            <div class="action-row">
              <el-button type="primary" :icon="VideoPlay" :disabled="!canSubmit" :loading="submitting" @click="startTraining">
                启动训练
              </el-button>
              <el-button :icon="DocumentChecked" :disabled="!canSubmit" @click="handleValidateConfig">验证配置</el-button>
              <el-button @click="handleSaveConfig">保存配置</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 下方区域：左侧任务列表，右侧所选任务日志。 -->
    <div class="bottom-panels">
      <!-- 左侧：训练任务列表，点击行后会加载任务详情和日志。 -->
      <div class="card task-list-card">
        <div class="card-header">
          <h3 class="card-title">训练任务</h3>
          <el-button size="small" @click="loadTasks">刷新</el-button>
        </div>
        <div class="card-body">
          <el-table :data="tasks" stripe v-loading="loading" highlight-current-row
            @row-click="selectTask" :max-height="400">
            <el-table-column prop="task_code" label="任务ID" width="150" />
            <el-table-column prop="task_name" label="名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="framework" label="框架" width="100">
              <template #default="{ row }">{{ frameworkLabel(row.framework) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusBadge :label="statusLabel(row.status)" :type="statusType(row.status)" />
              </template>
            </el-table-column>
            <el-table-column label="进度" width="130">
              <template #default="{ row }">
                <div class="progress-cell">
                  <div class="progress-bar"><div class="progress-fill blue" :style="{ width: `${row.progress}%` }"></div></div>
                  <span>{{ row.progress }}%</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="380" fixed="right">
              <template #default="{ row }">
                <el-button size="small" :disabled="!canPause(row)" :loading="row.status === 'pausing'" @click.stop="handlePause(row)">暂停</el-button>
                <el-button size="small" :disabled="!canResume(row)" :loading="row.status === 'resuming'" @click.stop="handleResume(row)">恢复</el-button>
                <el-button size="small" :disabled="!canScale(row)" @click.stop="openScaleDialog(row)">扩缩容</el-button>
                <el-button size="small" :disabled="row.status !== 'completed'" @click.stop="handlePromote(row)">转为模型</el-button>
                <el-popconfirm title="确定删除此训练任务？" @confirm="handleDeleteTask(row)">
                  <template #reference>
                    <el-button size="small" type="danger" @click.stop>删除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 右侧：训练日志，支持级别筛选、关键词搜索和自动滚动。 -->
      <div class="card log-card">
        <div class="card-header">
          <div class="log-header-left">
            <h3 class="card-title">训练日志</h3>
            <span v-if="selectedTask" class="log-task-badge">{{ selectedTask.task_code }}</span>
          </div>
          <div class="log-header-right">
            <el-select v-model="logLevel" size="small" style="width:100px" clearable placeholder="级别">
              <el-option label="INFO" value="INFO" />
              <el-option label="WARN" value="WARN" />
              <el-option label="ERROR" value="ERROR" />
            </el-select>
            <el-input v-model="logSearch" size="small" style="width:180px" placeholder="搜索日志..." clearable />
            <el-switch v-model="logAutoScroll" size="small" active-text="自动滚动" />
            <el-button size="small" @click="clearLogs">清空</el-button>
          </div>
        </div>
        <div class="card-body log-body" ref="logContainer">
          <!-- 任务完成差分隐私训练后，后端可能在 config_json 中回填审计报告。 -->
          <div v-if="selectedPrivacyReport" class="privacy-report">
            <div><span>隐私预算</span><strong>{{ selectedPrivacyReport.spent_epsilon }} / {{ selectedPrivacyReport.total_epsilon }}</strong></div>
            <div><span>δ</span><strong>{{ selectedPrivacyReport.delta }}</strong></div>
            <div><span>噪声</span><strong>{{ selectedPrivacyReport.noise_mechanism }}</strong></div>
            <div><span>状态</span><strong>{{ selectedPrivacyReport.budget_exhausted ? '预算耗尽' : '已生成' }}</strong></div>
          </div>
          <div v-if="!selectedTask" class="log-empty">点击任务列表中的任务查看训练日志</div>
          <div v-else-if="filteredLogs.length === 0" class="log-empty">暂无日志</div>
          <div v-else ref="logScroll" class="log-container">
            <div v-for="(log, i) in filteredLogs" :key="i" class="log-entry" :class="log.level.toLowerCase()">
              <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              <span class="log-level">{{ log.level }}</span>
              <span class="log-msg">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 扩缩容弹窗：对运行中或暂停中的任务修改 GPU 数和并行策略。 -->
    <el-dialog v-model="scaleDialogVisible" title="训练任务扩缩容" width="520px">
      <el-form label-position="top">
        <el-form-item label="任务">
          <el-input :model-value="scaleTarget ? `${scaleTarget.task_code} / ${scaleTarget.task_name}` : ''" disabled />
        </el-form-item>
        <el-form-item label="当前配置">
          <span class="scale-current">{{ scaleCurrentCfg }}</span>
        </el-form-item>
        <el-form-item label="目标 GPU 数量">
          <el-select v-model="scaleForm.gpu_count" class="full" @change="onScaleGpuChange">
            <el-option v-for="item in scaleGpuOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标并行策略">
          <el-select v-model="scaleForm.parallel_strategy" class="full" placeholder="选择策略">
            <el-option v-for="item in scaleStrategies" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-alert v-if="scaleWarning" :title="scaleWarning" type="warning" show-icon :closable="false" style="margin-top:8px" />
      </el-form>
      <template #footer>
        <el-button @click="scaleDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!canSubmitScale" :loading="scaleSubmitting" @click="submitScale">确认扩缩容并重启</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, VideoPlay } from '@element-plus/icons-vue'

import {
  createTrainingTask,
  deleteTrainingTask,
  pauseTrainingTask,
  resumeTrainingTask,
  scaleTrainingTask,
  validateTrainingConfig,
  promoteTrainingTask,
  fetchTrainingTasks,
  fetchTrainingTask,
  fetchTrainingOptions,
  fetchTrainingStats,
  fetchTrainingLogs,
  type TrainingOptions,
  type TrainingTaskListItem,
  type TrainingLog,
} from '@/api/training'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatBeijingTime } from '@/utils/time'

// ── State ──
// 训练配置草稿保存在 localStorage，方便刷新页面后恢复表单。
const TRAINING_CONFIG_STORAGE_KEY = 'llmt_training_config_draft'

// 页面级加载与提交状态。
const loading = ref(false)
const submitting = ref(false)

// 任务列表、当前选中任务和其日志。
const tasks = ref<TrainingTaskListItem[]>([])
const selectedTask = ref<TrainingTaskListItem | null>(null)
const trainingLogs = ref<TrainingLog[]>([])

// 扩缩容弹窗状态和当前目标任务。
const scaleDialogVisible = ref(false)
const scaleTarget = ref<TrainingTaskListItem | null>(null)

// 任务状态统计、日志筛选条件和自动滚动配置。
const statsCounts = ref<Record<string, number>>({})
const logLevel = ref('')
const logSearch = ref('')
const logAutoScroll = ref(true)
const logScroll = ref<HTMLDivElement>()
const logContainer = ref<HTMLDivElement>()
let refreshTimer: number | null = null

// 训练选项来自后端 /training/options；这里提供默认值，后端接口失败时页面仍可使用。
const options = reactive<TrainingOptions>({
  base_models: [],
  datasets: [],
  frameworks: [
    { value: 'pytorch', label: 'PyTorch' },
    { value: 'deepspeed', label: 'DeepSpeed' },
    { value: 'megatron', label: 'Megatron-LM' },
  ],
  gpu_options: [
    { value: '1', label: '1 × GPU' }, { value: '2', label: '2 × GPU' },
    { value: '4', label: '4 × GPU' }, { value: '8', label: '8 × GPU' },
  ],
  parallel_strategies: [
    { value: 'ddp', label: 'DDP' }, { value: 'zero1', label: 'ZeRO Stage 1' },
    { value: 'zero2', label: 'ZeRO Stage 2' }, { value: 'zero3', label: 'ZeRO Stage 3' },
    { value: 'zero3_offload', label: 'ZeRO-3 + Offload' },
    { value: 'tp', label: '张量并行 (TP)' }, { value: 'pp', label: '流水线并行 (PP)' },
    { value: '3d', label: '3D 混合并行' },
  ],
})

// GPU 选择控件使用字符串值，提交前会转换为数字。
const gpuOptionValue = ref('1')

// 选择基础模型时表示继续训练；为空表示从零训练。
const baseModelId = ref<number | undefined>(undefined)

// 训练任务表单。config 会作为后端训练配置透传给训练服务。
const form = reactive({
  task_name: '',
  dataset_id: undefined as number | undefined,
  framework: 'pytorch' as 'pytorch' | 'deepspeed' | 'megatron',
  parallel_strategy: 'ddp' as string,
  config: {
    vocab_size: 32000, tokenizer_type: 'sentencepiece' as 'gpt2' | 'sentencepiece', tokenizer_path: 'tokenizers/industry_spm.model',
    hidden_size: 384, num_layers: 6, num_attention_heads: 6, num_gpus: 1,
    batch_size: 1, learning_rate: 2e-5,
    max_epochs: 10, max_steps: 0, seq_length: 128, precision: 'fp16' as const,
    enable_dp: false,
    dp_epsilon: 8.0,
    dp_delta: 1e-5,
    dp_noise_mechanism: 'Gaussian' as 'Gaussian' | 'Laplace',
    dp_noise_multiplier: 1.1 as number | null,
    dp_max_grad_norm: 1.0,
  },
})

// 扩缩容表单：修改目标 GPU 数和并行策略。
const scaleForm = reactive({ gpu_count: 1, parallel_strategy: 'ddp' as string })
const scaleSubmitting = ref(false)

// ── Scale helpers ──
// 任务操作按钮可用性判断。
const canPause = (row: TrainingTaskListItem) => row.status === 'running'
const canResume = (row: TrainingTaskListItem) => row.status === 'paused'
const canScale = (row: TrainingTaskListItem) =>
  row.status === 'running' || row.status === 'paused'

// 扩缩容弹窗可选 GPU 数，优先使用后端返回的资源选项。
const scaleGpuOptions = computed(() => {
  if (options.gpu_options.length > 0) return options.gpu_options.map(o => ({ value: Number(o.value), label: o.label }))
  return [1, 2, 4, 8].map(n => ({ value: n, label: `${n} × GPU` }))
})

// 根据目标 GPU 数限制可选并行策略，避免明显不合理的组合。
const scaleStrategies = computed(() => {
  const n = scaleForm.gpu_count
  if (n <= 1) {
    return [{ value: 'ddp', label: 'DDP（单卡）' }]
  }
  if (n === 2) {
    return [
      { value: 'ddp', label: 'DDP' },
      { value: 'zero1', label: 'ZeRO Stage 1' },
      { value: 'zero2', label: 'ZeRO Stage 2' },
    ]
  }
  // 4+ GPUs
  return options.parallel_strategies
})

// 扩缩容配置风险提示。
const scaleWarning = computed(() => {
  if (scaleForm.gpu_count <= 1 && scaleForm.parallel_strategy !== 'ddp') {
    return '单卡只能使用 DDP 策略'
  }
  if (scaleForm.gpu_count === 2 && ['zero3', 'zero3_offload', 'tp', 'pp', '3d'].includes(scaleForm.parallel_strategy)) {
    return '2 卡不建议使用该策略，可能内存不足'
  }
  return ''
})

// 当前任务配置摘要，用于扩缩容弹窗展示。
const scaleCurrentCfg = computed(() => {
  if (!scaleTarget.value) return ''
  const cfg = scaleTarget.value.config_json || {} as Record<string, unknown>
  const gpu = cfg.num_gpus ?? 1
  return `${gpu} GPU · ${scaleTarget.value.parallel_strategy || 'ddp'}`
})

// 只有 GPU 数或并行策略发生变化时才允许提交扩缩容。
const canSubmitScale = computed(() => {
  if (!scaleTarget.value) return false
  const curGpu = (scaleTarget.value.config_json as Record<string, unknown> | null)?.num_gpus ?? 1
  const curStrat = scaleTarget.value.parallel_strategy || 'ddp'
  // At least one thing changed
  return scaleForm.gpu_count !== curGpu || scaleForm.parallel_strategy !== curStrat
})

// 打开扩缩容弹窗，并用当前任务配置初始化表单。
const openScaleDialog = (row: TrainingTaskListItem) => {
  scaleTarget.value = row
  const cfg = (row.config_json || {}) as Record<string, unknown>
  scaleForm.gpu_count = (cfg.num_gpus as number) || Number((row.gpu_display || '1').charAt(0)) || 1
  scaleForm.parallel_strategy = row.parallel_strategy || 'ddp'
  scaleDialogVisible.value = true
}

// GPU 数变化后，如果原策略不可用，则自动切到第一个合法策略。
const onScaleGpuChange = () => {
  const valid = scaleStrategies.value.map(s => s.value)
  if (!valid.includes(scaleForm.parallel_strategy)) {
    scaleForm.parallel_strategy = valid[0]!
  }
}

// 提交扩缩容请求，后端会负责暂停/重启任务。
const submitScale = async () => {
  if (!scaleTarget.value || !canSubmitScale.value) return
  scaleSubmitting.value = true
  try {
    await scaleTrainingTask(scaleTarget.value.id, {
      gpu_count: scaleForm.gpu_count,
      parallel_strategy: scaleForm.parallel_strategy,
    })
    ElMessage.success(`已提交 ${scaleTarget.value.task_code} 的扩缩容请求，任务将暂停并重启`)
    scaleDialogVisible.value = false
    await loadTasks()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '扩缩容失败')
  } finally {
    scaleSubmitting.value = false
  }
}

// ── Computed ──
// 创建训练任务的最小条件：任务名和数据集。
const canSubmit = computed(() => form.task_name && form.dataset_id)

// 顶部统计卡片数据，由后端状态计数转换而来。
const trainingStats = computed(() => {
  const c = statsCounts.value
  return [
    { label: '运行', value: String(c.running ?? 0), cls: 'running' },
    { label: '排队', value: String(c.queued ?? 0), cls: 'queued' },
    { label: '已完成', value: String(c.completed ?? 0), cls: 'completed' },
    { label: '失败/取消', value: String((c.failed ?? 0) + (c.cancelled ?? 0)), cls: 'failed' },
  ]
})

// 日志筛选：按级别和关键词在前端本地过滤。
const filteredLogs = computed(() => {
  let logs = trainingLogs.value
  if (logLevel.value) logs = logs.filter(l => l.level.toUpperCase() === logLevel.value!.toUpperCase())
  if (logSearch.value) {
    const q = logSearch.value.toLowerCase()
    logs = logs.filter(l => l.message.toLowerCase().includes(q))
  }
  return logs
})

// 差分隐私审计报告，从所选任务 config_json 中读取。
const selectedPrivacyReport = computed(() => {
  const report = selectedTask.value?.config_json?.privacy_audit_report
  return report && typeof report === 'object' ? report as Record<string, any> : null
})

// 根据框架和 GPU 数给出推荐策略文案。
const recommendedStrategy = computed(() => {
  const n = Number(gpuOptionValue.value)
  if (form.framework === 'megatron') return '张量并行 + 流水线并行'
  if (n <= 1) return 'DDP (单卡)'
  return 'ZeRO Stage 2 (推荐)'
})

// 根据 GPU 数给出资源使用建议。
const resourceAdvice = computed(() => {
  const n = Number(gpuOptionValue.value)
  if (n <= 1) return '单卡适合小规模微调，建议使用 DDP。'
  return '当前资源满足混合并行训练，可在任务运行中发起扩缩容请求。'
})

// 前端估算每步隐私预算消耗，仅用于提示；最终结果以训练后端审计报告为准。
const dpStepEstimate = computed(() => {
  if (!form.config.enable_dp) return '-'
  const delta = Math.max(form.config.dp_delta || 1e-5, 1e-12)
  const multiplier = form.config.dp_noise_multiplier || Math.sqrt(2 * Math.log(1.25 / delta)) / Math.max(form.config.dp_epsilon, 0.01)
  if (form.config.dp_noise_mechanism === 'Laplace') {
    return (1 / Math.max(form.config.dp_epsilon, 0.01)).toFixed(4)
  }
  return (Math.sqrt(2 * Math.log(1.25 / delta)) / Math.max(multiplier, 1e-6)).toFixed(4)
})

// 差分隐私配置提示，避免用户选择明显不推荐的参数。
const dpWarning = computed(() => {
  if (!form.config.enable_dp) return ''
  if (form.framework !== 'pytorch') return '当前普通训练的梯度加噪仅在 PyTorch/DDP 路径生效'
  if (form.config.dp_epsilon < 1 || form.config.dp_epsilon > 10) return '推荐 ε 范围为 1.0-10.0'
  if (form.config.dp_delta < 1e-6 || form.config.dp_delta > 1e-5) return '推荐 δ 范围为 1e-6 到 1e-5'
  return ''
})

// ── Align parallel_strategy with framework on change ──
// 切换训练框架时自动切换默认并行策略。
const strategyDefaults: Record<string, string> = { pytorch: 'ddp', deepspeed: 'zero2', megatron: 'tp' }
watch(() => form.framework, (fw) => {
  form.parallel_strategy = strategyDefaults[fw] ?? 'ddp'
})

// ── Auto-scroll logs ──
// 日志更新后，如果启用自动滚动，则滚到日志容器底部。
watch(filteredLogs, () => {
  if (logAutoScroll.value) {
    nextTick(() => {
      logContainer.value?.scrollTo({ top: logContainer.value.scrollHeight, behavior: 'smooth' })
    })
  }
})

// ── Methods ──
// 加载训练表单下拉选项：基础模型、数据集、框架、GPU、并行策略。
const loadOptions = async () => {
  try {
    const res = await fetchTrainingOptions()
    if (res) {
      if (res.base_models?.length) options.base_models = res.base_models as any
      if (res.datasets?.length) options.datasets = res.datasets
      if (res.frameworks?.length) options.frameworks = res.frameworks
      if (res.gpu_options?.length) options.gpu_options = res.gpu_options
      if (res.parallel_strategies?.length) options.parallel_strategies = res.parallel_strategies
    }
  } catch { /* use defaults */ }
}

// 加载训练任务列表。
const loadTasks = async () => {
  loading.value = true
  try { const res = await fetchTrainingTasks(); tasks.value = res.data ?? [] }
  catch { tasks.value = [] }
  finally { loading.value = false }
}

// 加载任务状态计数，用于顶部统计卡片。
const loadStats = async () => {
  try { const res = await fetchTrainingStats(); statsCounts.value = (res ?? {}) as Record<string, number> }
  catch { /* ignore */ }
}

// 加载所选训练任务日志。
const loadLogs = async (taskId: number) => {
  try { const res = await fetchTrainingLogs(taskId); trainingLogs.value = res.data?.logs ?? [] }
  catch { trainingLogs.value = [] }
}

// 选择任务：先更新选中项，再拉任务详情和日志。
const selectTask = async (row: TrainingTaskListItem) => {
  selectedTask.value = row
  try { const res = await fetchTrainingTask(row.id); if (res.data) Object.assign(row, res.data) }
  catch { /* ignore */ }
  await loadLogs(row.id)
}

// 选择基础模型时，将模型超参数同步到训练配置，保证继续训练结构一致。
const onBaseModelChange = (selectedId: number | undefined) => {
  if (selectedId == null) return
  const found = options.base_models.find(m => m.value === selectedId)
  if (!found) return
  const hp = found.hyperparams_json || {}
  const baseTokenizer = hp.tokenizer_type
  const baseVocabSize = Number(hp.vocab_size || 0)
  if ((baseTokenizer && baseTokenizer !== 'sentencepiece') || (baseVocabSize && baseVocabSize !== 32000)) {
    ElMessage.warning('当前系统只支持继续训练 SentencePiece 模型，请选择使用 SentencePiece 训练出的模型版本')
    baseModelId.value = undefined
    return
  }
  if (hp.hidden_size != null) form.config.hidden_size = hp.hidden_size as number
  if (hp.num_layers != null) form.config.num_layers = hp.num_layers as number
  if (hp.num_attention_heads != null) form.config.num_attention_heads = hp.num_attention_heads as number
  form.config.vocab_size = 32000
  form.config.tokenizer_type = 'sentencepiece'
  form.config.tokenizer_path = 'tokenizers/industry_spm.model'
  if (hp.seq_length != null) form.config.seq_length = hp.seq_length as number
}

// 只清空当前页面日志，不影响后端日志。
const clearLogs = () => { trainingLogs.value = [] }

// 组装提交给后端的训练任务 payload，统一固定 tokenizer 相关配置。
const buildTrainingPayload = () => {
  const gpuCount = Number(gpuOptionValue.value)
  const cfg: Record<string, any> = { ...form.config, num_gpus: gpuCount }
  cfg.vocab_size = 32000
  cfg.tokenizer_type = 'sentencepiece'
  cfg.tokenizer_path = 'tokenizers/industry_spm.model'
  if (!cfg.max_steps) delete cfg.max_steps
  return {
    task_name: form.task_name, dataset_id: form.dataset_id!, framework: form.framework,
    parallel_strategy: form.parallel_strategy as any,
    config: cfg,
    ...(baseModelId.value != null ? { base_model_version_id: baseModelId.value } : {}),
  }
}

// 创建训练任务。
const startTraining = async () => {
  if (!canSubmit.value) { ElMessage.warning('请填写任务名称并选择数据集'); return }
  submitting.value = true
  try {
    const payload: any = buildTrainingPayload()
    const res = await createTrainingTask(payload)
    ElMessage.success(`训练任务已创建: ${res.data?.task_code ?? ''}`)
    await loadTasks(); await loadStats()
  } catch (e: unknown) { ElMessage.error((e as Error).message || '创建失败') }
  finally { submitting.value = false }
}

// 暂停训练任务。
const handlePause = async (row: TrainingTaskListItem) => {
  try { await pauseTrainingTask(row.id); ElMessage.success(`已暂停 ${row.task_code}`); await loadTasks(); await loadStats() }
  catch (e: unknown) { ElMessage.error((e as Error).message || '暂停失败') }
}

// 恢复训练任务。
const handleResume = async (row: TrainingTaskListItem) => {
  try { await resumeTrainingTask(row.id); ElMessage.success(`已恢复 ${row.task_code}`); await loadTasks(); await loadStats() }
  catch (e: unknown) { ElMessage.error((e as Error).message || '恢复失败') }
}

// 将已完成训练任务提升为模型版本，后续可在模型管理页面查看。
const handlePromote = async (row: TrainingTaskListItem) => {
  try {
    const res = await promoteTrainingTask(row.id)
    ElMessage.success(`已转为模型版本: ${(res.data as any)?.model_code ?? ''}`)
    await loadTasks(); await loadStats()
  } catch (e: unknown) { ElMessage.error((e as Error).message || '转为模型失败') }
}

// 删除训练任务。
const handleDeleteTask = async (row: TrainingTaskListItem) => {
  try { await deleteTrainingTask(row.id); ElMessage.success(`已删除 ${row.task_code}`); await loadTasks(); await loadStats() }
  catch (e: unknown) { ElMessage.error((e as Error).message || '删除失败') }
}

// 保存当前训练配置草稿到浏览器，方便下次打开页面继续编辑。
const handleSaveConfig = () => {
  localStorage.setItem(TRAINING_CONFIG_STORAGE_KEY, JSON.stringify({
    form,
    gpuOptionValue: gpuOptionValue.value,
    baseModelId: baseModelId.value ?? null,
    savedAt: new Date().toISOString(),
  }))
  ElMessage.success(`配置已保存到浏览器 localStorage：${TRAINING_CONFIG_STORAGE_KEY}`)
}

// 调后端配置校验接口，提前发现训练配置错误或警告。
const handleValidateConfig = async () => {
  if (!canSubmit.value) { ElMessage.warning('请先填写任务名称和数据集'); return }
  try {
    const body = buildTrainingPayload()
    const res = await validateTrainingConfig(body)
    const result = res.data
    if (result?.valid) ElMessage.success('配置验证通过')
    else ElMessage.warning([...(result?.errors ?? []), ...(result?.warnings ?? [])].join('；') || '配置存在问题')
  } catch (e: unknown) { ElMessage.error((e as Error).message || '验证失败') }
}

// ── Helpers ──
// 日志时间统一按北京时间显示。
const formatTime = (ts: string) => formatBeijingTime(ts)
const frameworkLabel = (f?: string) => ({ pytorch: 'PyTorch', deepspeed: 'DeepSpeed', megatron: 'Megatron-LM' } as Record<string, string>)[f ?? ''] ?? f ?? '-'
const statusLabel = (s: string) => ({ created: '已创建', queued: '排队中', running: '运行中', pausing: '暂停中…', paused: '已暂停', resuming: '恢复中…', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[s] ?? s
const statusType = (s: string): 'success' | 'warning' | 'danger' | 'info' => ({ created: 'info', queued: 'warning', running: 'success', pausing: 'warning', paused: 'warning', resuming: 'info', completed: 'success', failed: 'danger', cancelled: 'info' } as Record<string, any>)[s] ?? 'info'

// ── Lifecycle ──
onMounted(() => {
  // 页面打开时先恢复本地保存的训练配置草稿。
  const saved = localStorage.getItem(TRAINING_CONFIG_STORAGE_KEY)
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (parsed?.form) {
        const { config, ...rest } = parsed.form
        Object.assign(form, rest)
        Object.assign(form.config, config ?? {})
      }
      if (parsed?.gpuOptionValue) gpuOptionValue.value = parsed.gpuOptionValue
      if (parsed?.baseModelId != null) baseModelId.value = parsed.baseModelId
    } catch {
      localStorage.removeItem(TRAINING_CONFIG_STORAGE_KEY)
    }
  }

  // 初次加载下拉选项、任务列表和状态统计。
  loadOptions(); loadTasks(); loadStats()

  // 训练任务是长任务，使用定时轮询刷新任务状态、统计和当前任务日志。
  refreshTimer = window.setInterval(async () => {
    await loadTasks(); await loadStats()
    if (selectedTask.value) await loadLogs(selectedTask.value.id)
  }, 5000)
})

onBeforeUnmount(() => {
  // 离开页面时清理轮询，避免后台继续请求接口。
  if (refreshTimer !== null) { window.clearInterval(refreshTimer); refreshTimer = null }
})
</script>

<style scoped>
.full { width: 100%; }

.stats { margin-bottom: 20px; }
.stat-tile {
  display: flex; flex-direction: column; gap: 8px; padding: 18px 22px;
  border-radius: 12px; background: #fff; border: 1px solid var(--border-color);
}
.stat-tile.running { border-left: 4px solid var(--primary-color); }
.stat-tile.queued { border-left: 4px solid #f59e0b; }
.stat-tile.completed { border-left: 4px solid #10b981; }
.stat-tile.failed { border-left: 4px solid #ef4444; }
.stat-tile span { font-size: 13px; color: var(--text-muted); }
.stat-tile strong { font-size: 24px; font-weight: 700; }

.config-card { margin-bottom: 20px; }
.config-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 32px;
}

.recommend-box {
  margin-top: 16px; padding: 14px;
  border-radius: 8px; background: var(--bg-color);
}
.recommend-box span { font-size: 12px; color: var(--text-muted); display: block; }
.recommend-box strong { font-size: 15px; }
.recommend-box p { margin: 6px 0 0; font-size: 13px; color: var(--text-secondary); }

.dp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  color: var(--text-secondary);
  font-size: 13px;
}

.action-row {
  display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap;
}

/* bottom panels: task list + logs side by side */
.bottom-panels {
  display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
}

.task-list-card .card-body { padding: 0 16px 16px; }
.progress-cell { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.progress-bar {
  flex: 1; height: 6px; border-radius: 3px; background: #e2e8f0; overflow: hidden;
}
.progress-fill { height: 100%; }
.progress-fill.blue { background: var(--primary-color); }

/* log viewer */
.log-card .card-header {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 10px;
}
.log-header-left { display: flex; align-items: center; gap: 10px; }
.log-task-badge {
  font-size: 12px; padding: 2px 8px; border-radius: 4px;
  background: var(--primary-color); color: #fff;
}
.log-header-right {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.log-body {
  padding: 0 !important;
  max-height: 360px; overflow-y: auto;
}
.privacy-report {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 12px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border-color);
}
.privacy-report div {
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #fff;
}
.privacy-report span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}
.privacy-report strong {
  display: block;
  margin-top: 4px;
  font-size: 14px;
}
.log-empty {
  padding: 40px; text-align: center; color: var(--text-muted); font-size: 14px;
}
.log-container {
  background: #1e293b; padding: 14px; min-height: 200px;
  font-family: 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.6;
}
.log-entry {
  display: flex; gap: 12px; padding: 3px 0; border-bottom: 1px solid #334155;
}
.log-entry.info .log-level { color: #93c5fd; }
.log-entry.warn .log-level { color: #fcd34d; }
.log-entry.error .log-level { color: #fca5a5; }
.log-entry.error { background: rgb(239 68 68 / 8%); }
.log-time { color: #64748b; flex-shrink: 0; min-width: 70px; }
.log-level { color: #93c5fd; flex-shrink: 0; min-width: 44px; font-weight: 600; }
.log-msg { color: #cbd5e1; word-break: break-all; }

@media (max-width: 900px) {
  .config-grid { grid-template-columns: 1fr; }
  .bottom-panels { grid-template-columns: 1fr; }
  .privacy-report { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
