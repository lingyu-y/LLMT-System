import { roleMenuVisibility } from '@/mock/auth'

export const users = [
  { name: '系统管理员', account: 'admin', role: '系统管理员', status: '启用', lastLogin: '2026-04-25 09:30' },
  { name: '运维人员', account: 'ops', role: '运维人员', status: '启用', lastLogin: '2026-04-25 08:58' },
  { name: '算法工程师', account: 'algorithm', role: '算法工程师', status: '启用', lastLogin: '2026-04-25 09:12' },
  { name: '数据工程师', account: 'data', role: '数据工程师', status: '启用', lastLogin: '2026-04-25 08:40' },
  { name: '普通用户', account: 'user', role: '普通用户', status: '启用', lastLogin: '2026-04-24 16:02' },
]

export const roles = [
  { code: 'admin', name: '系统管理员', users: 1, desc: '拥有全部菜单和系统管理能力', status: '启用', menus: roleMenuVisibility.admin },
  { code: 'ops', name: '运维人员', users: 1, desc: '查看仪表盘和全系统日志', status: '启用', menus: roleMenuVisibility.ops },
  { code: 'algorithm', name: '算法工程师', users: 1, desc: '使用数据、训练、模型和文档模块', status: '启用', menus: roleMenuVisibility.algorithm },
  { code: 'data', name: '数据工程师', users: 1, desc: '使用仪表盘和数据处理模块', status: '启用', menus: roleMenuVisibility.data },
  { code: 'user', name: '普通用户', users: 1, desc: '查看仪表盘和文档生成模块', status: '启用', menus: roleMenuVisibility.user },
]

export const menus = [
  { key: 'dashboard', label: '仪表盘' },
  { key: 'dataset', label: '数据处理' },
  { key: 'training', label: '模型训练' },
  { key: 'model', label: '模型管理' },
  { key: 'document', label: '文档生成' },
  {
    key: 'system',
    label: '系统管理',
    children: [
      { key: 'system:user', label: '用户管理' },
      { key: 'system:role', label: '角色管理' },
      { key: 'system:menu', label: '菜单管理' },
      { key: 'system:log', label: '日志管理' },
    ],
  },
]
