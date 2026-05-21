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

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getToken())
  const user = ref<AuthUser | null>(getCurrentUser())
  const roleMenus = reactive<Record<RoleCode, string[]>>({
    admin: [...roleMenuVisibility.admin],
    ops: [...roleMenuVisibility.ops],
    algorithm: [...roleMenuVisibility.algorithm],
    data: [...roleMenuVisibility.data],
    user: [...roleMenuVisibility.user],
  })

  const roleCodes = computed<RoleCode[]>(() => user.value?.roleCodes ?? (user.value ? [user.value.roleCode as RoleCode] : []))
  const visibleMenuKeys = computed(() => {
    if (user.value?.menuKeys?.length) return user.value.menuKeys
    return Array.from(new Set(roleCodes.value.flatMap((roleCode) => roleMenus[roleCode] ?? [])))
  })
  const isLoggedIn = computed(() => Boolean(token.value && user.value))

  const login = async (payload: LoginPayload) => {
    const result = await loginApi(payload)
    saveAuth(result)
    token.value = result.token
    user.value = result.user
    return result
  }

  const register = async (payload: RegisterPayload) => {
    const result = await registerApi(payload)
    saveAuth(result)
    token.value = result.token
    user.value = result.user
    return result
  }

  const logout = () => {
    void logoutApi().catch(() => undefined)
    clearAuth()
    token.value = null
    user.value = null
  }

  const refreshCurrentUser = async () => {
    if (!token.value) return null
    const nextUser = await getMe()
    user.value = nextUser
    updateStoredUser(nextUser)
    return nextUser
  }

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

  const updateRoleMenus = (roleCode: RoleCode, menuKeys: string[]) => {
    roleMenus[roleCode] = [...menuKeys]
  }

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
