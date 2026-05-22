<template>
  <div>
    <div class="page-header doc-header">
      <div>
        <h1 class="page-title">对话式文档生成</h1>
        <p class="page-description">选择文档模型后，通过多轮对话生成提纲、段落草稿和修订建议</p>
      </div>
      <el-button :icon="Management" @click="modelDrawerVisible = true">
        当前模型：{{ selectedModel.name }}
      </el-button>
    </div>

    <div class="chat-container">
      <div ref="messageBox" class="chat-messages">
        <div v-for="message in messages" :key="message.id" class="chat-message" :class="message.role">
          <div class="chat-avatar">{{ message.role === 'ai' ? 'AI' : '我' }}</div>
          <div class="chat-bubble">
            <p>{{ message.content }}</p>
            <div v-if="message.quick" class="quick-actions">
              <el-button v-for="item in quickActions" :key="item.type" @click="selectQuick(item.prompt)">{{ item.label }}</el-button>
            </div>
            <div v-if="message.preview" class="doc-preview">
              <div class="preview-head">
                <h3>{{ message.preview.title }}</h3>
                <span>{{ message.preview.model }}</span>
              </div>
              <div v-for="section in message.preview.sections" :key="section.title" class="document-section">
                <strong>{{ section.title }}</strong>
                <p>{{ section.content }}</p>
              </div>
              <div class="preview-actions">
                <el-button type="primary" :icon="Download" @click="saveDraft(message.preview)">保存草稿</el-button>
                <el-button :icon="Edit" @click="ElMessage.info('可继续通过对话修改草稿')">继续修改</el-button>
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
          placeholder="输入文档生成需求，例如：帮我补写模型训练模块的需求描述..."
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :icon="Promotion" circle @click="send" />
      </div>
    </div>

    <el-drawer v-model="modelDrawerVisible" title="选择文档生成模型" size="520px">
      <div class="model-drawer">
        <button
          v-for="model in docModels"
          :key="model.id"
          class="doc-model-card"
          :class="{ active: selectedModel.id === model.id }"
          @click="selectModel(model)"
        >
          <span class="model-name">{{ model.name }}</span>
          <span class="model-meta">{{ model.provider }} · {{ model.context }}</span>
          <p>{{ model.desc }}</p>
          <span class="model-tags">
            <span v-for="tag in model.tags" :key="tag">{{ tag }}</span>
          </span>
        </button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Edit, Management, Promotion } from '@element-plus/icons-vue'
import { chatGenerate, createDraft, listDocumentModels } from '@/api/documents'

interface Message {
  id: number
  role: 'ai' | 'user'
  content: string
  quick?: boolean
  preview?: { title: string; model: string; sections: { title: string; content: string }[] }
}

interface DocModel {
  id: string
  name: string
  provider: string
  context: string
  desc: string
  tags: string[]
}

const quickActions = [
  { type: 'outline', label: '生成文档提纲', prompt: '请帮我生成离线大数据训练与应用系统的需求文档提纲' },
  { type: 'section', label: '补写模块段落', prompt: '请帮我补写模型训练模块的功能需求段落' },
  { type: 'polish', label: '润色已有内容', prompt: '请帮我把下面这段需求描述改得更规范：' },
  { type: 'test', label: '生成测试要点', prompt: '请帮我生成模型训练模块的验收测试要点' },
]

const defaultDocModels: DocModel[] = [
  {
    id: 'gpt-doc',
    name: 'GPT-Generator v1.5',
    provider: '文本生成模型',
    context: '32K 上下文',
    desc: '适合生成需求描述、概要设计段落和测试说明，输出更偏通用文档草稿。',
    tags: ['需求段落', '测试要点', '润色'],
  },
  {
    id: 'layout-doc',
    name: 'LayoutLMv3-Doc v2.0',
    provider: '文档理解模型',
    context: '16K 上下文',
    desc: '适合基于已有文档内容进行结构整理、章节补全和格式化改写。',
    tags: ['结构整理', '章节补全', '格式规范'],
  },
  {
    id: 'llmt-assistant',
    name: 'LLMT-Assistant',
    provider: '项目定制模型',
    context: '8K 上下文',
    desc: '适合围绕本系统需求进行对话式补写，强调功能范围收敛和术语一致。',
    tags: ['项目需求', '范围收敛', '术语一致'],
  },
]

const input = ref('')
const messageBox = ref<HTMLDivElement>()
const modelDrawerVisible = ref(false)
const docModels = ref<DocModel[]>(defaultDocModels)
const selectedModel = ref<DocModel>(defaultDocModels[0]!)
const messages = ref<Message[]>([
  {
    id: 1,
    role: 'ai',
    content: '您好！我是对话式文档助手。请先确认右上角选择的模型，然后通过对话生成提纲、段落草稿、润色建议或测试要点。',
    quick: true,
  },
])

const scrollBottom = () => nextTick(() => messageBox.value?.scrollTo({ top: messageBox.value.scrollHeight, behavior: 'smooth' }))

const buildPreview = (prompt: string, content?: string) => ({
  title: prompt.includes('测试') ? '模型训练模块测试要点草稿' : '离线大数据训练与应用系统文档片段草稿',
  model: selectedModel.value.name,
  sections: [
    { title: '1. 建议写入位置', content: '可作为需求规格说明书中对应模块的小节草稿，后续需要人工确认后再纳入正式文档。' },
    { title: '2. 草稿内容', content: content ?? '系统支持通过对话方式生成文档提纲、模块描述、验收测试点和修订建议，生成内容以片段形式保存。' },
    { title: '3. 后续确认项', content: '需确认术语是否与需求文档一致、功能范围是否过度承诺、是否需要补充接口字段或截图。' },
  ],
})

const saveDraft = async (preview: Message['preview']) => {
  if (!preview) return
  await createDraft({
    model_code: selectedModel.value.id,
    doc_type: '对话草稿',
    title: preview.title,
    content: preview.sections.map((section) => `## ${section.title}\n\n${section.content}`).join('\n\n'),
  })
  ElMessage.success('已保存到草稿箱')
}

const selectQuick = (prompt: string) => {
  input.value = prompt
  send()
}

const selectModel = (model: DocModel) => {
  selectedModel.value = model
  modelDrawerVisible.value = false
  ElMessage.success(`已切换到 ${model.name}`)
}

const send = () => {
  const content = input.value.trim()
  if (!content) return
  messages.value.push({ id: Date.now(), role: 'user', content })
  input.value = ''
  chatGenerate({ message: content, model_code: selectedModel.value.id })
    .then((result) => {
    messages.value.push({
      id: Date.now() + 1,
      role: 'ai',
      content: result.content,
      preview: buildPreview(content, result.content),
    })
    scrollBottom()
    })
    .catch((error) => {
      ElMessage.error(error instanceof Error ? error.message : '文档生成失败')
    })
  scrollBottom()
}

onMounted(async () => {
  try {
    const models = await listDocumentModels()
    docModels.value = models.map((model) => ({
      id: model.value,
      name: model.label,
      provider: '后端文档模型',
      context: '项目配置',
      desc: `支持 ${model.types.join('、')} 类型文档生成`,
      tags: model.types,
    }))
    selectedModel.value = docModels.value[0] ?? defaultDocModels[0]!
  } catch {
    docModels.value = defaultDocModels
  }
})
</script>

<style scoped>
.doc-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

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
  margin: 0;
}

.preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.preview-head span {
  color: var(--text-muted);
  font-size: 12px;
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

.model-drawer {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.doc-model-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #fff;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.doc-model-card.active {
  border-color: var(--primary-color);
  background: rgb(37 99 235 / 5%);
}

.model-name {
  font-size: 16px;
  font-weight: 700;
}

.model-meta,
.doc-model-card p {
  color: var(--text-secondary);
  font-size: 13px;
}

.doc-model-card p {
  margin: 0;
  line-height: 1.6;
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.model-tags span {
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--bg-color);
  color: var(--text-muted);
  font-size: 12px;
}

@media (max-width: 700px) {
  .doc-header {
    flex-direction: column;
  }

  .chat-bubble {
    max-width: 86%;
  }
}
</style>
