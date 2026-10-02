<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue';

defineProps<{
  title?: string;
  message: string;
}>();

const emit = defineEmits<{
  retry: [];
}>();
</script>

<template>
  <section class="error-state" role="alert">
    <el-icon aria-hidden="true"><WarningFilled /></el-icon>
    <div>
      <h2>{{ title || '加载失败' }}</h2>
      <p>{{ message }}</p>
    </div>
    <el-button type="primary" @click="emit('retry')">重新加载</el-button>
  </section>
</template>
