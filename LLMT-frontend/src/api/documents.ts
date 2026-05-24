import { del, get, post, put, type ApiMessage, type PageResult, unwrap } from '@/api/http'

export interface DocumentModel {
  value: string
  label: string
  version: string
  framework: string
  model_type: string
  types: string[]
}

export interface ChatResult {
  role: 'assistant'
  content: string
  model_code: string
}

export interface Draft {
  id: string
  user_id?: number
  doc_type: string
  title: string
  content?: string
  created_at?: string
  updated_at: string
  model_code?: string
  word_count?: number
}

export interface GenerateResult {
  model_code: string
  doc_type: string
  title: string
  content: string
  word_count: number
}

export interface QualityCheckResult {
  score: number
  word_count: number
  issues: Array<{ level: string; item: string; detail: string }>
  passed: boolean
}

export const listDocumentModels = async () => unwrap(await get<ApiMessage<DocumentModel[]>>('/documents/models'))

export const chatGenerate = async (payload: { message: string; model_code: string }) =>
  unwrap(await post<ApiMessage<ChatResult>>('/documents/chat', payload))

export const generateDocument = async (payload: { model_code: string; doc_type: string; title: string; outline?: string; requirements?: string }) =>
  unwrap(await post<ApiMessage<GenerateResult>>('/documents/generate', payload))

export const checkDocumentQuality = async (content: string) =>
  unwrap(await post<ApiMessage<QualityCheckResult>>('/documents/quality-check', { content }))

export const createDraft = async (payload: { model_code: string; doc_type: string; title: string; content: string }) =>
  unwrap(await post<ApiMessage<Draft>>('/documents/drafts', payload))

export const listDrafts = async () => unwrap(await get<ApiMessage<Draft[]>>('/documents/drafts'))

export const getDraft = async (draftId: string) => unwrap(await get<ApiMessage<Draft>>(`/documents/drafts/${draftId}`))

export const updateDraft = async (draftId: string, payload: { title?: string; content?: string }) =>
  unwrap(await put<ApiMessage<Draft>>(`/documents/drafts/${draftId}`, payload))

export const deleteDraft = async (draftId: string) => {
  await del(`/documents/drafts/${draftId}`)
}

export const getDocumentDownloadUrl = (docId: string) => `/api/v1/documents/${docId}/download`
