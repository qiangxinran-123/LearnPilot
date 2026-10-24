<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Collection, Timer } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import QuestionBankPanel from '@/components/diagnostic/QuestionBankPanel.vue';
import { fetchCourses } from '@/services/courses';
import {
  createOrResumeAssessment,
  fetchAssessments,
} from '@/services/diagnostics';
import { normalizeApiError } from '@/services/http';
import type { CourseSummary } from '@/types/course';
import type { AssessmentSummary } from '@/types/diagnostic';

const router = useRouter();
const route = useRoute();
const courses = ref<CourseSummary[]>([]);
const assessments = ref<AssessmentSummary[]>([]);
const selectedCourseId = ref<number | null>(null);
const pageState = ref<'loading' | 'ready' | 'error'>('loading');
const pageError = ref('');
const isStarting = ref(false);

const selectedCourse = computed(
  () => courses.value.find((item) => item.id === selectedCourseId.value) ?? null,
);
const unfinished = computed(() =>
  assessments.value.find(
    (item) =>
      item.course_id === selectedCourseId.value && ['ready', 'in_progress'].includes(item.status),
  ),
);

function statusLabel(status: AssessmentSummary['status']): string {
  return { draft: '准备中', ready: '待开始', in_progress: '进行中', submitted: '已完成' }[status];
}
function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}
async function loadPage(): Promise<void> {
  pageState.value = 'loading';
  pageError.value = '';
  try {
    const [courseResponse, assessmentResponse] = await Promise.all([
      fetchCourses(),
      fetchAssessments(),
    ]);
    courses.value = courseResponse.courses;
    assessments.value = assessmentResponse.assessments;
    if (!selectedCourseId.value && courses.value.length) {
      const rawCourseId = Array.isArray(route.query.courseId)
        ? route.query.courseId[0]
        : route.query.courseId;
      const requestedCourseId = Number(rawCourseId);
      selectedCourseId.value = courses.value.some((course) => course.id === requestedCourseId)
        ? requestedCourseId
        : courses.value[0]!.id;
    }
    pageState.value = 'ready';
  } catch (error: unknown) {
    pageError.value = normalizeApiError(error).message;
    pageState.value = 'error';
  }
}
async function openAssessment(): Promise<void> {
  if (unfinished.value) {
    await router.push({
      name: 'diagnostic-assessment',
      params: { assessmentId: unfinished.value.id },
    });
    return;
  }
  if (!selectedCourseId.value) return;
  isStarting.value = true;
  try {
    const assessment = await createOrResumeAssessment(selectedCourseId.value);
    await router.push({ name: 'diagnostic-assessment', params: { assessmentId: assessment.id } });
  } catch (error: unknown) {
    ElMessage.error(normalizeApiError(error).message);
  } finally {
    isStarting.value = false;
  }
}
function openKnowledgeStructure(): void {
  if (selectedCourseId.value) {
    void router.push(`/courses/${selectedCourseId.value}?tab=knowledge-structure`);
  }
}
function openHistory(item: AssessmentSummary): void {
  void router.push({
    name: item.status === 'submitted' ? 'diagnostic-report' : 'diagnostic-assessment',
    params: { assessmentId: item.id },
  });
}

onMounted(() => void loadPage());
</script>

<template>
  <section class="page-view diagnose-page">
    <PageHeader
      title="学习诊断"
      description="以课程知识结构为范围，完成一次专注、可恢复的初始诊断。"
    />
    <LoadingBlock v-if="pageState === 'loading'" :count="2" />
    <ErrorState
      v-else-if="pageState === 'error'"
      title="诊断信息加载失败"
      :message="pageError"
      @retry="loadPage"
    />
    <EmptyState
      v-else-if="courses.length === 0"
      :icon="Collection"
      title="还没有可诊断的课程"
      description="先创建课程并建立知识结构，再回来进行学习诊断。"
    >
      <template #action
        ><el-button type="primary" @click="router.push('/courses')">前往课程</el-button></template
      >
    </EmptyState>
    <template v-else>
      <section class="diagnose-setup" aria-labelledby="diagnose-setup-title">
        <div class="diagnose-setup__intro">
          <h2 id="diagnose-setup-title">选择一门课程</h2>
          <p>切换课程即可查看真实题库覆盖与当前诊断状态。</p>
          <el-select v-model="selectedCourseId" class="course-select" aria-label="选择诊断课程">
            <el-option
              v-for="course in courses"
              :key="course.id"
              :label="course.name"
              :value="course.id"
            />
          </el-select>
          <nav class="course-list" aria-label="诊断课程列表">
            <button
              v-for="course in courses"
              :key="course.id"
              type="button"
              :class="{ 'course-list__item--active': selectedCourseId === course.id }"
              @click="selectedCourseId = course.id"
            >
              <strong>{{ course.name }}</strong>
              <span>{{ course.description || '查看诊断准备状态' }}</span>
            </button>
          </nav>
        </div>
        <div class="readiness-panel" aria-live="polite">
          <div v-if="unfinished" class="readiness-ready">
            <div class="readiness-heading">
              <span class="readiness-dot" aria-hidden="true"></span>
              <div>
                <p>诊断草稿已保存</p>
                <h3>{{ selectedCourse?.name }}</h3>
              </div>
            </div>
            <dl class="readiness-metrics">
              <div>
                <dt>已完成</dt>
                <dd>{{ unfinished.answered_count }} / {{ unfinished.question_count }} 题</dd>
              </div>
              <div>
                <dt>剩余题目</dt>
                <dd>{{ Math.max(unfinished.question_count - unfinished.answered_count, 0) }} 题</dd>
              </div>
              <div>
                <dt>当前状态</dt>
                <dd>可继续作答</dd>
              </div>
            </dl>
            <p class="readiness-note">将继续使用原试卷，并恢复已经保存的答案。</p>
            <el-button type="primary" size="large" @click="openAssessment">继续作答</el-button>
          </div>
          <QuestionBankPanel
            v-else-if="selectedCourseId && selectedCourse"
            :key="selectedCourseId"
            :course-id="selectedCourseId"
            :course-name="selectedCourse.name"
            @start="openAssessment"
            @knowledge="openKnowledgeStructure"
          />
        </div>
      </section>

      <section class="history-section" aria-labelledby="history-heading">
        <div class="section-title">
          <div>
            <p class="eyebrow">HISTORY</p>
            <h2 id="history-heading">最近诊断</h2>
          </div>
          <el-icon><Timer /></el-icon>
        </div>
        <div v-if="assessments.length" class="history-list">
          <article v-for="item in assessments" :key="item.id" class="history-row">
            <div>
              <h3>{{ item.course_name }}</h3>
              <p>{{ formatDate(item.submitted_at || item.created_at) }}</p>
            </div>
            <span class="status-pill" :class="`status-pill--${item.status}`">{{
              statusLabel(item.status)
            }}</span>
            <p>{{ item.question_count }} 题</p>
            <strong v-if="item.status === 'submitted' && item.accuracy !== null"
              >{{ Math.round(item.accuracy * 100) }}%</strong
            >
            <span v-else class="history-muted">暂无成绩</span>
            <el-button plain @click="openHistory(item)">{{
              item.status === 'submitted' ? '查看报告' : '继续作答'
            }}</el-button>
          </article>
        </div>
        <p v-else class="history-empty">完成一次初始诊断后，记录会显示在这里。</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.diagnose-setup {
  display: grid;
  grid-template-columns: minmax(260px, 0.82fr) minmax(420px, 1.18fr);
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
  overflow: hidden;
}
.diagnose-setup__intro {
  padding: 34px;
  border-right: 1px solid var(--lp-border);
  background: #fbfcfe;
}
.eyebrow {
  margin-bottom: 8px;
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.14em;
}
.diagnose-setup h2,
.history-section h2 {
  margin-bottom: 10px;
  color: var(--lp-ink);
  font-size: 22px;
}
.diagnose-setup__intro > p:not(.eyebrow),
.readiness-note {
  color: var(--lp-text-secondary);
}
.course-select {
  display: none;
  width: 100%;
  margin-top: 22px;
}
.course-list {
  display: grid;
  gap: 8px;
  margin-top: 22px;
}
.course-list button {
  display: grid;
  gap: 3px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
  color: var(--lp-ink);
  background: var(--lp-surface);
  text-align: left;
  cursor: pointer;
}
.course-list button:hover,
.course-list button:focus-visible,
.course-list__item--active {
  border-color: var(--lp-primary);
  background: #edf5ff;
  outline: none;
}
.course-list span {
  overflow: hidden;
  color: var(--lp-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.readiness-panel {
  min-height: 300px;
  padding: 34px;
}
.readiness-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}
.readiness-heading p,
.readiness-heading h3 {
  margin: 0;
}
.readiness-heading p {
  color: #32734c;
  font-size: 12px;
  font-weight: 700;
}
.readiness-heading h3 {
  color: var(--lp-ink);
  font-size: 20px;
}
.readiness-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #3d9661;
  box-shadow: 0 0 0 5px #e7f5ec;
}
.readiness-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin: 26px 0;
}
.readiness-metrics div {
  padding: 14px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
}
.readiness-metrics dt {
  color: var(--lp-text-tertiary);
  font-size: 12px;
}
.readiness-metrics dd {
  margin: 5px 0 0;
  color: var(--lp-ink);
  font-size: 17px;
  font-weight: 650;
}
.readiness-message {
  display: grid;
  min-height: 230px;
  place-content: center;
  justify-items: center;
  text-align: center;
}
.readiness-message .el-icon {
  color: var(--lp-primary);
  font-size: 32px;
}
.readiness-message h3 {
  margin: 12px 0 6px;
  color: var(--lp-ink);
}
.readiness-message p {
  max-width: 480px;
  color: var(--lp-text-secondary);
}
.readiness-message--error h3 {
  color: var(--lp-danger);
}
.history-section {
  margin-top: 34px;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title .el-icon {
  color: var(--lp-text-tertiary);
  font-size: 22px;
}
.history-list {
  display: grid;
  gap: 10px;
}
.history-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 90px 70px 90px auto;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
  background: var(--lp-surface);
}
.history-row h3,
.history-row p {
  margin: 0;
}
.history-row h3 {
  color: var(--lp-ink);
  font-size: 15px;
}
.history-row p,
.history-muted {
  color: var(--lp-text-secondary);
  font-size: 13px;
}
.status-pill {
  width: max-content;
  padding: 3px 9px;
  border-radius: 999px;
  color: #6b7280;
  background: #f0f2f5;
  font-size: 12px;
}
.status-pill--in_progress {
  color: #235f9f;
  background: #eaf2fc;
}
.status-pill--submitted {
  color: #287548;
  background: #edf8f1;
}
.history-empty {
  padding: 24px;
  border: 1px dashed var(--lp-border-strong);
  border-radius: var(--lp-radius-md);
  color: var(--lp-text-secondary);
  text-align: center;
}
@media (max-width: 900px) {
  .diagnose-setup {
    grid-template-columns: 1fr;
  }
  .diagnose-setup__intro {
    border-right: 0;
    border-bottom: 1px solid var(--lp-border);
  }
  .course-select {
    display: block;
  }
  .course-list {
    display: none;
  }
  .history-row {
    grid-template-columns: 1fr auto;
  }
  .history-row > p,
  .history-row > strong,
  .history-muted {
    display: none;
  }
}
@media (max-width: 620px) {
  .readiness-metrics {
    grid-template-columns: 1fr;
  }
  .diagnose-setup__intro,
  .readiness-panel {
    padding: 22px;
  }
}
</style>
