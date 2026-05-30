<template>
  <div>
    <!-- 页面标题区，说明当前模块覆盖数据加载、质量校验、血缘追踪三条主线。 -->
    <div class="page-header">
      <h1 class="page-title">数据处理</h1>
      <p class="page-description">对接数据集接口，覆盖数据加载、质量校验和血缘追踪能力</p>
    </div>

    <!-- 顶部统计卡片，数据由 datasetStats computed 汇总得到。 -->
    <div class="grid-4 stats">
      <MetricCard v-for="item in datasetStats" :key="item.title" :title="item.title" :value="item.value" />
    </div>

    <!-- 主工作区：左侧数据集列表，右侧当前数据集的处理工作台。 -->
    <div class="data-workbench">
      <div class="card dataset-list-panel">
        <div class="card-header">
          <div>
            <h3 class="card-title">数据集</h3>
            <p class="section-note">{{ datasets.length }} 个数据集 · {{ processingJobs.length }} 个处理任务</p>
          </div>
          <el-button type="primary" :icon="Upload" @click="openCreateDialog">数据加载</el-button>
        </div>
        <div class="card-body dataset-list-body">
          <!-- 本地搜索，不重新请求后端；搜索范围在 filteredDatasets 中定义。 -->
          <el-input
            v-model="datasetKeyword"
            class="dataset-search"
            clearable
            :prefix-icon="Search"
            placeholder="搜索数据集"
          />
          <el-table
            v-loading="loading"
            :data="filteredDatasets"
            class="dataset-list-table"
            highlight-current-row
            row-key="id"
            stripe
            :current-row-key="selectedDatasetId"
            @row-click="handleRowClick"
          >
            <el-table-column prop="name" label="数据集" min-width="170">
              <template #default="{ row }">
                <div class="dataset-cell">
                  <strong>{{ row.name }}</strong>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="92">
              <template #default="{ row }"><StatusBadge :label="row.qualityLabel" :type="row.qualityType" /></template>
            </el-table-column>
            <el-table-column prop="sizeLabel" label="大小" width="92" />
          </el-table>
        </div>
      </div>

      <div class="card dataset-workspace">
        <div class="card-header">
          <div>
            <h3 class="card-title">数据处理工作台</h3>
            <p class="section-note">选择数据集后查看加载信息、质量报告和血缘链路。</p>
          </div>
          <div class="workspace-actions">
            <el-button v-if="selectedDataset" :icon="Delete" type="danger" plain @click="removeDataset(selectedDataset.id)">删除</el-button>
          </div>
        </div>

        <div class="card-body">
          <el-empty v-if="!selectedDataset" description="暂无数据集，请先通过数据加载创建或导入数据集" />

          <template v-else>
            <!-- 当前选中数据集的摘要信息。 -->
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
              <div>
                <span class="context-label">血缘状态</span>
                <StatusBadge :label="selectedDataset.lineageLabel" :type="selectedDataset.lineageType" />
              </div>
              <div>
                <span class="context-label">上传者</span>
                <strong>{{ selectedDataset.ownerLabel }}</strong>
              </div>
            </div>

          <el-tabs v-model="activeDataTab">
            <!-- 数据加载 Tab：追加文件、启动预处理、查看处理任务。 -->
            <el-tab-pane label="数据加载" name="load">
              <div class="feature-grid">
                <div class="feature-panel load-actions-panel">
                  <div class="panel-copy">
                    <h4>数据加载操作</h4>
                  </div>
                  <div class="load-action-grid">
                    <el-button type="primary" :icon="Upload" @click="openAppendDialog">追加文件</el-button>
                    <span class="shard-control">
                      <span>分片大小</span>
                      <el-input-number
                        v-model="shardSizeMb"
                        :min="0"
                        :max="10240"
                        :step="100"
                        size="small"
                      />
                      <span>MB</span>
                    </span>
                    <el-button :icon="VideoPlay" :loading="preprocessing" @click="startPreprocessJob">启动预处理</el-button>
                    <el-button :icon="Clock" :loading="refreshingJobs" @click="refreshProcessingJobs">刷新处理任务</el-button>
                  </div>
                </div>

                <div class="feature-panel">
                  <div class="panel-copy">
                    <h4>上传状态</h4>
                    <p>展示本次选择文件的校验、上传和后端处理结果。</p>
                  </div>
                  <div v-if="uploadRecords.length" class="upload-records">
                    <!-- 上传记录展示本次选择文件的前端校验、上传进度和最终结果。 -->
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
                  <el-empty v-else class="upload-empty" description="尚未选择上传文件" />
                </div>
              </div>

              <!-- 后端处理任务列表，包括预处理任务进度。 -->
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

            <!-- 质量校验 Tab：展示后端质量报告，并提供校验和修复入口。 -->
            <el-tab-pane label="质量校验" name="quality">
              <div class="quality-toolbar">
                <div>
                  <h4>数据质量校验</h4>
                  <p>展示后端返回的完整性、一致性、时效性、准确性与异常记录。</p>
                </div>
                <div class="button-row">
                  <el-button type="primary" :loading="checking" :icon="VideoPlay" @click="startQualityCheck">开始校验</el-button>
                  <el-button :icon="Document" @click="openQualityReport">查看报告</el-button>
                  <!-- <el-button :loading="repairing" :icon="Tools" @click="repairQuality">自动修复/标记修复</el-button> -->
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
                <el-empty v-if="qualityIssues.length === 0" class="text-empty" description="后端未返回质量问题" />
                <el-table v-else :data="qualityIssues" stripe>
                  <el-table-column prop="index" label="#" width="70" />
                  <el-table-column prop="description" label="问题描述" min-width="180" />
                  <el-table-column prop="suggestion" label="修复建议" min-width="180" />
                </el-table>
              </div>
            </el-tab-pane>

            <!-- 血缘追踪 Tab：展示转换链路和下游影响分析入口。 -->
            <el-tab-pane label="血缘追踪" name="lineage">
              <div class="quality-toolbar">
                <div>
                  <h4>数据血缘追踪</h4>
                  <p>展示来源、转换记录、上下游使用关系和影响分析。</p>
                </div>
                <div class="button-row">
                  <el-button type="primary" :icon="Share" @click="openLineageDrawer">查看血缘链路</el-button>
                  <el-button :loading="impactLoading" :icon="Connection" @click="openImpactDrawer">影响分析</el-button>
                  <!-- <el-button :icon="Clock" @click="showVersionTip">查看历史版本</el-button> -->
                </div>
              </div>

              <div class="lineage-flow">
                <div class="lineage-node">
                  <span>来源</span>
                  <strong>{{ selectedDataset.ownerLabel }}</strong>
                  <small>上传时间：{{ selectedDataset.createdAt }}</small>
                </div>
                <div v-for="step in lineageSteps" :key="step.key" class="lineage-node">
                  <span>转换</span>
                  <strong>{{ step.description }}</strong>
                  <small>{{ step.timeLabel }} · {{ step.operatorLabel }}</small>
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
    </div>

    <!-- 数据加载弹窗：创建数据集和追加文件复用同一弹窗，通过 uploadMode 区分。 -->
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
              <!-- <el-option label="图像数据" value="image" />
              <el-option label="音频数据" value="audio" />
              <el-option label="表格数据" value="tabular" /> -->
            </el-select>
          </el-form-item>
        </div>

        <el-form-item v-if="uploadMode === 'create'" label="描述">
          <el-input v-model="importForm.desc" type="textarea" :rows="3" placeholder="输入数据集描述..." />
        </el-form-item>

        <!-- <el-form-item label="断点续传">
          <div class="resume-option">
            <el-switch v-model="resumeEnabled" />
            <div>
              <strong>{{ resumeEnabled ? '已启用' : '未启用' }}</strong>
              <p>启用后上传过程保留本地文件状态，失败后可重新提交同一批文件继续处理。</p>
            </div>
          </div>
        </el-form-item> -->
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">{{ submitButtonLabel }}</el-button>
      </template>
    </el-dialog>

    <!-- 质量报告抽屉：展示已加载的 qualityReport 明细。 -->
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

    <!-- 血缘链路抽屉：展示来源和 transformations 转换记录。 -->
    <el-drawer v-model="lineageDrawerVisible" title="数据血缘链路" size="560px">
      <el-descriptions v-if="selectedDataset" :column="1" border>
        <el-descriptions-item label="数据来源">{{ selectedDataset.ownerLabel }}</el-descriptions-item>
        <el-descriptions-item label="上传者">{{ selectedDataset.ownerLabel }}</el-descriptions-item>
        <el-descriptions-item label="上传时间">{{ selectedDataset.createdAt }}</el-descriptions-item>
      </el-descriptions>
      <div class="drawer-section">
        <h4>转换记录</h4>
        <el-timeline>
          <el-timeline-item v-for="step in lineageSteps" :key="step.key" :timestamp="step.timeLabel">
            <strong>{{ step.description }}</strong>
            <p class="timeline-meta">{{ step.operatorLabel }} · {{ step.ruleLabel }} · {{ step.versionLabel }}</p>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="lineageSteps.length === 0" description="暂无转换记录" :image-size="70" />
      </div>
    </el-drawer>

    <!-- 影响分析抽屉：展示删除或变更当前数据集可能影响的任务、模型和下游数据集。 -->
    <el-drawer v-model="impactDrawerVisible" title="影响分析" size="560px">
      <el-alert
        :title="impactRiskTitle"
        :type="impactRiskType"
        :closable="false"
        show-icon
      >
        <template #default>
          <span>{{ impactRiskMessage }}</span>
        </template>
      </el-alert>

      <div class="impact-summary">
        <div v-for="item in impactSummary" :key="item.label" class="impact-stat">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>

      <el-descriptions v-if="selectedDataset" :column="1" border>
        <el-descriptions-item label="分析对象">{{ selectedDataset.name }}</el-descriptions-item>
        <el-descriptions-item label="建议动作">{{ impactRecommendation }}</el-descriptions-item>
      </el-descriptions>

      <div class="impact-group">
        <h4>受影响训练任务</h4>
        <el-empty v-if="lineageImpact.affected_tasks.length === 0" description="暂无训练任务依赖" :image-size="70" />
        <div v-else class="impact-list">
          <div v-for="item in lineageImpact.affected_tasks" :key="item" class="impact-item">
            <span>训练任务</span>
            <strong>{{ item }}</strong>
          </div>
        </div>
      </div>
      <div class="impact-group">
        <h4>受影响模型版本</h4>
        <el-empty v-if="lineageImpact.affected_models.length === 0" description="暂无模型版本依赖" :image-size="70" />
        <div v-else class="impact-list">
          <div v-for="item in lineageImpact.affected_models" :key="item" class="impact-item">
            <span>模型版本</span>
            <strong>{{ item }}</strong>
          </div>
        </div>
      </div>
      <div class="impact-group">
        <h4>关联下游数据集</h4>
        <el-empty v-if="lineageImpact.affected_datasets.length === 0" description="暂无同源或同版本数据集" :image-size="70" />
        <div v-else class="impact-list">
          <div v-for="item in lineageImpact.affected_datasets" :key="item" class="impact-item">
            <span>数据集</span>
            <strong>{{ item }}</strong>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import type { UploadFile, UploadUserFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Clock, Connection, Delete, Document, Search, Share, Tools, Upload, UploadFilled, VideoPlay } from '@element-plus/icons-vue'

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
import { formatBeijingDate, formatBeijingDateTime } from '@/utils/time'

type StatusType = 'success' | 'warning' | 'info' | 'danger'

// 页面内部使用的数据集展示结构：由后端 BackendDataset 转换而来，包含中文标签和状态样式。
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

// 本次上传文件的前端展示状态，用于上传弹窗和工作台里的进度展示。
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

// 单文件最大 2GB；前端先做格式和大小校验，减少无效上传请求。
const MAX_UPLOAD_FILE_SIZE = 2 * 1024 ** 3
const supportedFormats = ['TXT', 'CSV', 'JSON', 'JSONL', 'DOC', 'DOCX', 'XLS', 'XLSX']

// 不同数据类型对应的建议文件格式，用于页面展示。
const formatByType: Record<string, string> = {
  text: 'TXT/CSV/JSON/JSONL/DOC/DOCX',
  image: '暂不支持',
  audio: '暂不支持',
  tabular: 'CSV/JSON/XLS/XLSX',
  video: '暂不支持',
}

// 后端 data_type 到中文类型的映射。
const typeMap: Record<string, string> = {
  text: '文本',
  image: '图像',
  audio: '音频',
  video: '视频',
  tabular: '表格',
}

// 后端质量状态到 StatusBadge 展示文案和颜色的映射。
const qualityStatusMap: Record<string, { label: string; type: StatusType }> = {
  passed: { label: '合格', type: 'success' },
  unchecked: { label: '待校验', type: 'info' },
  checking: { label: '校验中', type: 'info' },
  repairing: { label: '修复中', type: 'warning' },
  failed: { label: '不合格', type: 'danger' },
}

// 后端血缘状态到 StatusBadge 展示文案和颜色的映射。
const lineageStatusMap: Record<string, { label: string; type: StatusType }> = {
  tracked: { label: '已追踪', type: 'success' },
  complete: { label: '已追踪', type: 'success' },
  pending: { label: '待生成', type: 'info' },
  none: { label: '待生成', type: 'info' },
  missing: { label: '缺失', type: 'warning' },
}

// 页面 loading 状态按操作拆开，避免一个操作阻塞整页。
const loading = ref(false)
const importing = ref(false)
const checking = ref(false)
const repairing = ref(false)
const impactLoading = ref(false)
const preprocessing = ref(false)
const refreshingJobs = ref(false)
const dialogVisible = ref(false)
const qualityDrawerVisible = ref(false)
const lineageDrawerVisible = ref(false)
const impactDrawerVisible = ref(false)

// 当前右侧工作台 Tab。
const activeDataTab = ref('load')
const selectedDatasetId = ref<number>()
const datasetKeyword = ref('')

// 主要业务数据：数据集列表、统计、上传记录、质量报告、血缘报告、处理任务。
const datasets = ref<DatasetView[]>([])
const stats = ref<DatasetStats>()
const uploadFiles = ref<UploadUserFile[]>([])
const uploadRecords = ref<UploadRecord[]>([])
const qualityReport = ref<QualityReport>()
const lineageReport = ref<Lineage>()
const lineageImpact = ref<LineageImpact>({ dataset_id: 0, affected_models: [], affected_tasks: [], affected_datasets: [] })
const processingJobs = ref<ProcessingJob[]>([])

// 预处理任务轮询定时器，启动预处理后会定时刷新处理任务。
let processingPollTimer: ReturnType<typeof window.setInterval> | undefined
const resumeEnabled = ref(true)
const shardSizeMb = ref(512)

// create 表示创建数据集并上传，append 表示向当前数据集追加文件。
const uploadMode = ref<'create' | 'append'>('create')
const importForm = reactive({
  name: '',
  type: 'text',
  desc: '',
})

// 弹窗标题和提交按钮文案随 uploadMode 自动切换。
const dialogTitle = computed(() => (uploadMode.value === 'create' ? '数据加载' : `追加文件到 ${selectedDataset.value?.name ?? '当前数据集'}`))
const submitButtonLabel = computed(() => (uploadMode.value === 'create' ? '创建并上传' : '追加上传'))

// 字节数格式化，用于数据集大小、上传文件大小、处理输出大小展示。
const formatSize = (size = 0) => {
  if (size >= 1024 ** 4) return `${(size / 1024 ** 4).toFixed(1)} TB`
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1)} GB`
  if (size >= 1024 ** 2) return `${(size / 1024 ** 2).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

const formatDate = (value?: string) => formatBeijingDate(value)
const formatDateTime = (value?: string | null) => formatBeijingDateTime(value, '接口未返回')
const passLabel = (value: boolean) => (value ? '通过' : '未通过')

const getQualityStatus = (status: string) => qualityStatusMap[status] ?? { label: status || '未知', type: 'info' as const }
const getLineageStatus = (status: string) => lineageStatusMap[status] ?? { label: status || '未记录', type: 'info' as const }

// 将后端数据集对象转换为页面展示对象，把状态、大小、时间、用户等字段都整理好。
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

// 当前选中的数据集，右侧工作台所有操作都围绕它展开。
const selectedDataset = computed(() => datasets.value.find((item) => item.id === selectedDatasetId.value))

// 本地搜索过滤数据集列表。
const filteredDatasets = computed(() => {
  const keyword = datasetKeyword.value.trim().toLowerCase()
  if (!keyword) return datasets.value
  return datasets.value.filter((item) =>
    [item.name, item.typeLabel, item.formatLabel, item.ownerLabel, item.qualityLabel, item.lineageLabel]
      .some((value) => value.toLowerCase().includes(keyword)),
  )
})

// 顶部四个统计卡片的数据，部分来自后端 stats，部分由当前数据集列表聚合。
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

// 质量报告相关 computed：把后端质量报告整理成评分、等级、指标卡和问题清单。
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

// 血缘报告相关 computed：把 transformations 和 downstream 整理成页面可展示的链路节点。
const lineageSteps = computed(() =>
  (lineageReport.value?.transformations ?? []).map((step, index) => ({
    key: `${step.rule ?? 'transform'}-${step.timestamp ?? index}`,
    description: step.description || step.rule || '未命名转换',
    ruleLabel: step.rule || '未记录规则',
    timeLabel: formatDateTime(step.timestamp),
    operatorLabel: step.operator || '系统',
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

// 影响分析相关 computed：根据后端返回的依赖列表推导风险提示和建议动作。
const impactSummary = computed(() => [
  { label: '训练任务', value: lineageImpact.value.affected_tasks.length },
  { label: '模型版本', value: lineageImpact.value.affected_models.length },
  { label: '关联数据集', value: lineageImpact.value.affected_datasets.length },
])
const impactRiskType = computed<'success' | 'warning' | 'info' | 'error'>(() => {
  const level = lineageImpact.value.risk?.level
  if (level === 'warning') return 'warning'
  if (level === 'danger' || level === 'error') return 'error'
  return impactSummary.value.some((item) => item.value > 0) ? 'warning' : 'success'
})
const impactRiskTitle = computed(() => {
  if (lineageImpact.value.risk?.message) return '存在变更影响'
  return impactSummary.value.some((item) => item.value > 0) ? '检测到下游依赖' : '未检测到下游影响'
})
const impactRiskMessage = computed(() =>
  lineageImpact.value.risk?.message
  ?? (impactSummary.value.some((item) => item.value > 0)
    ? '变更或删除该数据集前，请确认下游训练任务、模型版本和关联数据集是否需要同步更新。'
    : '当前数据集暂未发现训练任务、模型版本或关联数据集依赖。'),
)
const impactRecommendation = computed(() => {
  const taskCount = lineageImpact.value.affected_tasks.length
  const modelCount = lineageImpact.value.affected_models.length
  if (taskCount > 0 || modelCount > 0) return '先暂停相关训练任务，确认模型版本无需回滚后再变更数据集'
  if (lineageImpact.value.affected_datasets.length > 0) return '变更前同步检查同源或同版本数据集的一致性'
  return '可按常规流程更新，建议保留变更记录'
})

const getFileFormat = (filename: string) => filename.split('.').pop()?.toUpperCase() ?? ''
const isSupportedFile = (filename: string) => supportedFormats.includes(getFileFormat(filename))
const formatPercent = (value?: number) => (value === undefined || Number.isNaN(value) ? '-' : `${value.toFixed(1)}%`)

// 创建数据集时生成一个相对稳定的存储路径，后端会据此组织文件对象。
const buildStoragePath = (name: string) => {
  const safe = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
  return `/datasets/${safe || "dataset"}-${Date.now()}`
}

// 将 Element Plus 上传组件的 file-list 同步成页面自己的 UploadRecord 展示状态。
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

// 文件选择变化时，重新做格式/大小校验并更新上传记录。
const handleUploadChange = (_file: UploadFile, files: UploadUserFile[]) => {
  uploadFiles.value = files
  syncUploadRecords()
}

// 文件移除时同步更新上传记录。
const handleUploadRemove = (_file: UploadFile, files: UploadUserFile[]) => {
  uploadFiles.value = files
  syncUploadRecords()
}

// 重置数据加载弹窗表单，创建和追加文件都会复用。
const resetImportForm = () => {
  importForm.name = ''
  importForm.type = 'text'
  importForm.desc = ''
  uploadFiles.value = []
  uploadRecords.value = []
}

// 打开“创建数据集并上传文件”弹窗。
const openCreateDialog = () => {
  uploadMode.value = 'create'
  resetImportForm()
  dialogVisible.value = true
}

// 打开“向当前数据集追加文件”弹窗，需要先选择一个数据集。
const openAppendDialog = () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  uploadMode.value = 'append'
  resetImportForm()
  dialogVisible.value = true
}

// 加载数据处理首页所需数据：统计、数据集列表、处理任务列表。
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

    // 首次进入页面默认选中第一个数据集；如果当前选中的数据集已不存在，则切换到新的第一个。
    if (!selectedDatasetId.value && datasets.value[0]) {
      await selectDataset(datasets.value[0].id)
    } else if (selectedDatasetId.value && !datasets.value.some((item) => item.id === selectedDatasetId.value)) {
      selectedDatasetId.value = datasets.value[0]?.id
    }
  } finally {
    loading.value = false
  }
}

// 刷新处理任务列表；轮询时 showLoading=false，避免按钮一直闪 loading。
const refreshProcessingJobs = async (showLoading = true) => {
  if (showLoading) refreshingJobs.value = true
  try {
    const jobsPage = await listProcessingJobs({ page: 1, page_size: 20 })
    processingJobs.value = jobsPage.data
  } finally {
    if (showLoading) refreshingJobs.value = false
  }
}

// 判断某个数据集是否还有运行中的处理任务，用于决定是否继续轮询。
const hasRunningProcessingJob = (datasetId: number) =>
  processingJobs.value.some((job) =>
    job.dataset_id === datasetId && ['running', 'processing', 'pending'].includes(String(job.status).toLowerCase()),
  )

// 停止预处理任务轮询。
const stopProcessingJobPolling = () => {
  if (processingPollTimer) {
    window.clearInterval(processingPollTimer)
    processingPollTimer = undefined
  }
}

// 启动预处理任务轮询：每 2 秒刷新任务，任务结束后刷新数据集详情。
const startProcessingJobPolling = (datasetId: number) => {
  stopProcessingJobPolling()
  processingPollTimer = window.setInterval(() => {
    refreshProcessingJobs(false)
      .then(async () => {
        if (!hasRunningProcessingJob(datasetId)) {
          stopProcessingJobPolling()
          preprocessing.value = false
          await loadDatasets()
          await loadDatasetDetails(datasetId)
        }
      })
      .catch(() => {
        stopProcessingJobPolling()
        preprocessing.value = false
      })
  }, 2000)
}

// 加载当前数据集的质量报告和血缘报告。失败时不阻断页面，只展示已有数据。
const loadDatasetDetails = async (datasetId: number) => {
  qualityReport.value = undefined
  lineageReport.value = undefined
  lineageImpact.value = { dataset_id: datasetId, affected_models: [], affected_tasks: [], affected_datasets: [] }

  const [quality, lineage] = await Promise.allSettled([getQualityReport(datasetId), getLineage(datasetId)])
  if (quality.status === 'fulfilled') {
    qualityReport.value = quality.value
    // 质量报告返回后，同步更新左侧列表里的质量状态，避免等待下一次列表刷新。
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

// 切换当前数据集，可选地切换右侧 Tab。
const selectDataset = async (datasetId: number, tab?: string) => {
  selectedDatasetId.value = datasetId
  if (tab) activeDataTab.value = tab
  await loadDatasetDetails(datasetId)
}

// 表格行点击即选中数据集并加载详情。
const handleRowClick = (row: DatasetView) => {
  void selectDataset(row.id)
}

// 触发后端质量校验接口，完成后刷新列表和报告。
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

// 打开质量报告抽屉。
const openQualityReport = () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  qualityDrawerVisible.value = true
}

// 触发后端质量修复/标记修复，随后刷新数据集和详情。
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

// 打开血缘链路抽屉，数据来自 loadDatasetDetails 中的 getLineage。
const openLineageDrawer = () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  lineageDrawerVisible.value = true
}

// 调用影响分析接口并打开抽屉。
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

// 历史版本功能目前等待后端接口。
const showVersionTip = () => {
  ElMessage.info('历史版本需要后端提供版本列表接口后展示')
}

// 启动预处理任务，并开启处理任务轮询直到后端任务结束。
const startPreprocessJob = async () => {
  if (!selectedDataset.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  const datasetId = selectedDataset.value.id
  preprocessing.value = true
  try {
    await startPreprocess(datasetId, shardSizeMb.value)
    await refreshProcessingJobs(false)
    startProcessingJobPolling(datasetId)
    await loadDatasets()
    ElMessage.success('预处理任务已启动')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '预处理失败')
    preprocessing.value = false
  }
}

// 删除数据集，并在删除后选择新的数据集或清空详情。
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

// 提交数据加载弹窗：根据 uploadMode 决定是先创建数据集再上传，还是直接追加到当前数据集。
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

  // 前端校验发现不支持格式或文件过大时，阻止上传。
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
    // Element Plus 的 UploadUserFile 需要从 raw 中取浏览器原始 File 对象。
    const rawFiles: File[] = []
    uploadFiles.value.forEach((file) => {
      if (!file.raw) throw new Error('未能读取到浏览器文件对象，请重新选择文件后再上传')
      rawFiles.push(file.raw as File)
    })

    if (uploadMode.value === 'create') {
      // 创建模式下先创建空数据集，拿到 datasetId 后再上传文件。
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
      // 新建数据集立即插入左侧列表，提升反馈速度；后面仍会重新拉取列表保证一致。
      datasets.value = [mapDataset(createdDataset), ...datasets.value.filter((item) => item.id !== createdDataset?.id)]
      selectedDatasetId.value = ensuredTargetDatasetId
      qualityReport.value = undefined
      lineageReport.value = undefined
    }
    activeDataTab.value = 'load'
    dialogVisible.value = false

    if (rawFiles.length > 1) {
      // 多文件走批量上传接口，通过统一进度回调更新每条记录。
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
      // 单文件走单文件上传接口，进度只更新当前文件记录。
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
    // 创建模式下如果文件一个都没上传成功，尝试清理刚创建的空数据集。
    if (uploadMode.value === 'create' && createdDatasetId && uploadedCount === 0) {
      try {
        await deleteDatasetApi(createdDatasetId)
        datasets.value = datasets.value.filter((item) => item.id !== createdDatasetId)
        if (selectedDatasetId.value === createdDatasetId) selectedDatasetId.value = datasets.value[0]?.id
      } catch {
        ElMessage.warning('上传未成功，空数据集清理失败，请稍后手动删除')
      }
    }
    // 将仍处于上传中的记录标记为中断，给用户明确反馈。
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
  // 进入页面时加载数据集列表和默认选中项。
  loadDatasets().catch((error) => {
    ElMessage.error(error instanceof Error ? error.message : '数据集加载失败')
  })
})

onBeforeUnmount(() => {
  // 离开页面时停止预处理轮询，避免后台继续请求接口。
  stopProcessingJobPolling()
})
</script>

<style scoped>
.stats {
  margin-bottom: 16px;
}

.full {
  width: 100%;
}

.data-workbench {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
}

.dataset-list-panel,
.dataset-workspace {
  min-width: 0;
}

.dataset-list-panel {
  display: flex;
  height: clamp(560px, calc(100vh - 250px), 760px);
  flex-direction: column;
}

.dataset-list-panel .card-header {
  gap: 12px;
}

.dataset-list-body {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 12px;
}

.dataset-search {
  flex: 0 0 auto;
}

.dataset-list-table {
  min-height: 0;
  flex: 1;
}

.dataset-cell {
  min-width: 0;
}

.dataset-cell strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dataset-workspace .card-header {
  align-items: flex-start;
}

.workspace-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.section-note {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.dataset-context,
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
  grid-template-columns: repeat(6, minmax(0, 1fr));
  margin-bottom: 14px;
  padding: 12px;
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

.feature-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
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
  min-height: 220px;
  flex-direction: column;
  gap: 14px;
}

.load-actions-panel {
  min-height: 0;
}

.panel-copy {
  padding-bottom: 12px;
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

.button-row,
.upload-records,
.dialog-file-list,
.impact-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.upload-records {
  flex-direction: column;
  margin-top: 14px;
}

.load-action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.load-action-grid :deep(.el-button) {
  width: 100%;
  height: 36px;
  margin-left: 0;
  justify-content: center;
}

.shard-control {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: #fff;
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.shard-control :deep(.el-input-number) {
  width: 108px;
}

.shard-control :deep(.el-input__wrapper) {
  box-shadow: none;
}

.upload-empty,
.text-empty {
  --el-empty-padding: 18px 0;
}

.upload-empty :deep(.el-empty__image),
.text-empty :deep(.el-empty__image) {
  display: none;
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
  margin-bottom: 14px;
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
  gap: 12px;
  margin-bottom: 14px;
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

.job-list {
  margin-top: 14px;
}

.job-list h4 {
  margin: 0 0 10px;
  font-size: 16px;
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

.impact-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0;
}

.impact-stat,
.impact-item {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #fff;
}

.impact-stat {
  display: flex;
  min-height: 72px;
  flex-direction: column;
  justify-content: center;
  padding: 12px;
}

.impact-stat span,
.impact-item span {
  color: var(--text-secondary);
  font-size: 12px;
}

.impact-stat strong {
  margin-top: 4px;
  font-size: 22px;
}

.impact-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.impact-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
}

.impact-item strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .data-workbench {
    grid-template-columns: 1fr;
  }

  .dataset-list-panel {
    height: auto;
  }

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
  .dataset-list-panel .card-header,
  .quality-toolbar {
    flex-direction: column;
  }

  .workspace-actions,
  .button-row {
    width: 100%;
  }

  .workspace-actions,
  .button-row {
    justify-content: flex-start;
  }

  .dataset-context,
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .load-action-grid {
    grid-template-columns: 1fr;
  }

  .dataset-context,
  .inline-grid,
  .form-grid,
  .upload-record,
  .dialog-file {
    grid-template-columns: 1fr;
  }
}
</style>
