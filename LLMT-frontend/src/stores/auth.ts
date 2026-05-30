import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  clearAuth,
  getCurrentUser,
  getToken,
  getMe,
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
  saveAuth,
  updateStoredUser,
  type AuthUser,
  type LoginPayload,
  type RegisterPayload,
} from '@/api/auth'
import { demoUsers, roleMenuVisibility, systemMenuKeys, type RoleCode } from '@/mock/auth'
import { hasAnyPermission as checkAnyPermission, hasPermission as checkPermission } from '@/utils/permission'

// 认证与权限 Store：集中维护登录态、当前用户、角色菜单和页面权限判断。
export const useAuthStore = defineStore('auth', () => {
  // 初始化时先从 localStorage 恢复登录态，刷新页面后仍能保持登录。
  const token = ref(getToken())
  const user = ref<AuthUser | null>(getCurrentUser())

  // 角色到菜单权限的映射。这里使用 mock 中的默认配置作为前端兜底权限表。
  const roleMenus = reactive<Record<RoleCode, string[]>>({
    admin: [...roleMenuVisibility.admin],
    ops: [...roleMenuVisibility.ops],
    algorithm: [...roleMenuVisibility.algorithm],
    data: [...roleMenuVisibility.data],
    user: [...roleMenuVisibility.user],
  })

  // 当前用户可能拥有多个角色；兼容只有单个 roleCode 的旧数据结构。
  const roleCodes = computed<RoleCode[]>(() => user.value?.roleCodes ?? (user.value ? [user.value.roleCode as RoleCode] : []))

  // 当前用户可见菜单：优先使用后端返回的 menuKeys；没有时按角色默认权限合并去重。
  const visibleMenuKeys = computed(() => {
    if (user.value?.menuKeys?.length) return user.value.menuKeys
    return Array.from(new Set(roleCodes.value.flatMap((roleCode) => roleMenus[roleCode] ?? [])))
  })

  // 同时存在 token 和用户信息时，认为前端处于已登录状态。
  const isLoggedIn = computed(() => Boolean(token.value && user.value))

  // 登录成功后，同步更新 localStorage 和 Pinia 状态，供路由守卫和页面权限使用。
  const login = async (payload: LoginPayload) => {
    const result = await loginApi(payload)
    saveAuth(result)
    token.value = result.token
    user.value = result.user
    return result
  }

  // 注册成功后的处理和登录一致：后端返回 token 后直接进入已登录状态。
  const register = async (payload: RegisterPayload) => {
    const result = await registerApi(payload)
    saveAuth(result)
    token.value = result.token
    user.value = result.user
    return result
  }

  // 退出登录时不阻塞后端 logout 请求；无论接口是否成功，前端都会清空本地登录态。
  const logout = () => {
    void logoutApi().catch(() => undefined)
    clearAuth()
    token.value = null
    user.value = null
  }

  // 从后端重新拉取当前用户信息，适合菜单权限变更后刷新本地缓存。
  const refreshCurrentUser = async () => {
    if (!token.value) return null
    const nextUser = await getMe()
    user.value = nextUser
    updateStoredUser(nextUser)
    return nextUser
  }

  // 演示/开发用的角色切换逻辑：不用重新登录，直接切换本地用户与菜单权限。
  const switchRole = (roleCode: RoleCode) => {
    const nextUser = demoUsers.find((item) => item.roleCode === roleCode)
    if (!nextUser) return

    const { password: _password, ...authUser } = nextUser
    const nextAuthUser = { ...authUser, menuKeys: roleMenus[roleCode] ?? [], department: '' }
    const nextToken = token.value ?? `mock-token-${nextUser.username}-${Date.now()}`
    saveAuth({ token: nextToken, user: nextAuthUser })
    token.value = nextToken
    user.value = nextAuthUser
  }

  // 系统管理中调整角色菜单后，同步更新前端权限映射。
  const updateRoleMenus = (roleCode: RoleCode, menuKeys: string[]) => {
    roleMenus[roleCode] = [...menuKeys]
  }

  // 权限判断方法供路由守卫、侧边栏和页面按钮显隐复用。
  const hasPermission = (menuKey?: string) => checkPermission(visibleMenuKeys.value, menuKey)
  const hasAnyPermission = (requiredMenuKeys: string[] = []) =>
    checkAnyPermission(visibleMenuKeys.value, requiredMenuKeys)
  const canViewMenu = (menuKey?: string) => hasPermission(menuKey)
  const canViewAnySystemMenu = () => hasAnyPermission(systemMenuKeys)

  return {
    token,
    user,
    roleCodes,
    visibleMenuKeys,
    roleMenus,
    isLoggedIn,
    login,
    register,
    logout,
    refreshCurrentUser,
    switchRole,
    updateRoleMenus,
    hasPermission,
    hasAnyPermission,
    canViewMenu,
    canViewAnySystemMenu,
  }
})
