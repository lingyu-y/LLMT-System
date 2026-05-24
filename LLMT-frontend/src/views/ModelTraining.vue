<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">模型训练</h1>
        <p class="page-description">配置训练参数后直接启动，下方可查看任务进度和训练日志</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="grid-4 stats">
      <div v-for="item in trainingStats" :key="item.label" class="stat-tile" :class="item.cls">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <!-- 训练配置 -->
    <div class="card config-card">
      <div class="card-header"><h3 class="card-title">训练配置</h3></div>
      <div class="card-body">
        <div class="config-grid">
          <!-- 左列 -->
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
                  <el-form-item label="训练模型">
                    <el-select v-model="form.config.model_type" class="full" placeholder="选择模型">
                      <el-option v-for="item in options.models" :key="item.value" :label="item.label" :value="item.value" />
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
              <el-collapse-item title="训练超参数（点击展开）" name="hp">
                <el-form label-position="top">
                  <el-row :gutter="12">
                    <el-col :span="12">
                      <el-form-item label="Hidden Size（768=标准, 384=轻量）">
                        <el-input-number v-model="form.config.hidden_size" :min="128" :max="2048" :step="64" style="width:100%" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="12">
                      <el-form-item label="Num Layers（12=标准, 6=轻量）">
                        <el-input-number v-model="form.config.num_layers" :min="2" :max="48" style="width:100%" />
                      </el-form-item>
                    </el-col>
                  </el-row>
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
            </el-collapse>
          </div>

          <!-- 右列 -->
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

    <!-- 任务列表 + 日志 -->
    <div class="bottom-panels">
      <!-- 左侧：任务列表 -->
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

      <!-- 右侧：训练日志 -->
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

    <!-- 扩缩容弹窗 -->
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

// ── State ──
const loading = ref(false)
const submitting = ref(false)
const tasks = ref<TrainingTaskListItem[]>([])
const selectedTask = ref<TrainingTaskListItem | null>(null)
const trainingLogs = ref<TrainingLog[]>([])
const scaleDialogVisible = ref(false)
const scaleTarget = ref<TrainingTaskListItem | null>(null)
const statsCounts = ref<Record<string, number>>({})
const logLevel = ref('')
const logSearch = ref('')
const logAutoScroll = ref(true)
const logScroll = ref<HTMLDivElement>()
const logContainer = ref<HTMLDivElement>()
let refreshTimer: number | null = null

const options = reactive<TrainingOptions>({
  models: [],
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

const gpuOptionValue = ref('1')

const form = reactive({
  task_name: '',
  dataset_id: undefined as number | undefined,
  framework: 'pytorch' as 'pytorch' | 'deepspeed' | 'megatron',
  parallel_strategy: 'zero2' as string,
  config: {
    model_type: 'gpt2', hidden_size: 384, num_layers: 6, num_gpus: 1,
    batch_size: 1, learning_rate: 2e-5,
    max_epochs: 10, max_steps: 0, seq_length: 128, precision: 'fp16' as const,
  },
})

const scaleForm = reactive({ gpu_count: 1, parallel_strategy: 'ddp' as string })
const scaleSubmitting = ref(false)

// ── Scale helpers ──
const canPause = (row: TrainingTaskListItem) => row.status === 'running'
const canResume = (row: TrainingTaskListItem) => row.status === 'paused'
const canScale = (row: TrainingTaskListItem) =>
  row.status === 'running' || row.status === 'paused' || row.status === 'pausing'

const scaleGpuOptions = computed(() => {
  if (options.gpu_options.length > 0) return options.gpu_options.map(o => ({ value: Number(o.value), label: o.label }))
  return [1, 2, 4, 8].map(n => ({ value: n, label: `${n} × GPU` }))
})

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

const scaleWarning = computed(() => {
  if (scaleForm.gpu_count <= 1 && scaleForm.parallel_strategy !== 'ddp') {
    return '单卡只能使用 DDP 策略'
  }
  if (scaleForm.gpu_count === 2 && ['zero3', 'zero3_offload', 'tp', 'pp', '3d'].includes(scaleForm.parallel_strategy)) {
    return '2 卡不建议使用该策略，可能内存不足'
  }
  return ''
})

const scaleCurrentCfg = computed(() => {
  if (!scaleTarget.value) return ''
  const cfg = scaleTarget.value.config_json || {} as Record<string, unknown>
  const gpu = cfg.num_gpus ?? 1
  return `${gpu} GPU · ${scaleTarget.value.parallel_strategy || 'ddp'}`
})

const canSubmitScale = computed(() => {
  if (!scaleTarget.value) return false
  const curGpu = (scaleTarget.value.config_json as Record<string, unknown> | null)?.num_gpus ?? 1
  const curStrat = scaleTarget.value.parallel_strategy || 'ddp'
  // At least one thing changed
  return scaleForm.gpu_count !== curGpu || scaleForm.parallel_strategy !== curStrat
})

const openScaleDialog = (row: TrainingTaskListItem) => {
  scaleTarget.value = row
  const cfg = (row.config_json || {}) as Record<string, unknown>
  scaleForm.gpu_count = (cfg.num_gpus as number) || Number((row.gpu_display || '1').charAt(0)) || 1
  scaleForm.parallel_strategy = row.parallel_strategy || 'ddp'
  scaleDialogVisible.value = true
}

const onScaleGpuChange = () => {
  // Auto-pick a valid strategy when GPU count changes
  const valid = scaleStrategies.value.map(s => s.value)
  if (!valid.includes(scaleForm.parallel_strategy)) {
    scaleForm.parallel_strategy = valid[0]!
  }
}

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
const canSubmit = computed(() => form.task_name && form.dataset_id)

const trainingStats = computed(() => {
  const c = statsCounts.value
  return [
    { label: '运行', value: String(c.running ?? 0), cls: 'running' },
    { label: '排队', value: String(c.queued ?? 0), cls: 'queued' },
    { label: '已完成', value: String(c.completed ?? 0), cls: 'completed' },
    { label: '失败/取消', value: String((c.failed ?? 0) + (c.cancelled ?? 0)), cls: 'failed' },
  ]
})

const filteredLogs = computed(() => {
  let logs = trainingLogs.value
  if (logLevel.value) logs = logs.filter(l => l.level.toUpperCase() === logLevel.value!.toUpperCase())
  if (logSearch.value) {
    const q = logSearch.value.toLowerCase()
    logs = logs.filter(l => l.message.toLowerCase().includes(q))
  }
  return logs
})

const recommendedStrategy = computed(() => {
  const n = Number(gpuOptionValue.value)
  if (form.framework === 'megatron') return '张量并行 + 流水线并行'
  if (n <= 1) return 'DDP (单卡)'
  return 'ZeRO Stage 2 (推荐)'
})

const resourceAdvice = computed(() => {
  const n = Number(gpuOptionValue.value)
  if (n <= 1) return '单卡适合小规模微调，建议使用 DDP。'
  return '当前资源满足混合并行训练，可在任务运行中发起扩缩容请求。'
})

// ── Auto-scroll logs ──
watch(filteredLogs, () => {
  if (logAutoScroll.value) {
    nextTick(() => {
      logContainer.value?.scrollTo({ top: logContainer.value.scrollHeight, behavior: 'smooth' })
    })
  }
})

// ── Methods ──
const loadOptions = async () => {
  try {
    const res = await fetchTrainingOptions()
    if (res) {
      if (res.models?.length) options.models = res.models
      if (res.datasets?.length) options.datasets = res.datasets
      if (res.frameworks?.length) options.frameworks = res.frameworks
      if (res.gpu_options?.length) options.gpu_options = res.gpu_options
      if (res.parallel_strategies?.length) options.parallel_strategies = res.parallel_strategies
    }
  } catch { /* use defaults */ }
}

const loadTasks = async () => {
  loading.value = true
  try { const res = await fetchTrainingTasks(); tasks.value = res.data ?? [] }
  catch { tasks.value = [] }
  finally { loading.value = false }
}

const loadStats = async () => {
  try { const res = await fetchTrainingStats(); statsCounts.value = (res ?? {}) as Record<string, number> }
  catch { /* ignore */ }
}

const loadLogs = async (taskId: number) => {
  try { const res = await fetchTrainingLogs(taskId); trainingLogs.value = res.data?.logs ?? [] }
  catch { trainingLogs.value = [] }
}

const selectTask = async (row: TrainingTaskListItem) => {
  selectedTask.value = row
  try { const res = await fetchTrainingTask(row.id); if (res.data) Object.assign(row, res.data) }
  catch { /* ignore */ }
  await loadLogs(row.id)
}

const clearLogs = () => { trainingLogs.value = [] }

const startTraining = async () => {
  if (!canSubmit.value) { ElMessage.warning('请填写任务名称并选择数据集'); return }
  submitting.value = true
  try {
    const gpuCount = Number(gpuOptionValue.value)
    const cfg: Record<string, any> = { ...form.config, num_gpus: gpuCount }
    if (!cfg.max_steps) delete cfg.max_steps
    const res = await createTrainingTask({
      task_name: form.task_name, dataset_id: form.dataset_id!, framework: form.framework,
      parallel_strategy: form.parallel_strategy as any, config: cfg,
    })
    ElMessage.success(`训练任务已创建: ${res.data?.task_code ?? ''}`)
    await loadTasks(); await loadStats()
  } catch (e: unknown) { ElMessage.error((e as Error).message || '创建失败') }
  finally { submitting.value = false }
}

const handlePause = async (row: TrainingTaskListItem) => {
  try { await pauseTrainingTask(row.id); ElMessage.success(`已暂停 ${row.task_code}`); await loadTasks(); await loadStats() }
  catch (e: unknown) { ElMessage.error((e as Error).message || '暂停失败') }
}

const handleResume = async (row: TrainingTaskListItem) => {
  try { await resumeTrainingTask(row.id); ElMessage.success(`已恢复 ${row.task_code}`); await loadTasks(); await loadStats() }
  catch (e: unknown) { ElMessage.error((e as Error).message || '恢复失败') }
}

const handlePromote = async (row: TrainingTaskListItem) => {
  try {
    const res = await promoteTrainingTask(row.id)
    ElMessage.success(`已转为模型版本: ${(res.data as any)?.model_code ?? ''}`)
    await loadTasks(); await loadStats()
  } catch (e: unknown) { ElMessage.error((e as Error).message || '转为模型失败') }
}

const handleDeleteTask = async (row: TrainingTaskListItem) => {
  try { await deleteTrainingTask(row.id); ElMessage.success(`已删除 ${row.task_code}`); await loadTasks(); await loadStats() }
  catch (e: unknown) { ElMessage.error((e as Error).message || '删除失败') }
}

const handleSaveConfig = () => { ElMessage.success('并行配置已保存') }
const handleValidateConfig = async () => {
  if (!canSubmit.value) { ElMessage.warning('请先填写任务名称和数据集'); return }
  try {
    const body = {
      task_name: form.task_name, dataset_id: form.dataset_id!, framework: form.framework,
      parallel_strategy: form.parallel_strategy as any,
      config: { ...form.config, num_gpus: Number(gpuOptionValue.value) },
    }
    const res = await validateTrainingConfig(body)
    const result = res.data
    if (result?.valid) ElMessage.success('配置验证通过')
    else ElMessage.warning([...(result?.errors ?? []), ...(result?.warnings ?? [])].join('；') || '配置存在问题')
  } catch (e: unknown) { ElMessage.error((e as Error).message || '验证失败') }
}

// ── Helpers ──
const formatTime = (ts: string) => ts ? new Date(ts).toLocaleTimeString() : ''
const frameworkLabel = (f?: string) => ({ pytorch: 'PyTorch', deepspeed: 'DeepSpeed', megatron: 'Megatron-LM' } as Record<string, string>)[f ?? ''] ?? f ?? '-'
const statusLabel = (s: string) => ({ created: '已创建', queued: '排队中', running: '运行中', pausing: '暂停中…', paused: '已暂停', resuming: '恢复中…', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[s] ?? s
const statusType = (s: string): 'success' | 'warning' | 'danger' | 'info' => ({ created: 'info', queued: 'warning', running: 'success', pausing: 'warning', paused: 'warning', resuming: 'info', completed: 'success', failed: 'danger', cancelled: 'info' } as Record<string, any>)[s] ?? 'info'

// ── Lifecycle ──
onMounted(() => {
  loadOptions(); loadTasks(); loadStats()
  refreshTimer = window.setInterval(async () => {
    await loadTasks(); await loadStats()
    if (selectedTask.value) await loadLogs(selectedTask.value.id)
  }, 5000)
})

onBeforeUnmount(() => {
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
}
</style>
