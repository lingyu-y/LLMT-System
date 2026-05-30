import { get, post } from '@/api/http'
import type { RoleCode } from '@/mock/auth'

// 登录态在浏览器本地存储中的 key，auth store 会读取它们恢复登录状态。
const TOKEN_KEY = 'llmt_token'
const USER_KEY = 'llmt_user'

// 登录接口入参。
export interface LoginPayload {
  username: string
  password: string
}

// 注册接口入参。realName 是前端字段，后端字段转换由接口层或后端约定处理。
export interface RegisterPayload {
  username: string
  password: string
  realName?: string
  email?: string
  phone?: string
}

// 前端统一使用的用户模型，路由权限、侧边栏和页面按钮都依赖这个结构。
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

// 登录/注册成功后，前端需要同时拿到 token 和标准化后的用户信息。
export interface LoginResult {
  token: string
  user: AuthUser
}

// 登录页展示用的演示账号结构。
export interface DemoAccount {
  username: string
  password: string
  realName: string
  role: string
  roleCodes: RoleCode[]
}

// 后端返回的用户字段。这里单独建类型，是为了和前端 AuthUser 解耦。
interface BackendUser {
  id: number
  username: string
  realName?: string | null
  roleCodes?: string[]
  menuKeys?: string[]
}

// 后端演示账号接口返回值，不包含密码；前端统一展示默认密码。
interface BackendDemoAccount {
  username: string
  realName?: string | null
  roleCodes?: string[]
}

// 角色编码到中文展示名称的映射。
const roleNameMap: Record<string, string> = {
  admin: '系统管理员',
  ops: '运维人员',
  algorithm: '算法工程师',
  data: '数据工程师',
  user: '普通用户',
}

// 将后端角色编码归一化成前端已知角色。未知角色默认按普通用户处理。
const normalizeRoleCode = (roleCode?: string): RoleCode => {
  if (roleCode === 'admin' || roleCode === 'ops' || roleCode === 'algorithm' || roleCode === 'data' || roleCode === 'user') {
    return roleCode
  }
  return roleCode?.includes('管理员') ? 'admin' : 'user'
}

// 将后端用户对象转换为前端统一用户模型，补齐角色、菜单和展示字段。
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

// 获取演示账号列表，并补充前端固定展示的默认密码。
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

// 登录：调用后端接口后，将后端用户标准化为 AuthUser。
export const login = async (payload: LoginPayload): Promise<LoginResult> => {
  const result = await post<{ token: string; user: BackendUser }>('/auth/login', payload)
  return { token: result.token, user: normalizeUser(result.user) }
}

// 注册：后端注册成功后直接返回登录态，前端处理方式和 login 一致。
export const register = async (payload: RegisterPayload): Promise<LoginResult> => {
  const result = await post<{ token: string; user: BackendUser }>('/auth/register', payload)
  return { token: result.token, user: normalizeUser(result.user) }
}

// 获取当前登录用户，用于刷新本地缓存或权限变更后的重新同步。
export const getMe = async () => {
  const result = await get<{ data: BackendUser }>('/auth/me')
  return normalizeUser(result.data)
}

// 通知后端退出登录；前端本地清理在 auth store 中处理。
export const logout = () => post('/auth/logout')

// 保存登录结果到 localStorage，保证刷新页面后仍能恢复登录态。
export const saveAuth = (result: LoginResult) => {
  localStorage.setItem(TOKEN_KEY, result.token)
  localStorage.setItem(USER_KEY, JSON.stringify(result.user))
}

// 只更新本地用户缓存，常用于刷新当前用户权限后写回 localStorage。
export const updateStoredUser = (user: AuthUser) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

// 清除本地登录态。
export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 读取本地 token，http.ts 会用它组装 Authorization 请求头。
export const getToken = () => localStorage.getItem(TOKEN_KEY)

// 读取本地用户信息；JSON 损坏时自动清空，避免应用卡在异常登录态。
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

// 简单判断是否已登录，同时要求 token 和用户信息都存在。
export const isAuthenticated = () => Boolean(getToken() && getCurrentUser())
