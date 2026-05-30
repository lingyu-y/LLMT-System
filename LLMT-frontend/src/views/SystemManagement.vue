<template>
  <div>
    <!-- 系统管理总页：根据当前用户权限展示用户、角色、菜单、日志 Tab。 -->
    <div class="page-header">
      <h1 class="page-title">系统管理</h1>
      <p class="page-description">管理后端用户、角色、菜单可见性和系统日志</p>
    </div>

    <div class="card">
      <div class="card-body system-body">
        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
          <!-- 用户管理：增删改用户、启停账号、分配角色。 -->
          <el-tab-pane v-if="canUserManage" label="用户管理" name="users">
            <div class="toolbar">
              <el-input v-model="userKeyword" class="toolbar-input" placeholder="搜索用户/账号" clearable />
              <el-button type="primary" :icon="Plus" @click="openUserDialog()">新增用户</el-button>
            </div>

            <div class="table-wrap">
                <el-table :data="filteredUsers" stripe>
                <el-table-column prop="name" label="姓名" min-width="110" />
                <el-table-column prop="account" label="账号" min-width="110" />
                <el-table-column label="当前角色" min-width="180">
                  <template #default="{ row }">{{ formatRoleNames(row.roleCodes) }}</template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="90">
                  <template #default="{ row }">
                    <StatusBadge :label="row.status" :type="row.status === '启用' ? 'success' : 'warning'" />
                  </template>
                </el-table-column>
                <el-table-column prop="lastLogin" label="最近登录" min-width="150" />
                <el-table-column label="操作" min-width="300" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" @click="openUserDialog(row)">编辑</el-button>
                    <el-button size="small" @click="openAssignDialog(row)">分配角色</el-button>
                    <el-button size="small" @click="toggleUserStatus(row)">{{ row.status === '启用' ? '禁用' : '启用' }}</el-button>
                    <el-button size="small" type="danger" @click="deleteUser(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>

          <!-- 角色管理：维护角色基本信息和启停状态。菜单权限在菜单管理中配置。 -->
          <el-tab-pane v-if="canRoleManage" label="角色管理" name="roles">
            <div class="toolbar">
              <el-alert class="role-tip" title="菜单可见性请在“菜单管理”中配置。" type="info" show-icon :closable="false" />
              <el-button type="primary" :icon="Plus" @click="openRoleDialog()">新增角色</el-button>
            </div>

            <div class="table-wrap">
              <el-table :data="roleRows" stripe>
                <el-table-column prop="name" label="角色名称" min-width="130" />
                <el-table-column prop="code" label="角色编码" min-width="120" />
                <el-table-column prop="desc" label="描述" min-width="220" />
                <el-table-column prop="status" label="状态" width="90">
                  <template #default="{ row }">
                    <StatusBadge :label="row.status" :type="row.status === '启用' ? 'success' : 'warning'" />
                  </template>
                </el-table-column>
                <el-table-column label="操作" min-width="260" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" @click="openRoleDialog(row)">编辑</el-button>
                    <el-button size="small" @click="toggleRoleStatus(row)">{{ row.status === '启用' ? '禁用' : '启用' }}</el-button>
                    <el-button size="small" type="danger" @click="deleteRole(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>

          <!-- 菜单管理：给角色配置可见菜单，影响侧边栏和路由权限。 -->
          <el-tab-pane v-if="canMenuManage" label="菜单管理" name="menus">
            <div class="menu-config">
              <!-- 左侧角色列表，选择后加载该角色拥有的菜单。 -->
              <aside class="role-list">
                <button
                  v-for="role in roleRows"
                  :key="role.code"
                  class="role-item"
                  :class="{ active: selectedMenuRole === role.code }"
                  @click="selectMenuRole(role.code)"
                >
                  <strong>{{ role.name }}</strong>
                  <span>{{ role.code }}</span>
                </button>
              </aside>

              <!-- 右侧菜单勾选区域，保存时会把菜单 key 转成后端 menu id。 -->
              <section class="menu-panel">
                <div class="menu-panel-head">
                  <div>
                    <h3>{{ selectedMenuRoleName }} 可见菜单</h3>
                    <p>配置该角色登录后左侧菜单中可看到的模块。</p>
                  </div>
                  <el-button type="primary" @click="saveMenuVisibility">保存</el-button>
                </div>

                <div class="menu-tree">
                  <el-checkbox-group v-model="checkedMenuKeys">
                    <section class="menu-group">
                      <h4>一级菜单</h4>
                      <el-checkbox v-for="item in businessMenuOptions" :key="item.key" :label="item.key" border>
                        {{ item.name }}
                      </el-checkbox>
                    </section>

                    <section class="menu-group">
                      <h4>系统管理</h4>
                      <div class="system-menu-title">系统管理</div>
                      <el-checkbox v-for="item in systemMenuOptions" :key="item.key" :label="item.key" border>
                        {{ item.name }}
                      </el-checkbox>
                    </section>
                  </el-checkbox-group>
                </div>
              </section>
            </div>
          </el-tab-pane>

          <!-- 日志管理：按级别、类别、模块和关键词筛选系统日志，可导出 CSV。 -->
          <el-tab-pane v-if="canLogView" label="日志管理" name="logs">
            <div class="toolbar logs-toolbar">
              <el-select v-model="level" class="toolbar-select" placeholder="级别筛选" clearable>
                <el-option label="DEBUG" value="DEBUG" />
                <el-option label="INFO" value="INFO" />
                <el-option label="WARN" value="WARN" />
                <el-option label="ERROR" value="ERROR" />
                <el-option label="CRITICAL" value="CRITICAL" />
              </el-select>
              <el-select v-model="category" class="toolbar-select" placeholder="类别筛选" clearable>
                <el-option label="审计操作" value="audit" />
                <el-option label="训练日志" value="training" />
                <el-option label="异常日志" value="exception" />
                <el-option label="应用日志" value="application" />
              </el-select>
              <el-select v-model="module" class="toolbar-select" placeholder="模块筛选" clearable>
                <el-option label="训练任务" value="training" />
                <el-option label="数据集" value="dataset" />
                <el-option label="模型版本" value="model_version" />
                <el-option label="认证" value="auth" />
                <el-option label="用户" value="user" />
                <el-option label="角色" value="role" />
                <el-option label="应用异常" value="app.exception" />
              </el-select>
              <el-input v-model="logKeyword" class="toolbar-input" placeholder="搜索日志内容" clearable @keyup.enter="loadLogs" />
              <el-button :icon="Refresh" @click="loadLogs">刷新</el-button>
              <el-button :icon="Download" @click="handleExportLogs">导出日志</el-button>
            </div>

            <div class="table-wrap">
              <el-table :data="logs" stripe>
                <el-table-column prop="created_at" label="时间" width="180" />
                <el-table-column prop="level" label="级别" width="90">
                  <template #default="{ row }">
                    <el-tag :type="logLevelTagType(row.level)">{{ row.level ?? 'INFO' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="类别" width="90">
                  <template #default="{ row }">{{ logCategoryLabel(row.category) }}</template>
                </el-table-column>
                <el-table-column label="模块" width="110">
                  <template #default="{ row }">{{ logModuleLabel(row.module || row.resource) }}</template>
                </el-table-column>
                <el-table-column prop="action" label="操作" width="110">
                  <template #default="{ row }">
                    <el-tag type="success">{{ row.action }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="task_code" label="任务" width="150" show-overflow-tooltip />
                <el-table-column prop="username" label="用户" width="120" />
                <el-table-column label="内容" min-width="320" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.message || row.detail }}</template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 新增/编辑用户弹窗。新增用户默认密码为 123456。 -->
    <el-dialog v-model="userDialogVisible" :title="editingUser ? '编辑用户' : '新增用户'" width="520px">
      <el-form :model="userForm" label-position="top">
        <el-form-item label="姓名"><el-input v-model="userForm.name" /></el-form-item>
        <el-form-item label="账号"><el-input v-model="userForm.account" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="userForm.status" class="full">
            <el-option label="启用" value="启用" />
            <el-option label="禁用" value="禁用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <!-- 用户角色分配弹窗。 -->
    <el-dialog v-model="assignDialogVisible" title="分配角色" width="520px">
      <el-form label-position="top">
        <el-form-item label="选择角色">
          <el-select v-model="assignedRoleCodes" class="full" multiple>
            <el-option v-for="role in roleRows" :key="role.code" :label="role.name" :value="role.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAssignedRoles">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑角色弹窗。编辑时不允许修改角色编码。 -->
    <el-dialog v-model="roleDialogVisible" :title="editingRole ? '编辑角色' : '新增角色'" width="520px">
      <el-form :model="roleForm" label-position="top">
        <el-form-item label="角色名称"><el-input v-model="roleForm.name" /></el-form-item>
        <el-form-item label="角色编码"><el-input v-model="roleForm.code" :disabled="Boolean(editingRole)" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="roleForm.desc" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="roleForm.status" class="full">
            <el-option label="启用" value="启用" />
            <el-option label="禁用" value="禁用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Refresh } from '@element-plus/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'
import type { RoleCode } from '@/mock/auth'
import {
  createRole,
  createUser,
  deleteRole as deleteRoleApi,
  deleteUser as deleteUserApi,
  exportLogs,
  getRoleMenus,
  listLogs,
  listMenus,
  listRoles,
  listUsers,
  saveRoleMenus as saveRoleMenusApi,
  updateRole,
  updateRoleStatus,
  updateUser,
  updateUserRoles,
  updateUserStatus,
  type SystemLog,
  type SystemMenu,
  type SystemRole,
  type SystemUser,
} from '@/api/system'
import { useAuthStore } from '@/stores/auth'
import { formatBeijingDateTime } from '@/utils/time'

// 用户表格使用的前端展示结构。
interface UserRow {
  id: number
  name: string
  account: string
  status: string
  lastLogin: string
  roleCodes: string[]
  roleIds: number[]
}

// 角色表格使用的前端展示结构。
interface RoleRow {
  id: number
  code: string
  name: string
  users: number
  desc: string
  status: string
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// 当前激活 Tab 和日志筛选条件。
const activeTab = ref('')
const level = ref('')
const module = ref('')
const category = ref('')
const logKeyword = ref('')
const userKeyword = ref('')

// 弹窗显隐和当前编辑对象。
const userDialogVisible = ref(false)
const assignDialogVisible = ref(false)
const roleDialogVisible = ref(false)
const editingUser = ref<UserRow | null>(null)
const assigningUser = ref<UserRow | null>(null)
const editingRole = ref<RoleRow | null>(null)
const assignedRoleCodes = ref<string[]>([])

// 菜单管理：当前选中的角色和已勾选菜单 key。
const selectedMenuRole = ref('admin')
const checkedMenuKeys = ref<string[]>([])

// 后端数据：日志、菜单树、菜单 key 到 id 的映射。
const logs = ref<SystemLog[]>([])
const menus = ref<SystemMenu[]>([])
const menuKeyIdMap = ref<Record<string, number>>({})

// 用户和角色表格数据。
const userRows = ref<UserRow[]>([])
const roleRows = ref<RoleRow[]>([])

// 用户/角色弹窗表单。
const userForm = reactive({ name: '', account: '', status: '启用' })
const roleForm = reactive({ name: '', code: '', desc: '', status: '启用' })

// Tab 和路由保持同步，方便直接访问 /system/users 等子路径。
const tabRoutes: Record<string, string> = {
  users: '/system/users',
  roles: '/system/roles',
  menus: '/system/menus',
  logs: '/system/log',
}

// 菜单树拆成普通业务菜单和系统管理子菜单，便于勾选展示。
const businessMenuOptions = computed(() => menus.value.filter((item) => !item.children?.length))
const systemMenuOptions = computed(() => menus.value.find((item) => item.key === 'system')?.children ?? [])

// 当前用户是否有对应系统管理子模块权限。
const canUserManage = computed(() => authStore.canViewMenu('system:user'))
const canRoleManage = computed(() => authStore.canViewMenu('system:role'))
const canMenuManage = computed(() => authStore.canViewMenu('system:menu'))
const canLogView = computed(() => authStore.canViewMenu('system:log'))

// 当前用户实际可访问的 Tab，用于路由兜底选择。
const accessibleTabs = computed(() =>
  [
    { name: 'users', visible: canUserManage.value },
    { name: 'roles', visible: canRoleManage.value },
    { name: 'menus', visible: canMenuManage.value },
    { name: 'logs', visible: canLogView.value },
  ].filter((item) => item.visible),
)

const selectedMenuRoleName = computed(() => roleRows.value.find((item) => item.code === selectedMenuRole.value)?.name)

// 用户搜索在前端本地完成。
const filteredUsers = computed(() => {
  const keyword = userKeyword.value.trim().toLowerCase()
  if (!keyword) return userRows.value
  return userRows.value.filter((item) => `${item.name}${item.account}`.toLowerCase().includes(keyword))
})

// 日志级别到标签颜色的映射。
const logLevelTagType = (logLevel?: string) => {
  if (logLevel === 'CRITICAL') return 'danger'
  if (logLevel === 'ERROR') return 'danger'
  if (logLevel === 'WARN') return 'warning'
  return 'info'
}

// 日志类别后端值到中文文案的映射。
const logCategoryLabel = (value?: string) => ({
  audit: '审计',
  training: '训练',
  exception: '异常',
  application: '应用',
}[value ?? ''] ?? value ?? '-')

// 日志模块/资源后端值到中文文案的映射。
const logModuleLabel = (value?: string) => ({
  training: '训练任务',
  dataset: '数据集',
  model_version: '模型版本',
  auth: '认证',
  user: '用户',
  role: '角色',
  'app.exception': '应用异常',
}[value ?? ''] ?? value ?? '-')

// 将角色编码列表格式化为中文角色名。
const formatRoleNames = (roleCodes: string[]) =>
  roleCodes.map((roleCode) => roleRows.value.find((role) => role.code === roleCode)?.name ?? roleCode).join('、')

// 前端中文启用/禁用与后端 active/disabled 的转换。
const statusToLabel = (status: string) => (status === 'active' ? '启用' : '禁用')
const labelToStatus = (status: string) => (status === '启用' ? 'active' : 'disabled')

// 将后端用户对象映射为表格行。
const mapUser = (user: SystemUser): UserRow => ({
  id: user.id,
  name: user.real_name ?? user.username,
  account: user.username,
  status: statusToLabel(user.status),
  lastLogin: formatBeijingDateTime(user.last_login_at).slice(0, 16),
  roleCodes: user.roles.map((role) => role.name),
  roleIds: user.roles.map((role) => role.id),
})

// 将后端角色对象映射为表格行。
const mapRole = (role: SystemRole): RoleRow => ({
  id: role.id,
  code: role.name,
  name: role.name,
  users: 0,
  desc: role.description ?? '',
  status: statusToLabel(role.status),
})

// 遍历菜单树，建立 menu key 到后端 menu id 的映射，保存角色菜单时会用到。
const collectMenuIds = (items: SystemMenu[]) => {
  const result: Record<string, number> = {}
  const walk = (menu: SystemMenu) => {
    result[menu.key] = menu.id
    menu.children?.forEach(walk)
  }
  items.forEach(walk)
  return result
}

// 加载系统管理所需的用户、角色、菜单和日志数据。
const loadSystemData = async () => {
  const [usersPage, rolesPage, menuTree] = await Promise.all([
    listUsers({ page: 1, page_size: 100 }),
    listRoles({ page: 1, page_size: 100 }),
    listMenus(),
  ])

  userRows.value = usersPage.data.map(mapUser)
  roleRows.value = rolesPage.data.map(mapRole)
  menus.value = menuTree
  menuKeyIdMap.value = collectMenuIds(menuTree)
  await loadLogs()
  if (!roleRows.value.some((role) => role.code === selectedMenuRole.value)) {
    selectedMenuRole.value = roleRows.value[0]?.code ?? 'admin'
  }
  await selectMenuRole(selectedMenuRole.value)
}

// 按当前筛选条件加载系统日志。
const loadLogs = async () => {
  const logsPage = await listLogs({
    page: 1,
    page_size: 100,
    keyword: logKeyword.value,
    level: level.value,
    module: module.value,
    category: category.value,
  })
  logs.value = logsPage.data
}

// 重置用户表单。
const resetUserForm = () => {
  userForm.name = ''
  userForm.account = ''
  userForm.status = '启用'
}

// 打开新增/编辑用户弹窗。
const openUserDialog = (row?: UserRow) => {
  editingUser.value = row ?? null
  if (row) {
    userForm.name = row.name
    userForm.account = row.account
    userForm.status = row.status
  } else {
    resetUserForm()
  }
  userDialogVisible.value = true
}

// 保存用户信息。新增用户使用默认密码 123456。
const saveUser = async () => {
  if (!userForm.name || !userForm.account) {
    ElMessage.warning('请填写姓名和账号')
    return
  }

  if (editingUser.value) {
    await updateUser(editingUser.value.id, {
      username: userForm.account,
      real_name: userForm.name,
    })
    const nextStatus = labelToStatus(userForm.status)
    if (nextStatus !== labelToStatus(editingUser.value.status)) {
      await updateUserStatus(editingUser.value.id, nextStatus)
    }
  } else {
    const createdUser = await createUser({ username: userForm.account, real_name: userForm.name, password: '123456' })
    const nextStatus = labelToStatus(userForm.status)
    if (nextStatus !== 'active') {
      await updateUserStatus(createdUser.id, nextStatus)
    }
  }
  userDialogVisible.value = false
  await loadSystemData()
  ElMessage.success('用户信息已保存')
}

// 打开角色分配弹窗。
const openAssignDialog = (row: UserRow) => {
  assigningUser.value = row
  assignedRoleCodes.value = [...row.roleCodes]
  assignDialogVisible.value = true
}

// 保存用户角色分配，前端用 role code 选择，提交时转换为 role id。
const saveAssignedRoles = async () => {
  if (!assigningUser.value) return
  const roleIds = assignedRoleCodes.value
    .map((roleCode) => roleRows.value.find((role) => role.code === roleCode)?.id)
    .filter((id): id is number => typeof id === 'number')
  await updateUserRoles(assigningUser.value.id, roleIds)
  assignDialogVisible.value = false
  await loadSystemData()
  ElMessage.success('用户角色已分配')
}

// 启用/禁用用户。
const toggleUserStatus = async (row: UserRow) => {
  await updateUserStatus(row.id, row.status === '启用' ? 'disabled' : 'active')
  await loadSystemData()
}

// 删除用户。
const deleteUser = async (row: UserRow) => {
  await ElMessageBox.confirm(`确认删除用户 ${row.name}？`, '删除用户', { type: 'warning' })
  await deleteUserApi(row.id)
  await loadSystemData()
  ElMessage.success('用户已删除')
}

// 打开新增/编辑角色弹窗。
const openRoleDialog = (row?: RoleRow) => {
  editingRole.value = row ?? null
  roleForm.name = row?.name ?? ''
  roleForm.code = row?.code ?? ''
  roleForm.desc = row?.desc ?? ''
  roleForm.status = row?.status ?? '启用'
  roleDialogVisible.value = true
}

// 保存角色信息。角色菜单权限不在这里保存。
const saveRole = async () => {
  if (!roleForm.name || !roleForm.code) {
    ElMessage.warning('请填写角色名称和编码')
    return
  }

  if (editingRole.value) {
    await updateRole(editingRole.value.id, { name: roleForm.code, description: roleForm.desc, role_type: roleForm.name })
  } else {
    await createRole({ name: roleForm.code, description: roleForm.desc, role_type: roleForm.name })
  }
  roleDialogVisible.value = false
  await loadSystemData()
  ElMessage.success('角色信息已保存')
}

// 启用/禁用角色。
const toggleRoleStatus = async (row: RoleRow) => {
  await updateRoleStatus(row.id, row.status === '启用' ? 'disabled' : 'active')
  await loadSystemData()
}

// 删除角色。
const deleteRole = async (row: RoleRow) => {
  await ElMessageBox.confirm(`确认删除角色 ${row.name}？`, '删除角色', { type: 'warning' })
  await deleteRoleApi(row.id)
  await loadSystemData()
  ElMessage.success('角色已删除')
}

// 选择角色后加载该角色已拥有的菜单。
const selectMenuRole = async (roleCode: string) => {
  selectedMenuRole.value = roleCode
  const role = roleRows.value.find((item) => item.code === roleCode)
  if (!role) return
  const roleMenus = await getRoleMenus(role.id)
  checkedMenuKeys.value = roleMenus.map((menu) => menu.key)
}

// 保存角色菜单可见性，并同步更新 authStore 中的前端权限映射。
const saveMenuVisibility = async () => {
  const role = roleRows.value.find((item) => item.code === selectedMenuRole.value)
  if (!role) return
  const menuIds = checkedMenuKeys.value
    .map((menuKey) => menuKeyIdMap.value[menuKey])
    .filter((id): id is number => typeof id === 'number')
  await saveRoleMenusApi(role.id, menuIds)
  authStore.updateRoleMenus(selectedMenuRole.value as RoleCode, checkedMenuKeys.value)
  ElMessage.success(`${selectedMenuRoleName.value} 的菜单可见性已保存`)
}

// Tab 切换时同步路由地址。
const handleTabChange = (name: string | number) => {
  const tabName = String(name)
  if (tabRoutes[tabName] && route.path !== tabRoutes[tabName]) {
    router.push(tabRoutes[tabName])
  }
}

// 导出当前筛选条件下的日志 CSV。
const handleExportLogs = async () => {
  const blob = await exportLogs({
    keyword: logKeyword.value,
    level: level.value,
    module: module.value,
    category: category.value,
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `system-logs-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('日志 CSV 已开始下载')
}

// 根据路由 meta.systemTab 和当前用户权限，决定默认打开哪个 Tab。
watch(
  () => [route.meta.systemTab, accessibleTabs.value.map((item) => item.name).join(',')],
  () => {
    const requestedTab = String(route.meta.systemTab ?? '')
    const fallbackTab = accessibleTabs.value[0]?.name ?? ''
    activeTab.value = accessibleTabs.value.some((item) => item.name === requestedTab) ? requestedTab : fallbackTab
  },
  { immediate: true },
)

// 菜单管理中切换角色时，自动加载该角色菜单。
watch(
  selectedMenuRole,
  (roleCode) => {
    void selectMenuRole(roleCode)
  },
  { immediate: true },
)

// 日志筛选条件变化时自动刷新日志。
watch(
  [level, module, category],
  () => {
    if (activeTab.value === 'logs') {
      loadLogs().catch((error) => {
        ElMessage.error(error instanceof Error ? error.message : '日志加载失败')
      })
    }
  },
)

onMounted(() => {
  // 页面进入时加载系统管理基础数据。
  loadSystemData().catch((error) => {
    ElMessage.error(error instanceof Error ? error.message : '系统数据加载失败')
  })
})
</script>

<style scoped>
.system-body {
  overflow-x: hidden;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-input {
  width: min(320px, 100%);
}

.toolbar-select {
  width: 150px;
}

.logs-toolbar {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.role-tip {
  max-width: 420px;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

.full {
  width: 100%;
}

.menu-config {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 20px;
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-item {
  width: 100%;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #fff;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.role-item.active,
.role-item:hover {
  border-color: var(--primary-color);
  background: var(--primary-light);
}

.role-item strong,
.role-item span {
  display: block;
}

.role-item span {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.menu-panel {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
}

.menu-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.menu-panel-head h3 {
  margin: 0 0 6px;
  font-size: 16px;
}

.menu-panel-head p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}

.menu-tree :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.menu-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.menu-group h4,
.system-menu-title {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 13px;
}

.system-menu-title {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-secondary);
}

.menu-group :deep(.el-checkbox.is-bordered) {
  width: 100%;
  margin: 0;
}

@media (max-width: 1100px) {
  .toolbar {
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .menu-config {
    grid-template-columns: 200px minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .toolbar,
  .logs-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-input,
  .toolbar-select,
  .toolbar .el-button {
    width: 100%;
  }

  .menu-config {
    grid-template-columns: 1fr;
  }

  .role-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .menu-panel-head {
    flex-direction: column;
  }

  .menu-panel-head .el-button {
    width: 100%;
  }

  .menu-group {
    grid-template-columns: 1fr;
  }
}
</style>
