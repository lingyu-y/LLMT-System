<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">模型版本管理</h1>
      <p class="page-description">管理模型版本、训练超参数和性能指标，支持一键回滚</p>
    </div>

    <template v-if="!selectedModel">
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">选择模型</h3>
          <div class="filters">
            <el-input v-model="keyword" placeholder="搜索模型..." clearable />
            <el-select v-model="typeFilter">
              <el-option label="全部类型" value="全部类型" />
              <el-option label="NLP" value="NLP" />
              <el-option label="CV" value="CV" />
              <el-option label="Audio" value="Audio" />
              <el-option label="MultiModal" value="MultiModal" />
            </el-select>
          </div>
        </div>
        <div class="card-body model-grid">
          <button v-for="model in filteredModels" :key="model.id" class="model-card" @click="selectModel(model)">
            <span class="model-icon" :style="{ background: model.color }"><el-icon><Management /></el-icon></span>
            <span class="model-info">
              <strong>{{ model.name }}</strong>
              <span>{{ model.type }} · {{ model.params }}</span>
            </span>
            <span class="model-meta">
              <span class="version-badge">{{ model.version }}</span>
              <span>{{ model.accuracy }}</span>
            </span>
          </button>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="detail-header">
        <el-button :icon="ArrowLeft" @click="selectedModel = null">返回模型列表</el-button>
        <span class="detail-icon" :style="{ background: selectedModel.color }"><el-icon><Management /></el-icon></span>
        <div class="detail-title">
          <h2>{{ selectedModel.name }}</h2>
          <span>{{ selectedModel.type }}</span>
        </div>
        <div class="detail-actions">
          <el-button :icon="Upload" @click="importDialogVisible = true">导入</el-button>
          <el-button :icon="Download" @click="openExportDialog">导出</el-button>
          <el-button :icon="Clock" @click="versionHistoryDrawerVisible = true">版本历史</el-button>
          <el-popconfirm title="确定删除此模型？将删除所有版本及MinIO文件" @confirm="handleDeleteModel">
            <template #reference>
              <el-button type="danger" :icon="Delete">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>

      <div class="metrics-bar">
        <div class="metric-stat">
          <span class="metric-stat-label">当前版本</span>
          <strong class="metric-stat-value">{{ selectedModel.version }}</strong>
        </div>
        <div class="metric-stat">
          <span class="metric-stat-label">评估指标</span>
          <strong class="metric-stat-value">{{ selectedModel.accuracy }}</strong>
        </div>
        <div class="metric-stat">
          <span class="metric-stat-label">参数量</span>
          <strong class="metric-stat-value">{{ selectedModel.params }}</strong>
        </div>
        <div class="metric-stat">
          <span class="metric-stat-label">来源任务</span>
          <strong class="metric-stat-value">{{ selectedTrainingMeta.taskId }}</strong>
        </div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-header"><h3 class="card-title">训练配置</h3></div>
          <div class="card-body params-grid">
            <div v-for="[label, value] in trainingConfigItems" :key="label" class="param-item">
              <span>{{ label }}</span>
              <strong>{{ value }}</strong>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><h3 class="card-title">Checkpoint 与产物</h3></div>
          <div class="card-body artifact-list">
            <div v-for="item in artifacts" :key="item.label" class="artifact-item">
              <StatusBadge :label="item.status" :type="item.type" />
              <div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.path }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="card inference-card">
        <div class="card-header">
          <h3 class="card-title">在线推理试跑</h3>
          <el-button size="small" type="primary" :icon="Promotion" :loading="predicting" @click="runPredict">运行</el-button>
        </div>
        <div class="card-body inference-row">
          <div class="inference-input">
            <el-input v-model="inferenceInput" type="textarea" :rows="6" placeholder="输入一段文本，调用当前模型同步推理" />
          </div>
          <div class="inference-output">
            <div class="result-box">
              <template v-if="prediction">
                <div class="result-header">
                  <span>推理结果</span>
                  <strong>{{ prediction.latency_ms }} ms</strong>
                </div>
                <p>{{ prediction.output }}</p>
              </template>
              <span v-else class="result-placeholder">输入文本后点击「运行」查看推理结果</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <el-drawer v-model="versionHistoryDrawerVisible" title="版本历史" size="480px">
      <div class="timeline">
        <div v-for="item in versionHistory" :key="item.version" class="timeline-item" :class="{ current: item.current }">
          <div class="timeline-marker"><el-icon v-if="item.current"><Check /></el-icon></div>
          <div class="timeline-content">
            <div class="timeline-head">
              <strong>{{ item.version }}</strong>
              <StatusBadge v-if="item.status" :label="item.status" :type="item.current ? 'success' : 'info'" />
              <span class="muted">{{ item.date }}</span>
            </div>
            <p>{{ item.metrics }}</p>
            <p class="muted">{{ item.params }}</p>
            <p class="muted">{{ item.training }}</p>
            <div v-if="!item.current" class="timeline-actions">
              <el-button size="small" type="primary" :icon="RefreshLeft" @click="rollback(item.version)">回滚到此版本</el-button>
              <el-button size="small" :icon="Download" @click="downloadVersion(item.version)">下载</el-button>
              <el-button size="small" :icon="DataLine" @click="openCompareDrawer(item)">对比</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="compareDrawerVisible" title="版本对比" size="720px">
      <div v-if="compareVersion && currentVersion" class="compare-drawer">
        <div class="compare-summary">
          <div>
            <span>当前版本</span>
            <strong>{{ currentVersion.version }}</strong>
          </div>
          <div>
            <span>对比版本</span>
            <strong>{{ compareVersion.version }}</strong>
          </div>
        </div>

        <div class="compare-section">
          <h3>评估结果</h3>
          <div class="compare-grid">
            <div class="compare-column current">
              <span>{{ currentVersion.version }}</span>
              <strong>{{ currentVersion.metrics }}</strong>
            </div>
            <div class="compare-column">
              <span>{{ compareVersion.version }}</span>
              <strong>{{ compareVersion.metrics }}</strong>
            </div>
          </div>
        </div>

        <div class="compare-section">
          <h3>训练配置</h3>
          <div class="compare-grid">
            <div class="compare-column current">
              <span>当前版本</span>
              <strong>{{ currentVersion.params }}</strong>
            </div>
            <div class="compare-column">
              <span>历史版本</span>
              <strong>{{ compareVersion.params }}</strong>
            </div>
          </div>
        </div>

        <div class="compare-section">
          <h3>训练来源</h3>
          <div class="compare-grid">
            <div class="compare-column current">
              <span>当前版本</span>
              <strong>{{ currentVersion.training }}</strong>
            </div>
            <div class="compare-column">
              <span>历史版本</span>
              <strong>{{ compareVersion.training }}</strong>
            </div>
          </div>
        </div>

        <div class="compare-section">
          <h3>产物差异</h3>
          <div class="compare-grid">
            <div class="compare-column current">
              <span>模型文件</span>
              <strong>models/{{ selectedModel?.id }}/{{ currentVersion.version }}/model.bin</strong>
              <p>{{ selectedTrainingMeta.checkpoint }}</p>
            </div>
            <div class="compare-column">
              <span>模型文件</span>
              <strong>models/{{ selectedModel?.id }}/{{ compareVersion.version }}/model.bin</strong>
              <p>{{ historicalCheckpoint }}</p>
            </div>
          </div>
        </div>

        <div class="compare-actions">
          <el-button :icon="Download" @click="downloadVersion(compareVersion.version)">下载历史版本</el-button>
          <el-button type="primary" :icon="RefreshLeft" @click="rollback(compareVersion.version)">回滚到此版本</el-button>
        </div>
      </div>
    </el-drawer>

    <el-dialog v-model="importDialogVisible" title="从模型仓库导入" width="560px">
      <el-form label-position="top">
        <el-form-item label="源路径"><el-input v-model="importForm.source_path" placeholder="models/source/path" /></el-form-item>
        <el-form-item label="模型名称"><el-input v-model="importForm.model_name" /></el-form-item>
        <el-form-item label="模型编码"><el-input v-model="importForm.model_code" /></el-form-item>
        <el-form-item label="版本"><el-input v-model="importForm.version" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="exportDialogVisible" title="导出到模型仓库" width="520px">
      <el-form label-position="top">
        <el-form-item label="目标路径"><el-input v-model="exportForm.target_path" placeholder="exports/models/current" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exportDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitExport">导出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, Clock, DataLine, Delete, Download, Management, Promotion, RefreshLeft, Upload } from '@element-plus/icons-vue'

import { predict, type PredictResult } from '@/api/inference'
import StatusBadge from '@/components/StatusBadge.vue'
import {
  compareModelVersions,
  deleteModel,
  exportModel,
  getModelDownloadUrl,
  importModel,
  getModelVersions,
  listModels,
  rollbackModelVersion,
  type BackendModel,
} from '@/api/models'

type ModelItem = {
  id: string
  name: string
  type: string
  version: string
  accuracy: string
  params: string
  color: string
  raw: BackendModel
}
type VersionItem = {
  version: string
  status: string
  date: string
  metrics: string
  params: string
  training: string
  current?: boolean
  raw: BackendModel
}

const keyword = ref('')
const typeFilter = ref('全部类型')
const selectedModel = ref<ModelItem | null>(null)
const compareDrawerVisible = ref(false)
const versionHistoryDrawerVisible = ref(false)

const importDialogVisible = ref(false)
const exportDialogVisible = ref(false)
const compareVersion = ref<VersionItem>()
const models = ref<ModelItem[]>([])
const versionHistory = ref<VersionItem[]>([])
const predicting = ref(false)
const inferenceInput = ref('请对当前模型做一次测试推理')
const prediction = ref<PredictResult>()

const importForm = ref({ source_path: '', model_name: '', model_code: '', version: 'v1.0.0' })
const exportForm = ref({ target_path: '' })

const colors = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #06b6d4, #0891b2)',
]

const getMetricText = (metrics?: Record<string, unknown>) => {
  if (!metrics || Object.keys(metrics).length === 0) return '-'
  const accuracy = metrics.accuracy_train ?? metrics.accuracy_val ?? metrics.accuracy ?? metrics.acc ?? metrics.score
  if (typeof accuracy === 'number') return `${accuracy > 1 ? accuracy.toFixed(1) : (accuracy * 100).toFixed(1)}%`
  if (typeof accuracy === 'string') return accuracy
  // Show loss if no accuracy
  const loss = metrics.loss_final
  if (typeof loss === 'number') return `loss ${loss.toFixed(4)}`
  return '-'
}

const getParamsText = (hyperparams?: Record<string, unknown>) => {
  if (!hyperparams) return '-'
  const { hidden_size, num_layers, num_attention_heads, vocab_size } = hyperparams
  const parts: string[] = []
  if (typeof hidden_size === 'number') parts.push(`${hidden_size}`)
  if (typeof num_layers === 'number') parts.push(`${num_layers}层`)
  return parts.length ? parts.join('·') : '-'
}

const getHyperSummary = (hyperparams?: Record<string, unknown>): Record<string, string> => {
  if (!hyperparams) return {}
  const result: Record<string, string> = {}
  const keyLabels: Record<string, string> = {
    framework: '训练框架', parallel_strategy: '并行策略', model_type: '模型架构',
    learning_rate: '学习率', batch_size: 'Batch Size', max_epochs: '最大Epoch',
    seq_length: '序列长度', hidden_size: '隐层维度', num_layers: '层数',
    num_attention_heads: '注意力头数', precision: '精度', optimizer: '优化器',
    weight_decay: '权重衰减', warmup_steps: '预热步数', max_steps: '最大步数',
  }
  for (const [key, label] of Object.entries(keyLabels)) {
    if (key in hyperparams) {
      const val = hyperparams[key]
      result[label] = val != null ? String(val) : '-'
    }
  }
  return result
}

const mapModel = (item: BackendModel, index = 0): ModelItem => ({
  id: item.model_code,
  name: item.model_name,
  type: item.framework ?? 'Unknown',
  version: item.version,
  accuracy: getMetricText(item.metrics_json),
  params: getParamsText(item.hyperparams_json),
  color: colors[index % colors.length]!,
  raw: item,
})

const mapVersion = (item: BackendModel): VersionItem => ({
  version: item.version,
  status: item.is_current ? '当前版本' : item.tag ?? '',
  date: item.created_at?.replace('T', ' ').slice(0, 16) ?? '-',
  metrics: getMetricText(item.metrics_json),
  params: getParamsText(item.hyperparams_json),
  training: item.dataset_version ? `数据集 ${item.dataset_version}` : `模型 ${item.model_code}`,
  current: item.is_current,
  raw: item,
})

const loadModels = async () => {
  const page = await listModels({ page: 1, page_size: 100, keyword: keyword.value })
  models.value = page.data.map(mapModel)
}

const loadVersions = async (modelCode: string) => {
  versionHistory.value = (await getModelVersions(modelCode)).map(mapVersion)
}

const filteredModels = computed(() =>
  models.value.filter((item) => {
    const matchText = `${item.name}${item.type}`.toLowerCase().includes(keyword.value.toLowerCase())
    const matchType = typeFilter.value === '全部类型' || item.type.includes(typeFilter.value)
    return matchText && matchType
  }),
)

const selectedTrainingMeta = computed(() => {
  const raw = selectedModel.value?.raw
  const hp = raw?.hyperparams_json ?? {}
  const meta = raw?.training_metadata ?? {}
  return {
    taskId: raw?.id ? `TASK-${raw.id}` : '-',
    dataset: (typeof hp.dataset_id === 'number' ? `数据集 #${hp.dataset_id}` : null)
      ?? (typeof meta.dataset_version === 'string' ? meta.dataset_version : null)
      ?? '-',
    framework: (typeof hp.framework === 'string' ? hp.framework : null)
      ?? (typeof raw?.framework === 'string' ? raw.framework : null)
      ?? '-',
    parallel: typeof hp.parallel_strategy === 'string' ? hp.parallel_strategy : '-',
    resource: typeof hp.num_gpus === 'number' ? `${hp.num_gpus}x GPU` : '-',
    checkpoint: typeof raw?.storage_path === 'string' ? raw.storage_path : '-',
    config: typeof raw?.model_code === 'string' ? `models/${raw.model_code}/${raw?.version ?? 'latest'}` : '-',
  }
})

const hyperParamsSummary = computed(() => {
  const hp = selectedModel.value?.raw?.hyperparams_json
  return hp ? getHyperSummary(hp) : {}
})

const trainingConfigItems = computed<[string, string][]>(() => {
  const meta = selectedTrainingMeta.value
  const hp = hyperParamsSummary.value
  const items: [string, string][] = [
    ['训练框架', meta.framework],
    ['并行策略', meta.parallel],
  ]
  const hpKeys = ['学习率', '精度', '序列长度', '隐层维度', '层数', '注意力头数']
  for (const key of hpKeys) {
    const val = hp[key]
    if (val && val !== '-') items.push([key, val])
  }
  return items
})

const artifacts = computed(() => [
  { label: '模型文件', path: `models/${selectedModel.value?.id}/${selectedModel.value?.version}/model.bin`, status: '已归档', type: 'success' as const },
  { label: 'Checkpoint', path: selectedTrainingMeta.value.checkpoint, status: '可恢复', type: 'info' as const },
  { label: '训练配置', path: selectedTrainingMeta.value.config, status: '已保存', type: 'success' as const },
])

const currentVersion = computed(() => versionHistory.value.find((item) => item.current) ?? versionHistory.value[0])
const historicalCheckpoint = computed(() => `ckpt/${compareVersion.value?.version ?? 'history'}/best`)

const openCompareDrawer = async (version: VersionItem) => {
  compareVersion.value = version
  if (selectedModel.value && currentVersion.value) {
    await compareModelVersions(selectedModel.value.id, currentVersion.value.version, version.version).catch(() => undefined)
  }
  compareDrawerVisible.value = true
}

const handleDeleteModel = async () => {
  if (!selectedModel.value?.id) return
  try {
    await deleteModel(selectedModel.value.id)
    ElMessage.success('模型已删除')
    selectedModel.value = null
    await loadModels()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '删除失败')
  }
}

const openExportDialog = () => {
  exportForm.value = { target_path: selectedModel.value ? `exports/${selectedModel.value.id}/${selectedModel.value.version}` : '' }
  exportDialogVisible.value = true
}

const rollback = async (version: string) => {
  await ElMessageBox.confirm(`确认回滚到 ${version}？该操作会生成回滚记录。`, '版本回滚确认', { type: 'warning' })
  if (selectedModel.value) {
    await rollbackModelVersion(selectedModel.value.id, version)
    await loadVersions(selectedModel.value.id)
    // 回滚后更新详情数据：用新的当前版本刷新 selectedModel
    const newCurrent = versionHistory.value.find(v => v.current)
    if (newCurrent) {
      selectedModel.value = {
        ...selectedModel.value,
        version: newCurrent.version,
        accuracy: newCurrent.metrics,
        params: newCurrent.params,
        raw: newCurrent.raw,
      }
    }
  }
  ElMessage.success(`已回滚到 ${version}`)
}

const downloadVersion = (version: string) => {
  if (!selectedModel.value) return
  window.open(getModelDownloadUrl(selectedModel.value.id, version), '_blank')
}

const selectModel = async (model: ModelItem) => {
  selectedModel.value = model
  prediction.value = undefined
  inferenceInput.value = '请对当前模型做一次测试推理'
  await loadVersions(model.id)
}

const runPredict = async () => {
  if (!selectedModel.value || !inferenceInput.value.trim()) return
  predicting.value = true
  const modelCode = selectedModel.value.raw.model_code || selectedModel.value.id
  try {
    prediction.value = await predict(modelCode, { input: inferenceInput.value.trim() })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '推理失败')
  } finally {
    predicting.value = false
  }
}

const submitImport = async () => {
  if (!importForm.value.source_path || !importForm.value.model_name || !importForm.value.model_code) {
    ElMessage.warning('请填写导入信息')
    return
  }
  await importModel({ ...importForm.value })
  importDialogVisible.value = false
  await loadModels()
  ElMessage.success('模型导入成功')
}

const submitExport = async () => {
  if (!selectedModel.value || !exportForm.value.target_path) return
  await exportModel({
    model_code: selectedModel.value.id,
    version: selectedModel.value.version,
    target_path: exportForm.value.target_path,
  })
  exportDialogVisible.value = false
  ElMessage.success('模型导出成功')
}

onMounted(() => {
  loadModels().catch((error) => {
    ElMessage.error(error instanceof Error ? error.message : '模型列表加载失败')
  })
})
</script>

<style scoped>
.filters,
.detail-header,
.detail-actions,
.timeline-head,
.timeline-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.inference-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.inference-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.inference-input :deep(.el-textarea__inner) {
  height: 200px;
  resize: none;
}

.inference-output {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-header span {
  color: var(--text-muted);
  font-size: 13px;
}

.result-header strong {
  color: var(--primary-color);
  font-size: 14px;
}

.result-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 14px;
}

.result-box {
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  max-height: 240px;
  overflow-y: auto;
  flex: 1;
}


.result-box p {
  margin: 8px 0 0;
  color: var(--text-secondary);
}


.filters {
  width: 380px;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.model-card {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: #fff;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.model-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 8px 24px rgb(37 99 235 / 10%);
}

.model-icon,
.detail-icon {
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #fff;
}

.model-icon {
  width: 48px;
  height: 48px;
  font-size: 22px;
}

.model-info {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.model-info span {
  color: var(--text-muted);
  font-size: 13px;
}

.model-meta {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 13px;
}

.detail-header {
  margin-bottom: 20px;
}

.detail-icon {
  width: 56px;
  height: 56px;
  font-size: 24px;
}

.detail-title {
  flex: 1;
}

.detail-title h2 {
  margin: 0;
}

.detail-title span {
  color: var(--text-muted);
}

.metrics-bar {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.metric-stat {
  padding: 20px 24px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.metric-stat:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 16px rgb(37 99 235 / 8%);
}

.metric-stat-label {
  display: block;
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 8px;
}

.metric-stat-value {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.params-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.param-item {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.param-item span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.param-item strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

.artifact-item p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.artifact-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.artifact-item strong {
  display: block;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 14px;
}

.timeline-marker {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 50%;
  background: var(--border-color);
  color: #fff;
}

.timeline-item.current .timeline-marker {
  background: var(--success-color);
}

.timeline-content {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: #fff;
}

.timeline-content p {
  margin: 8px 0 0;
  font-size: 13px;
}

.timeline-actions {
  margin-top: 12px;
}

.compare-drawer {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.compare-summary,
.compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.compare-summary > div,
.compare-column {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.compare-summary span,
.compare-column span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.compare-summary strong,
.compare-column strong {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.5;
}

.compare-column.current {
  border-color: rgb(37 99 235 / 35%);
  background: rgb(37 99 235 / 5%);
}

.compare-column p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.compare-section h3 {
  margin: 0 0 10px;
  font-size: 15px;
}

.compare-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 4px;
}

@media (max-width: 900px) {
  .filters,
  .detail-header,
  .timeline-head,
  .timeline-actions {
    flex-wrap: wrap;
  }

  .filters,
  .model-grid {
    width: 100%;
  }

  .model-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metrics-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .model-grid,
  .metrics-bar,
  .params-grid,
  .compare-summary,
  .compare-grid,
  .inference-row {
    grid-template-columns: 1fr;
  }
}
</style>
