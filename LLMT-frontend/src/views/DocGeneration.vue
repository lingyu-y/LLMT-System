<template>
  <div>
    <div class="page-header doc-header">
      <div>
        <h1 class="page-title">对话式文档生成</h1>
        <p class="page-description">选择文档模型后，通过多轮对话生成提纲、段落草稿和修订建议</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Management" @click="modelDrawerVisible = true">
          当前模型：{{ selectedModel.name }}
        </el-button>
        <el-badge :value="drafts.length" :hidden="drafts.length === 0">
          <el-button @click="draftDrawerVisible = true">草稿箱</el-button>
        </el-badge>
      </div>
    </div>

    <div class="doc-layout">
      <!-- 历史对话侧边栏 -->
      <div class="conversation-sidebar">
        <el-button type="primary" style="width:100%;margin-bottom:12px" @click="newConversation">
          新建对话
        </el-button>
        <div class="conversation-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === activeConvId }"
            @click="switchConversation(conv.id)"
          >
            <span class="conv-title">{{ conv.title }}</span>
            <span class="conv-time">{{ formatTime(conv.updatedAt) }}</span>
            <el-button class="conv-delete" size="small" text type="danger" @click.stop="deleteConversation(conv.id)">
              删除
            </el-button>
          </div>
          <div v-if="conversations.length === 0" class="conv-empty">
            暂无历史对话
          </div>
        </div>
      </div>

      <!-- 对话主区域 -->
      <div class="chat-container">
        <div ref="messageBox" class="chat-messages">
          <div v-if="messages.length === 0" class="chat-empty">
            <p>开始新的对话，输入文档需求后发送</p>
            <div class="quick-actions">
              <el-button v-for="item in quickActions" :key="item.type" @click="selectQuick(item.prompt)">{{ item.label }}</el-button>
            </div>
          </div>
          <div v-for="message in messages" :key="message.id" class="chat-message" :class="message.role">
            <div class="chat-avatar">{{ message.role === 'ai' ? 'AI' : '我' }}</div>
            <div class="chat-bubble">
              <div class="chat-content" v-html="renderContent(message.content)" />
              <div v-if="message.quick" class="quick-actions">
                <el-button v-for="item in quickActions" :key="item.type" @click="selectQuick(item.prompt)">{{ item.label }}</el-button>
              </div>
              <div v-if="message.role === 'ai' && message.id !== 1" class="preview-actions">
                <el-button type="primary" size="small" :icon="Download" @click="saveDraftMsg(message)">保存草稿</el-button>
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
            :disabled="sending"
            @keydown.enter.exact.prevent="send"
          />
          <el-button type="primary" :icon="Promotion" circle :loading="sending" :disabled="sending" @click="send" />
        </div>
      </div>
    </div>

    <!-- 模型选择抽屉 -->
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

    <!-- 草稿箱抽屉 -->
    <el-drawer v-model="draftDrawerVisible" title="草稿箱" size="600px">
      <div v-if="drafts.length === 0" class="draft-empty">
        <p>暂无保存的草稿</p>
      </div>
      <div v-else class="draft-list">
        <div v-for="draft in drafts" :key="draft.id" class="draft-item">
          <div class="draft-info" @click="viewDraft(draft)">
            <span class="draft-title">{{ draft.title }}</span>
            <span class="draft-meta">{{ draft.doc_type }} · {{ draft.word_count }} 字 · {{ formatTime(draft.updated_at) }}</span>
          </div>
          <div class="draft-actions">
            <el-button size="small" text @click="downloadDraft(draft)">下载</el-button>
            <el-button size="small" text type="danger" @click="removeDraft(draft.id)">删除</el-button>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 草稿详情弹窗 -->
    <el-dialog v-model="draftDetailVisible" :title="viewingDraft?.title ?? '草稿详情'" width="700px">
      <div v-if="viewingDraft" class="draft-detail">
        <div class="draft-detail-meta">
          <span>{{ viewingDraft.doc_type }}</span>
          <span>{{ viewingDraft.word_count ?? 0 }} 字</span>
          <span>{{ viewingDraft.updated_at }}</span>
        </div>
        <div class="draft-detail-content" v-html="renderContent(viewingDraft.content ?? '')" />
      </div>
      <template #footer>
        <el-button @click="draftDetailVisible = false">关闭</el-button>
        <el-button v-if="viewingDraft" type="primary" @click="downloadDraft(viewingDraft)">下载</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Management, Promotion } from '@element-plus/icons-vue'
import { chatGenerate, createDraft, deleteDraft, getDraft, listDocumentModels, listDrafts } from '@/api/documents'
import type { Draft } from '@/api/documents'
import { formatBeijingMonthDayTime } from '@/utils/time'

interface Message {
  id: number
  role: 'ai' | 'user'
  content: string
  quick?: boolean
}

interface DocModel {
  id: string
  name: string
  provider: string
  context: string
  desc: string
  tags: string[]
}

interface Conversation {
  id: string
  title: string
  modelId: string
  messages: Message[]
  updatedAt: string
}

const STORAGE_KEY = 'docgen_conversations'
const ACTIVE_KEY = 'docgen_active_conv'

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return []
}

function saveConversations(convs: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
  } catch { /* ignore */ }
}

function loadActiveId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY)
  } catch { return null }
}

function saveActiveId(id: string) {
  try {
    localStorage.setItem(ACTIVE_KEY, id)
  } catch { /* ignore */ }
}

function makeWelcomeMsg(): Message[] {
  return [{ id: Date.now(), role: 'ai', content: '您好！我是对话式文档助手。请先确认右上角选择的模型，然后通过对话生成提纲、段落草稿、润色建议或测试要点。', quick: true }]
}

const quickActions = [
  { type: 'outline', label: '生成文档提纲', prompt: '请帮我生成离线大数据训练与应用系统的需求文档提纲' },
  { type: 'section', label: '补写模块段落', prompt: '请帮我补写模型训练模块的功能需求段落' },
  { type: 'polish', label: '润色已有内容', prompt: '请帮我把下面这段需求描述改得更规范：' },
  { type: 'test', label: '生成测试要点', prompt: '请帮我生成模型训练模块的验收测试要点' },
]

const defaultDocModels: DocModel[] = [
  {
    id: 'default',
    name: '默认文档模型',
    provider: '规则模板',
    context: '基础',
    desc: '尚未训练任何模型时使用的内置模板引擎，生成结构化文档草稿。',
    tags: ['需求段落', '测试要点', '润色', '提纲'],
  },
]

// ---- state ----
const input = ref('')
const sending = ref(false)
const messageBox = ref<HTMLDivElement>()
const modelDrawerVisible = ref(false)
const draftDrawerVisible = ref(false)
const draftDetailVisible = ref(false)
const docModels = ref<DocModel[]>(defaultDocModels)
const selectedModel = ref<DocModel>(defaultDocModels[0]!)
const messages = ref<Message[]>(makeWelcomeMsg())
const drafts = ref<Draft[]>([])
const viewingDraft = ref<Draft | null>(null)
const conversations = ref<Conversation[]>(loadConversations())
const activeConvId = ref<string>(loadActiveId() ?? '')

// Persist current conversation to history whenever messages change
watch(messages, () => {
  const idx = conversations.value.findIndex(c => c.id === activeConvId.value)
  if (idx === -1) return
  const title = buildConvTitle()
  const existing = conversations.value[idx]!
  conversations.value[idx] = {
    id: existing.id,
    modelId: existing.modelId,
    title,
    messages: messages.value,
    updatedAt: new Date().toISOString(),
  }
  saveConversations(conversations.value)
}, { deep: true })

// When activeConvId changes, persist it
watch(activeConvId, (id) => { if (id) saveActiveId(id) })

// ---- helpers ----
const scrollBottom = () => nextTick(() => {
  messageBox.value?.scrollTo({ top: messageBox.value.scrollHeight, behavior: 'smooth' })
})

const buildConvTitle = () => {
  const userMsg = messages.value.find(m => m.role === 'user')
  if (userMsg) {
    const text = userMsg.content.slice(0, 30).replace(/\n/g, ' ').trim()
    return text.length > 25 ? text + '...' : text
  }
  return '新对话'
}

const renderContent = (text: string) => {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/- (.+)/g, '· $1')
}

const formatTime = (iso: string) => {
  return formatBeijingMonthDayTime(iso, iso)
}

// ---- conversation management ----
const newConversation = () => {
  // save current conversation if it has user messages
  const hasContent = messages.value.some(m => m.role === 'user')
  if (hasContent && activeConvId.value) {
    // already persisted via watch, just snapshot the list
  }
  // create new
  const id = 'conv_' + Date.now()
  conversations.value.unshift({
    id,
    title: '新对话',
    modelId: selectedModel.value.id,
    messages: [],
    updatedAt: new Date().toISOString(),
  })
  saveConversations(conversations.value)
  activeConvId.value = id
  messages.value = makeWelcomeMsg()
  scrollBottom()
}

const switchConversation = (convId: string) => {
  if (convId === activeConvId.value) return
  const conv = conversations.value.find(c => c.id === convId)
  if (!conv) return
  activeConvId.value = convId
  messages.value = conv.messages.length > 0 ? conv.messages : makeWelcomeMsg()
  // restore model selection
  const model = docModels.value.find(m => m.id === conv.modelId)
  if (model) selectedModel.value = model
  scrollBottom()
}

const deleteConversation = (convId: string) => {
  conversations.value = conversations.value.filter(c => c.id !== convId)
  saveConversations(conversations.value)
  if (convId === activeConvId.value) {
    // switch to the most recent or create new
    const latest = conversations.value[0]
    if (latest) {
      switchConversation(latest.id)
    } else {
      activeConvId.value = ''
      messages.value = makeWelcomeMsg()
    }
  }
}

const selectModel = (model: DocModel) => {
  selectedModel.value = model
  modelDrawerVisible.value = false
  ElMessage.success(`已切换到 ${model.name}`)
}

const selectQuick = (prompt: string) => {
  input.value = prompt
  send()
}

const send = async () => {
  const content = input.value.trim()
  if (!content || sending.value) return
  messages.value.push({ id: Date.now(), role: 'user', content })
  input.value = ''
  sending.value = true
  try {
    const result = await chatGenerate({ message: content, model_code: selectedModel.value.id })
    messages.value.push({ id: Date.now() + 1, role: 'ai', content: result.content })
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : '文档生成失败'
    messages.value.push({ id: Date.now() + 1, role: 'ai', content: `请求失败：${errMsg}` })
    ElMessage.error(errMsg)
  } finally {
    sending.value = false
  }
  scrollBottom()
}

const buildDocTitle = (msg: Message) => {
  const words = msg.content.slice(0, 40).replace(/\n/g, ' ').trim()
  return words ? `文档草稿：${words}...` : '文档草稿'
}

const saveDraftMsg = async (msg: Message) => {
  const title = buildDocTitle(msg)
  const content = msg.content.startsWith('#') ? msg.content : `# ${title}\n\n${msg.content}`
  await createDraft({
    model_code: selectedModel.value.id,
    doc_type: 'summary',
    title,
    content,
  })
  ElMessage.success('已保存到草稿箱')
  loadDrafts()
}

const loadDrafts = async () => {
  try {
    const res = await listDrafts()
    drafts.value = res ?? []
  } catch { /* drafts unavailable */ }
}

const viewDraft = async (draft: Draft) => {
  try {
    const detail = await getDraft(draft.id)
    viewingDraft.value = detail
    draftDetailVisible.value = true
  } catch {
    ElMessage.error('无法加载草稿详情')
  }
}

const removeDraft = async (draftId: string) => {
  try {
    await ElMessageBox.confirm('确定删除该草稿？', '删除确认', { type: 'warning' })
  } catch {
    return // user cancelled
  }
  try {
    await deleteDraft(draftId)
    drafts.value = drafts.value.filter(d => d.id !== draftId)
    ElMessage.success('草稿已删除')
  } catch {
    ElMessage.error('删除草稿失败')
  }
}

const downloadDraft = async (draft: Draft) => {
  let content = draft.content
  if (!content) {
    try {
      const detail = await getDraft(draft.id)
      content = detail.content ?? ''
    } catch {
      ElMessage.error('无法获取草稿内容')
      return
    }
  }
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${draft.title ?? 'draft'}.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  // Init active conversation
  if (!activeConvId.value || !conversations.value.find(c => c.id === activeConvId.value)) {
    if (conversations.value.length > 0) {
      switchConversation(conversations.value[0]!.id)
    } else {
      const id = 'conv_' + Date.now()
      conversations.value = [{
        id,
        title: '新对话',
        modelId: selectedModel.value.id,
        messages: messages.value,
        updatedAt: new Date().toISOString(),
      }]
      activeConvId.value = id
      saveConversations(conversations.value)
    }
  } else {
    // restore messages from the active conversation
    const conv = conversations.value.find(c => c.id === activeConvId.value)
    if (conv) messages.value = conv.messages.length > 0 ? conv.messages : makeWelcomeMsg()
  }

  // Load models and drafts
  const [models] = await Promise.allSettled([
    listDocumentModels().catch(() => null),
    loadDrafts(),
  ])
  if (models.status === 'fulfilled' && models.value && models.value.length > 0) {
    docModels.value = models.value.map((model) => ({
      id: model.value,
      name: model.label,
      provider: `${model.framework ?? '训练模型'} · ${model.model_type ?? 'gpt2'}`,
      context: `v${model.version}`,
      desc: `支持 ${model.types.join('、')} 类型文档生成`,
      tags: model.types,
    }))
    // keep existing selection if still valid
    const stillExists = docModels.value.find(m => m.id === selectedModel.value.id)
    if (!stillExists) selectedModel.value = docModels.value[0]!
  }
})
</script>

<style scoped>
.doc-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* layout */
.doc-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 176px);
  min-height: 560px;
}

/* conversation sidebar */
.conversation-sidebar {
  width: 220px;
  flex-shrink: 0;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: #fff;
  overflow-y: auto;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.conv-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
}

.conv-item:hover {
  background: var(--bg-color);
}

.conv-item.active {
  border-color: var(--primary-color);
  background: rgb(37 99 235 / 6%);
}

.conv-title {
  display: block;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 28px;
}

.conv-time {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.conv-delete {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0;
  transition: opacity .15s;
}

.conv-item:hover .conv-delete {
  opacity: 1;
}

.conv-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px 0;
}

/* chat area */
.chat-container {
  flex: 1;
  display: flex;
  min-width: 0;
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

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: 16px;
}

.chat-empty p {
  font-size: 15px;
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

.chat-content :deep(h2) { margin: 0 0 8px; font-size: 17px; }
.chat-content :deep(h3) { margin: 0 0 6px; font-size: 15px; }
.chat-content :deep(h4) { margin: 0 0 4px; font-size: 14px; }
.chat-content :deep(p) { margin: 0; }
.chat-content :deep(strong) { font-weight: 700; }

.chat-message.user .chat-content :deep(h2),
.chat-message.user .chat-content :deep(h3),
.chat-message.user .chat-content :deep(h4),
.chat-message.user .chat-content :deep(p),
.chat-message.user .chat-content :deep(strong) {
  color: #fff;
}

.quick-actions,
.preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.chat-input-container {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid var(--border-color);
  background: #fff;
}

/* model drawer */
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

.model-name { font-size: 16px; font-weight: 700; }
.model-meta, .doc-model-card p { color: var(--text-secondary); font-size: 13px; }
.doc-model-card p { margin: 0; line-height: 1.6; }

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

/* drafts */
.draft-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 40px 0;
}

.draft-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.draft-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.draft-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
}

.draft-title {
  font-weight: 600;
  font-size: 14px;
}

.draft-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.draft-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.draft-detail-meta {
  display: flex;
  gap: 16px;
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
}

.draft-detail-content {
  max-height: 50vh;
  overflow-y: auto;
  line-height: 1.8;
}

.draft-detail-content :deep(h2) { font-size: 18px; margin: 16px 0 8px; }
.draft-detail-content :deep(h3) { font-size: 16px; margin: 12px 0 6px; }
.draft-detail-content :deep(h4) { font-size: 14px; margin: 10px 0 4px; }

@media (max-width: 700px) {
  .doc-header { flex-direction: column; }
  .doc-layout { flex-direction: column; height: auto; }
  .conversation-sidebar { width: 100%; max-height: 200px; }
  .chat-container { height: calc(100vh - 420px); min-height: 400px; }
  .chat-bubble { max-width: 86%; }
}
</style>
