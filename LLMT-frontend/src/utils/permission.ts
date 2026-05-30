// 可被权限过滤工具处理的菜单结构：菜单本身可以有权限标识，也可以有子菜单。
export interface PermissionMenuItem<T> {
  permission?: string
  children?: T[]
}

// 判断是否拥有某个权限。没有配置 permission 的菜单/页面默认可见。
export const hasPermission = (permissions: string[], permission?: string) =>
  !permission || permissions.includes(permission)

// 判断是否拥有一组权限中的任意一个；没有传入要求时默认通过。
export const hasAnyPermission = (permissions: string[], requiredPermissions: string[] = []) =>
  requiredPermissions.length === 0 || requiredPermissions.some((permission) => permissions.includes(permission))

// 根据当前用户权限过滤菜单树。父菜单没有权限但存在可见子菜单时，父菜单仍会保留。
export const filterMenusByPermission = <T extends PermissionMenuItem<T>>(menus: T[], permissions: string[]): T[] =>
  menus
    .map((item) => {
      // 先递归过滤子菜单，再决定当前菜单是否展示。
      const children = item.children ? filterMenusByPermission(item.children, permissions) : undefined
      const visible = hasPermission(permissions, item.permission) || Boolean(children?.length)

      if (!visible) return null

      return {
        ...item,
        ...(children ? { children } : {}),
      } as T
    })
    .filter((item): item is T => item !== null)
