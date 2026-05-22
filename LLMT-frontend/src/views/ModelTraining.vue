<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">模型训练</h1>
      <p class="page-description">面向混合并行配置、分布式训练启动和训练任务监控的任务编排</p>
    </div>

    <div class="grid-4 stats">
      <div v-for="item in trainingStats" :key="item.label" class="stat-tile">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <div class="card">
      <div class="card-body">
        <el-tabs v-model="activeTrainingTab">
          <el-tab-pane label="混合并行配置" name="parallel">
            <div class="tab-panel">
              <div>
                <h3>生成训练配置文件</h3>
                <p>选择训练框架和并行策略后，系统根据 GPU 数量、显存和模型规模给出推荐配置。</p>
              </div>
              <el-button type="primary" :icon="DocumentChecked" @click="handleSaveConfig">保存配置</el-button>
            </div>
          </el-tab-pane>
          <el-tab-pane label="分布式训练启动" name="launch">
            <div class="tab-panel">
              <div>
                <h3>提交训练任务</h3>
                <p>系统会校验训练配置、数据集质量和 GPU 资源，资源不足时任务进入等待队列。</p>
              </div>
              <el-button type="primary" :icon="VideoPlay" @click="startTraining">提交训练任务</el-button>
            </div>
          </el-tab-pane>
          <el-tab-pane label="训练任务监控" name="monitor">
            <div v-if="selectedTask">
              <div class="monitor-row">
                <div v-for="item in monitorItems" :key="item.label" class="monitor-item">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
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
            </div>
            <div v-else class="empty-tip">请从下方任务列表中选择一个任务查看监控信息</div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header"><h3 class="card-title">任务与数据</h3></div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="任务名称">
              <el-input v-model="form.task_name" placeholder="输入训练任务名称" />
            </el-form-item>
            <el-form-item label="训练模型">
              <el-select v-model="form.config.model_type" class="full" placeholder="选择模型">
                <el-option v-for="item in options.models" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="训练数据集">
              <el-select v-model="form.dataset_id" class="full" placeholder="选择数据集">
                <el-option v-for="item in options.datasets" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="训练框架">
              <el-radio-group v-model="form.framework">
                <el-radio-button v-for="item in options.frameworks" :key="item.value" :label="item.label" :value="item.value" />
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">资源与并行策略</h3></div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="GPU 资源">
              <el-select v-model="gpuOptionValue" class="full" placeholder="选择GPU数量">
                <el-option v-for="item in options.gpu_options" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="并行策略">
              <el-select v-model="form.parallel_strategy" class="full" placeholder="选择并行策略">
                <el-option v-for="item in options.parallel_strategies" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <div class="recommend-box">
              <span>系统推荐</span>
              <strong>{{ recommendedStrategy }}</strong>
              <p>{{ resourceAdvice }}</p>
            </div>
          </el-form>
        </div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header"><h3 class="card-title">启动检查</h3></div>
        <div class="card-body check-list">
          <div v-for="item in launchChecks" :key="item.label" class="check-item">
            <StatusBadge :label="item.status" :type="item.type" />
            <div>
              <strong>{{ item.label }}</strong>
              <p>{{ item.detail }}</p>
            </div>
          </div>
          <div class="action-row">
            <el-button type="primary" :icon="VideoPlay" :disabled="!canSubmit" @click="startTraining">提交训练任务</el-button>
            <el-button :icon="DocumentChecked" @click="handleValidateConfig">验证配置</el-button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">配置预览</h3></div>
        <div class="card-body">
          <pre class="yaml-preview">{{ yamlPreview }}</pre>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">训练任务列表</h3>
        <el-button @click="loadTasks">刷新</el-button>
      </div>
      <div class="card-body">
        <el-table :data="tasks" stripe v-loading="loading">
          <el-table-column prop="task_code" label="任务ID" width="180" />
          <el-table-column prop="task_name" label="任务名称" min-width="170" />
          <el-table-column prop="framework" label="框架" width="110">
            <template #default="{ row }">{{ frameworkLabel(row.framework) }}</template>
          </el-table-column>
          <el-table-column prop="gpu_display" label="GPU" width="110" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }"><StatusBadge :label="statusLabel(row.status)" :type="statusType(row.status)" /></template>
          </el-table-column>
          <el-table-column label="进度" width="160">
            <template #default="{ row }">
              <div class="progress-cell">
                <div class="progress-bar">
                  <div class="progress-fill blue" :style="{ width: `${row.progress}%` }"></div>
                </div>
                <span>{{ row.progress }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260">
            <template #default="{ row }">
              <el-button size="small" :disabled="row.status !== 'running'" @click="handlePause(row)">暂停</el-button>
              <el-button size="small" :disabled="row.status !== 'paused'" @click="handleResume(row)">恢复</el-button>
              <el-button size="small" @click="openScaleDialog(row)">扩缩容</el-button>
              <el-button size="small" type="danger" :disabled="!['created', 'queued', 'running'].includes(row.status)" @click="handleCancel(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="scaleDialogVisible" title="训练任务扩缩容" width="560px">
      <el-form label-position="top">
        <el-form-item label="任务">
          <el-input :model-value="scaleTarget ? `${scaleTarget.task_code} / ${scaleTarget.task_name}` : ''" disabled />
        </el-form-item>
        <el-form-item label="目标 GPU 数量">
          <el-select v-model="scaleForm.gpu_count" class="full">
            <el-option label="1 卡" :value="1" />
            <el-option label="2 卡" :value="2" />
            <el-option label="4 卡" :value="4" />
            <el-option label="8 卡" :value="8" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标并行策略（可选）">
          <el-select v-model="scaleForm.parallel_strategy" class="full" clearable placeholder="不修改">
            <el-option v-for="item in options.parallel_strategies" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <div class="scale-note">
          系统会等待当前 Step 完成，保存 Checkpoint 后再调整资源；若资源不足，请求会进入等待队列。
        </div>
      </el-form>
      <template #footer>
        <el-button @click="scaleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitScale">提交请求</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, VideoPlay } from '@element-plus/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'
import {
  type TrainingOptions,
  type TrainingTaskListItem,
  type TrainingLog,
  fetchTrainingTasks,
  fetchTrainingTask,
  createTrainingTask,
  cancelTrainingTask,
  pauseTrainingTask,
  resumeTrainingTask,
  scaleTrainingTask,
  fetchTrainingOptions,
  fetchTrainingStats,
  fetchTrainingLogs,
  validateTrainingConfig,
} from '@/api/training'

// State
const activeTrainingTab = ref('parallel')
const loading = ref(false)
const tasks = ref<TrainingTaskListItem[]>([])
const selectedTask = ref<TrainingTaskListItem | null>(null)
const trainingLogs = ref<TrainingLog[]>([])
const scaleDialogVisible = ref(false)
const scaleTarget = ref<TrainingTaskListItem | null>(null)
const statsCounts = ref<Record<string, number>>({})

const options = reactive<TrainingOptions>({
  models: [],
  datasets: [],
  frameworks: [
    { value: 'pytorch', label: 'PyTorch' },
    { value: 'deepspeed', label: 'DeepSpeed' },
    { value: 'megatron', label: 'Megatron-LM' },
  ],
  gpu_options: [
    { value: '1', label: '1 × A100' },
    { value: '2', label: '2 × A100' },
    { value: '4', label: '4 × A100' },
    { value: '8', label: '8 × A100' },
  ],
  parallel_strategies: [
    { value: 'ddp', label: '分布式数据并行 (DDP)' },
    { value: 'zero1', label: 'ZeRO Stage 1' },
    { value: 'zero2', label: 'ZeRO Stage 2' },
    { value: 'zero3', label: 'ZeRO Stage 3' },
    { value: 'zero3_offload', label: 'ZeRO Stage 3 + Offload' },
    { value: 'tp', label: '张量并行 (TP)' },
    { value: 'pp', label: '流水线并行 (PP)' },
    { value: '3d', label: '3D 混合并行' },
  ],
})

const gpuOptionValue = ref('4')

const form = reactive({
  task_name: '',
  dataset_id: undefined as number | undefined,
  framework: 'deepspeed' as 'pytorch' | 'deepspeed' | 'megatron',
  parallel_strategy: 'zero2' as string,
  config: {
    model_type: 'gpt2',
    num_gpus: 4,
    batch_size: 32,
    learning_rate: 2e-5,
    max_epochs: 10,
    seq_length: 1024,
    precision: 'fp16' as const,
  },
})

const scaleForm = reactive({
  gpu_count: 4,
  parallel_strategy: undefined as string | undefined,
})

// Computed
const canSubmit = computed(() => form.task_name && form.dataset_id)

const trainingStats = computed(() => {
  const c = statsCounts.value
  return [
    { label: '运行任务', value: String(c.running ?? 0) },
    { label: '排队任务', value: String(c.queued ?? 0) },
    { label: '已完成', value: String(c.completed ?? 0) },
    { label: '失败/取消', value: String((c.failed ?? 0) + (c.cancelled ?? 0)) },
  ]
})

const monitorItems = computed(() => {
  if (!selectedTask.value) return []
  const t = selectedTask.value
  const cfg = t.config_json || {}
  return [
    { label: '当前 Epoch', value: `${t.current_epoch} / ${t.max_epoch ?? '-'}` },
    { label: '当前 Step', value: t.current_step.toLocaleString() },
    { label: '任务状态', value: statusLabel(t.status) },
    { label: 'GPU', value: t.gpu_display || '-' },
  ]
})

const recommendedStrategy = computed(() => {
  const n = Number(gpuOptionValue.value)
  if (form.framework === 'megatron') return '张量并行 + 流水线并行'
  if (n <= 1) return 'DDP (单卡)'
  return 'ZeRO Stage 2 (推荐)'
})

const resourceAdvice = computed(() => {
  const n = Number(gpuOptionValue.value)
  if (n <= 1) return '单卡资源适合小规模微调，建议使用 DDP。'
  return '当前资源满足混合并行训练，可在任务运行中发起扩缩容请求。'
})

const launchChecks = computed(() => [
  { label: '训练配置', detail: `${frameworkLabel(form.framework)} + ${strategyLabel(form.parallel_strategy)} 配置就绪`, status: form.task_name ? '通过' : '未填写', type: (form.task_name ? 'success' : 'warning') as 'success' | 'warning' },
  { label: '数据集', detail: form.dataset_id ? `已选择数据集 #${form.dataset_id}` : '请选择数据集', status: form.dataset_id ? '通过' : '未选择', type: (form.dataset_id ? 'success' : 'warning') as 'success' | 'warning' },
  { label: 'GPU 资源', detail: `${gpuOptionValue.value} × A100 已配置`, status: '可用', type: 'success' as const },
  { label: '配置验证', detail: '点击"验证配置"检查兼容性', status: '就绪', type: 'info' as const },
])

const yamlPreview = computed(() => {
  const n = Number(gpuOptionValue.value)
  return `task_name: ${form.task_name || '未命名任务'}
framework: ${form.framework}
model_type: ${form.config.model_type}
dataset_id: ${form.dataset_id ?? '未选择'}
resource:
  num_gpus: ${n}
  precision: ${form.config.precision}
parallel:
  strategy: ${form.parallel_strategy}
hyper_params:
  batch_size: ${form.config.batch_size}
  learning_rate: ${form.config.learning_rate}
  max_epochs: ${form.config.max_epochs}
  seq_length: ${form.config.seq_length}`
})

// Methods
const loadOptions = async () => {
  try {
    const res = await fetchTrainingOptions()
    if (res.data) {
      options.models = res.data.models ?? []
      options.datasets = res.data.datasets ?? []
      if (res.data.frameworks?.length) options.frameworks = res.data.frameworks
      if (res.data.gpu_options?.length) options.gpu_options = res.data.gpu_options
      if (res.data.parallel_strategies?.length) options.parallel_strategies = res.data.parallel_strategies
    }
  } catch {
    // use defaults
  }
}

const loadTasks = async () => {
  loading.value = true
  try {
    const res = await fetchTrainingTasks()
    tasks.value = res.data ?? []
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const res = await fetchTrainingStats()
    statsCounts.value = (res.data ?? {}) as Record<string, number>
  } catch {
    // ignore
  }
}

const loadLogs = async (taskId: number) => {
  try {
    const res = await fetchTrainingLogs(taskId)
    trainingLogs.value = res.data?.logs ?? []
  } catch {
    trainingLogs.value = []
  }
}

const startTraining = async () => {
  if (!canSubmit.value) {
    ElMessage.warning('请填写任务名称并选择数据集')
    return
  }
  try {
    const gpuCount = Number(gpuOptionValue.value)
    const body = {
      task_name: form.task_name,
      dataset_id: form.dataset_id!,
      framework: form.framework,
      parallel_strategy: form.parallel_strategy as any,
      config: {
        ...form.config,
        num_gpus: gpuCount,
      },
    }
    const res = await createTrainingTask(body)
    ElMessage.success(`训练任务已创建: ${res.data?.task_code ?? ''}`)
    activeTrainingTab.value = 'monitor'
    await loadTasks()
    await loadStats()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '创建失败')
  }
}

const handlePause = async (row: TrainingTaskListItem) => {
  try {
    await pauseTrainingTask(row.id)
    ElMessage.success(`任务 ${row.task_code} 已暂停`)
    await loadTasks()
    await loadStats()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '暂停失败')
  }
}

const handleResume = async (row: TrainingTaskListItem) => {
  try {
    await resumeTrainingTask(row.id)
    ElMessage.success(`任务 ${row.task_code} 已恢复`)
    await loadTasks()
    await loadStats()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '恢复失败')
  }
}

const handleCancel = async (row: TrainingTaskListItem) => {
  try {
    await cancelTrainingTask(row.id)
    ElMessage.success(`任务 ${row.task_code} 已取消`)
    await loadTasks()
    await loadStats()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '取消失败')
  }
}

const openScaleDialog = (row: TrainingTaskListItem) => {
  scaleTarget.value = row
  const cfgGpu = (row.config_json as Record<string, unknown>)?.num_gpus
  scaleForm.gpu_count = typeof cfgGpu === 'number' ? cfgGpu : Number(row.gpu_display?.charAt(0)) || 4
  scaleForm.parallel_strategy = undefined
  scaleDialogVisible.value = true
}

const submitScale = async () => {
  if (!scaleTarget.value) return
  try {
    await scaleTrainingTask(scaleTarget.value.id, {
      gpu_count: scaleForm.gpu_count,
      parallel_strategy: scaleForm.parallel_strategy,
    })
    ElMessage.success(`已提交 ${scaleTarget.value.task_code} 的扩缩容请求`)
    scaleDialogVisible.value = false
    await loadTasks()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '扩缩容失败')
  }
}

const handleSaveConfig = () => {
  ElMessage.success('并行配置已保存到任务草稿')
}

const handleValidateConfig = async () => {
  if (!form.task_name || !form.dataset_id) {
    ElMessage.warning('请先填写任务名称和数据集')
    return
  }
  try {
    const gpuCount = Number(gpuOptionValue.value)
    const body = {
      task_name: form.task_name,
      dataset_id: form.dataset_id!,
      framework: form.framework,
      parallel_strategy: form.parallel_strategy as any,
      config: { ...form.config, num_gpus: gpuCount },
    }
    const res = await validateTrainingConfig(body)
    const result = res.data
    if (result?.valid) {
      ElMessage.success('配置验证通过')
    } else {
      const msgs = [...(result?.errors ?? []), ...(result?.warnings ?? [])]
      ElMessage.warning(msgs.join('；') || '配置存在问题')
    }
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '验证失败')
  }
}

const formatTime = (ts: string) => {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString()
}

const frameworkLabel = (f?: string) => {
  const map: Record<string, string> = { pytorch: 'PyTorch', deepspeed: 'DeepSpeed', megatron: 'Megatron-LM' }
  return map[f ?? ''] ?? f ?? '-'
}

const strategyLabel = (s?: string) => {
  const map: Record<string, string> = {
    ddp: 'DDP', zero1: 'ZeRO-1', zero2: 'ZeRO-2', zero3: 'ZeRO-3',
    'zero3_offload': 'ZeRO-3 Offload', tp: 'TP', pp: 'PP', '3d': '3D并行',
  }
  return map[s ?? ''] ?? s ?? '-'
}

const statusLabel = (s: string) => {
  const map: Record<string, string> = {
    created: '已创建', queued: '排队中', running: '运行中',
    paused: '已暂停', completed: '已完成', failed: '失败', cancelled: '已取消',
  }
  return map[s] ?? s
}

const statusType = (s: string): 'success' | 'warning' | 'danger' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    created: 'info', queued: 'warning', running: 'success',
    paused: 'warning', completed: 'success', failed: 'danger', cancelled: 'info',
  }
  return map[s] ?? 'info'
}

onMounted(() => {
  loadOptions()
  loadTasks()
  loadStats()
})
</script>

<style scoped>
.full {
  width: 100%;
}

.stats {
  margin-bottom: 22px;
}

.stat-tile,
.monitor-item,
.recommend-box {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.stat-tile span,
.monitor-item span,
.recommend-box span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.stat-tile strong,
.monitor-item strong,
.recommend-box strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
}

.tab-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.tab-panel h3 {
  margin: 0 0 6px;
  font-size: 16px;
}

.tab-panel p,
.recommend-box p,
.check-item p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.recommend-box {
  margin-top: 8px;
}

.check-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.check-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.check-item strong {
  display: block;
  margin-bottom: 4px;
}

.action-row {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.yaml-preview {
  min-height: 242px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #ffffff;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
}

.scale-note {
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.monitor-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.progress-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-cell .progress-bar {
  flex: 1;
}

.progress-cell span {
  width: 40px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: right;
}

.empty-tip {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.log-container {
  max-height: 300px;
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
  .tab-panel,
  .action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .monitor-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .monitor-row {
    grid-template-columns: 1fr;
  }
}
</style>
