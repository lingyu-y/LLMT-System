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

// 前端路由统一在这里注册。meta 中的字段会被导航守卫、侧边栏和页面标题等逻辑使用：
// public: true 表示不需要登录即可访问；menuKeys 表示进入页面需要具备的菜单权限；
// menuMode: 'any' 表示满足任意一个 menuKey 即可访问；systemTab 用于系统管理页切换默认 Tab。
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // 登录、注册页是公开页面，不放在主布局 AppLayout 下面。
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
    // 业务页面统一挂在 AppLayout 下，共用顶部栏、侧边栏和主体内容区域。
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
        // /system 是系统管理总入口，只要拥有任意系统子菜单权限即可进入。
        {
          path: 'system',
          name: 'system',
          component: SystemManagement,
          meta: { title: '系统管理', menuKeys: systemMenuKeys, menuMode: 'any' },
        },
        // 系统管理的几个子页面复用同一个组件，通过 systemTab 决定默认展示哪个 Tab。
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
    // 未匹配到的地址统一回到仪表盘，避免空白页。
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

// 全局导航守卫：先处理登录态，再处理菜单权限。
router.beforeEach((to) => {
  const authStore = useAuthStore()

  // 已登录用户再次访问登录/注册页时，直接回到首页。
  if ((to.path === '/login' || to.path === '/register') && authStore.isLoggedIn) return '/dashboard'

  // 非公开页面必须登录；redirect 用于登录成功后回到原目标页面。
  if (!to.meta.public && !authStore.isLoggedIn) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  // 页面配置了 menuKeys 时，需要校验当前用户是否拥有对应菜单权限。
  const requiredMenuKeys = to.meta.menuKeys as string[] | undefined
  if (requiredMenuKeys?.length) {
    // 默认要求拥有全部权限；menuMode 为 any 时，只需拥有其中一个权限。
    const allowed =
      to.meta.menuMode === 'any'
        ? authStore.hasAnyPermission(requiredMenuKeys)
        : requiredMenuKeys.every((menuKey) => authStore.hasPermission(menuKey))

    // 已登录但权限不足，跳转到 403 页面。
    if (!allowed) return '/403'
  }

  return true
})

export default router
