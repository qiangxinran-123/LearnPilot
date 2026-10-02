<script setup lang="ts">
import { Compass } from '@element-plus/icons-vue';

import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
</script>

<template>
  <section class="page-view product-introduction">
    <PageHeader title="学习" description="把下一步学习安排建立在真实知识状态之上。" />
    <EmptyState
      :icon="Compass"
      title="个性化学习路径"
      description="完成学习诊断后，这里将生成你的个性化学习路径。"
    />
  </section>
</template>
