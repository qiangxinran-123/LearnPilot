<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';

import AppHeader from '@/components/navigation/AppHeader.vue';
import AppSidebar from '@/components/navigation/AppSidebar.vue';
import { useAppStore } from '@/stores/app';

const appStore = useAppStore();
const mobileOpen = ref(false);

function updateSidebarForViewport(): void {
  if (window.innerWidth < 768) {
    appStore.setSidebarCollapsed(true);
    mobileOpen.value = false;
    return;
  }

  if (window.innerWidth < 1024) {
    appStore.setSidebarCollapsed(true);
    return;
  }

  appStore.setSidebarCollapsed(false);
}

function toggleNavigation(): void {
  if (window.innerWidth < 768) {
    mobileOpen.value = !mobileOpen.value;
    return;
  }

  appStore.toggleSidebar();
}

onMounted(() => {
  updateSidebarForViewport();
  window.addEventListener('resize', updateSidebarForViewport);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateSidebarForViewport);
});
</script>

<template>
  <div class="app-layout">
    <AppSidebar
      :collapsed="appStore.sidebarCollapsed"
      :mobile-open="mobileOpen"
      @close-mobile="mobileOpen = false"
    />
    <div class="app-layout__content">
      <AppHeader @toggle-navigation="toggleNavigation" />
      <main class="app-layout__main">
        <RouterView />
      </main>
    </div>
  </div>
</template>
