<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">训练配置</h1>
      <p class="page-description">配置模型训练参数、优化器和学习率调度策略</p>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header"><h3 class="card-title">基础配置</h3></div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="任务名称"><el-input v-model="form.taskName" placeholder="输入训练任务名称" /></el-form-item>
            <el-form-item label="选择模型">
              <el-select v-model="form.model" class="full">
                <el-option v-for="item in modelOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="选择数据集">
              <el-select v-model="form.dataset" class="full">
                <el-option v-for="item in datasetOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="GPU配置">
              <el-select v-model="form.gpu" class="full">
                <el-option v-for="item in gpuOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="card-title">训练超参数</h3></div>
        <div class="card-body">
          <el-form label-position="top" class="param-grid">
            <el-form-item label="学习率 (Learning Rate)"><el-input v-model="form.lr" /></el-form-item>
            <el-form-item label="批次大小 (Batch Size)"><el-input-number v-model="form.batchSize" :min="1" /></el-form-item>
            <el-form-item label="训练轮次 (Epochs)"><el-input-number v-model="form.epochs" :min="1" /></el-form-item>
            <el-form-item label="权重衰减 (Weight Decay)"><el-input v-model="form.weightDecay" /></el-form-item>
            <el-form-item label="预热步数 (Warmup Steps)"><el-input-number v-model="form.warmup" :min="0" /></el-form-item>
            <el-form-item label="梯度裁剪 (Max Grad Norm)"><el-input v-model="form.maxGradNorm" /></el-form-item>
          </el-form>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">优化器配置</h3></div>
      <div class="card-body">
        <el-form label-position="top" class="grid-3">
          <el-form-item label="优化器类型">
            <el-select v-model="form.optimizer" class="full">
              <el-option label="AdamW" value="AdamW" />
              <el-option label="Adam" value="Adam" />
              <el-option label="SGD" value="SGD" />
              <el-option label="Adafactor" value="Adafactor" />
            </el-select>
          </el-form-item>
          <el-form-item label="Beta1"><el-input v-model="form.beta1" /></el-form-item>
          <el-form-item label="Beta2"><el-input v-model="form.beta2" /></el-form-item>
        </el-form>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">学习率调度</h3></div>
      <div class="card-body">
        <el-form label-position="top" class="grid-2">
          <el-form-item label="调度器类型">
            <el-select v-model="form.scheduler" class="full">
              <el-option label="Linear Warmup + Decay" value="Linear Warmup + Decay" />
              <el-option label="Cosine Annealing" value="Cosine Annealing" />
              <el-option label="Constant with Warmup" value="Constant with Warmup" />
              <el-option label="Polynomial Decay" value="Polynomial Decay" />
            </el-select>
          </el-form-item>
          <el-form-item label="最小学习率"><el-input v-model="form.minLr" /></el-form-item>
        </el-form>
        <ChartCard title="学习率曲线" :option="lrOption" height="280px" />
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">高级设置</h3></div>
      <div class="card-body">
        <el-form label-position="top" class="grid-2">
          <el-form-item label="混合精度训练">
            <el-select v-model="form.precision" class="full">
              <el-option label="FP16 (推荐)" value="FP16" />
              <el-option label="BF16" value="BF16" />
              <el-option label="FP32" value="FP32" />
            </el-select>
          </el-form-item>
          <el-form-item label="梯度累积步数"><el-input-number v-model="form.accumulate" :min="1" /></el-form-item>
          <el-form-item label="保存间隔 (每N步)"><el-input-number v-model="form.saveStep" :min="1" /></el-form-item>
          <el-form-item label="评估间隔 (每N步)"><el-input-number v-model="form.evalStep" :min="1" /></el-form-item>
        </el-form>
        <div class="action-row">
          <el-button type="primary" :icon="VideoPlay" @click="startTraining">开始训练</el-button>
          <el-button :icon="DocumentChecked" @click="tip('训练配置已保存')">保存配置</el-button>
          <el-button :icon="Upload" @click="tip('已读取本地配置模板')">导入配置</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, Upload, VideoPlay } from '@element-plus/icons-vue'

import ChartCard from '@/components/ChartCard.vue'

const modelOptions = ['BERT-base-chinese', 'ResNet-50', 'GPT-2-medium', 'Whisper-small', '自定义模型']
const datasetOptions = ['电商评论文本数据 (1.25M样本)', '产品图像分类集 (125K样本)', '语音指令识别数据 (32K样本)']
const gpuOptions = ['1x NVIDIA A100 80GB', '2x NVIDIA A100 80GB', '4x NVIDIA A100 80GB', '8x NVIDIA A100 80GB']

const form = reactive({
  taskName: 'BERT情感分析微调',
  model: modelOptions[0],
  dataset: datasetOptions[0],
  gpu: gpuOptions[2],
  lr: '2e-5',
  batchSize: 32,
  epochs: 10,
  weightDecay: '0.01',
  warmup: 1000,
  maxGradNorm: '1.0',
  optimizer: 'AdamW',
  beta1: '0.9',
  beta2: '0.999',
  scheduler: 'Linear Warmup + Decay',
  minLr: '0',
  precision: 'FP16',
  accumulate: 1,
  saveStep: 500,
  evalStep: 100,
})

const lrOption = computed<EChartsOption>(() => {
  const steps = Array.from({ length: 20 }, (_, index) => index * 500)
  const peak = Number(form.lr.replace('e-5', '')) || 2
  const data = steps.map((_, index) => (index < 4 ? (peak * (index + 1)) / 4 : Math.max(0.2, peak * (1 - (index - 4) / 18))))
  return {
    tooltip: { trigger: 'axis' },
    grid: { top: 24, right: 20, bottom: 32, left: 44 },
    xAxis: { type: 'category', data: steps },
    yAxis: { type: 'value', name: '1e-5' },
    series: [{ type: 'line', data, smooth: true, color: '#2563eb', areaStyle: { opacity: 0.12 } }],
  }
})

const tip = (message: string) => ElMessage.success(message)
const startTraining = () => ElMessage.success(`训练任务「${form.taskName || '未命名任务'}」已加入队列`)
</script>

<style scoped>
.full {
  width: 100%;
}

.param-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

.action-row {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}
</style>
