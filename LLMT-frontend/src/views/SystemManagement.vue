<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">系统管理</h1>
      <p class="page-description">日志管理、菜单管理、角色管理和用户管理</p>
    </div>

    <div class="card">
      <div class="card-body">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="用户管理" name="users">
            <div class="tab-toolbar"><el-button type="primary" :icon="Plus" @click="ElMessage.success('添加用户弹窗待接入')">添加用户</el-button></div>
            <el-table :data="users" stripe>
              <el-table-column prop="name" label="姓名" />
              <el-table-column prop="account" label="账号" />
              <el-table-column prop="role" label="角色" />
              <el-table-column prop="department" label="部门" />
              <el-table-column prop="status" label="状态"><template #default="{ row }"><StatusBadge :label="row.status" type="success" /></template></el-table-column>
              <el-table-column prop="lastLogin" label="最近登录" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="角色管理" name="roles">
            <div class="grid-2">
              <el-table :data="roles" stripe>
                <el-table-column prop="name" label="角色名称" />
                <el-table-column prop="users" label="用户数" />
                <el-table-column prop="desc" label="说明" />
              </el-table>
              <div class="permission-panel">
                <h3>权限配置 - 数据科学家</h3>
                <el-table :data="permissionRows" border>
                  <el-table-column prop="module" label="模块" />
                  <el-table-column label="查看"><template #default><el-checkbox model-value /></template></el-table-column>
                  <el-table-column label="编辑"><template #default><el-checkbox /></template></el-table-column>
                  <el-table-column label="删除"><template #default><el-checkbox /></template></el-table-column>
                </el-table>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="菜单管理" name="menus">
            <div class="menu-layout">
              <el-tree :data="menus" default-expand-all />
              <el-table :data="menuRows" stripe>
                <el-table-column prop="name" label="菜单名称" />
                <el-table-column prop="path" label="路由路径" />
                <el-table-column prop="sort" label="排序" />
                <el-table-column prop="status" label="状态" />
              </el-table>
            </div>
          </el-tab-pane>

          <el-tab-pane label="日志管理" name="logs">
            <div class="tab-toolbar logs-toolbar">
              <el-select v-model="level" placeholder="级别筛选" clearable>
                <el-option label="INFO" value="INFO" />
                <el-option label="WARN" value="WARN" />
                <el-option label="ERROR" value="ERROR" />
              </el-select>
              <el-select v-model="module" placeholder="模块筛选" clearable>
                <el-option label="训练模块" value="训练模块" />
                <el-option label="数据处理" value="数据处理" />
                <el-option label="模型管理" value="模型管理" />
                <el-option label="系统" value="系统" />
              </el-select>
              <el-button :icon="Download" @click="ElMessage.success('日志导出任务已创建')">导出日志</el-button>
            </div>
            <el-table :data="filteredLogs" stripe>
              <el-table-column prop="time" label="时间" width="180" />
              <el-table-column prop="level" label="级别" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.level === 'ERROR' ? 'danger' : row.level === 'WARN' ? 'warning' : 'success'">{{ row.level }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="module" label="模块" width="120" />
              <el-table-column prop="user" label="用户" width="100" />
              <el-table-column prop="content" label="内容" />
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Plus } from '@element-plus/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'
import { logs } from '@/mock/logs'
import { menus, roles, users } from '@/mock/users'

const activeTab = ref('users')
const level = ref('')
const module = ref('')
const permissionRows = [
  { module: '数据处理' },
  { module: '模型训练' },
  { module: '模型管理' },
  { module: '系统管理' },
]
const menuRows = [
  { name: '仪表盘', path: '/dashboard', sort: 1, status: '启用' },
  { name: '数据处理', path: '/data-processing', sort: 2, status: '启用' },
  { name: '模型训练', path: '/model-training', sort: 3, status: '启用' },
  { name: '模型管理', path: '/model-management', sort: 4, status: '启用' },
  { name: '文档生成', path: '/doc-generation', sort: 5, status: '启用' },
  { name: '系统管理', path: '/system-management', sort: 6, status: '启用' },
]

const filteredLogs = computed(() => logs.filter((item) => (!level.value || item.level === level.value) && (!module.value || item.module === module.value)))
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.logs-toolbar {
  justify-content: flex-start;
}

.logs-toolbar .el-select {
  width: 150px;
}

.permission-panel {
  padding: 18px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
}

.permission-panel h3 {
  margin: 0 0 14px;
  font-size: 16px;
}

.menu-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 20px;
}
</style>
