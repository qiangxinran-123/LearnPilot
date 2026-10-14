<script setup lang="ts">
import type { Component } from 'vue';
defineProps<{
  icon: Component;
  title: string;
  description: string;
  actionLabel?: string;
  actionTo?: string;
}>();
</script>
<template>
  <section class="empty-state" :aria-label="title">
    <div class="empty-state__icon" aria-hidden="true">
      <el-icon :size="40"><component :is="icon" /></el-icon>
    </div>
    <h2 class="empty-state__title">{{ title }}</h2>
    <p class="empty-state__description">{{ description }}</p>
    <slot name="action"
      ><RouterLink v-if="actionLabel && actionTo" :to="actionTo" custom v-slot="{ navigate }"
        ><el-button type="primary" @click="navigate">{{ actionLabel }}</el-button></RouterLink
      ></slot
    >
  </section>
</template>
