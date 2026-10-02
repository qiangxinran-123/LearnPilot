<script setup lang="ts">
import { DataAnalysis } from '@element-plus/icons-vue';

import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
</script>

<template>
  <section class="page-view product-introduction">
    <PageHeader title="学习诊断" description="从课程结构开始，逐步理解你的知识状态。" />
    <EmptyState
      :icon="DataAnalysis"
      title="学习诊断"
      description="LearnPilot 将通过课程知识结构和学习表现，识别你的真实知识薄弱点。"
    />
    <ol class="future-steps" aria-label="未来诊断流程">
      <li>课程结构</li>
      <li>诊断测评</li>
      <li>知识薄弱点</li>
    </ol>
  </section>
</template>
