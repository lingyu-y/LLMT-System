import { get, post, type ApiMessage, type PageResult, unwrap } from '@/api/http'

export interface DocumentModel {
  code: string
  name: string
  description: string
}

export interface ChatResult {
  reply: string
  model_code: string
}

export interface Draft {
  id: string
  user_id: number
  doc_type: string
  title: string
  content: string
  created_at: string
  updated_at: string
}

export const listDocumentModels = async () => unwrap(await get<ApiMessage<DocumentModel[]>>('/documents/models'))

export const chatGenerate = async (payload: { prompt: string; model_code?: string; context?: string }) =>
  unwrap(await post<ApiMessage<ChatResult>>('/documents/chat', payload))

export const createDraft = async (payload: { doc_type: string; title: string; content: string }) =>
  unwrap(await post<ApiMessage<Draft>>('/documents/drafts', payload))

export const listDrafts = (params?: { page?: number; page_size?: number }) => get<PageResult<Draft>>('/documents/drafts', params)
