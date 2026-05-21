<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">我的操作日志</h1>
      <p class="page-description">仅展示当前 mock 用户自己的操作记录</p>
    </div>

    <div class="card">
      <div class="card-body">
        <el-table :data="myLogs" stripe>
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column prop="action" label="操作" width="110">
            <template #default="{ row }">
              <el-tag type="success">{{ row.action }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="resource" label="资源" width="120" />
          <el-table-column prop="detail" label="内容" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { listMyLogs, type SystemLog } from '@/api/system'

const myLogs = ref<SystemLog[]>([])

onMounted(async () => {
  try {
    const page = await listMyLogs({ page: 1, page_size: 100 })
    myLogs.value = page.data
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '日志加载失败')
  }
})
</script>
