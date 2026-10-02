<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Collection, Plus } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import CourseCard from '@/components/common/CourseCard.vue';
import CourseFormDialog from '@/components/common/CourseFormDialog.vue';
import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { createCourse } from '@/services/courses';
import { normalizeApiError } from '@/services/http';
import { useCourseStore } from '@/stores/courses';
import type { CourseInput } from '@/types/course';

const courseStore = useCourseStore();
const isCreateDialogOpen = ref(false);
const isSubmitting = ref(false);

onMounted(() => {
  void courseStore.loadCourses();
});

async function createNewCourse(payload: CourseInput): Promise<void> {
  isSubmitting.value = true;
  try {
    const course = await createCourse(payload);
    await courseStore.loadCourses(true);
    isCreateDialogOpen.value = false;
    ElMessage.success(`已创建课程「${course.name}」`);
  } catch (error: unknown) {
    ElMessage.error(normalizeApiError(error).message);
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <section class="page-view">
    <PageHeader title="课程" description="建立课程空间，集中管理真实的学习资料。">
      <template #actions>
        <el-button type="primary" @click="isCreateDialogOpen = true">
          <el-icon><Plus /></el-icon>
          创建课程
        </el-button>
      </template>
    </PageHeader>

    <LoadingBlock v-if="courseStore.isLoading" />
    <ErrorState
      v-else-if="courseStore.hasError"
      title="课程加载失败"
      :message="courseStore.errorMessage"
      @retry="courseStore.loadCourses(true)"
    />
    <EmptyState
      v-else-if="courseStore.courses.length === 0"
      :icon="Collection"
      title="开始你的第一门课程"
      description="建立课程后，即可上传讲义、教材或笔记，逐步整理你的学习内容。"
    >
      <template #action>
        <el-button type="primary" @click="isCreateDialogOpen = true">创建课程</el-button>
      </template>
    </EmptyState>
    <section v-else class="course-grid" aria-label="课程列表">
      <CourseCard v-for="course in courseStore.courses" :key="course.id" :course="course" />
    </section>

    <CourseFormDialog v-model="isCreateDialogOpen" :submitting="isSubmitting" @submit="createNewCourse" />
  </section>
</template>
