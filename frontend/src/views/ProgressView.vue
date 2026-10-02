<script setup lang="ts">
import { TrendCharts } from '@element-plus/icons-vue';

import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
</script>

<template>
  <section class="page-view product-introduction">
    <PageHeader title="进展" description="让每一次学习都留下可回顾的证据。" />
    <EmptyState
      :icon="TrendCharts"
      title="暂无学习数据"
      description="完成诊断和学习任务后，这里将展示知识掌握趋势与学习进展。"
    />
  </section>
</template>
