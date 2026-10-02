<script setup lang="ts">
import { CircleCloseFilled } from '@element-plus/icons-vue';

import EmptyState from '@/components/common/EmptyState.vue';
</script>

<template>
  <section class="page-view not-found-view">
    <EmptyState
      :icon="CircleCloseFilled"
      title="页面未找到"
      description="你访问的页面不存在，或已被移动。"
      action-label="返回首页"
      action-to="/dashboard"
    />
  </section>
</template>
