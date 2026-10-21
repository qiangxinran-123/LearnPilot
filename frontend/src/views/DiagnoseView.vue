<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { Collection, DataAnalysis, Timer } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { fetchCourses } from '@/services/courses';
import { createOrResumeAssessment, fetchAssessments, fetchDiagnosticReadiness } from '@/services/diagnostics';
import { normalizeApiError } from '@/services/http';
import type { CourseSummary } from '@/types/course';
import type { AssessmentSummary, DiagnosticReadiness } from '@/types/diagnostic';

const router = useRouter();
const courses = ref<CourseSummary[]>([]);
const assessments = ref<AssessmentSummary[]>([]);
const selectedCourseId = ref<number | null>(null);
const readiness = ref<DiagnosticReadiness | null>(null);
const pageState = ref<'loading' | 'ready' | 'error'>('loading');
const readinessState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle');
const pageError = ref('');
const readinessError = ref('');
const isStarting = ref(false);
let readinessRequest = 0;

const selectedCourse = computed(() => courses.value.find((item) => item.id === selectedCourseId.value) ?? null);
const unfinished = computed(() =>
  assessments.value.find(
    (item) => item.course_id === selectedCourseId.value && ['ready', 'in_progress'].includes(item.status),
  ),
);

function statusLabel(status: AssessmentSummary['status']): string {
  return { draft: '准备中', ready: '待开始', in_progress: '进行中', submitted: '已完成' }[status];
}
function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}
async function loadPage(): Promise<void> {
  pageState.value = 'loading';
  pageError.value = '';
  try {
    const [courseResponse, assessmentResponse] = await Promise.all([fetchCourses(), fetchAssessments()]);
    courses.value = courseResponse.courses;
    assessments.value = assessmentResponse.assessments;
    if (!selectedCourseId.value && courses.value.length) selectedCourseId.value = courses.value[0]!.id;
    pageState.value = 'ready';
  } catch (error: unknown) {
    pageError.value = normalizeApiError(error).message;
    pageState.value = 'error';
  }
}
async function loadReadiness(courseId: number | null): Promise<void> {
  const request = ++readinessRequest;
  readiness.value = null;
  readinessError.value = '';
  if (!courseId) { readinessState.value = 'idle'; return; }
  readinessState.value = 'loading';
  try {
    const response = await fetchDiagnosticReadiness(courseId);
    if (request !== readinessRequest) return;
    readiness.value = response;
    readinessState.value = 'ready';
  } catch (error: unknown) {
    if (request !== readinessRequest) return;
    readinessError.value = normalizeApiError(error).message;
    readinessState.value = 'error';
  }
}
async function openAssessment(): Promise<void> {
  if (unfinished.value) {
    await router.push({ name: 'diagnostic-assessment', params: { assessmentId: unfinished.value.id } });
    return;
  }
  if (!selectedCourseId.value || !readiness.value?.can_start) return;
  isStarting.value = true;
  try {
    const assessment = await createOrResumeAssessment(selectedCourseId.value);
    await router.push({ name: 'diagnostic-assessment', params: { assessmentId: assessment.id } });
  } catch (error: unknown) { ElMessage.error(normalizeApiError(error).message); }
  finally { isStarting.value = false; }
}
function openHistory(item: AssessmentSummary): void {
  void router.push({
    name: item.status === 'submitted' ? 'diagnostic-report' : 'diagnostic-assessment',
    params: { assessmentId: item.id },
  });
}

watch(selectedCourseId, (courseId) => void loadReadiness(courseId));
onMounted(() => void loadPage());
</script>

<template>
  <section class="page-view diagnose-page">
    <PageHeader title="学习诊断" description="以课程知识结构为范围，完成一次专注、可恢复的初始诊断。" />
    <LoadingBlock v-if="pageState === 'loading'" :count="2" />
    <ErrorState v-else-if="pageState === 'error'" title="诊断信息加载失败" :message="pageError" @retry="loadPage" />
    <EmptyState v-else-if="courses.length === 0" :icon="Collection" title="还没有可诊断的课程" description="先创建课程并建立知识结构，再回来进行学习诊断。">
      <template #action><el-button type="primary" @click="router.push('/courses')">前往课程</el-button></template>
    </EmptyState>
    <template v-else>
      <section class="diagnose-setup" aria-labelledby="diagnose-setup-title">
        <div class="diagnose-setup__intro">
          <p class="eyebrow">INITIAL DIAGNOSTIC</p>
          <h2 id="diagnose-setup-title">选择一门课程</h2>
          <p>系统只使用已经验证、具有课程来源的题目。提交后的答案与成绩不可更改。</p>
          <el-select v-model="selectedCourseId" class="course-select" aria-label="选择诊断课程">
            <el-option v-for="course in courses" :key="course.id" :label="course.name" :value="course.id" />
          </el-select>
        </div>
        <div class="readiness-panel" aria-live="polite">
          <el-skeleton v-if="readinessState === 'loading'" :rows="4" animated />
          <div v-else-if="readinessState === 'error'" class="readiness-message readiness-message--error">
            <h3>准备状态加载失败</h3><p>{{ readinessError }}</p><el-button plain @click="loadReadiness(selectedCourseId)">重试</el-button>
          </div>
          <template v-else-if="readiness">
            <div v-if="readiness.can_start" class="readiness-ready">
              <div class="readiness-heading"><span class="readiness-dot" aria-hidden="true"></span><div><p>诊断已就绪</p><h3>{{ selectedCourse?.name }}</h3></div></div>
              <dl class="readiness-metrics">
                <div><dt>预计题量</dt><dd>{{ readiness.estimated_question_count }} 题</dd></div>
                <div><dt>预计时间</dt><dd>{{ readiness.estimated_minutes }} 分钟</dd></div>
                <div><dt>知识覆盖</dt><dd>{{ readiness.covered_knowledge_nodes }} 个核心节点</dd></div>
              </dl>
              <p class="readiness-note">可包含未答题提交；未答题由后端确定性规则计零分。</p>
              <el-button type="primary" size="large" :loading="isStarting" @click="openAssessment">{{ unfinished ? '继续诊断' : '开始初始诊断' }}</el-button>
            </div>
            <div v-else class="readiness-message">
              <el-icon><DataAnalysis /></el-icon>
              <h3>{{ readiness.status === 'knowledge_not_ready' ? '尚未建立课程知识结构' : '当前课程的诊断题目尚不充足' }}</h3>
              <p v-if="readiness.status === 'question_bank_insufficient'">已有 {{ readiness.available_questions }} 道合格题，覆盖 {{ readiness.covered_knowledge_nodes }} / {{ readiness.eligible_knowledge_nodes }} 个核心知识节点。</p>
              <p v-else>请先在课程空间完成知识结构构建。</p>
              <el-button plain @click="router.push(`/courses/${selectedCourseId}?tab=knowledge-structure`)">前往课程</el-button>
            </div>
          </template>
        </div>
      </section>

      <section class="history-section" aria-labelledby="history-heading">
        <div class="section-title"><div><p class="eyebrow">HISTORY</p><h2 id="history-heading">最近诊断</h2></div><el-icon><Timer /></el-icon></div>
        <div v-if="assessments.length" class="history-list">
          <article v-for="item in assessments" :key="item.id" class="history-row">
            <div><h3>{{ item.course_name }}</h3><p>{{ formatDate(item.submitted_at || item.created_at) }}</p></div>
            <span class="status-pill" :class="`status-pill--${item.status}`">{{ statusLabel(item.status) }}</span>
            <p>{{ item.question_count }} 题</p>
            <strong v-if="item.status === 'submitted' && item.accuracy !== null">{{ Math.round(item.accuracy * 100) }}%</strong>
            <span v-else class="history-muted">暂无成绩</span>
            <el-button plain @click="openHistory(item)">{{ item.status === 'submitted' ? '查看报告' : '继续诊断' }}</el-button>
          </article>
        </div>
        <p v-else class="history-empty">完成一次初始诊断后，记录会显示在这里。</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.diagnose-setup { display: grid; grid-template-columns: minmax(260px, .82fr) minmax(420px, 1.18fr); border: 1px solid var(--lp-border); border-radius: var(--lp-radius-lg); background: var(--lp-surface); box-shadow: var(--lp-shadow-sm); overflow: hidden; }
.diagnose-setup__intro { padding: 34px; border-right: 1px solid var(--lp-border); background: #fbfcfe; }
.eyebrow { margin-bottom: 8px; color: var(--lp-primary); font-size: 11px; font-weight: 750; letter-spacing: .14em; }
.diagnose-setup h2, .history-section h2 { margin-bottom: 10px; color: var(--lp-ink); font-size: 22px; }
.diagnose-setup__intro > p:not(.eyebrow), .readiness-note { color: var(--lp-text-secondary); }
.course-select { width: 100%; margin-top: 22px; }
.readiness-panel { min-height: 300px; padding: 34px; }
.readiness-heading { display: flex; align-items: center; gap: 12px; }
.readiness-heading p, .readiness-heading h3 { margin: 0; }
.readiness-heading p { color: #32734c; font-size: 12px; font-weight: 700; }
.readiness-heading h3 { color: var(--lp-ink); font-size: 20px; }
.readiness-dot { width: 10px; height: 10px; border-radius: 50%; background: #3d9661; box-shadow: 0 0 0 5px #e7f5ec; }
.readiness-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 26px 0; }
.readiness-metrics div { padding: 14px; border: 1px solid var(--lp-border); border-radius: var(--lp-radius-md); }
.readiness-metrics dt { color: var(--lp-text-tertiary); font-size: 12px; }
.readiness-metrics dd { margin: 5px 0 0; color: var(--lp-ink); font-size: 17px; font-weight: 650; }
.readiness-message { display: grid; min-height: 230px; place-content: center; justify-items: center; text-align: center; }
.readiness-message .el-icon { color: var(--lp-primary); font-size: 32px; }
.readiness-message h3 { margin: 12px 0 6px; color: var(--lp-ink); }
.readiness-message p { max-width: 480px; color: var(--lp-text-secondary); }
.readiness-message--error h3 { color: var(--lp-danger); }
.history-section { margin-top: 34px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.section-title .el-icon { color: var(--lp-text-tertiary); font-size: 22px; }
.history-list { display: grid; gap: 10px; }
.history-row { display: grid; grid-template-columns: minmax(180px, 1fr) 90px 70px 90px auto; align-items: center; gap: 16px; padding: 16px 18px; border: 1px solid var(--lp-border); border-radius: var(--lp-radius-md); background: var(--lp-surface); }
.history-row h3, .history-row p { margin: 0; }
.history-row h3 { color: var(--lp-ink); font-size: 15px; }
.history-row p, .history-muted { color: var(--lp-text-secondary); font-size: 13px; }
.status-pill { width: max-content; padding: 3px 9px; border-radius: 999px; color: #6b7280; background: #f0f2f5; font-size: 12px; }
.status-pill--in_progress { color: #235f9f; background: #eaf2fc; }
.status-pill--submitted { color: #287548; background: #edf8f1; }
.history-empty { padding: 24px; border: 1px dashed var(--lp-border-strong); border-radius: var(--lp-radius-md); color: var(--lp-text-secondary); text-align: center; }
@media (max-width: 900px) { .diagnose-setup { grid-template-columns: 1fr; } .diagnose-setup__intro { border-right: 0; border-bottom: 1px solid var(--lp-border); } .history-row { grid-template-columns: 1fr auto; } .history-row > p, .history-row > strong, .history-muted { display: none; } }
@media (max-width: 620px) { .readiness-metrics { grid-template-columns: 1fr; } .diagnose-setup__intro, .readiness-panel { padding: 22px; } }
</style>
