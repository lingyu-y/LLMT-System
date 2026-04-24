export const users = [
  { name: '张三', account: 'zhangsan', role: '数据科学家', department: '算法组', status: '启用', lastLogin: '2024-01-15 15:20' },
  { name: '李四', account: 'lisi', role: '模型开发者', department: '平台组', status: '启用', lastLogin: '2024-01-15 11:08' },
  { name: '王五', account: 'wangwu', role: '系统管理员', department: '运维组', status: '启用', lastLogin: '2024-01-14 18:40' },
]

export const roles = [
  { name: '系统管理员', users: 2, desc: '拥有系统所有权限' },
  { name: '数据科学家', users: 8, desc: '可进行数据处理和模型训练' },
  { name: '模型开发者', users: 5, desc: '可进行模型开发和部署' },
  { name: '普通用户', users: 16, desc: '只能查看和使用模型' },
]

export const menus = [
  { label: '训练监控', children: [{ label: '仪表盘' }] },
  { label: '数据处理' },
  { label: '模型训练' },
  { label: '模型管理' },
  { label: '文档生成' },
  { label: '系统管理', children: [{ label: '用户管理' }, { label: '角色管理' }, { label: '日志管理' }] },
]
