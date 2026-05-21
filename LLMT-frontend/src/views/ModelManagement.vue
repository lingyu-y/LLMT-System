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
              <span>{{ model.type }}</span>
            </span>
            <span class="model-meta">
              <span>{{ model.version }}</span>
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
        <el-button type="primary" :icon="Plus" @click="ElMessage.success('已创建新版本草稿')">创建新版本</el-button>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-header"><h3 class="card-title">版本概述</h3></div>
          <div class="card-body overview-grid">
            <div class="overview-card"><span>当前版本</span><strong>{{ selectedModel.version }}</strong></div>
            <div class="overview-card"><span>来源任务</span><strong>{{ selectedTrainingMeta.taskId }}</strong></div>
            <div class="overview-card"><span>评估指标</span><strong>{{ selectedModel.accuracy }}</strong></div>
            <div class="overview-card"><span>参数量</span><strong>{{ selectedModel.params }}</strong></div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><h3 class="card-title">训练来源</h3></div>
          <div class="card-body params-grid">
            <div v-for="[label, value] in trainingSourceItems" :key="label" class="param-item">
              <span>{{ label }}</span>
              <strong>{{ value }}</strong>
            </div>
          </div>
        </div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-header"><h3 class="card-title">训练配置追溯</h3></div>
          <div class="card-body trace-list">
            <div v-for="item in trainingTrace" :key="item.label" class="trace-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <p>{{ item.detail }}</p>
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

      <div class="card">
        <div class="card-header"><h3 class="card-title">版本历史</h3></div>
        <div class="card-body timeline">
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
      </div>
    </template>

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, DataLine, Download, Management, Plus, RefreshLeft } from '@element-plus/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'
import {
  getModelDownloadUrl,
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
const compareVersion = ref<VersionItem>()
const models = ref<ModelItem[]>([])
const versionHistory = ref<VersionItem[]>([])

const colors = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #06b6d4, #0891b2)',
]

const getMetricText = (metrics?: Record<string, unknown>) => {
  const accuracy = metrics?.accuracy ?? metrics?.acc ?? metrics?.score
  if (typeof accuracy === 'number') return `${accuracy > 1 ? accuracy.toFixed(1) : (accuracy * 100).toFixed(1)}%`
  if (typeof accuracy === 'string') return accuracy
  return '-'
}

const mapModel = (item: BackendModel, index = 0): ModelItem => ({
  id: item.model_code,
  name: item.model_name,
  type: `${item.framework ?? 'Unknown'} · ${item.tag ?? '模型'}`,
  version: item.version,
  accuracy: getMetricText(item.metrics_json),
  params: typeof item.hyperparams_json?.params === 'string' ? item.hyperparams_json.params : '-',
  color: colors[index % colors.length]!,
  raw: item,
})

const mapVersion = (item: BackendModel): VersionItem => ({
  version: item.version,
  status: item.is_current ? '当前版本' : item.tag ?? '',
  date: item.created_at?.replace('T', ' ').slice(0, 16) ?? '-',
  metrics: Object.keys(item.metrics_json ?? {}).length ? JSON.stringify(item.metrics_json) : '暂无评估指标',
  params: `框架 ${item.framework ?? '-'} · 超参数 ${JSON.stringify(item.hyperparams_json ?? {})}`,
  training: `数据集版本 ${item.dataset_version ?? '-'} · 模型编码 ${item.model_code}`,
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

const trainingMetaMap = {
  bert: {
    taskId: 'TR-20260425-01',
    dataset: '电商评论文本数据 v2.3',
    framework: 'DeepSpeed',
    parallel: '数据并行 + 流水线并行',
    resource: '4x A100 80GB',
    checkpoint: 'ckpt/TR-20260425-01/step-12840',
    config: 'configs/TR-20260425-01.yaml',
  },
  resnet: {
    taskId: 'TR-20260425-02',
    dataset: '产品图像分类集 v1.8',
    framework: 'PyTorch',
    parallel: '数据并行',
    resource: '2x A100 80GB',
    checkpoint: 'ckpt/TR-20260425-02/best',
    config: 'configs/TR-20260425-02.yaml',
  },
  whisper: {
    taskId: 'TR-20260424-09',
    dataset: '语音指令识别数据 v1.4',
    framework: 'PyTorch',
    parallel: '数据并行',
    resource: '1x A100 80GB',
    checkpoint: 'ckpt/TR-20260424-09/paused-step-8400',
    config: 'configs/TR-20260424-09.yaml',
  },
} as const

const defaultTrainingMeta = {
  taskId: 'TR-20260420-06',
  dataset: '训练数据集 v1.0',
  framework: 'DeepSpeed',
  parallel: '数据并行',
  resource: '2x A100 80GB',
  checkpoint: 'ckpt/default/best',
  config: 'configs/default.yaml',
}

const selectedTrainingMeta = computed(() =>
  selectedModel.value ? (trainingMetaMap[selectedModel.value.id as keyof typeof trainingMetaMap] ?? defaultTrainingMeta) : defaultTrainingMeta,
)

const trainingSourceItems = computed<[string, string][]>(() => [
  ['训练任务', selectedTrainingMeta.value.taskId],
  ['数据集版本', selectedTrainingMeta.value.dataset],
  ['训练框架', selectedTrainingMeta.value.framework],
  ['资源规格', selectedTrainingMeta.value.resource],
])

const trainingTrace = computed(() => [
  { label: '并行策略', value: selectedTrainingMeta.value.parallel, detail: '由训练模块的混合并行配置生成' },
  { label: '配置文件', value: selectedTrainingMeta.value.config, detail: '保存训练框架、资源规格和监控采集配置' },
  { label: '数据来源', value: selectedTrainingMeta.value.dataset, detail: '关联数据处理模块中的数据集版本和质量校验结果' },
])

const artifacts = computed(() => [
  { label: '模型文件', path: `models/${selectedModel.value?.id}/${selectedModel.value?.version}/model.bin`, status: '已归档', type: 'success' as const },
  { label: 'Checkpoint', path: selectedTrainingMeta.value.checkpoint, status: '可恢复', type: 'info' as const },
  { label: '训练配置', path: selectedTrainingMeta.value.config, status: '已保存', type: 'success' as const },
])

const currentVersion = computed(() => versionHistory.value.find((item) => item.current) ?? versionHistory.value[0])
const historicalCheckpoint = computed(() => `ckpt/${compareVersion.value?.version ?? 'history'}/best`)

const openCompareDrawer = (version: VersionItem) => {
  compareVersion.value = version
  compareDrawerVisible.value = true
}

const rollback = async (version: string) => {
  await ElMessageBox.confirm(`确认回滚到 ${version}？该操作会生成回滚记录。`, '版本回滚确认', { type: 'warning' })
  if (selectedModel.value) {
    await rollbackModelVersion(selectedModel.value.id, version)
    await loadVersions(selectedModel.value.id)
  }
  ElMessage.success(`已回滚到 ${version}`)
}

const downloadVersion = (version: string) => {
  if (!selectedModel.value) return
  window.open(getModelDownloadUrl(selectedModel.value.id, version), '_blank')
}

const selectModel = async (model: ModelItem) => {
  selectedModel.value = model
  await loadVersions(model.id)
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
.timeline-head,
.timeline-actions {
  display: flex;
  align-items: center;
  gap: 12px;
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

.overview-grid,
.params-grid,
.trace-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.overview-card,
.param-item,
.trace-item {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.overview-card span,
.param-item span,
.trace-item span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.overview-card strong,
.param-item strong,
.trace-item strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

.trace-list {
  grid-template-columns: 1fr;
}

.trace-item p,
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
}

@media (max-width: 640px) {
  .model-grid,
  .overview-grid,
  .params-grid,
  .compare-summary,
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
