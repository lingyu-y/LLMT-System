import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { systemMenuKeys } from '@/mock/auth'
import { useAuthStore } from '@/stores/auth'
import Dashboard from '@/views/Dashboard.vue'
import DataProcessing from '@/views/DataProcessing.vue'
import DocGeneration from '@/views/DocGeneration.vue'
import Forbidden from '@/views/Forbidden.vue'
import Login from '@/views/Login.vue'
import ModelManagement from '@/views/ModelManagement.vue'
import FederatedLearning from '@/views/FederatedLearning.vue'
import ModelTraining from '@/views/ModelTraining.vue'
import MyLogs from '@/views/MyLogs.vue'
import Register from '@/views/Register.vue'
import SystemManagement from '@/views/SystemManagement.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: Login,
      meta: { public: true, title: '登录' },
    },
    {
      path: '/register',
      name: 'register',
      component: Register,
      meta: { public: true, title: '注册' },
    },
    {
      path: '/',
      component: AppLayout,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'dashboard',
          component: Dashboard,
          meta: { title: '仪表盘', menuKeys: ['dashboard'] },
        },
        {
          path: 'data-processing',
          name: 'data-processing',
          component: DataProcessing,
          meta: { title: '数据处理', menuKeys: ['dataset'] },
        },
        {
          path: 'model-training',
          name: 'model-training',
          component: ModelTraining,
          meta: { title: '模型训练', menuKeys: ['training'] },
        },
        {
          path: 'federated-learning',
          name: 'federated-learning',
          component: FederatedLearning,
          meta: { title: '联邦学习', menuKeys: ['training'] },
        },
        {
          path: 'model-management',
          name: 'model-management',
          component: ModelManagement,
          meta: { title: '模型管理', menuKeys: ['model'] },
        },
        {
          path: 'doc-generation',
          name: 'doc-generation',
          component: DocGeneration,
          meta: { title: '文档生成', menuKeys: ['document'] },
        },
        {
          path: 'system',
          name: 'system',
          component: SystemManagement,
          meta: { title: '系统管理', menuKeys: systemMenuKeys, menuMode: 'any' },
        },
        {
          path: 'system/users',
          name: 'system-users',
          component: SystemManagement,
          meta: { title: '用户管理', systemTab: 'users', menuKeys: ['system:user'] },
        },
        {
          path: 'system/roles',
          name: 'system-roles',
          component: SystemManagement,
          meta: { title: '角色管理', systemTab: 'roles', menuKeys: ['system:role'] },
        },
        {
          path: 'system/menus',
          name: 'system-menus',
          component: SystemManagement,
          meta: { title: '菜单管理', systemTab: 'menus', menuKeys: ['system:menu'] },
        },
        {
          path: 'system/log',
          name: 'system-log',
          component: SystemManagement,
          meta: { title: '日志管理', systemTab: 'logs', menuKeys: ['system:log'] },
        },
        {
          path: 'my-logs',
          name: 'my-logs',
          component: MyLogs,
          meta: { title: '我的操作日志' },
        },
        {
          path: '403',
          name: 'forbidden',
          component: Forbidden,
          meta: { title: '无权访问' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach((to) => {
  const authStore = useAuthStore()

  if ((to.path === '/login' || to.path === '/register') && authStore.isLoggedIn) return '/dashboard'

  if (!to.meta.public && !authStore.isLoggedIn) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  const requiredMenuKeys = to.meta.menuKeys as string[] | undefined
  if (requiredMenuKeys?.length) {
    const allowed =
      to.meta.menuMode === 'any'
        ? authStore.hasAnyPermission(requiredMenuKeys)
        : requiredMenuKeys.every((menuKey) => authStore.hasPermission(menuKey))

    if (!allowed) return '/403'
  }

  return true
})

export default router
