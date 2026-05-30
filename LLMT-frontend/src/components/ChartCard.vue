<template>
  <!-- 通用图表卡片：负责统一标题栏、操作插槽和 ECharts 挂载容器。 -->
  <div class="card chart-card">
    <div class="card-header">
      <h3 class="card-title">
        <el-icon v-if="icon"><component :is="icon" /></el-icon>
        {{ title }}
      </h3>
      <!-- 右上角扩展区域，父组件可放筛选器、时间范围、刷新按钮等。 -->
      <slot name="extra" />
    </div>
    <div class="card-body">
      <!-- ECharts 会挂载到这个 div；高度通过 props.height 控制。 -->
      <div ref="chartRef" class="chart" :style="{ height }"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// 父组件只需要传入标题和 ECharts option；组件内部负责创建和更新图表实例。
const props = withDefaults(
  defineProps<{
    title: string
    option: echarts.EChartsOption
    height?: string
    icon?: unknown
  }>(),
  { height: '300px' },
)

// 图表容器 DOM 引用。
const chartRef = ref<HTMLDivElement>()

// ECharts 实例缓存，避免每次数据变化都重复 init。
let chart: echarts.ECharts | undefined

// 初始化或更新图表。第二个参数 true 表示不合并旧配置，直接使用新 option。
const render = () => {
  if (!chartRef.value) return
  chart ||= echarts.init(chartRef.value)
  chart.setOption(props.option, true)
}

// 浏览器窗口变化时，通知 ECharts 重新计算尺寸。
const resize = () => chart?.resize()

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})

// option 可能是嵌套对象，deep watch 可以响应 series、xAxis 等内部数据变化。
watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  // 组件销毁时释放图表实例，避免内存泄漏。
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
