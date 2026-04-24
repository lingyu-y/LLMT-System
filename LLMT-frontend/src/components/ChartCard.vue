<template>
  <div class="card chart-card">
    <div class="card-header">
      <h3 class="card-title">
        <el-icon v-if="icon"><component :is="icon" /></el-icon>
        {{ title }}
      </h3>
      <slot name="extra" />
    </div>
    <div class="card-body">
      <div ref="chartRef" class="chart" :style="{ height }"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    option: echarts.EChartsOption
    height?: string
    icon?: unknown
  }>(),
  { height: '300px' },
)

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined

const render = () => {
  if (!chartRef.value) return
  chart ||= echarts.init(chartRef.value)
  chart.setOption(props.option, true)
}

const resize = () => chart?.resize()

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
})
</script>

<style scoped>
.chart-card {
  min-width: 0;
}

.chart {
  width: 100%;
}
</style>
