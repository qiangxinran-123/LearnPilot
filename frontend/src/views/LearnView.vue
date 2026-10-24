<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Collection, Connection, Guide, RefreshRight } from '@element-plus/icons-vue';

import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import {
  learningTaskTypeLabel,
  planLevelPresentation,
  recommendationReasonLabel,
  unavailablePresentation,
} from '@/components/learning/planPresentation';
import { useLearningPlan } from '@/composables/useLearningPlan';
import { useCourseStore } from '@/stores/courses';

const route = useRoute();
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
const levelPresentation = computed(() => planLevelPresentation(learningPlan.planLevel.value));
const prerequisiteItems = computed(
  () =>
    learningPlan.plan.value?.prerequisite_evidence.filter(
      (item) => item.target_node_id === learningPlan.plan.value?.target_node_id,
    ) ?? [],
);

function queryCourseId(): number | null {
  const raw = Array.isArray(route.query.courseId) ? route.query.courseId[0] : route.query.courseId;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}
function knowledgeName(nodeId: number): string {
  return learningPlan.nodes.value.get(nodeId)?.name ?? `知识点 #${nodeId}`;
}
function openKnowledgeMap(): void {
  if (!selectedCourseId.value || !learningPlan.plan.value) return;
  void router.push({
    name: 'course-detail',
    params: { courseId: selectedCourseId.value },
    query: {
      tab: 'knowledge-structure',
      nodeId: String(learningPlan.plan.value.target_node_id),
    },
  });
}
function openDiagnosis(): void {
  if (!selectedCourseId.value) return;
  void router.push({ name: 'diagnose', query: { courseId: String(selectedCourseId.value) } });
}

watch(selectedCourseId, (courseId) => {
  void learningPlan.load(courseId);
  if (courseId && String(route.query.courseId ?? '') !== String(courseId)) {
    void router.replace({ name: 'learn', query: { courseId: String(courseId) } });
  }
});
watch(
  () => courseStore.courses,
  (courses) => {
    if (courses.some((course) => course.id === selectedCourseId.value)) return;
    const requested = queryCourseId();
    selectedCourseId.value = courses.some((course) => course.id === requested)
      ? requested
      : (courses[0]?.id ?? null);
  },
  { immediate: true },
);
onMounted(async () => {
  await courseStore.loadCourses();
});
</script>

<template>
  <section class="page-view learn-page">
    <PageHeader
      title="学习计划"
      description="把下一步学习安排建立在真实知识状态与课程结构之上。"
    />
    <section class="course-context" aria-labelledby="current-course-title">
      <div class="course-context__copy">
        <p id="current-course-title">当前学习课程</p>
        <strong>{{ selectedCourse?.name ?? '请选择课程' }}</strong>
        <span>切换课程后，仅加载该课程的学习状态，不会自动生成新计划。</span>
      </div>
      <el-select
        v-if="courseStore.courses.length"
        v-model="selectedCourseId"
        class="learn-course-select"
        aria-label="选择学习计划课程"
      >
        <el-option
          v-for="course in courseStore.courses"
          :key="course.id"
          :label="course.name"
          :value="course.id"
        />
      </el-select>
    </section>

    <LoadingBlock
      v-if="courseStore.isLoading || learningPlan.state.value === 'loading'"
      :count="2"
    />
    <ErrorState
      v-else-if="courseStore.hasError"
      title="课程加载失败"
      :message="courseStore.errorMessage"
      @retry="courseStore.loadCourses(true)"
    />
    <EmptyState
      v-else-if="courseStore.courses.length === 0"
      :icon="Collection"
      title="还没有可制定计划的课程"
      description="先创建课程并建立知识结构，再回来查看学习计划。"
      action-label="前往课程"
      action-to="/courses"
    />
    <ErrorState
      v-else-if="learningPlan.state.value === 'error'"
      title="学习计划加载失败"
      :message="learningPlan.errorMessage.value"
      @retry="learningPlan.load(selectedCourseId)"
    />

    <section
      v-else-if="learningPlan.state.value === 'stale'"
      class="stale-panel"
      aria-labelledby="stale-title"
    >
      <div class="stale-panel__icon" aria-hidden="true">
        <el-icon><RefreshRight /></el-icon>
      </div>
      <div>
        <p class="eyebrow">PLAN STATUS</p>
        <h2 id="stale-title">学习计划需要更新</h2>
        <p>你的学习状态或课程知识结构可能已经变化，建议重新生成当前学习计划。</p>
        <p v-if="learningPlan.regenerationError.value" class="stale-panel__error" role="alert">
          {{ learningPlan.regenerationError.value }}
        </p>
      </div>
      <el-button
        type="primary"
        size="large"
        :loading="learningPlan.isGenerating.value"
        :disabled="learningPlan.isGenerating.value"
        @click="learningPlan.regenerate"
        >重新生成计划</el-button
      >
    </section>

    <section
      v-else-if="learningPlan.state.value === 'unavailable' && levelPresentation"
      class="plan-entry"
      aria-labelledby="plan-entry-title"
    >
      <div>
        <p class="plan-entry__course">{{ selectedCourse?.name }}</p>
        <h2 id="plan-entry-title">{{ levelPresentation.title }}</h2>
        <p>{{ levelPresentation.description }}</p>
        <p v-if="learningPlan.regenerationError.value" class="plan-entry__error" role="alert">
          {{ learningPlan.regenerationError.value }}
        </p>
      </div>
      <div class="plan-entry__actions">
        <el-button
          type="primary"
          size="large"
          :loading="learningPlan.isGenerating.value"
          :disabled="learningPlan.isGenerating.value"
          @click="learningPlan.regenerate"
        >
          {{ levelPresentation.generateLabel }}
        </el-button>
        <el-button
          v-if="learningPlan.planLevel.value !== 'personalized'"
          plain
          :disabled="learningPlan.isGenerating.value"
          @click="openDiagnosis"
        >
          前往诊断
        </el-button>
      </div>
    </section>

    <EmptyState
      v-else-if="learningPlan.state.value === 'unavailable' || learningPlan.state.value === 'idle'"
      :icon="Guide"
      :title="unavailable.title"
      :description="unavailable.description"
      :action-label="unavailable.actionLabel"
      :action-to="unavailable.actionTo"
    />

    <template v-else-if="learningPlan.state.value === 'available' && learningPlan.plan.value">
      <section v-if="levelPresentation" class="plan-level" aria-labelledby="plan-level-title">
        <div>
          <p>当前学习计划状态</p>
          <h2 id="plan-level-title">{{ levelPresentation.title }}</h2>
        </div>
        <span>{{ levelPresentation.description }}</span>
      </section>
      <section class="learning-target" aria-labelledby="learning-target-title">
        <div class="learning-target__main">
          <p class="eyebrow">CURRENT TARGET · {{ selectedCourse?.name }}</p>
          <h2 id="learning-target-title">{{ learningPlan.targetNode.value?.name }}</h2>
          <p v-if="learningPlan.targetNode.value?.description" class="learning-target__description">
            {{ learningPlan.targetNode.value.description }}
          </p>
          <div class="learning-target__meta">
            <span>计划状态：当前有效</span>
            <span>{{ learningPlan.plan.value.tasks.length }} 个任务</span>
            <span v-if="learningPlan.estimatedMinutes.value"
              >预计 {{ learningPlan.estimatedMinutes.value }} 分钟</span
            >
          </div>
        </div>
        <el-button plain @click="openKnowledgeMap">
          <el-icon><Connection /></el-icon>在知识地图中定位
        </el-button>
      </section>

      <div class="plan-context-grid">
        <section class="context-card" aria-labelledby="recommendation-reasons-title">
          <p class="eyebrow">WHY THIS TARGET</p>
          <h2 id="recommendation-reasons-title">为什么推荐这里</h2>
          <ul class="reason-list">
            <li v-for="code in learningPlan.plan.value.reason_codes" :key="code">
              {{ recommendationReasonLabel(code) }}
            </li>
          </ul>
        </section>
        <section class="context-card" aria-labelledby="prerequisite-title">
          <p class="eyebrow">PREREQUISITES</p>
          <h2 id="prerequisite-title">前置知识依据</h2>
          <ul v-if="prerequisiteItems.length" class="prerequisite-list">
            <li
              v-for="item in prerequisiteItems"
              :key="`${item.source_node_id}-${item.target_node_id}`"
            >
              <strong>{{ knowledgeName(item.source_node_id) }}</strong>
              <span>{{ item.status === 'satisfied' ? '已满足' : '需要先巩固' }}</span>
            </li>
          </ul>
          <p v-else class="context-card__empty">当前目标没有需要展示的直接前置知识。</p>
        </section>
      </div>

      <section class="task-section" aria-labelledby="learning-tasks-title">
        <header class="task-section__header">
          <div>
            <p class="eyebrow">ORDERED PLAN</p>
            <h2 id="learning-tasks-title">学习任务</h2>
          </div>
          <p>以下为计划内容，不代表任务已经执行或完成。</p>
        </header>
        <ol class="task-list">
          <li v-for="task in learningPlan.plan.value.tasks" :key="task.task_id" class="task-card">
            <span class="task-card__index" aria-hidden="true">{{ task.order_index + 1 }}</span>
            <div class="task-card__content">
              <div class="task-card__heading">
                <div>
                  <p>{{ learningTaskTypeLabel(task.task_type) }}</p>
                  <h3>{{ task.title }}</h3>
                </div>
                <span v-if="task.estimated_minutes"
                  >建议用时 {{ task.estimated_minutes }} 分钟</span
                >
              </div>
              <p>{{ task.description }}</p>
              <small>关联知识点：{{ knowledgeName(task.knowledge_node_id) }}</small>
            </div>
          </li>
        </ol>
      </section>
    </template>
  </section>
</template>

<style scoped>
.course-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
  padding: 18px 20px;
  border: 1px solid var(--lp-border);
  border-left: 4px solid var(--lp-primary);
  border-radius: var(--lp-radius-md);
  background: var(--lp-surface);
}
.course-context__copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}
.course-context__copy p,
.plan-level p {
  margin: 0;
  color: var(--lp-text-secondary);
  font-size: 12px;
  font-weight: 650;
}
.course-context__copy strong {
  overflow-wrap: anywhere;
  color: var(--lp-ink);
  font-size: 18px;
}
.course-context__copy span {
  color: var(--lp-text-tertiary);
  font-size: 12px;
}
.learn-course-select {
  width: min(340px, 100%);
  flex: 0 1 340px;
}
.plan-level {
  display: grid;
  grid-template-columns: minmax(190px, 0.45fr) minmax(0, 1fr);
  align-items: center;
  gap: 24px;
  margin-bottom: 14px;
  padding: 18px 22px;
  border-radius: var(--lp-radius-md);
  color: var(--lp-text-secondary);
  background: var(--lp-primary-soft);
}
.plan-level h2 {
  margin: 3px 0 0;
  color: var(--lp-ink);
  font-size: 20px;
}
.plan-level > span {
  line-height: 1.7;
}
.plan-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 28px;
  padding: 28px;
  border: 1px solid #cadcf2;
  border-radius: var(--lp-radius-lg);
  background: linear-gradient(135deg, #f8fbff, #fff);
}
.plan-entry__course {
  margin: 0 0 4px;
  color: var(--lp-primary);
  font-size: 12px;
  font-weight: 700;
}
.plan-entry h2 {
  margin-bottom: 8px;
  color: var(--lp-ink);
}
.plan-entry p {
  max-width: 680px;
  color: var(--lp-text-secondary);
}
.plan-entry__error {
  margin-top: 8px;
  color: var(--lp-danger) !important;
}
.plan-entry__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
}
.eyebrow {
  margin-bottom: 6px;
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.14em;
}
.learning-target {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 30px;
  border: 1px solid #cadcf2;
  border-radius: var(--lp-radius-lg);
  background: linear-gradient(135deg, #f8fbff, #fff);
  box-shadow: var(--lp-shadow-sm);
}
.learning-target__main {
  min-width: 0;
}
.learning-target h2 {
  margin-bottom: 8px;
  color: var(--lp-ink);
  font-size: 26px;
}
.learning-target__description {
  max-width: 760px;
  color: var(--lp-text-secondary);
}
.learning-target__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 18px;
  color: var(--lp-primary-hover);
  font-size: 13px;
  font-weight: 620;
}
.plan-context-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 20px;
}
.context-card {
  padding: 24px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
}
.context-card h2,
.task-section h2 {
  margin-bottom: 12px;
  color: var(--lp-ink);
  font-size: 19px;
}
.reason-list {
  display: grid;
  gap: 9px;
  margin: 0;
  padding-left: 19px;
  color: var(--lp-text-secondary);
}
.reason-list li::marker {
  color: var(--lp-primary);
}
.prerequisite-list {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.prerequisite-list li {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 12px;
  border-radius: var(--lp-radius-sm);
  background: var(--lp-surface-subtle);
}
.prerequisite-list span {
  color: var(--lp-text-secondary);
  font-size: 12px;
}
.context-card__empty {
  margin: 0;
  color: var(--lp-text-secondary);
}
.task-section {
  margin-top: 30px;
}
.task-section__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 14px;
}
.task-section__header h2 {
  margin-bottom: 0;
}
.task-section__header > p {
  margin: 0;
  color: var(--lp-text-secondary);
  font-size: 12px;
}
.task-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.task-card {
  display: flex;
  gap: 18px;
  padding: 20px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
  background: var(--lp-surface);
}
.task-card__index {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  place-items: center;
  border: 1px solid #bed3ec;
  border-radius: 50%;
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
  font-weight: 720;
}
.task-card__content {
  flex: 1;
  min-width: 0;
}
.task-card__heading {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 20px;
}
.task-card__heading p {
  margin-bottom: 2px;
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 700;
}
.task-card h3 {
  margin-bottom: 8px;
  color: var(--lp-ink);
  font-size: 16px;
}
.task-card__heading > span {
  white-space: nowrap;
  color: var(--lp-text-secondary);
  font-size: 12px;
}
.task-card__content > p {
  margin-bottom: 9px;
  color: var(--lp-text-secondary);
}
.task-card small {
  color: var(--lp-text-tertiary);
}
.stale-panel {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 22px;
  padding: 28px;
  border: 1px solid #e6d5ad;
  border-radius: var(--lp-radius-lg);
  background: #fffdf7;
}
.stale-panel__icon {
  display: grid;
  width: 46px;
  height: 46px;
  place-items: center;
  border-radius: 50%;
  color: #866416;
  background: #f8edcf;
  font-size: 22px;
}
.stale-panel h2 {
  margin-bottom: 6px;
  color: var(--lp-ink);
}
.stale-panel p {
  margin-bottom: 0;
  color: var(--lp-text-secondary);
}
.stale-panel__error {
  margin-top: 8px !important;
  color: var(--lp-danger) !important;
}
@media (max-width: 900px) {
  .plan-context-grid {
    grid-template-columns: 1fr;
  }
  .learning-target {
    align-items: stretch;
    flex-direction: column;
  }
}
@media (max-width: 700px) {
  .course-context,
  .plan-entry,
  .plan-level,
  .task-section__header,
  .task-card__heading {
    align-items: stretch;
    flex-direction: column;
  }
  .plan-level {
    display: flex;
  }
  .learn-course-select {
    width: 100%;
    flex-basis: auto;
  }
  .plan-entry__actions {
    align-items: stretch;
    flex-direction: column;
  }
  .stale-panel {
    grid-template-columns: 1fr;
  }
  .stale-panel__icon {
    display: none;
  }
}
</style>
