<script setup lang="ts">
withDefaults(
  defineProps<{
    count?: number;
  }>(),
  {
    count: 3,
  },
);
</script>

<template>
  <div class="loading-block" aria-label="正在加载">
    <el-skeleton v-for="item in count" :key="item" animated>
      <template #template>
        <div class="loading-block__card">
          <el-skeleton-item variant="circle" class="loading-block__icon" />
          <div class="loading-block__lines">
            <el-skeleton-item variant="h3" class="loading-block__title" />
            <el-skeleton-item variant="text" />
            <el-skeleton-item variant="text" class="loading-block__short-line" />
          </div>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>
