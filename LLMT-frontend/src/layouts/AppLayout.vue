<template>
  <div class="app-shell">
    <Sidebar />
    <main class="main-content">
      <TopHeader />
      <section class="page-content">
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
  margin-left: var(--sidebar-width);
}

.page-content {
  min-height: calc(100vh - 73px);
  padding: 22px 32px 36px;
}
</style>
