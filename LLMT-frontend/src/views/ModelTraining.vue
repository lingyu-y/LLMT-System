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
              <el-button type="primary" :icon="DocumentChecked" @click="tip('并行配置已保存到任务草稿')">
                保存配置
              </el-button>
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
            <div class="monitor-row">
              <div v-for="item in monitorItems" :key="item.label" class="monitor-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
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
              <el-input v-model="form.taskName" placeholder="输入训练任务名称" />
            </el-form-item>
            <el-form-item label="训练模型">
              <el-select v-model="form.model" class="full">
                <el-option v-for="item in modelOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="训练数据集">
              <el-select v-model="form.dataset" class="full">
                <el-option v-for="item in datasetOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="训练框架">
              <el-radio-group v-model="form.framework">
                <el-radio-button v-for="item in frameworkOptions" :key="item" :label="item" :value="item" />
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
              <el-select v-model="form.gpu" class="full">
                <el-option v-for="item in gpuOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="并行策略">
              <el-checkbox-group v-model="form.parallelStrategies" class="strategy-group">
                <el-checkbox-button v-for="item in parallelOptions" :key="item" :label="item" :value="item" />
              </el-checkbox-group>
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
            <el-button type="primary" :icon="VideoPlay" @click="startTraining">提交训练任务</el-button>
            <el-button :icon="DocumentChecked" @click="tip('已生成 YAML 配置预览')">生成配置</el-button>
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
      <div class="card-header"><h3 class="card-title">训练任务列表</h3></div>
      <div class="card-body">
        <el-table :data="trainingTasks" stripe>
          <el-table-column prop="id" label="任务ID" width="130" />
          <el-table-column prop="name" label="任务名称" min-width="170" />
          <el-table-column prop="framework" label="框架" width="120" />
          <el-table-column prop="gpu" label="GPU" width="120" />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }"><StatusBadge :label="row.status" :type="row.type" /></template>
          </el-table-column>
          <el-table-column prop="progress" label="进度" width="160">
            <template #default="{ row }">
              <div class="progress-cell">
                <div class="progress-bar">
                  <div class="progress-fill blue" :style="{ width: `${row.progress}%` }"></div>
                </div>
                <span>{{ row.progress }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240">
            <template #default="{ row }">
              <el-button size="small" :disabled="row.status !== '运行中'" @click="tip(`已暂停 ${row.id}`)">暂停</el-button>
              <el-button size="small" :disabled="row.status !== '已暂停'" @click="tip(`已恢复 ${row.id}`)">恢复</el-button>
              <el-button size="small" @click="openScaleDialog(row)">扩缩容</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="scaleDialogVisible" title="训练任务扩缩容" width="560px">
      <el-form label-position="top">
        <el-form-item label="任务">
          <el-input :model-value="selectedTask ? `${selectedTask.id} / ${selectedTask.name}` : ''" disabled />
        </el-form-item>
        <el-form-item label="调整方式">
          <el-radio-group v-model="scaleForm.mode">
            <el-radio-button label="扩容" value="扩容" />
            <el-radio-button label="缩容" value="缩容" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="目标 GPU 数量">
          <el-select v-model="scaleForm.targetGpu" class="full">
            <el-option label="1 卡" :value="1" />
            <el-option label="2 卡" :value="2" />
            <el-option label="4 卡" :value="4" />
            <el-option label="8 卡" :value="8" />
          </el-select>
        </el-form-item>
        <el-form-item label="调整原因">
          <el-input v-model="scaleForm.reason" type="textarea" :rows="3" placeholder="例如：GPU 利用率过低，缩容释放资源" />
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
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, VideoPlay } from '@element-plus/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'

type TrainingTask = {
  id: string
  name: string
  framework: string
  gpu: string
  status: string
  type: 'success' | 'warning' | 'info'
  progress: number
}

const modelOptions = ['BERT-base-chinese', 'ResNet-50', 'GPT-2-medium', 'Whisper-small']
const datasetOptions = ['电商评论文本数据 v2.3', '产品图像分类集 v1.8', '语音指令识别数据 v1.4']
const frameworkOptions = ['PyTorch', 'DeepSpeed', 'Megatron-LM']
const parallelOptions = ['数据并行', '模型并行', '流水线并行']
const gpuOptions = ['1x A100 80GB', '2x A100 80GB', '4x A100 80GB', '8x A100 80GB']
const activeTrainingTab = ref('parallel')
const scaleDialogVisible = ref(false)
const selectedTask = ref<TrainingTask>()

const form = reactive({
  taskName: 'BERT情感分析分布式训练',
  model: modelOptions[0],
  dataset: datasetOptions[0],
  framework: frameworkOptions[1],
  gpu: gpuOptions[2],
  parallelStrategies: ['数据并行', '流水线并行'],
})

const trainingStats = [
  { label: '运行任务', value: '3' },
  { label: '排队任务', value: '2' },
  { label: '可用 GPU', value: '12 / 32' },
  { label: '告警事件', value: '1' },
]

const monitorItems = [
  { label: '当前 Epoch', value: '6 / 10' },
  { label: '当前 Step', value: '12,840' },
  { label: '训练 Loss', value: '0.184' },
  { label: '通信延迟', value: '18 ms' },
]

const launchChecks = computed(() => [
  { label: '训练配置', detail: `${form.framework} 配置已生成，可保存为 YAML`, status: '通过', type: 'success' as const },
  { label: '数据质量', detail: `${form.dataset} 已完成质量校验，评分满足训练门槛`, status: '通过', type: 'success' as const },
  { label: 'GPU 资源', detail: `${form.gpu} 当前可申请，资源不足时进入等待队列`, status: '可用', type: 'success' as const },
  { label: '监控采集', detail: 'TensorBoard 指标、GPU 利用率和通信延迟已接入', status: '就绪', type: 'info' as const },
])

const recommendedStrategy = computed(() => {
  if (form.framework === 'Megatron-LM') return '模型并行 + 流水线并行'
  if (form.gpu?.startsWith('1x')) return '数据并行'
  return '数据并行 + 流水线并行'
})

const resourceAdvice = computed(() => {
  if (form.gpu?.startsWith('1x')) return '单卡资源适合小规模微调，建议关闭模型并行。'
  return '当前资源满足混合并行训练，可在任务运行中发起扩缩容请求。'
})

const yamlPreview = computed(
  () => `task_name: ${form.taskName || '未命名任务'}
framework: ${form.framework}
model: ${form.model}
dataset: ${form.dataset}
resource:
  gpu: ${form.gpu}
parallel:
${form.parallelStrategies.map((item) => `  - ${item}`).join('\n')}
monitor:
  tensorboard: enabled
  refresh_interval: 5s
checkpoint:
  save_on_pause: true`,
)

const trainingTasks: TrainingTask[] = [
  { id: 'TR-20260425-01', name: 'BERT情感分析分布式训练', framework: 'DeepSpeed', gpu: '4x A100', status: '运行中', type: 'success' as const, progress: 64 },
  { id: 'TR-20260425-02', name: '医学影像分类训练', framework: 'PyTorch', gpu: '2x A100', status: '排队', type: 'warning' as const, progress: 0 },
  { id: 'TR-20260424-09', name: '语音指令识别训练', framework: 'PyTorch', gpu: '1x A100', status: '已暂停', type: 'info' as const, progress: 42 },
]

const scaleForm = reactive({
  mode: '扩容',
  targetGpu: 4,
  reason: '',
})

const tip = (message: string) => ElMessage.success(message)
const openScaleDialog = (task: TrainingTask) => {
  selectedTask.value = task
  scaleForm.targetGpu = Number.parseInt(task.gpu, 10) || 4
  scaleForm.mode = '扩容'
  scaleForm.reason = ''
  scaleDialogVisible.value = true
}

const submitScale = () => {
  if (!selectedTask.value) return
  scaleDialogVisible.value = false
  ElMessage.success(`已提交 ${selectedTask.value.id} 的${scaleForm.mode}请求，目标 GPU: ${scaleForm.targetGpu} 卡`)
}

const startTraining = () => {
  activeTrainingTab.value = 'monitor'
  ElMessage.success(`训练任务「${form.taskName || '未命名任务'}」已提交，任务ID: TR-20260425-03`)
}
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

.strategy-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
