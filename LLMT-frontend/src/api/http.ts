// 前端接口基础路径。开发环境下 /api 会被 Vite 代理到后端 FastAPI 服务。
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

// 和 src/api/auth.ts 保持一致，用于从 localStorage 读取 token。
const TOKEN_KEY = 'llmt_token'

// 通用分页返回结构，适用于列表类接口。
export interface PageResult<T> {
  data: T[]
  total: number
  page: number
  page_size: number
}

// 后端大部分业务接口使用的统一响应结构。
export interface ApiMessage<T = unknown> {
  message: string
  data?: T
}

// 统一接口错误类型，页面可以通过 status 判断 401、403、500 等情况。
export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// 拼接请求地址，并把 params 中有效值追加为 query string。
const buildUrl = (path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)

  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })

  return url.toString()
}

// 尽量从后端响应体中提取可读错误信息，兼容 FastAPI 的 detail 和自定义 message。
const parseErrorMessage = async (response: Response) => {
  try {
    const body = await response.json()
    return body.detail ?? body.message ?? `请求失败 (${response.status})`
  } catch {
    return `请求失败 (${response.status})`
  }
}

// 所有普通接口请求的底层封装：负责加 token、设置 JSON 请求头、统一抛错和解析 JSON。
export const request = async <T>(path: string, init: RequestInit = {}, params?: Record<string, string | number | boolean | undefined | null>) => {
  const headers = new Headers(init.headers)
  const token = localStorage.getItem(TOKEN_KEY)

  // 登录后所有请求自动携带 JWT，后端通过 Authorization 识别当前用户。
  if (token) headers.set('Authorization', `Bearer ${token}`)

  // FormData 让浏览器自己生成 multipart boundary；普通对象请求才设置 JSON。
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(buildUrl(path, params), { ...init, headers })

  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status)
  }

  // 204 没有响应体，直接返回 undefined，避免 response.json() 报错。
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

// GET 请求：params 会被拼到 URL 查询参数中。
export const get = <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) =>
  request<T>(path, {}, params)

// POST 请求：支持普通 JSON body，也支持 FormData 上传。
export const post = <T>(path: string, body?: unknown, params?: Record<string, string | number | boolean | undefined | null>) =>
  request<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }, params)

// PUT 请求：用于整体更新资源。
export const put = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) })

// PATCH 请求：用于局部更新资源。
export const patch = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) })

// DELETE 请求：删除资源。
export const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

// 从 { message, data } 结构里取 data。使用前要确认接口确实返回 ApiMessage。
export const unwrap = <T>(response: ApiMessage<T>) => response.data as T
