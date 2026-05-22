<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">多模态数据处理</h1>
      <p class="page-description">对接数据集接口，覆盖数据加载、质量校验和血缘追踪能力</p>
    </div>

    <div class="grid-4 stats">
      <MetricCard v-for="item in datasetStats" :key="item.title" :title="item.title" :value="item.value" />
    </div>

    <div class="card dataset-workspace">
      <div class="card-header">
        <div>
          <h3 class="card-title">数据处理工作台</h3>
          <p class="section-note">选择数据集后查看加载信息、质量报告和血缘链路。</p>
        </div>
        <el-select
          v-model="selectedDatasetId"
          class="dataset-select"
          :disabled="datasets.length === 0"
          placeholder="选择数据集"
          @change="handleDatasetChange"
        >
          <el-option v-for="item in datasets" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </div>

      <div class="card-body">
        <el-empty v-if="!selectedDataset" description="暂无数据集，请先通过数据加载创建或导入数据集" />

        <template v-else>
          <div class="dataset-context">
            <div>
              <span class="context-label">当前数据集</span>
              <strong>{{ selectedDataset.name }}</strong>
            </div>
            <div>
              <span class="context-label">类型</span>
              <strong>{{ selectedDataset.typeLabel }}</strong>
            </div>
            <div>
              <span class="context-label">大小</span>
              <strong>{{ selectedDataset.sizeLabel }}</strong>
            </div>
            <div>
              <span class="context-label">质量状态</span>
              <StatusBadge :label="selectedDataset.qualityLabel" :type="selectedDataset.qualityType" />
            </div>
          </div>

          <el-tabs v-model="activeDataTab">
            <el-tab-pane label="数据加载" name="load">
              <div class="feature-grid">
                <div class="feature-panel">
                  <div class="panel-copy">
                    <h4>多模态数据加载</h4>
                    <p>当前支持文本类数据集登记与文件上传。</p>
                  </div>
                  <div class="format-tags">
                    <el-tag v-for="format in supportedFormats" :key="format" effect="plain">{{ format }}</el-tag>
                  </div>
                  <div class="upload-summary">
                    <div>
                      <span class="context-label">来源</span>
                      <strong>{{ selectedDataset.raw.source || '未记录' }}</strong>
                    </div>
                    <div>
                      <span class="context-label">文件数</span>
                      <strong>{{ selectedDataset.raw.file_count }}</strong>
                    </div>
                  </div>
                  <div class="button-row">
                    <el-button type="primary" :icon="Upload" @click="openAppendDialog">追加文件</el-button>
                    <el-button :icon="VideoPlay" @click="startPreprocessJob">启动预处理</el-button>
                    <el-button :icon="Clock" @click="refreshProcessingJobs">刷新处理任务</el-button>
                  </div>
                </div>

                <div class="feature-panel">
                  <div class="panel-copy">
                    <h4>上传状态</h4>
                    <p>展示本次选择文件的校验、上传和后端处理结果。</p>
                  </div>
                  <div v-if="uploadRecords.length" class="upload-records">
                    <div v-for="file in uploadRecords" :key="file.uid" class="upload-record">
                      <div>
                        <strong>{{ file.name }}</strong>
                        <span>{{ file.sizeLabel }} · {{ file.format || '未知格式' }}</span>
                      </div>
                      <div class="upload-progress">
                        <el-progress :percentage="file.percent" :status="file.progressStatus" />
                        <StatusBadge :label="file.statusLabel" :type="file.statusType" />
                      </div>
                    </div>
                  </div>
                  <el-empty v-else description="尚未选择上传文件" :image-size="70" />
                </div>
              </div>

              <div class="job-list">
                <h4>处理任务</h4>
                <el-table :data="processingJobs" stripe>
                  <el-table-column prop="job_id" label="任务ID" min-width="160" />
                  <el-table-column prop="dataset_name" label="数据集" min-width="140" />
                  <el-table-column prop="job_type" label="类型" width="120" />
                  <el-table-column prop="status" label="状态" width="100" />
                  <el-table-column label="输出样本" width="110">
                    <template #default="{ row }">{{ row.record_count ?? '-' }}</template>
                  </el-table-column>
                  <el-table-column label="输出大小" width="110">
                    <template #default="{ row }">{{ row.processed_size ? formatSize(row.processed_size) : '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="progress" label="进度" width="160">
                    <template #default="{ row }"><el-progress :percentage="row.progress" /></template>
                  </el-table-column>
                </el-table>
              </div>
            </el-tab-pane>

            <el-tab-pane label="质量校验" name="quality">
              <div class="quality-toolbar">
                <div>
                  <h4>数据质量校验</h4>
                  <p>展示后端返回的完整性、一致性、时效性、准确性与异常记录。</p>
                </div>
                <div class="button-row">
                  <el-button type="primary" :loading="checking" :icon="VideoPlay" @click="startQualityCheck">开始校验</el-button>
                  <el-button :icon="Document" @click="openQualityReport">查看报告</el-button>
                  <el-button :loading="repairing" :icon="Tools" @click="repairQuality">自动修复/标记修复</el-button>
                </div>
              </div>

              <div class="score-band" :class="qualityLevel.className">
                <span>质量评分</span>
                <strong>{{ qualityScoreLabel }}</strong>
                <em>{{ qualityLevel.label }}</em>
              </div>

              <div class="inline-grid">
                <div v-for="item in qualityItems" :key="item.label" class="inline-card">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                  <small>{{ item.detail }}</small>
                </div>
              </div>

              <div class="issue-list">
                <h4>问题清单与修复建议</h4>
                <el-empty v-if="qualityIssues.length === 0" description="后端未返回质量问题" :image-size="70" />
                <el-table v-else :data="qualityIssues" stripe>
                  <el-table-column prop="index" label="#" width="70" />
                  <el-table-column prop="description" label="问题描述" min-width="180" />
                  <el-table-column prop="suggestion" label="修复建议" min-width="180" />
                </el-table>
              </div>
            </el-tab-pane>

            <el-tab-pane label="血缘追踪" name="lineage">
              <div class="quality-toolbar">
                <div>
                  <h4>数据血缘追踪</h4>
                  <p>展示来源、转换记录、上下游使用关系和影响分析。</p>
                </div>
                <div class="button-row">
                  <el-button type="primary" :icon="Share" @click="openLineageDrawer">查看血缘链路</el-button>
                  <el-button :loading="impactLoading" :icon="Connection" @click="openImpactDrawer">影响分析</el-button>
                  <el-button :icon="Clock" @click="showVersionTip">查看历史版本</el-button>
                </div>
              </div>

              <div class="lineage-flow">
                <div class="lineage-node">
                  <span>来源</span>
                  <strong>{{ lineageReport?.source || selectedDataset.raw.source || '未记录' }}</strong>
                  <small>上传者：{{ selectedDataset.ownerLabel }} · {{ selectedDataset.createdAt }}</small>
                </div>
                <div v-for="step in lineageSteps" :key="step.key" class="lineage-node">
                  <span>转换</span>
                  <strong>{{ step.description }}</strong>
                  <small>{{ step.timeLabel }} · {{ step.versionLabel }}</small>
                </div>
                <div class="lineage-node">
                  <span>使用</span>
                  <strong>{{ downstreamLabel }}</strong>
                  <small>关联训练任务与使用结果通过影响分析接口查看</small>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">数据集列表</h3>
        <el-button type="primary" :icon="Upload" @click="openCreateDialog">数据加载</el-button>
      </div>
      <div class="card-body table-wrap">
        <el-table v-loading="loading" :data="datasets" stripe @row-click="handleRowClick">
          <el-table-column prop="name" label="数据集名称" min-width="180">
            <template #default="{ row }"><strong>{{ row.name }}</strong></template>
          </el-table-column>
          <el-table-column prop="typeLabel" label="类型" width="100">
            <template #default="{ row }"><StatusBadge :label="row.typeLabel" type="info" /></template>
          </el-table-column>
          <el-table-column label="格式" width="130">
            <template #default="{ row }">{{ row.formatLabel }}</template>
          </el-table-column>
          <el-table-column prop="sizeLabel" label="大小" width="110" />
          <el-table-column prop="ownerLabel" label="上传者" min-width="120" />
          <el-table-column prop="createdAt" label="上传时间" width="120" />
          <el-table-column label="质量评分" width="120">
            <template #default="{ row }">{{ row.scoreLabel }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }"><StatusBadge :label="row.qualityLabel" :type="row.qualityType" /></template>
          </el-table-column>
          <el-table-column label="血缘状态" width="120">
            <template #default="{ row }"><StatusBadge :label="row.lineageLabel" :type="row.lineageType" /></template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="260">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button size="small" @click.stop="selectDataset(row.id, 'quality')">校验</el-button>
                <el-button size="small" @click.stop="selectDataset(row.id, 'lineage')">血缘</el-button>
                <el-button size="small" @click.stop="selectDataset(row.id, 'load')">加载</el-button>
                <el-button size="small" type="danger" @click.stop="removeDataset(row.id)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="680px">
      <el-form :model="importForm" label-position="top">
        <el-form-item label="批量上传入口">
          <el-upload
            v-model:file-list="uploadFiles"
            drag
            multiple
            action="#"
            :auto-upload="false"
            :on-change="handleUploadChange"
            :on-remove="handleUploadRemove"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>拖拽文件到此处，或点击选择数据文件</div>
            <template #tip>
              <div class="muted">支持 TXT、CSV、JSON、JSONL、DOC、DOCX、XLS、XLSX，单文件最大 2GB</div>
            </template>
          </el-upload>
        </el-form-item>

        <div v-if="uploadRecords.length" class="dialog-file-list">
          <div v-for="file in uploadRecords" :key="file.uid" class="dialog-file">
            <span>{{ file.name }}</span>
            <strong>{{ file.sizeLabel }} · {{ file.format || '未知格式' }}</strong>
            <StatusBadge :label="file.statusLabel" :type="file.statusType" />
          </div>
        </div>

        <div v-if="uploadMode === 'create'" class="form-grid">
          <el-form-item label="数据集名称">
            <el-input v-model="importForm.name" placeholder="输入数据集名称" />
          </el-form-item>
          <el-form-item label="数据类型">
            <el-select v-model="importForm.type" class="full">
              <el-option label="文本数据" value="text" />
              <el-option label="图像数据" value="image" />
              <el-option label="音频数据" value="audio" />
              <el-option label="表格数据" value="tabular" />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item v-if="uploadMode === 'create'" label="描述">
          <el-input v-model="importForm.desc" type="textarea" :rows="3" placeholder="输入数据集描述..." />
        </el-form-item>

        <el-form-item label="断点续传">
          <div class="resume-option">
            <el-switch v-model="resumeEnabled" />
            <div>
              <strong>{{ resumeEnabled ? '已启用' : '未启用' }}</strong>
              <p>启用后上传过程保留本地文件状态，失败后可重新提交同一批文件继续处理。</p>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">{{ submitButtonLabel }}</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="qualityDrawerVisible" title="质量校验报告" size="520px">
      <el-descriptions v-if="selectedDataset" :column="1" border>
        <el-descriptions-item label="数据集">{{ selectedDataset.name }}</el-descriptions-item>
        <el-descriptions-item label="评分">{{ qualityScoreLabel }}</el-descriptions-item>
        <el-descriptions-item label="结果状态">{{ qualityLevel.label }}</el-descriptions-item>
        <el-descriptions-item label="完整性">{{ qualityReport?.completeness === undefined ? '接口未返回' : passLabel(qualityReport.completeness) }}</el-descriptions-item>
        <el-descriptions-item label="一致性">{{ qualityReport?.consistency === undefined ? '接口未返回' : passLabel(qualityReport.consistency) }}</el-descriptions-item>
        <el-descriptions-item label="时效性">{{ qualityReport?.timeliness === undefined ? '接口未返回' : passLabel(qualityReport.timeliness) }}</el-descriptions-item>
        <el-descriptions-item label="准确性">{{ qualityReport?.accuracy === undefined ? '接口未返回' : passLabel(qualityReport.accuracy) }}</el-descriptions-item>
        <el-descriptions-item label="校验时间">{{ formatDateTime(qualityReport?.checked_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>

    <el-drawer v-model="lineageDrawerVisible" title="数据血缘链路" size="560px">
      <el-descriptions v-if="selectedDataset" :column="1" border>
        <el-descriptions-item label="数据来源">{{ lineageReport?.source || selectedDataset.raw.source || '未记录' }}</el-descriptions-item>
        <el-descriptions-item label="上传者">{{ selectedDataset.ownerLabel }}</el-descriptions-item>
        <el-descriptions-item label="上传时间">{{ selectedDataset.createdAt }}</el-descriptions-item>
      </el-descriptions>
      <div class="drawer-section">
        <h4>转换记录</h4>
        <el-timeline>
          <el-timeline-item v-for="step in lineageSteps" :key="step.key" :timestamp="step.timeLabel">
            <strong>{{ step.description }}</strong>
            <p class="timeline-meta">{{ step.versionLabel }} · {{ step.ruleLabel }}</p>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="lineageSteps.length === 0" description="暂无转换记录" :image-size="70" />
      </div>
    </el-drawer>

    <el-drawer v-model="impactDrawerVisible" title="影响分析" size="520px">
      <div class="impact-group">
        <h4>受影响训练任务</h4>
        <el-empty v-if="lineageImpact.affected_tasks.length === 0" description="暂无记录" :image-size="70" />
        <el-tag v-for="item in lineageImpact.affected_tasks" v-else :key="item" effect="plain">{{ item }}</el-tag>
      </div>
      <div class="impact-group">
        <h4>受影响模型版本</h4>
        <el-empty v-if="lineageImpact.affected_models.length === 0" description="暂无记录" :image-size="70" />
        <el-tag v-for="item in lineageImpact.affected_models" v-else :key="item" effect="plain">{{ item }}</el-tag>
      </div>
      <div class="impact-group">
        <h4>受影响下游数据集</h4>
        <el-empty v-if="lineageImpact.affected_datasets.length === 0" description="暂无记录" :image-size="70" />
        <el-tag v-for="item in lineageImpact.affected_datasets" v-else :key="item" effect="plain">{{ item }}</el-tag>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { UploadFile, UploadUserFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Clock, Connection, Document, Share, Tools, Upload, UploadFilled, VideoPlay } from '@element-plus/icons-vue'

import MetricCard from '@/components/MetricCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import {
  createDataset,
  deleteDataset as deleteDatasetApi,
  getDatasetStats,
  getLineage,
  getLineageImpact,
  getQualityReport,
  listDatasets,
  listProcessingJobs,
  startPreprocess,
  triggerQualityCheck,
  triggerQualityRepair,
  uploadDatasetFileWithProgress,
  uploadDatasetFilesBatchWithProgress,
  type BackendDataset,
  type DatasetStats,
  type Lineage,
  type LineageImpact,
  type ProcessingJob,
  type QualityReport,
} from '@/api/datasets'

type StatusType = 'success' | 'warning' | 'info' | 'danger'

interface DatasetView {
  id: number
  name: string
  typeLabel: string
  formatLabel: string
  sizeLabel: string
  ownerLabel: string
  createdAt: string
  updatedAt: string
  qualityLabel: string
  qualityType: StatusType
  lineageLabel: string
  lineageType: StatusType
  scoreLabel: string
  raw: BackendDataset
}

interface UploadRecord {
  uid: number
  name: string
  sizeLabel: string
  format: string
  percent: number
  statusLabel: string
  statusType: StatusType
  progressStatus?: 'success' | 'exception' | 'warning'
}

const MAX_UPLOAD_FILE_SIZE = 2 * 1024 ** 3
const supportedFormats = ['TXT', 'CSV', 'JSON', 'JSONL', 'DOC', 'DOCX', 'XLS', 'XLSX']
const formatByType: Record<string, string> = {
  text: 'TXT/CSV/JSON/JSONL/DOC/DOCX',
  image: '暂不支持',
  audio: '暂不支持',
  tabular: 'CSV/JSON/XLS/XLSX',
  video: '暂不支持',
}

const typeMap: Record<string, string> = {
  text: '文本',
  image: '图像',
  audio: '音频',
  video: '视频',
  tabular: '表格',
}

const qualityStatusMap: Record<string, { label: string; type: StatusType }> = {
  passed: { label: '合格', type: 'success' },
  unchecked: { label: '待校验', type: 'info' },
  checking: { label: '校验中', type: 'info' },
  repairing: { label: '修复中', type: 'warning' },
  failed: { label: '不合格', type: 'danger' },
}

const lineageStatusMap: Record<string, { label: string; type: StatusType }> = {
  tracked: { label: '已追踪', type: 'success' },
  complete: { label: '已追踪', type: 'success' },
  pending: { label: '待生成', type: 'info' },
  none: { label: '待生成', type: 'info' },
  missing: { label: '缺失', type: 'warning' },
}

const loading = ref(false)
const importing = ref(false)
const checking = ref(false)
const repairing = ref(false)
const impactLoading = ref(false)
const dialogVisible = ref(false)
const qualityDrawerVisible = ref(false)
const lineageDrawerVisible = ref(false)
const impactDrawerVisible = ref(false)
const activeDataTab = ref('load')
const selectedDatasetId = ref<number>()
const datasets = ref<DatasetView[]>([])
const stats = ref<DatasetStats>()
const uploadFiles = ref<UploadUserFile[]>([])
const uploadRecords = ref<UploadRecord[]>([])
const qualityReport = ref<QualityReport>()
const lineageReport = ref<Lineage>()
const lineageImpact = ref<LineageImpact>({ dataset_id: 0, affected_models: [], affected_tasks: [], affected_datasets: [] })
const processingJobs = ref<ProcessingJob[]>([])
const resumeEnabled = ref(true)
const uploadMode = ref<'create' | 'append'>('create')
const importForm = reactive({
  name: '',
  type: 'text',
  desc: '',
})

const dialogTitle = computed(() => (uploadMode.value === 'create' ? '多模态数据加载' : `追加文件到 ${selectedDataset.value?.name ?? '当前数据集'}`))
const submitButtonLabel = computed(() => (uploadMode.value === 'create' ? '创建并上传' : '追加上传'))

const formatSize = (size = 0) => {
  if (size >= 1024 ** 4) return `${(size / 1024 ** 4).toFixed(1)} TB`
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1)} GB`
  if (size >= 1024 ** 2) return `${(size / 1024 ** 2).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

const formatDate = (value?: string) => value?.slice(0, 10) || '-'
const formatDateTime = (value?: string | null) => (value ? value.replace('T', ' ').slice(0, 19) : '接口未返回')
const passLabel = (value: boolean) => (value ? '通过' : '未通过')

const getQualityStatus = (status: string) => qualityStatusMap[status] ?? { label: status || '未知', type: 'info' as const }
const getLineageStatus = (status: string) => lineageStatusMap[status] ?? { label: status || '未记录', type: 'info' as const }

const mapDataset = (item: BackendDataset): DatasetView => {
  const quality = getQualityStatus(item.quality_status)
  const lineage = getLineageStatus(item.lineage_status)

  return {
    id: item.id,
    name: item.name,
    typeLabel: typeMap[item.data_type] ?? item.data_type,
    formatLabel: formatByType[item.data_type] ?? '接口未返回',
    sizeLabel: formatSize(item.total_size),
    ownerLabel: item.owner?.real_name || item.owner?.username || '未记录',
    createdAt: formatDate(item.created_at),
    updatedAt: formatDate(item.updated_at),
    qualityLabel: quality.label,
    qualityType: quality.type,
    lineageLabel: lineage.label,
    lineageType: lineage.type,
    scoreLabel: '查看报告',
    raw: item,
  }
}

const selectedDataset = computed(() => datasets.value.find((item) => item.id === selectedDatasetId.value))

const datasetStats = computed(() => {
  const total = stats.value?.total_datasets ?? 0
  const completed = stats.value?.completed ?? 0
  const passRate = total > 0 ? `${Math.round((completed / total) * 100)}%` : '0%'
  const lineageCount = datasets.value.filter((item) => item.raw.lineage_status && item.raw.lineage_status !== 'pending').length

  return [
    { title: '数据集总数', value: total },
    { title: '已上传文件数', value: datasets.value.reduce((sum, item) => sum + item.raw.file_count, 0) },
    { title: '校验通过率', value: passRate },
    { title: '血缘记录数', value: lineageCount },
  ]
})

const qualityScore = computed(() => qualityReport.value?.overall_score)
const qualityScoreLabel = computed(() => (qualityScore.value === undefined ? '接口未返回' : qualityScore.value.toFixed(1)))
const qualityLevel = computed(() => {
  if (qualityScore.value === undefined) return { label: '暂无报告', className: 'score-empty' }
  if (qualityReport.value?.blocked_for_training) return { label: '阻断训练', className: 'score-danger' }
  if (qualityReport.value?.passed === false) return { label: qualityScore.value < 60 ? '告警' : '不合格', className: qualityScore.value < 60 ? 'score-danger' : 'score-warning' }
  if (qualityScore.value < 60) return { label: '告警', className: 'score-danger' }
  if (qualityScore.value < 80) return { label: '不合格', className: 'score-warning' }
  return { label: '合格', className: 'score-success' }
})

const qualityItems = computed(() => [
  {
    label: '完整性',
    value: qualityReport.value?.completeness === undefined ? '接口未返回' : passLabel(qualityReport.value.completeness),
    detail: `缺失率 ${formatPercent(qualityReport.value?.missing_rate_pct)} · 重复行 ${qualityReport.value?.duplicate_rows ?? 0}`,
  },
  {
    label: '一致性',
    value: qualityReport.value?.consistency === undefined ? '接口未返回' : passLabel(qualityReport.value.consistency),
    detail: `格式一致率 ${formatPercent(qualityReport.value?.format_rate_pct)} · 范围异常 ${qualityReport.value?.range_violations ?? 0}`,
  },
  {
    label: '时效性',
    value: qualityReport.value?.timeliness === undefined ? '接口未返回' : passLabel(qualityReport.value.timeliness),
    detail: `更新时间 ${selectedDataset.value?.updatedAt || '-'} · 数据年龄 ${qualityReport.value?.data_age_days ?? 0} 天`,
  },
  {
    label: '准确性',
    value: qualityReport.value?.accuracy === undefined ? '接口未返回' : passLabel(qualityReport.value.accuracy),
    detail: `异常值 ${formatPercent(qualityReport.value?.outlier_rate_pct)} · 规则异常 ${qualityReport.value?.rule_violations ?? 0}`,
  },
])

const qualityIssues = computed(() =>
  (qualityReport.value?.anomalies ?? []).map((item, index) => ({
    index: index + 1,
    description: String(item.issue ?? item.description ?? item.message ?? JSON.stringify(item)),
    suggestion: String(item.suggestion ?? qualityReport.value?.suggestions?.[index] ?? '请根据异常字段检查源数据或重新执行校验'),
  })),
)

const lineageSteps = computed(() =>
  (lineageReport.value?.transformations ?? []).map((step, index) => ({
    key: `${step.rule ?? 'transform'}-${step.timestamp ?? index}`,
    description: step.description || step.rule || '未命名转换',
    ruleLabel: step.rule || '未记录规则',
    timeLabel: formatDateTime(step.timestamp),
    versionLabel:
      step.version_before || step.version_after
        ? `${step.version_before ?? '初始'} -> ${step.version_after ?? '未记录'}`
        : '版本未变化',
  })),
)
const downstreamLabel = computed(() => {
  const downstream = lineageReport.value?.downstream ?? []
  if (downstream.length === 0) return '暂无下游记录'
  return downstream
    .map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object') {
        const record = item as Record<string, unknown>
        return String(record.task_name ?? record.model_code ?? record.task_id ?? record.type ?? '下游记录')
      }
      return String(item)
    })
    .join('、')
})

const getFileFormat = (filename: string) => filename.split('.').pop()?.toUpperCase() ?? ''
const isSupportedFile = (filename: string) => supportedFormats.includes(getFileFormat(filename))
const formatPercent = (value?: number) => (value === undefined || Number.isNaN(value) ? '-' : `${value.toFixed(1)}%`)
const buildStoragePath = (name: string) => {
  const safe = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
  return `/datasets/${safe || "dataset"}-${Date.now()}`
}

const syncUploadRecords = () => {
  uploadRecords.value = uploadFiles.value.map((file) => {
    const format = getFileFormat(file.name)
    const supported = isSupportedFile(file.name)
    const size = file.size ?? file.raw?.size ?? 0
    const tooLarge = size > MAX_UPLOAD_FILE_SIZE

    return {
      uid: Number(file.uid),
      name: file.name,
      sizeLabel: formatSize(size),
      format,
      percent: supported && !tooLarge ? 0 : 100,
      statusLabel: supported ? (tooLarge ? '文件过大' : '待上传') : '格式不支持',
      statusType: supported ? (tooLarge ? 'danger' : 'info') : 'danger',
      progressStatus: supported && !tooLarge ? undefined : 'exception',
    }
  })
}

const handleUploadChange = (_file: UploadFile, files: UploadUserFile[]) => {
  uploadFiles.value = files
  syncUploadRecords()
}

const handleUploadRemove = (_file: UploadFile, files: UploadUserFile[]) => {
  uploadFiles.value = files
  syncUploadRecords()
}

const resetImportForm = () => {
  importForm.name = ''
  importForm.type = 'text'
  importForm.desc = ''
  uploadFiles.value = []
  uploadRecords.value = []
}

const openCreateDialog = () => {
  uploadMode.value = 'create'
  resetImportForm()
  dialogVisible.value = true
}

const openAppendDialog = () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  uploadMode.value = 'append'
  resetImportForm()
  dialogVisible.value = true
}

const loadDatasets = async () => {
  loading.value = true
  try {
    const [statsData, datasetPage, jobsPage] = await Promise.all([
      getDatasetStats(),
      listDatasets({ page: 1, page_size: 100 }),
      listProcessingJobs({ page: 1, page_size: 20 }).catch(() => ({ data: [], total: 0, page: 1, page_size: 20 })),
    ])
    stats.value = statsData
    datasets.value = datasetPage.data.map(mapDataset)
    processingJobs.value = jobsPage.data

    if (!selectedDatasetId.value && datasets.value[0]) {
      await selectDataset(datasets.value[0].id)
    } else if (selectedDatasetId.value && !datasets.value.some((item) => item.id === selectedDatasetId.value)) {
      selectedDatasetId.value = datasets.value[0]?.id
    }
  } finally {
    loading.value = false
  }
}

const refreshProcessingJobs = async () => {
  const jobsPage = await listProcessingJobs({ page: 1, page_size: 20 })
  processingJobs.value = jobsPage.data
}

const loadDatasetDetails = async (datasetId: number) => {
  qualityReport.value = undefined
  lineageReport.value = undefined
  lineageImpact.value = { dataset_id: datasetId, affected_models: [], affected_tasks: [], affected_datasets: [] }

  const [quality, lineage] = await Promise.allSettled([getQualityReport(datasetId), getLineage(datasetId)])
  if (quality.status === 'fulfilled') {
    qualityReport.value = quality.value
    const item = datasets.value.find((dataset) => dataset.id === datasetId)
    if (item && quality.value) {
      item.raw.quality_status = quality.value.passed ? 'passed' : 'failed'
      const status = getQualityStatus(item.raw.quality_status)
      item.qualityLabel = status.label
      item.qualityType = status.type
    }
  }
  if (lineage.status === 'fulfilled') lineageReport.value = lineage.value
}

const selectDataset = async (datasetId: number, tab?: string) => {
  selectedDatasetId.value = datasetId
  if (tab) activeDataTab.value = tab
  await loadDatasetDetails(datasetId)
}

const handleDatasetChange = (datasetId: string | number | boolean | Record<string, unknown>) => {
  if (typeof datasetId === 'number') void selectDataset(datasetId)
}

const handleRowClick = (row: DatasetView) => {
  void selectDataset(row.id)
}

const startQualityCheck = async () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }

  checking.value = true
  try {
    qualityReport.value = await triggerQualityCheck(selectedDataset.value.id)
    await loadDatasets()
    ElMessage.success('质量校验已完成')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '质量校验失败')
  } finally {
    checking.value = false
  }
}

const openQualityReport = () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  qualityDrawerVisible.value = true
}

const repairQuality = async () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }

  repairing.value = true
  try {
    await triggerQualityRepair(selectedDataset.value.id)
    await loadDatasets()
    await loadDatasetDetails(selectedDataset.value.id)
    ElMessage.success('数据修复已提交')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '数据修复失败')
  } finally {
    repairing.value = false
  }
}

const openLineageDrawer = () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  lineageDrawerVisible.value = true
}

const openImpactDrawer = async () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }

  impactLoading.value = true
  try {
    lineageImpact.value = await getLineageImpact(selectedDataset.value.id)
    impactDrawerVisible.value = true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '影响分析加载失败')
  } finally {
    impactLoading.value = false
  }
}

const showVersionTip = () => {
  ElMessage.info('历史版本需要后端提供版本列表接口后展示')
}

const startPreprocessJob = async () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  const datasetId = selectedDataset.value.id
  try {
    await startPreprocess(datasetId)
    await refreshProcessingJobs()
    await loadDatasets()
    await loadDatasetDetails(datasetId)
    ElMessage.success('预处理已完成，质量状态已刷新')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '预处理失败')
  }
}

const removeDataset = async (datasetId: number) => {
  try {
    await deleteDatasetApi(datasetId)
    datasets.value = datasets.value.filter((item) => item.id !== datasetId)
    if (selectedDatasetId.value === datasetId) {
      selectedDatasetId.value = datasets.value[0]?.id
      if (selectedDatasetId.value) await loadDatasetDetails(selectedDatasetId.value)
      else {
        qualityReport.value = undefined
        lineageReport.value = undefined
      }
    }
    await loadDatasets()
    ElMessage.success('数据集已删除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '数据集删除失败')
  }
}

const submitImport = async () => {
  if (uploadMode.value === 'create' && !importForm.name.trim()) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  if (uploadMode.value === 'append' && !selectedDataset.value) {
    ElMessage.warning('请先选择要追加的数据集')
    return
  }
  if (uploadFiles.value.length === 0) {
    ElMessage.warning('请选择要上传的数据文件')
    return
  }

  const unsupported = uploadRecords.value.find((file) => file.statusLabel === '格式不支持' || file.statusLabel === '文件过大')
  if (unsupported) {
    ElMessage.warning(`${unsupported.name} ${unsupported.statusLabel}`)
    return
  }

  importing.value = true
  let targetDatasetId = selectedDataset.value?.id
  let createdDatasetId: number | undefined
  let createdDataset: BackendDataset | undefined
  let uploadedCount = 0

  try {
    const rawFiles: File[] = []
    uploadFiles.value.forEach((file) => {
      if (!file.raw) throw new Error('未能读取到浏览器文件对象，请重新选择文件后再上传')
      rawFiles.push(file.raw as File)
    })

    if (uploadMode.value === 'create') {
      const datasetName = importForm.name.trim()
      const dataset = await createDataset({
        name: datasetName,
        data_type: importForm.type,
        description: importForm.desc,
        source: '前端数据加载',
        storage_path: buildStoragePath(datasetName),
        file_count: 0,
        total_size: 0,
      })
      targetDatasetId = dataset.id
      createdDatasetId = dataset.id
      createdDataset = dataset
    }

    if (!targetDatasetId) throw new Error('未找到目标数据集')
    const ensuredTargetDatasetId = targetDatasetId
    if (createdDataset) {
      datasets.value = [mapDataset(createdDataset), ...datasets.value.filter((item) => item.id !== createdDataset?.id)]
      selectedDatasetId.value = ensuredTargetDatasetId
      qualityReport.value = undefined
      lineageReport.value = undefined
    }
    activeDataTab.value = 'load'
    dialogVisible.value = false

    if (rawFiles.length > 1) {
      uploadRecords.value.forEach((record) => {
        record.statusLabel = '批量上传中'
        record.statusType = 'info'
        record.percent = 1
      })
      const result = await uploadDatasetFilesBatchWithProgress(ensuredTargetDatasetId, rawFiles, (percent) => {
        uploadRecords.value.forEach((record) => {
          if (record.statusLabel === '批量上传中' || record.statusLabel === '写入存储中') {
            record.percent = percent
            if (percent >= 95 && percent < 100) record.statusLabel = '写入存储中'
          }
        })
      })
      uploadedCount = result.uploaded
      const resultsByName = new Map(result.files.map((item) => [String(item.filename ?? ''), item]))
      uploadRecords.value.forEach((record) => {
        const item = resultsByName.get(record.name)
        const success = item?.success === true
        record.statusLabel = success ? '上传成功' : String(item?.error ?? '上传失败')
        record.statusType = success ? 'success' : 'danger'
        record.percent = 100
        record.progressStatus = success ? 'success' : 'exception'
      })
      if (result.uploaded === 0) throw new Error('批量上传失败，未成功写入任何文件')
      if (result.failed > 0) ElMessage.warning(`已上传 ${result.uploaded} 个文件，${result.failed} 个文件失败`)
    } else {
      for (const file of uploadFiles.value) {
        const record = uploadRecords.value.find((item) => item.uid === Number(file.uid))
        if (!file.raw || !record) continue

        record.statusLabel = '上传中'
        record.statusType = 'info'
        record.percent = 1
        await uploadDatasetFileWithProgress(ensuredTargetDatasetId, file.raw, (percent) => {
          record.percent = percent
          if (percent >= 95 && percent < 100) record.statusLabel = '写入存储中'
        })
        uploadedCount += 1
        record.statusLabel = '上传成功'
        record.statusType = 'success'
        record.percent = 100
        record.progressStatus = 'success'
      }
    }

    await loadDatasets()
    await selectDataset(ensuredTargetDatasetId, 'load')
    uploadFiles.value = []
    importForm.name = ''
    importForm.desc = ''
    ElMessage.success(uploadMode.value === 'create' ? '数据集已创建，文件上传完成' : '文件已追加到当前数据集')
  } catch (error) {
    if (uploadMode.value === 'create' && createdDatasetId && uploadedCount === 0) {
      try {
        await deleteDatasetApi(createdDatasetId)
        datasets.value = datasets.value.filter((item) => item.id !== createdDatasetId)
        if (selectedDatasetId.value === createdDatasetId) selectedDatasetId.value = datasets.value[0]?.id
      } catch {
        ElMessage.warning('上传未成功，空数据集清理失败，请稍后手动删除')
      }
    }
    uploadRecords.value = uploadRecords.value.map((file) =>
      file.statusLabel === '上传中' || file.statusLabel === '批量上传中'
        ? { ...file, statusLabel: '上传中断', statusType: 'danger', progressStatus: 'exception' }
        : file,
    )
    ElMessage.error(error instanceof Error ? error.message : '数据加载失败')
  } finally {
    importing.value = false
  }
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

.dataset-context,
.upload-summary,
.form-grid {
  display: grid;
  gap: 14px;
}

.resume-option {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.resume-option strong {
  display: block;
  margin-bottom: 4px;
}

.resume-option p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.dataset-context {
  grid-template-columns: repeat(4, minmax(0, 1fr));
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

.dataset-context strong,
.upload-summary strong {
  margin-top: 5px;
  font-size: 15px;
}

.context-label {
  color: var(--text-muted);
  font-size: 12px;
}

.feature-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 18px;
}

.feature-panel,
.inline-card,
.issue-list {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.feature-panel {
  display: flex;
  min-height: 250px;
  flex-direction: column;
  gap: 16px;
}

.panel-copy {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-color);
}

.panel-copy h4,
.quality-toolbar h4,
.issue-list h4,
.drawer-section h4,
.impact-group h4 {
  margin: 0 0 6px;
  font-size: 16px;
}

.panel-copy p,
.quality-toolbar p,
.lineage-node small,
.inline-card small {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.format-tags,
.button-row,
.upload-records,
.dialog-file-list,
.impact-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.format-tags,
.upload-summary {
  margin-top: 0;
}

.upload-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.upload-summary > div {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #fff;
}

.upload-records {
  flex-direction: column;
  margin-top: 14px;
}

.upload-record,
.dialog-file {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 12px;
  align-items: center;
}

.upload-record strong,
.upload-record span,
.dialog-file span,
.dialog-file strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-record span,
.dialog-file strong {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 400;
}

.upload-progress {
  display: grid;
  gap: 6px;
}

.quality-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.button-row {
  justify-content: flex-end;
  margin-top: auto;
  padding-top: 2px;
}

.score-band {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--bg-color);
}

.score-band strong {
  font-size: 30px;
}

.score-band em {
  font-style: normal;
  font-weight: 700;
}

.score-success strong,
.score-success em {
  color: var(--success-color);
}

.score-warning strong,
.score-warning em {
  color: var(--warning-color);
}

.score-danger strong,
.score-danger em {
  color: var(--danger-color);
}

.score-empty strong,
.score-empty em {
  color: var(--text-muted);
}

.inline-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.inline-card span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.inline-card strong {
  display: block;
  margin-top: 6px;
  font-size: 20px;
}

.inline-card small {
  display: block;
  margin-top: 8px;
}

.lineage-flow {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.lineage-node {
  position: relative;
  min-height: 118px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.lineage-node span {
  color: var(--text-muted);
  font-size: 12px;
}

.lineage-node strong {
  display: block;
  margin: 8px 0;
  font-size: 16px;
}

.table-wrap {
  overflow-x: auto;
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.table-actions :deep(.el-button) {
  margin-left: 0;
}

.upload-icon {
  color: var(--primary-color);
  font-size: 36px;
}

.dialog-file-list {
  flex-direction: column;
  margin-bottom: 16px;
}

.dialog-file {
  grid-template-columns: minmax(0, 1fr) 160px 90px;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.timeline-meta {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.drawer-section,
.impact-group {
  margin-top: 18px;
}

.impact-group {
  flex-direction: column;
}

@media (max-width: 1100px) {
  .feature-grid,
  .lineage-flow {
    grid-template-columns: 1fr;
  }

  .inline-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .dataset-workspace .card-header,
  .quality-toolbar {
    flex-direction: column;
  }

  .dataset-select,
  .button-row {
    width: 100%;
  }

  .button-row {
    justify-content: flex-start;
  }

  .dataset-context,
  .upload-summary,
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .dataset-context,
  .upload-summary,
  .inline-grid,
  .form-grid,
  .upload-record,
  .dialog-file {
    grid-template-columns: 1fr;
  }
}
</style>
