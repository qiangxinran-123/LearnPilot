<script setup lang="ts">
import { Calendar, FolderOpened } from '@element-plus/icons-vue';
import type { CourseSummary } from '@/types/course';
defineProps<{ course: CourseSummary; }>();
function formatUpdatedAt(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', year: 'numeric' }).format(date);
}
</script>
<template>
  <article class="course-card">
    <div class="course-card__topline"><div class="course-card__icon" aria-hidden="true"><el-icon><FolderOpened /></el-icon></div><span v-if="course.category || course.semester" class="course-card__category">{{ course.category || course.semester }}</span></div>
    <div class="course-card__content"><h2>{{ course.name }}</h2><p v-if="course.description" class="course-card__description">{{ course.description }}</p></div>
    <div class="course-card__footer"><span v-if="typeof course.material_count === 'number'" class="course-card__meta">{{ course.material_count }} 份资料</span><span v-if="formatUpdatedAt(course.updated_at)" class="course-card__meta"><el-icon aria-hidden="true"><Calendar /></el-icon>更新于 {{ formatUpdatedAt(course.updated_at) }}</span><RouterLink :to="`/courses/${course.id}`" class="course-card__link">进入课程</RouterLink></div>
  </article>
</template>
