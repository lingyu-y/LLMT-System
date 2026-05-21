const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const TOKEN_KEY = 'llmt_token'

export interface PageResult<T> {
  data: T[]
  total: number
  page: number
  page_size: number
}

export interface ApiMessage<T = unknown> {
  message: string
  data?: T
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const buildUrl = (path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)

  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })

  return url.toString()
}

const parseErrorMessage = async (response: Response) => {
  try {
    const body = await response.json()
    return body.detail ?? body.message ?? `请求失败 (${response.status})`
  } catch {
    return `请求失败 (${response.status})`
  }
}

export const request = async <T>(path: string, init: RequestInit = {}, params?: Record<string, string | number | boolean | undefined | null>) => {
  const headers = new Headers(init.headers)
  const token = localStorage.getItem(TOKEN_KEY)

  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(buildUrl(path, params), { ...init, headers })

  if (!response.ok) {
    throw new ApiError(await parseErrorMessage(response), response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const get = <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) =>
  request<T>(path, {}, params)

export const post = <T>(path: string, body?: unknown, params?: Record<string, string | number | boolean | undefined | null>) =>
  request<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }, params)

export const put = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) })

export const patch = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) })

export const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

export const unwrap = <T>(response: ApiMessage<T>) => response.data as T
