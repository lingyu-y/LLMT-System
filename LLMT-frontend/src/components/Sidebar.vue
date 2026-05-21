<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo">
        <div class="logo-icon">
          <el-icon><Cpu /></el-icon>
        </div>
        <div>
          <div class="logo-text">离线大数据训练</div>
          <div class="logo-subtitle">训练与应用系统</div>
        </div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section-title">主要功能</div>
      <RouterLink v-for="item in businessMenus" :key="item.path" :to="item.path" class="nav-item">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
      </RouterLink>

      <template v-if="systemMenu">
        <div class="nav-section-title nav-gap">系统管理</div>
        <RouterLink :to="systemMenu.path" class="nav-item">
          <el-icon><component :is="systemMenu.icon" /></el-icon>
          <span>{{ systemMenu.title }}</span>
        </RouterLink>
      </template>
    </nav>

    <div class="sidebar-footer" v-if="currentUser">
      <div class="user-info">
        <div class="user-avatar">{{ userInitials }}</div>
        <div class="user-details">
          <div class="user-name">{{ currentUser.realName }}</div>
          <div class="user-role">{{ currentUser.role }}</div>
        </div>
        <el-tooltip content="退出登录" placement="top">
          <el-button class="logout-button" :icon="SwitchButton" circle text @click="handleLogout" />
        </el-tooltip>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Cpu, DataAnalysis, Document, Files, Management, Monitor, Setting, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'

import { systemMenuKeys } from '@/mock/auth'
import { useAuthStore } from '@/stores/auth'
import { filterMenusByPermission } from '@/utils/permission'

interface MenuItem {
  title: string
  path: string
  icon?: Component
  permission?: string
  children?: MenuItem[]
}

const menuItems: MenuItem[] = [
  { title: '仪表盘', path: '/dashboard', icon: Monitor, permission: 'dashboard' },
  { title: '数据处理', path: '/data-processing', icon: Files, permission: 'dataset' },
  { title: '模型训练', path: '/model-training', icon: DataAnalysis, permission: 'training' },
  { title: '模型管理', path: '/model-management', icon: Management, permission: 'model' },
  { title: '文档生成', path: '/doc-generation', icon: Document, permission: 'document' },
  {
    title: '系统管理',
    path: '/system',
    icon: Setting,
    children: [
      { title: '用户管理', path: '/system/users', permission: 'system:user' },
      { title: '角色管理', path: '/system/roles', permission: 'system:role' },
      { title: '菜单管理', path: '/system/menus', permission: 'system:menu' },
      { title: '日志管理', path: '/system/log', permission: 'system:log' },
    ],
  },
]

const router = useRouter()
const authStore = useAuthStore()
const currentUser = computed(() => authStore.user)
const userInitials = computed(() => currentUser.value?.realName.slice(0, 2).toUpperCase() ?? '用户')
const filteredMenus = computed(() => filterMenusByPermission(menuItems, authStore.visibleMenuKeys))
const businessMenus = computed(() => filteredMenus.value.filter((item) => item.path !== '/system'))
const systemMenu = computed(() =>
  authStore.hasAnyPermission(systemMenuKeys) ? filteredMenus.value.find((item) => item.path === '/system') : undefined,
)

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确认退出当前账号？', '退出登录', {
      type: 'warning',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    })
    authStore.logout()
    await router.push('/login')
  } catch {
    // User cancelled logout.
  }
}
</script>

<style scoped>
.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 100;
  display: flex;
  width: var(--sidebar-width);
  flex-direction: column;
  border-right: 1px solid var(--border-color);
  background: var(--card-bg);
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid var(--border-color);
}

.logo,
.nav-item,
.user-info {
  display: flex;
  align-items: center;
}

.logo {
  gap: 12px;
}

.logo-icon {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary-color), #3b82f6);
  color: #fff;
  font-size: 18px;
}

.logo-text {
  font-size: 16px;
  font-weight: 700;
}

.logo-subtitle {
  color: var(--text-muted);
  font-size: 11px;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  overflow-y: auto;
}

.nav-section-title {
  margin-bottom: 8px;
  padding: 0 12px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.nav-gap {
  margin-top: 24px;
}

.nav-item {
  gap: 12px;
  min-height: 46px;
  margin-bottom: 4px;
  padding: 12px 16px;
  border-radius: 8px;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 0.18s ease;
}

.nav-item:hover,
.nav-item.router-link-active {
  background: var(--primary-light);
  color: var(--primary-color);
  font-weight: 600;
}

.sidebar-footer {
  padding: 16px 12px;
  border-top: 1px solid var(--border-color);
}

.user-info {
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
}

.user-avatar {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  font-weight: 700;
}

.user-details {
  flex: 1;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
}

.user-role {
  color: var(--text-muted);
  font-size: 12px;
}

.logout-button {
  color: var(--text-secondary);
}
</style>
