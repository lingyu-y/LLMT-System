export interface PermissionMenuItem<T> {
  permission?: string
  children?: T[]
}

export const hasPermission = (permissions: string[], permission?: string) =>
  !permission || permissions.includes(permission)

export const hasAnyPermission = (permissions: string[], requiredPermissions: string[] = []) =>
  requiredPermissions.length === 0 || requiredPermissions.some((permission) => permissions.includes(permission))

export const filterMenusByPermission = <T extends PermissionMenuItem<T>>(menus: T[], permissions: string[]): T[] =>
  menus
    .map((item) => {
      const children = item.children ? filterMenusByPermission(item.children, permissions) : undefined
      const visible = hasPermission(permissions, item.permission) || Boolean(children?.length)

      if (!visible) return null

      return {
        ...item,
        ...(children ? { children } : {}),
      } as T
    })
    .filter((item): item is T => item !== null)
