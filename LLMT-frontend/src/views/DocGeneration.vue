<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">软件文档自动生成</h1>
      <p class="page-description">基于大语言模型自动生成需求分析、系统设计等软件开发文档</p>
    </div>

    <div class="chat-container">
      <div ref="messageBox" class="chat-messages">
        <div v-for="message in messages" :key="message.id" class="chat-message" :class="message.role">
          <div class="chat-avatar">{{ message.role === 'ai' ? 'AI' : '我' }}</div>
          <div class="chat-bubble">
            <p>{{ message.content }}</p>
            <div v-if="message.quick" class="quick-actions">
              <el-button v-for="item in quickActions" :key="item.type" @click="selectQuick(item.label)">{{ item.label }}</el-button>
            </div>
            <div v-if="message.preview" class="doc-preview">
              <h3>{{ message.preview.title }}</h3>
              <div v-for="section in message.preview.sections" :key="section.title" class="document-section">
                <strong>{{ section.title }}</strong>
                <p>{{ section.content }}</p>
              </div>
              <div class="preview-actions">
                <el-button type="primary" :icon="Download" @click="ElMessage.success('已生成导出任务')">导出文档</el-button>
                <el-button :icon="Edit">编辑文档</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input-container">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="描述您的项目需求，例如：生成离线大数据训练系统的需求分析文档..."
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :icon="Promotion" circle @click="send" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Edit, Promotion } from '@element-plus/icons-vue'

interface Message {
  id: number
  role: 'ai' | 'user'
  content: string
  quick?: boolean
  preview?: { title: string; sections: { title: string; content: string }[] }
}

const quickActions = [
  { type: 'requirement', label: '需求分析文档' },
  { type: 'design', label: '系统设计文档' },
  { type: 'api', label: 'API接口文档' },
  { type: 'test', label: '测试用例文档' },
]

const input = ref('')
const messageBox = ref<HTMLDivElement>()
const messages = ref<Message[]>([
  {
    id: 1,
    role: 'ai',
    content: '您好！我是软件文档生成助手，可以帮您自动生成以下类型的文档：',
    quick: true,
  },
])

const scrollBottom = () => nextTick(() => messageBox.value?.scrollTo({ top: messageBox.value.scrollHeight, behavior: 'smooth' }))

const buildPreview = (prompt: string) => ({
  title: prompt.includes('API') ? '离线大数据训练与应用系统 API 接口文档' : '离线大数据训练与应用系统文档预览',
  sections: [
    { title: '1. 项目概述', content: '系统面向离线大数据训练场景，覆盖数据导入、预处理、训练配置、监控、模型版本管理与文档生成。' },
    { title: '2. 核心功能', content: '包括多模态数据处理、GPU训练任务编排、损失曲线监控、模型版本回滚、系统用户权限与日志审计。' },
    { title: '3. 非功能需求', content: '要求训练过程可观测、配置可复用、权限边界清晰，并为后续 FastAPI 后端接口预留扩展能力。' },
  ],
})

const selectQuick = (label: string) => {
  input.value = `请生成一份${label}，项目是离线大数据训练与应用系统`
  send()
}

const send = () => {
  const content = input.value.trim()
  if (!content) return
  messages.value.push({ id: Date.now(), role: 'user', content })
  input.value = ''
  window.setTimeout(() => {
    messages.value.push({
      id: Date.now() + 1,
      role: 'ai',
      content: '已根据您的描述生成文档概要，以下是可导出的预览版本：',
      preview: buildPreview(content),
    })
    scrollBottom()
  }, 450)
  scrollBottom()
}
</script>

<style scoped>
.chat-container {
  display: flex;
  height: calc(100vh - 176px);
  min-height: 560px;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: #fff;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.chat-message {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.chat-avatar {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--ai-accent), #8b5cf6);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.chat-message.user .chat-avatar {
  background: linear-gradient(135deg, #64748b, #475569);
}

.chat-bubble {
  max-width: 72%;
  padding: 16px 20px;
  border: 1px solid var(--border-color);
  border-radius: 16px 16px 16px 4px;
  background: #f8fafc;
  line-height: 1.7;
}

.chat-message.user .chat-bubble {
  border-color: var(--primary-color);
  border-radius: 16px 16px 4px;
  background: var(--primary-color);
  color: #fff;
}

.chat-bubble p {
  margin: 0;
}

.quick-actions,
.preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.doc-preview {
  margin-top: 14px;
}

.doc-preview h3 {
  margin: 0 0 12px;
}

.document-section {
  margin-top: 10px;
  padding: 12px;
  border-radius: 8px;
  background: #fff;
}

.document-section p {
  margin-top: 6px;
  color: var(--text-secondary);
}

.chat-input-container {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid var(--border-color);
  background: #fff;
}
</style>
