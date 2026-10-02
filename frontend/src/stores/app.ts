import { ref } from 'vue';
import { defineStore } from 'pinia';

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false);

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  function setSidebarCollapsed(collapsed: boolean): void {
    sidebarCollapsed.value = collapsed;
  }

  return {
    sidebarCollapsed,
    toggleSidebar,
    setSidebarCollapsed,
  };
});
