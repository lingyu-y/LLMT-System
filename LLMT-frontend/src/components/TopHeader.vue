<template>
  <header class="header">
    <div class="breadcrumb">
      <span class="muted">离线大数据训练与应用系统</span>
      <el-icon><ArrowRight /></el-icon>
      <strong>{{ pageTitle }}</strong>
    </div>

    <el-button :icon="QuestionFilled" circle @click="helpVisible = true" />

    <el-dialog v-model="helpVisible" title="使用提示" width="520px">
      <div class="help-content">
        <p>这里展示系统使用提示占位内容。</p>
        <p>后续可以补充登录账号、菜单权限、训练任务和日志查看等说明。</p>
      </div>
      <template #footer>
        <el-button type="primary" @click="helpVisible = false">知道了</el-button>
      </template>
    </el-dialog>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight, QuestionFilled } from '@element-plus/icons-vue'

const route = useRoute()
const helpVisible = ref(false)
const pageTitle = computed(() => String(route.meta.title ?? '仪表盘'))
</script>

<style scoped>
.header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 73px;
  padding: 16px 32px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 12px;
}

.breadcrumb {
  color: var(--text-primary);
  font-size: 14px;
}

.help-content {
  color: var(--text-secondary);
  line-height: 1.8;
}
</style>
