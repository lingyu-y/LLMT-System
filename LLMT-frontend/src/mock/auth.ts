export type RoleCode = 'admin' | 'ops' | 'algorithm' | 'data' | 'user'

export interface DemoUser {
  id: number
  username: string
  password: string
  realName: string
  role: string
  roleCode: RoleCode
  roleCodes: RoleCode[]
}

export const menuKeys = ['dashboard', 'dataset', 'training', 'model', 'document', 'system:user', 'system:role', 'system:menu', 'system:log']

export const systemMenuKeys = ['system:user', 'system:role', 'system:menu', 'system:log']

export const roleMenuVisibility: Record<RoleCode, string[]> = {
  admin: menuKeys,
  ops: ['dashboard', 'system:log'],
  algorithm: ['dashboard', 'dataset', 'training', 'model', 'document'],
  data: ['dashboard', 'dataset'],
  user: ['dashboard', 'document'],
}

export const demoUsers: DemoUser[] = [
  {
    id: 1,
    username: 'admin',
    password: '123456',
    realName: '系统管理员',
    role: '系统管理员',
    roleCode: 'admin',
    roleCodes: ['admin'],
  },
  {
    id: 2,
    username: 'ops',
    password: '123456',
    realName: '运维人员',
    role: '运维人员',
    roleCode: 'ops',
    roleCodes: ['ops'],
  },
  {
    id: 3,
    username: 'algorithm',
    password: '123456',
    realName: '算法工程师',
    role: '算法工程师',
    roleCode: 'algorithm',
    roleCodes: ['algorithm'],
  },
  {
    id: 4,
    username: 'data',
    password: '123456',
    realName: '数据工程师',
    role: '数据工程师',
    roleCode: 'data',
    roleCodes: ['data'],
  },
  {
    id: 5,
    username: 'user',
    password: '123456',
    realName: '普通用户',
    role: '普通用户',
    roleCode: 'user',
    roleCodes: ['user'],
  },
]
