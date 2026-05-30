<template>
  <header class="header">
    <!-- 顶部面包屑：系统名 + 当前路由标题。 -->
    <div class="breadcrumb">
      <span class="muted">离线大数据训练与应用系统</span>
      <el-icon><ArrowRight /></el-icon>
      <strong>{{ pageTitle }}</strong>
    </div>

    <!-- 右侧问号按钮，用于打开系统使用提示弹窗。 -->
    <el-button :icon="QuestionFilled" circle @click="helpVisible = true" />

    <!-- 使用提示弹窗，给用户说明主要模块的基本操作路径。 -->
    <el-dialog v-model="helpVisible" title="使用提示" width="520px">
      <div class="help-content">
        <p>系统按角色控制菜单权限，若页面或按钮不可见，请联系管理员检查角色菜单配置。</p>
        <ul>
          <li>数据处理：先创建数据集，再上传文件，可在质量检查和血缘分析中查看处理结果。</li>
          <li>模型训练：提交任务后可在任务列表查看状态、日志、指标和 checkpoint。</li>
          <li>模型管理：训练完成后需提升为模型，才能进行版本管理、推理测试和安全扫描。</li>
          <li>文档生成：选择可用模型后进行对话生成，生成结果可保存为草稿并下载。</li>
          <li>系统日志：系统管理中可按级别、模块和关键词筛选日志，也可查看个人操作记录。</li>
        </ul>
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

// 当前路由对象提供 meta.title，顶部标题会随页面切换自动更新。
const route = useRoute()

// 控制“使用提示”弹窗显隐。
const helpVisible = ref(false)

// 页面标题来自 router/index.ts 中每个路由的 meta.title，没有配置时兜底为“仪表盘”。
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

.help-content p {
  margin: 0 0 12px;
}

.help-content ul {
  margin: 0;
  padding-left: 18px;
}

.help-content li + li {
  margin-top: 8px;
}
</style>
