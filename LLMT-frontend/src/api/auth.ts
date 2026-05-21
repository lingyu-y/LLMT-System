import { get, post } from '@/api/http'
import type { RoleCode } from '@/mock/auth'

const TOKEN_KEY = 'llmt_token'
const USER_KEY = 'llmt_user'

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload {
  username: string
  password: string
  realName?: string
  email?: string
  phone?: string
}

export interface AuthUser {
  id: number
  username: string
  realName: string
  role: string
  roleCode: string
  roleCodes: RoleCode[]
  menuKeys: string[]
  department: string
}

export interface LoginResult {
  token: string
  user: AuthUser
}

export interface DemoAccount {
  username: string
  password: string
  realName: string
  role: string
  roleCodes: RoleCode[]
}

interface BackendUser {
  id: number
  username: string
  realName?: string | null
  roleCodes?: string[]
  menuKeys?: string[]
}

interface BackendDemoAccount {
  username: string
  realName?: string | null
  roleCodes?: string[]
}

const roleNameMap: Record<string, string> = {
  admin: '系统管理员',
  ops: '运维人员',
  algorithm: '算法工程师',
  data: '数据工程师',
  user: '普通用户',
}

const normalizeRoleCode = (roleCode?: string): RoleCode => {
  if (roleCode === 'admin' || roleCode === 'ops' || roleCode === 'algorithm' || roleCode === 'data' || roleCode === 'user') {
    return roleCode
  }
  return roleCode?.includes('管理员') ? 'admin' : 'user'
}

const normalizeUser = (user: BackendUser): AuthUser => {
  const roleCodes = (user.roleCodes?.length ? user.roleCodes : ['user']).map(normalizeRoleCode)
  const primaryRole = roleCodes[0] ?? 'user'

  return {
    id: user.id,
    username: user.username,
    realName: user.realName ?? user.username,
    role: roleNameMap[primaryRole] ?? primaryRole,
    roleCode: primaryRole,
    roleCodes,
    menuKeys: user.menuKeys ?? [],
    department: '',
  }
}

export const getDemoAccounts = async (): Promise<DemoAccount[]> => {
  const accounts = await get<BackendDemoAccount[]>('/auth/demo-accounts')

  return accounts.map((account) => {
    const roleCodes = (account.roleCodes?.length ? account.roleCodes : ['user']).map(normalizeRoleCode)
    const primaryRole = roleCodes[0] ?? 'user'
    return {
      username: account.username,
      password: '123456',
      realName: account.realName ?? account.username,
      role: roleNameMap[primaryRole] ?? primaryRole,
      roleCodes,
    }
  })
}

export const login = async (payload: LoginPayload): Promise<LoginResult> => {
  const result = await post<{ token: string; user: BackendUser }>('/auth/login', payload)
  return { token: result.token, user: normalizeUser(result.user) }
}

export const register = async (payload: RegisterPayload): Promise<LoginResult> => {
  const result = await post<{ token: string; user: BackendUser }>('/auth/register', payload)
  return { token: result.token, user: normalizeUser(result.user) }
}

export const getMe = async () => {
  const result = await get<{ data: BackendUser }>('/auth/me')
  return normalizeUser(result.data)
}

export const logout = () => post('/auth/logout')

export const saveAuth = (result: LoginResult) => {
  localStorage.setItem(TOKEN_KEY, result.token)
  localStorage.setItem(USER_KEY, JSON.stringify(result.user))
}

export const updateStoredUser = (user: AuthUser) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export const getToken = () => localStorage.getItem(TOKEN_KEY)

export const getCurrentUser = (): AuthUser | null => {
  const rawUser = localStorage.getItem(USER_KEY)
  if (!rawUser) return null

  try {
    return JSON.parse(rawUser) as AuthUser
  } catch {
    clearAuth()
    return null
  }
}

export const isAuthenticated = () => Boolean(getToken() && getCurrentUser())
