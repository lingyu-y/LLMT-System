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
          <button v-for="model in filteredModels" :key="model.id" class="model-card" @click="selectedModel = model">
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
          <div class="card-header"><h3 class="card-title">模型概述</h3></div>
          <div class="card-body overview-grid">
            <div class="overview-card"><span>当前版本</span><strong>{{ selectedModel.version }}</strong></div>
            <div class="overview-card"><span>版本数量</span><strong>5</strong></div>
            <div class="overview-card"><span>最佳准确率</span><strong>{{ selectedModel.accuracy }}</strong></div>
            <div class="overview-card"><span>参数量</span><strong>{{ selectedModel.params }}</strong></div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><h3 class="card-title">当前训练参数</h3></div>
          <div class="card-body params-grid">
            <div v-for="[label, value] in modelParams" :key="label" class="param-item">
              <span>{{ label }}</span>
              <strong>{{ value }}</strong>
            </div>
          </div>
        </div>
      </div>

      <ChartCard title="性能趋势" :option="performanceOption" height="280px" />

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
              <div v-if="!item.current" class="timeline-actions">
                <el-button size="small" type="primary" :icon="RefreshLeft" @click="rollback(item.version)">回滚到此版本</el-button>
                <el-button size="small" :icon="Download" @click="ElMessage.success(`开始下载 ${item.version}`)">下载</el-button>
                <el-button size="small" :icon="DataLine" @click="ElMessage.info(`正在对比 ${item.version} 与当前版本`)">对比</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, DataLine, Download, Management, Plus, RefreshLeft } from '@element-plus/icons-vue'

import ChartCard from '@/components/ChartCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { modelParams, models, performanceTrend, versionHistory } from '@/mock/models'

type ModelItem = (typeof models)[number]

const keyword = ref('')
const typeFilter = ref('全部类型')
const selectedModel = ref<ModelItem | null>(null)

const filteredModels = computed(() =>
  models.filter((item) => {
    const matchText = `${item.name}${item.type}`.toLowerCase().includes(keyword.value.toLowerCase())
    const matchType = typeFilter.value === '全部类型' || item.type.includes(typeFilter.value)
    return matchText && matchType
  }),
)

const performanceOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { top: 24, right: 20, bottom: 32, left: 44 },
  xAxis: { type: 'category', data: versionHistory.map((item) => item.version).reverse() },
  yAxis: { type: 'value', min: 85, max: 100, name: '准确率%' },
  series: [{ type: 'line', smooth: true, data: performanceTrend, color: '#2563eb', areaStyle: { opacity: 0.12 } }],
}))

const rollback = async (version: string) => {
  await ElMessageBox.confirm(`确认回滚到 ${version}？该操作会生成回滚记录。`, '版本回滚确认', { type: 'warning' })
  ElMessage.success(`已模拟回滚到 ${version}`)
}
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
.params-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.overview-card,
.param-item {
  padding: 14px;
  border-radius: 8px;
  background: var(--bg-color);
}

.overview-card span,
.param-item span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.overview-card strong,
.param-item strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
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
</style>
