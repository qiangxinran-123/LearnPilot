<script setup lang="ts">
import { onMounted } from 'vue';
import { FolderOpened, Promotion } from '@element-plus/icons-vue';

import CourseCard from '@/components/common/CourseCard.vue';
import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { useCourseStore } from '@/stores/courses';

const courseStore = useCourseStore();

onMounted(() => {
  void courseStore.loadCourses();
});
</script>

<template>
  <section class="page-view dashboard-view">
    <PageHeader
      title="今天，从最值得学习的内容开始。"
      description="建立课程后，LearnPilot 会逐步形成你的个性化学习路径。"
    />

    <LoadingBlock v-if="courseStore.isLoading" :count="2" />

    <ErrorState
      v-else-if="courseStore.hasError"
      title="课程加载失败"
      :message="courseStore.errorMessage"
      @retry="courseStore.loadCourses(true)"
    />

    <EmptyState
      v-else-if="courseStore.courses.length === 0"
      :icon="Promotion"
      title="开始你的第一门课程"
      description="添加课程后，LearnPilot 将逐步帮助你组织学习资料、建立知识结构，并在后续形成个性化学习路径。"
      action-label="前往课程"
      action-to="/courses"
    />

    <section v-else class="dashboard-view__courses" aria-labelledby="dashboard-courses-title">
      <div class="section-heading">
        <div>
          <h2 id="dashboard-courses-title">继续构建你的学习空间</h2>
          <p>你已建立 {{ courseStore.courses.length }} 门课程。</p>
        </div>
        <el-icon aria-hidden="true"><FolderOpened /></el-icon>
      </div>
      <div class="course-grid">
        <CourseCard v-for="course in courseStore.courses" :key="course.id" :course="course" />
      </div>
    </section>
  </section>
</template>
