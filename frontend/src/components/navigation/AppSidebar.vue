<script setup lang="ts">
import { computed } from 'vue';
import { Menu } from '@element-plus/icons-vue';

import { navigationItems } from './navItems';

const props = defineProps<{
  collapsed: boolean;
  mobileOpen: boolean;
}>();

const emit = defineEmits<{
  closeMobile: [];
}>();

const sidebarClasses = computed(() => ({
  'app-sidebar--collapsed': props.collapsed,
  'app-sidebar--mobile-open': props.mobileOpen,
}));
</script>

<template>
  <aside class="app-sidebar" :class="sidebarClasses">
    <div class="app-sidebar__brand">
      <span class="brand-mark" aria-hidden="true"><Menu /></span>
      <span class="brand-name">LearnPilot</span>
    </div>

    <nav class="app-sidebar__nav" aria-label="主导航">
      <RouterLink
        v-for="item in navigationItems"
        :key="item.to"
        :to="item.to"
        class="app-sidebar__link"
        active-class="app-sidebar__link--active"
        @click="emit('closeMobile')"
      >
        <component :is="item.icon" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>
