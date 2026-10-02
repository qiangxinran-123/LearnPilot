<script setup lang="ts">
import { computed } from 'vue';
import { Menu, UserFilled } from '@element-plus/icons-vue';
import { useRoute } from 'vue-router';

const emit = defineEmits<{
  toggleNavigation: [];
}>();

const route = useRoute();
const pageTitle = computed(() => route.meta.title);
</script>

<template>
  <header class="app-header">
    <div class="app-header__leading">
      <el-button
        class="app-header__menu-button"
        text
        circle
        aria-label="打开导航"
        @click="emit('toggleNavigation')"
      >
        <el-icon><Menu /></el-icon>
      </el-button>
      <p class="app-header__title">{{ pageTitle }}</p>
    </div>

    <div class="app-header__user" aria-label="当前演示用户">
      <el-icon aria-hidden="true"><UserFilled /></el-icon>
      <span>Demo User</span>
    </div>
  </header>
</template>
