<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { Aim, FolderOpened, Promotion, RefreshRight } from '@element-plus/icons-vue';

import CourseCard from '@/components/common/CourseCard.vue';
import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import {
  recommendationReasonLabel,
  unavailablePresentation,
} from '@/components/learning/planPresentation';
import { useLearningPlan } from '@/composables/useLearningPlan';
import { useCourseStore } from '@/stores/courses';

const router = useRouter();
const courseStore = useCourseStore();
const selectedCourseId = ref<number | null>(null);
const learningPlan = useLearningPlan();

const selectedCourse = computed(
  () => courseStore.courses.find((course) => course.id === selectedCourseId.value) ?? null,
);
const unavailable = computed(() =>
  unavailablePresentation(
    learningPlan.recommendationStatus.value,
    selectedCourseId.value,
    learningPlan.businessCode.value,
  ),
);

function openLearn(): void {
  if (!selectedCourseId.value) return;
  void router.push({ name: 'learn', query: { courseId: String(selectedCourseId.value) } });
}

watch(selectedCourseId, (courseId) => void learningPlan.load(courseId));
watch(
  () => courseStore.courses,
  (courses) => {
    if (!courses.some((course) => course.id === selectedCourseId.value)) {
      selectedCourseId.value = courses[0]?.id ?? null;
    }
  },
  { immediate: true },
);
onMounted(async () => {
  await courseStore.loadCourses();
});
</script>

<template>
  <section class="page-view dashboard-view">
    <PageHeader
      title="今天，从最值得学习的内容开始。"
      description="学习建议来自课程知识结构、已保存的掌握状态与真实诊断依据。"
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
      description="添加课程后，LearnPilot 才能基于真实知识结构与学习状态提供建议。"
      action-label="前往课程"
      action-to="/courses"
    />

    <template v-else>
      <section class="recommendation-section" aria-labelledby="dashboard-recommendation-title">
        <header class="recommendation-section__header">
          <div>
            <p class="eyebrow">NEXT STEP</p>
            <h2 id="dashboard-recommendation-title">下一步，建议学习什么？</h2>
          </div>
          <el-select
            v-model="selectedCourseId"
            class="dashboard-course-select"
            aria-label="选择推荐课程"
          >
            <el-option
              v-for="course in courseStore.courses"
              :key="course.id"
              :label="course.name"
              :value="course.id"
            />
          </el-select>
        </header>

        <LoadingBlock v-if="learningPlan.state.value === 'loading'" :count="1" />
        <ErrorState
          v-else-if="learningPlan.state.value === 'error'"
          title="学习建议加载失败"
          :message="learningPlan.errorMessage.value"
          @retry="learningPlan.load(selectedCourseId)"
        />
        <article
          v-else-if="learningPlan.state.value === 'available' && learningPlan.plan.value"
          class="recommendation-card"
        >
          <div class="recommendation-card__mark" aria-hidden="true">
            <el-icon><Aim /></el-icon>
          </div>
          <div class="recommendation-card__content">
            <p class="recommendation-card__course">{{ selectedCourse?.name }}</p>
            <h3>{{ learningPlan.targetNode.value?.name }}</h3>
            <p v-if="learningPlan.plan.value.reason_codes[0]" class="recommendation-card__reason">
              {{ recommendationReasonLabel(learningPlan.plan.value.reason_codes[0]) }}
            </p>
            <p
              v-if="learningPlan.plan.value.blocked_target_node_ids.length"
              class="recommendation-card__relation"
            >
              该知识点是
              {{ learningPlan.plan.value.blocked_target_node_ids.length }} 个后续目标的前置基础。
            </p>
            <div class="recommendation-card__meta">
              <span>{{ learningPlan.plan.value.tasks.length }} 个学习任务</span>
              <span v-if="learningPlan.estimatedMinutes.value"
                >预计 {{ learningPlan.estimatedMinutes.value }} 分钟</span
              >
            </div>
          </div>
          <el-button type="primary" @click="openLearn">查看学习计划</el-button>
        </article>
        <article
          v-else-if="learningPlan.state.value === 'stale'"
          class="plan-notice plan-notice--stale"
        >
          <div>
            <h3>学习计划需要更新</h3>
            <p>你的学习状态或课程知识结构可能已经变化，建议重新生成当前学习计划。</p>
            <p v-if="learningPlan.regenerationError.value" class="plan-notice__error" role="alert">
              {{ learningPlan.regenerationError.value }}
            </p>
          </div>
          <el-button
            type="primary"
            :loading="learningPlan.isGenerating.value"
            :disabled="learningPlan.isGenerating.value"
            @click="learningPlan.regenerate"
          >
            <el-icon><RefreshRight /></el-icon>重新生成计划
          </el-button>
        </article>
        <article v-else class="plan-notice">
          <div>
            <h3>{{ unavailable.title }}</h3>
            <p>{{ unavailable.description }}</p>
          </div>
          <el-button v-if="unavailable.actionTo" plain @click="router.push(unavailable.actionTo)">
            {{ unavailable.actionLabel }}
          </el-button>
        </article>
      </section>

      <section class="dashboard-view__courses" aria-labelledby="dashboard-courses-title">
        <div class="section-heading">
          <div>
            <h2 id="dashboard-courses-title">你的课程空间</h2>
            <p>你已建立 {{ courseStore.courses.length }} 门课程。</p>
          </div>
          <el-icon aria-hidden="true"><FolderOpened /></el-icon>
        </div>
        <div class="course-grid">
          <CourseCard v-for="course in courseStore.courses" :key="course.id" :course="course" />
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.recommendation-section {
  margin-bottom: 36px;
}
.recommendation-section__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
}
.recommendation-section__header h2,
.section-heading h2 {
  margin-bottom: 4px;
  color: var(--lp-ink);
  font-size: 21px;
}
.eyebrow {
  margin-bottom: 5px;
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.14em;
}
.dashboard-course-select {
  width: min(280px, 100%);
}
.recommendation-card,
.plan-notice {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 24px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}
.recommendation-card__mark {
  display: grid;
  width: 46px;
  height: 46px;
  flex: 0 0 46px;
  place-items: center;
  border-radius: 12px;
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
  font-size: 23px;
}
.recommendation-card__content,
.plan-notice > div {
  flex: 1;
  min-width: 0;
}
.recommendation-card__course {
  margin-bottom: 3px;
  color: var(--lp-text-tertiary);
  font-size: 12px;
  font-weight: 650;
}
.recommendation-card h3,
.plan-notice h3 {
  margin-bottom: 6px;
  color: var(--lp-ink);
  font-size: 19px;
}
.recommendation-card__reason,
.recommendation-card__relation,
.plan-notice p {
  margin-bottom: 5px;
  color: var(--lp-text-secondary);
}
.recommendation-card__meta {
  display: flex;
  gap: 8px 18px;
  flex-wrap: wrap;
  margin-top: 14px;
  color: var(--lp-primary-hover);
  font-size: 13px;
  font-weight: 600;
}
.plan-notice--stale {
  border-color: #e6d5ad;
  background: #fffdf7;
}
.plan-notice__error {
  color: var(--lp-danger) !important;
}
.dashboard-view__courses {
  margin-top: 34px;
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-heading p {
  margin: 0;
  color: var(--lp-text-secondary);
}
.section-heading .el-icon {
  color: var(--lp-text-tertiary);
  font-size: 22px;
}
@media (max-width: 760px) {
  .recommendation-section__header {
    align-items: stretch;
    flex-direction: column;
  }
  .dashboard-course-select {
    width: 100%;
  }
  .recommendation-card,
  .plan-notice {
    align-items: stretch;
    flex-direction: column;
  }
  .recommendation-card__mark {
    display: none;
  }
}
</style>
