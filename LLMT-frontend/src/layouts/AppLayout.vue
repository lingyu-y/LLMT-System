<template>
  <!-- 业务页面的统一外壳：左侧菜单固定，右侧是顶部栏和当前路由页面。 -->
  <div class="app-shell">
    <Sidebar />
    <main class="main-content">
      <TopHeader />
      <section class="page-content">
        <!-- 子路由页面出口，对应 router/index.ts 中 AppLayout 下的 children。 -->
        <RouterView />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import Sidebar from '@/components/Sidebar.vue'
import TopHeader from '@/components/TopHeader.vue'
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--bg-color);
}

.main-content {
  min-height: 100vh;
  /* 给固定侧边栏留出横向空间，避免页面内容被 Sidebar 遮挡。 */
  margin-left: var(--sidebar-width);
}

.page-content {
  /* 73px 是顶部栏高度，保证页面主体至少铺满剩余视口。 */
  min-height: calc(100vh - 73px);
  padding: 22px 32px 36px;
}
</style>
