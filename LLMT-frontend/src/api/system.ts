import { del, get, patch, post, put, type ApiMessage, type PageResult, unwrap } from '@/api/http'

export interface SystemRole {
  id: number
  name: string
  description?: string | null
  role_type?: string | null
  status: string
  created_at: string
  updated_at?: string
}

export interface SystemUser {
  id: number
  username: string
  real_name?: string | null
  email?: string | null
  phone?: string | null
  status: string
  is_superuser: boolean
  roles: { id: number; name: string }[]
  last_login_at?: string | null
  created_at: string
  updated_at?: string
}

export interface SystemMenu {
  id: number
  key: string
  name: string
  path: string
  icon: string
  parent_id?: number | null
  sort_order?: number
  children?: SystemMenu[]
}

export interface SystemLog {
  id: number
  user_id?: number | null
  username: string
  level?: 'INFO' | 'WARN' | 'ERROR' | string
  action: string
  resource: string
  resource_id?: number | null
  detail: string
  ip_address?: string | null
  created_at?: string | null
}

export const listUsers = (params?: { page?: number; page_size?: number; keyword?: string; status?: string }) =>
  get<PageResult<SystemUser>>('/system/users', params)

export const createUser = async (payload: { username: string; password: string; real_name?: string; email?: string; phone?: string; role_ids?: number[] }) =>
  unwrap(await post<ApiMessage<SystemUser>>('/system/users', payload))

export const updateUser = async (id: number, payload: { username?: string; real_name?: string; email?: string; phone?: string; password?: string }) =>
  unwrap(await put<ApiMessage<SystemUser>>(`/system/users/${id}`, payload))

export const deleteUser = async (id: number) => await del<ApiMessage>(`/system/users/${id}`)

export const updateUserStatus = async (id: number, status: string) =>
  unwrap(await patch<ApiMessage<SystemUser>>(`/system/users/${id}/status`, { status }))

export const updateUserRoles = async (id: number, roleIds: number[]) =>
  unwrap(await put<ApiMessage<SystemUser>>(`/system/users/${id}/roles`, { role_ids: roleIds }))

export const listRoles = (params?: { page?: number; page_size?: number; keyword?: string }) =>
  get<PageResult<SystemRole>>('/system/roles', params)

export const createRole = async (payload: { name: string; description?: string; role_type?: string; permission_ids?: number[] }) =>
  unwrap(await post<ApiMessage<SystemRole>>('/system/roles', payload))

export const updateRole = async (id: number, payload: { name?: string; description?: string; role_type?: string; permission_ids?: number[] }) =>
  unwrap(await put<ApiMessage<SystemRole>>(`/system/roles/${id}`, payload))

export const deleteRole = async (id: number) => await del<ApiMessage>(`/system/roles/${id}`)

export const updateRoleStatus = async (id: number, status: string) =>
  unwrap(await patch<ApiMessage<SystemRole>>(`/system/roles/${id}/status`, { status }))

export const listMenus = async () => unwrap(await get<ApiMessage<SystemMenu[]>>('/system/menus'))

export const listCurrentMenus = async () => unwrap(await get<ApiMessage<SystemMenu[]>>('/system/menus/current'))

export const getRoleMenus = async (roleId: number) => unwrap(await get<ApiMessage<SystemMenu[]>>(`/system/roles/${roleId}/menus`))

export const saveRoleMenus = async (roleId: number, menuIds: number[]) =>
  await put<ApiMessage>(`/system/roles/${roleId}/menus`, { menu_ids: menuIds })

export const listLogs = (params?: { page?: number; page_size?: number; keyword?: string; action?: string; resource?: string; username?: string }) =>
  get<PageResult<SystemLog>>('/system/logs', params)

export const listMyLogs = (params?: { page?: number; page_size?: number }) => get<PageResult<SystemLog>>('/system/my-logs', params)

export const exportLogs = async () => {
  const token = localStorage.getItem('llmt_token')
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch('/api/v1/system/logs/export', { headers })
  if (!response.ok) {
    const body = await response.json().catch(() => undefined)
    throw new Error(body?.detail ?? body?.message ?? '日志导出失败')
  }
  return response.blob()
}
