<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">多模态数据处理</h1>
      <p class="page-description">支持文本、图像、音频等异构数据的统一处理与预处理</p>
    </div>

    <div class="grid-4 stats">
      <MetricCard v-for="item in datasetStats" :key="item.title" :title="item.title" :value="item.value" />
    </div>

    <div class="card dataset-workspace">
      <div class="card-header">
        <div>
          <h3 class="card-title">数据集工作台</h3>
          <p class="section-note">选择一个数据集后查看对应的处理配置、质量校验和血缘链路。</p>
        </div>
        <el-select v-model="selectedDatasetName" class="dataset-select" @change="handleDatasetChange">
          <el-option v-for="item in datasets" :key="item.name" :label="item.name" :value="item.name" />
        </el-select>
      </div>
      <div class="card-body">
        <div class="dataset-context">
          <div>
            <span class="context-label">当前数据集</span>
            <strong>{{ selectedDataset?.name }}</strong>
          </div>
          <div>
            <span class="context-label">数据类型</span>
            <strong>{{ selectedDataset?.type }}</strong>
          </div>
          <div>
            <span class="context-label">样本规模</span>
            <strong>{{ selectedDataset?.samples }}</strong>
          </div>
          <div>
            <span class="context-label">版本</span>
            <strong>{{ selectedProfile.version }}</strong>
          </div>
        </div>

        <el-tabs v-model="activeDataTab">
          <el-tab-pane label="数据处理" name="processing">
            <div class="dataset-panel">
              <div class="panel-copy">
                <h4>{{ selectedDataset?.name }} 处理任务</h4>
                <p>数据源：{{ selectedProfile.source }}；负责人：{{ selectedProfile.owner }}</p>
              </div>
              <div class="process-status">
                <StatusBadge :label="selectedDataset?.status ?? '-'" :type="selectedDataset?.statusType ?? 'info'" />
                <span v-if="selectedProcessingJob">{{ selectedProcessingJob.detail }}</span>
                <span v-else>暂无运行中的预处理任务，可在下方配置后提交。</span>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="数据质量校验" name="quality">
            <div class="inline-grid">
              <div v-for="item in qualityItems" :key="item.label" class="inline-card">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <p class="tab-note">以上指标仅对应当前选中的 {{ selectedDataset?.name }}，不会汇总其它数据集。</p>
          </el-tab-pane>
          <el-tab-pane label="数据血缘追踪" name="lineage">
            <el-steps :active="selectedProfile.activeStep" finish-status="success" align-center>
              <el-step
                v-for="step in selectedProfile.lineage"
                :key="step.title"
                :title="step.title"
                :description="step.description"
              />
            </el-steps>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">数据集列表</h3>
        <el-button type="primary" :icon="Upload" @click="dialogVisible = true">导入数据</el-button>
      </div>
      <div class="card-body">
        <el-table :data="datasets" stripe @row-click="handleRowClick">
          <el-table-column prop="name" label="数据集名称" min-width="180">
            <template #default="{ row }"><strong>{{ row.name }}</strong></template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="{ row }"><StatusBadge :label="row.type" type="info" /></template>
          </el-table-column>
          <el-table-column prop="samples" label="样本数" width="130" />
          <el-table-column prop="size" label="大小" width="110" />
          <el-table-column prop="status" label="预处理状态" width="130">
            <template #default="{ row }"><StatusBadge :label="row.status" :type="row.statusType" /></template>
          </el-table-column>
          <el-table-column prop="createdAt" label="创建时间" width="130" />
          <el-table-column label="操作" width="210">
            <template #default="{ row }">
              <el-button size="small" @click.stop="selectDataset(row.name, 'quality')">校验</el-button>
              <el-button size="small" @click.stop="selectDataset(row.name, 'lineage')">血缘</el-button>
              <el-button size="small" @click.stop="selectDataset(row.name, 'processing')">处理</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">预处理配置</h3>
        </div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="选择数据集">
              <el-select v-model="preprocess.dataset" class="full" @change="handlePreprocessDatasetChange">
                <el-option v-for="item in datasets" :key="item.name" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="批次大小 (Batch Size)">
              <el-input-number v-model="preprocess.batchSize" :min="1" />
            </el-form-item>
            <el-form-item label="工作进程数">
              <el-input-number v-model="preprocess.workers" :min="1" />
            </el-form-item>
            <el-form-item label="是否打乱数据">
              <el-switch v-model="preprocess.shuffle" />
            </el-form-item>
            <el-button type="primary" class="full" :icon="VideoPlay" @click="startProcess">开始处理</el-button>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">处理进度</h3>
        </div>
        <div class="card-body progress-list">
          <div v-for="job in processingJobs" :key="job.name" class="processing-item">
            <div class="processing-title">
              <strong>{{ job.name }}</strong>
              <span>{{ job.percent }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" :class="job.color" :style="{ width: `${job.percent}%` }"></div>
            </div>
            <p>{{ job.detail }}</p>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="导入数据" width="560px">
      <el-form :model="importForm" label-position="top">
        <el-form-item label="上传文件">
          <el-upload drag multiple action="#" :auto-upload="false">
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>拖拽文件到此处，或点击选择数据文件</div>
            <template #tip><div class="muted">支持文本、图像、音频、视频与压缩包数据集</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item label="数据集名称">
          <el-input v-model="importForm.name" placeholder="输入数据集名称" />
        </el-form-item>
        <el-form-item label="数据类型">
          <el-select v-model="importForm.type" class="full">
            <el-option label="文本数据" value="text" />
            <el-option label="图像数据" value="image" />
            <el-option label="音频数据" value="audio" />
            <el-option label="视频数据" value="video" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="importForm.desc" type="textarea" :rows="3" placeholder="输入数据集描述..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, UploadFilled, VideoPlay } from '@element-plus/icons-vue'

import MetricCard from '@/components/MetricCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import {
  createDataset,
  getLineage,
  getQualityReport,
  getDatasetStats,
  listDatasets,
  listProcessingJobs,
  startPreprocess,
  type BackendDataset,
  type Lineage,
  type ProcessingJob,
  type QualityReport,
} from '@/api/datasets'

type StatusType = 'success' | 'warning' | 'info' | 'danger'
type Dataset = {
  id: number
  name: string
  type: string
  samples: string
  size: string
  status: string
  statusType: StatusType
  createdAt: string
  raw: BackendDataset
}

const dialogVisible = ref(false)
const activeDataTab = ref('processing')
const datasets = ref<Dataset[]>([])
const datasetStats = ref<{ title: string; value: string | number }[]>([])
const processingJobs = ref<{ id: string; name: string; percent: number; detail: string; color: string }[]>([])
const selectedDatasetName = ref('')
const preprocess = reactive({ dataset: '', batchSize: 32, workers: 4, shuffle: true })
const importForm = reactive({ name: '', type: 'text', desc: '' })
const qualityReport = ref<QualityReport>()
const lineageReport = ref<Lineage>()

const formatSize = (size: number) => {
  if (size >= 1024 ** 4) return `${(size / 1024 ** 4).toFixed(1)} TB`
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1)} GB`
  if (size >= 1024 ** 2) return `${(size / 1024 ** 2).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

const statusMap: Record<string, { label: string; type: StatusType }> = {
  passed: { label: '已完成', type: 'success' },
  unchecked: { label: '未校验', type: 'info' },
  checking: { label: '处理中', type: 'info' },
  repairing: { label: '修复中', type: 'warning' },
  failed: { label: '失败', type: 'danger' },
}

const typeMap: Record<string, string> = {
  text: '文本',
  image: '图像',
  audio: '音频',
  video: '视频',
  tabular: '表格',
}

const mapDataset = (item: BackendDataset): Dataset => {
  const status = statusMap[item.quality_status] ?? { label: item.quality_status, type: 'info' as const }
  return {
    id: item.id,
    name: item.name,
    type: typeMap[item.data_type] ?? item.data_type,
    samples: item.file_count.toLocaleString(),
    size: formatSize(item.total_size),
    status: status.label,
    statusType: status.type,
    createdAt: item.created_at?.slice(0, 10) ?? '-',
    raw: item,
  }
}

const mapJob = (job: ProcessingJob) => ({
  id: job.job_id,
  name: job.dataset_name,
  percent: job.progress,
  detail: `状态: ${job.status} · 任务: ${job.job_id}`,
  color: job.status === 'running' ? 'blue' : 'green',
})

const loadDatasets = async () => {
  const [stats, datasetPage, jobPage] = await Promise.all([
    getDatasetStats(),
    listDatasets({ page: 1, page_size: 100 }),
    listProcessingJobs({ page: 1, page_size: 100 }),
  ])

  datasetStats.value = [
    { title: '数据集总数', value: stats.total_datasets },
    { title: '数据总量', value: formatSize(stats.total_size) },
    { title: '处理中', value: stats.processing },
    { title: '已完成', value: stats.completed },
  ]
  datasets.value = datasetPage.data.map(mapDataset)
  processingJobs.value = jobPage.data.map(mapJob)

  if (!selectedDatasetName.value && datasets.value[0]) {
    selectDataset(datasets.value[0].name)
  }
}

const defaultProfile = {
  owner: '数据工程组',
  source: '对象存储 / 批量上传',
  version: 'v1.0',
  activeStep: 3,
  quality: [
    { label: '完整率', value: '98.6%' },
    { label: '重复率', value: '1.2%' },
    { label: '异常样本', value: '342' },
    { label: '质量评分', value: 'A-' },
  ],
  lineage: [
    { title: '原始数据导入', description: '对象存储 / CSV / JSONL' },
    { title: '清洗去重', description: '规则过滤与样本归一化' },
    { title: '特征构建', description: 'Tokenizer 与向量索引' },
    { title: '训练集发布', description: '生成版本化数据集' },
  ],
}

const selectedDataset = computed(() => datasets.value.find((item) => item.name === selectedDatasetName.value) ?? datasets.value[0])
const selectedProfile = computed(() => ({
  ...defaultProfile,
  owner: selectedDataset.value?.raw.owner?.real_name ?? selectedDataset.value?.raw.owner?.username ?? defaultProfile.owner,
  source: selectedDataset.value?.raw.source ?? defaultProfile.source,
  version: selectedDataset.value?.raw.version ?? defaultProfile.version,
  activeStep: lineageReport.value ? 3 : defaultProfile.activeStep,
  lineage: lineageReport.value
    ? [
        { title: '数据来源', description: lineageReport.value.source ?? '未记录' },
        ...lineageReport.value.transformations.map((item) => ({ title: item, description: '已记录处理步骤' })),
      ]
    : defaultProfile.lineage,
}))
const selectedProcessingJob = computed(() => processingJobs.value.find((job) => job.name === selectedDatasetName.value))
const qualityItems = computed(() =>
  qualityReport.value
    ? [
        { label: '完整性', value: qualityReport.value.completeness ? '通过' : '未通过' },
        { label: '一致性', value: qualityReport.value.consistency ? '通过' : '未通过' },
        { label: '异常样本', value: String(qualityReport.value.anomalies.length) },
        { label: '质量评分', value: qualityReport.value.overall_score.toFixed(1) },
      ]
    : defaultProfile.quality,
)

const selectDataset = (name: string, tab?: string) => {
  selectedDatasetName.value = name
  preprocess.dataset = name
  if (tab) activeDataTab.value = tab
  const dataset = datasets.value.find((item) => item.name === name)
  if (dataset) {
    void Promise.all([getQualityReport(dataset.id), getLineage(dataset.id)])
      .then(([quality, lineage]) => {
        qualityReport.value = quality
        lineageReport.value = lineage
      })
      .catch(() => undefined)
  }
}

const handleDatasetChange = (name: string | number | boolean | Record<string, unknown>) => {
  if (typeof name === 'string') selectDataset(name)
}

const handlePreprocessDatasetChange = (name: string | number | boolean | Record<string, unknown>) => {
  if (typeof name === 'string') selectDataset(name, 'processing')
}

const handleRowClick = (row: Dataset) => selectDataset(row.name)

const startProcess = async () => {
  const dataset = datasets.value.find((item) => item.name === preprocess.dataset)
  if (!dataset) {
    ElMessage.warning('请先选择数据集')
    return
  }
  await startPreprocess(dataset.id)
  await loadDatasets()
  ElMessage.success(`已提交 ${preprocess.dataset} 的预处理任务`)
}

const submitImport = async () => {
  if (!importForm.name.trim()) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  await createDataset({
    name: importForm.name,
    data_type: importForm.type,
    description: importForm.desc,
    source: '前端导入',
  })
  dialogVisible.value = false
  await loadDatasets()
  ElMessage.success(`正在导入数据集: ${importForm.name}`)
}

onMounted(() => {
  loadDatasets().catch((error) => {
    ElMessage.error(error instanceof Error ? error.message : '数据集加载失败')
  })
})
</script>

<style scoped>
.stats {
  margin-bottom: 22px;
}

.full {
  width: 100%;
}

.dataset-workspace .card-header {
  align-items: flex-start;
}

.section-note {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.dataset-select {
  width: min(320px, 100%);
}

.dataset-context {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.dataset-context strong,
.context-label {
  display: block;
}

.dataset-context strong {
  margin-top: 5px;
  font-size: 15px;
}

.context-label {
  color: var(--text-muted);
  font-size: 12px;
}

.dataset-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.panel-copy h4 {
  margin: 0 0 6px;
  font-size: 16px;
}

.panel-copy p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.process-status {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  color: var(--text-muted);
  font-size: 13px;
  text-align: right;
}

.progress-list {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.processing-title {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.processing-title span {
  color: var(--primary-color);
  font-weight: 700;
}

.processing-item p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.upload-icon {
  color: var(--primary-color);
  font-size: 36px;
}

.tab-note {
  margin: 0;
  color: var(--text-secondary);
}

.inline-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.inline-card {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.inline-card span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.inline-card strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
}

@media (max-width: 900px) {
  .dataset-workspace .card-header,
  .dataset-panel {
    flex-direction: column;
  }

  .dataset-select {
    width: 100%;
  }

  .dataset-context {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .process-status {
    align-items: flex-start;
    text-align: left;
  }
}

@media (max-width: 640px) {
  .dataset-context,
  .inline-grid {
    grid-template-columns: 1fr;
  }
}
</style>
