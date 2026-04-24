import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import Dashboard from '@/views/Dashboard.vue'
import DataProcessing from '@/views/DataProcessing.vue'
import ModelTraining from '@/views/ModelTraining.vue'
import ModelManagement from '@/views/ModelManagement.vue'
import DocGeneration from '@/views/DocGeneration.vue'
import SystemManagement from '@/views/SystemManagement.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: AppLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'dashboard', component: Dashboard, meta: { title: '仪表盘' } },
        {
          path: 'data-processing',
          name: 'data-processing',
          component: DataProcessing,
          meta: { title: '数据处理' },
        },
        {
          path: 'model-training',
          name: 'model-training',
          component: ModelTraining,
          meta: { title: '模型训练' },
        },
        {
          path: 'model-management',
          name: 'model-management',
          component: ModelManagement,
          meta: { title: '模型管理' },
        },
        {
          path: 'doc-generation',
          name: 'doc-generation',
          component: DocGeneration,
          meta: { title: '文档生成' },
        },
        {
          path: 'system-management',
          name: 'system-management',
          component: SystemManagement,
          meta: { title: '系统管理' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

export default router
