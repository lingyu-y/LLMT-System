<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">多模态数据处理</h1>
      <p class="page-description">支持文本、图像、音频等异构数据的统一处理与预处理</p>
    </div>

    <div class="grid-4 stats">
      <MetricCard v-for="item in datasetStats" :key="item.title" :title="item.title" :value="item.value" />
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">数据集列表</h3>
        <el-button type="primary" :icon="Upload" @click="dialogVisible = true">导入数据</el-button>
      </div>
      <div class="card-body">
        <el-table :data="datasets" stripe>
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
            <template #default>
              <el-button size="small">预览</el-button>
              <el-button size="small">配置</el-button>
              <el-button size="small">处理</el-button>
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
              <el-select v-model="preprocess.dataset" class="full">
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
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, UploadFilled, VideoPlay } from '@element-plus/icons-vue'

import MetricCard from '@/components/MetricCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { datasets, datasetStats, processingJobs } from '@/mock/datasets'

const dialogVisible = ref(false)
const preprocess = reactive({ dataset: datasets[0]?.name ?? '', batchSize: 32, workers: 4, shuffle: true })
const importForm = reactive({ name: '', type: 'text', desc: '' })

const startProcess = () => ElMessage.success(`已提交 ${preprocess.dataset} 的预处理任务`)
const submitImport = () => {
  if (!importForm.name.trim()) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  dialogVisible.value = false
  ElMessage.success(`正在导入数据集: ${importForm.name}`)
}
</script>

<style scoped>
.stats {
  margin-bottom: 22px;
}

.full {
  width: 100%;
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
</style>
