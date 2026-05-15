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
      <RouterLink v-for="item in menuItems.slice(0, 4)" :key="item.path" :to="item.path" class="nav-item">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
        <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
      </RouterLink>

      <div class="nav-section-title nav-gap">应用与服务</div>
      <RouterLink v-for="item in menuItems.slice(4)" :key="item.path" :to="item.path" class="nav-item">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
      </RouterLink>
    </nav>

    <div class="sidebar-footer">
      <div class="user-info">
        <div class="user-avatar">AD</div>
        <div class="user-details">
          <div class="user-name">Admin User</div>
          <div class="user-role">系统管理员</div>
        </div>
        <el-icon><ArrowDown /></el-icon>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  ArrowDown,
  Cpu,
  DataAnalysis,
  Document,
  Files,
  Management,
  Monitor,
  Setting,
} from '@element-plus/icons-vue'

const menuItems = [
  { title: '仪表盘', path: '/dashboard', icon: Monitor, badge: '3' },
  { title: '数据处理', path: '/data-processing', icon: Files },
  { title: '模型训练', path: '/model-training', icon: DataAnalysis },
  { title: '模型管理', path: '/model-management', icon: Management },
  { title: '文档生成', path: '/doc-generation', icon: Document },
  { title: '系统管理', path: '/system-management', icon: Setting },
]
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

.nav-badge {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--primary-color);
  color: #fff;
  font-size: 11px;
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
</style>
