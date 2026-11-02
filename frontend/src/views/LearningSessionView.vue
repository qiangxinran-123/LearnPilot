<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ArrowLeft } from '@element-plus/icons-vue';
import { useRoute, useRouter } from 'vue-router';

import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import PracticePanel from '@/components/learning/PracticePanel.vue';
import LearningSummary from '@/components/learning/LearningSummary.vue';
import TutorPanel from '@/components/learning/TutorPanel.vue';
import { useLearningContent } from '@/composables/useLearningContent';
import {
  cancelLearningSession,
  completeLearningSession,
  createLearningSession,
  fetchLearningSession,
  fetchSessionContinuation,
  updateLearningSessionTask,
} from '@/services/learningSessions';
import { normalizeApiError } from '@/services/http';
import type {
  LearningSession,
  PracticeAttempt,
  SessionContinuation,
  TeachingStrategy,
} from '@/types/learningSession';

const route = useRoute();
const router = useRouter();
const session = ref<LearningSession | null>(null);
const isLoading = ref(true);
const pendingTaskId = ref<number | null>(null);
const isCancelling = ref(false);
const isSettling = ref(false);
const isStartingNext = ref(false);
const errorMessage = ref('');
const actionError = ref('');
const learningContent = useLearningContent();
const tutorPanel = ref<InstanceType<typeof TutorPanel> | null>(null);
const step = ref<'concept' | 'practice'>('concept');
const attempts = ref<PracticeAttempt[]>([]);
const continuation = ref<SessionContinuation | null>(null);
const continuationLoading = ref(false);
const continuationError = ref('');
let loadVersion = 0;

const sessionId = computed(() => {
  const value = Number(
    Array.isArray(route.params.sessionId) ? route.params.sessionId[0] : route.params.sessionId,
  );
  return Number.isInteger(value) && value > 0 ? value : null;
});
const completedTargets = computed(() => {
  const raw = Array.isArray(route.query?.completed) ? route.query.completed[0] : route.query?.completed;
  return typeof raw === 'string' ? raw.split(',').map(Number).filter((id) => Number.isSafeInteger(id) && id > 0) : [];
});
const canWrite = computed(
  () => session.value?.status === 'created' || session.value?.status === 'in_progress',
);

const conceptDone = computed(() => session.value?.tasks.filter((task) => task.phase !== 'adaptive_practice').every((task) => task.status === 'completed') ?? false);
const practiceDone = computed(() => session.value?.tasks.find((task) => task.phase === 'adaptive_practice')?.status === 'completed');

async function load(): Promise<void> {
  const version = ++loadVersion;
  errorMessage.value = '';
  actionError.value = '';
  session.value = null;
  attempts.value = [];
  continuation.value = null;
  learningContent.clear();
  if (!sessionId.value) {
    errorMessage.value = '学习会话地址无效，请返回学习计划重新进入。';
    isLoading.value = false;
    return;
  }
  isLoading.value = true;
  try {
    const loaded = await fetchLearningSession(sessionId.value);
    if (version !== loadVersion) return;
    session.value = loaded;
    attempts.value = loaded.practice_attempts ?? [];
    step.value = loaded.tasks.filter((task) => task.phase !== 'adaptive_practice').every((task) => task.status === 'completed') ? 'practice' : 'concept';
    await learningContent.load(loaded.session_id);
    if (loaded.status === 'completed') void loadContinuation(loaded.session_id);
  } catch (error: unknown) {
    if (version === loadVersion) errorMessage.value = normalizeApiError(error).message;
  } finally {
    if (version === loadVersion) isLoading.value = false;
  }
}
function retryContent(): void {
  if (session.value) void learningContent.load(session.value.session_id);
}
function openMaterial(materialId: number): void {
  if (!session.value) return;
  void router.push({
    name: 'material-detail',
    params: { courseId: session.value.course_id, materialId },
  });
}
async function startPractice(): Promise<void> {
  if (!session.value || pendingTaskId.value !== null) return;
  pendingTaskId.value = -1;
  actionError.value = '';
  try {
    for (const phase of ['concept_learning', 'guided_example'] as const) {
      let task = session.value.tasks.find((item) => item.phase === phase);
      if (task?.status === 'not_started') {
        session.value = await updateLearningSessionTask(session.value.session_id, phase, 'in_progress');
        task = session.value.tasks.find((item) => item.phase === phase);
      }
      if (task?.status === 'in_progress') session.value = await updateLearningSessionTask(session.value.session_id, phase, 'completed');
    }
    step.value = 'practice';
  } catch (error: unknown) {
    actionError.value = normalizeApiError(error).message;
  } finally {
    pendingTaskId.value = null;
  }
}
async function refreshSession(): Promise<void> {
  const currentId = session.value?.session_id;
  if (!currentId) return;
  try {
    const updated = await fetchLearningSession(currentId);
    if (session.value?.session_id === currentId) session.value = updated;
  } catch (error: unknown) {
    actionError.value = normalizeApiError(error).message;
  }
}
function askTutor(request: { message: string; mode: TeachingStrategy }): void {
  tutorPanel.value?.prepareQuestion(request.message, request.mode);
}
function backToLearn(): void {
  const query: Record<string, string> = { courseId: String(session.value?.course_id ?? '') };
  if (canWrite.value && completedTargets.value.length && session.value) {
    query.completed = completedTargets.value.join(',');
    query.flowSession = String(session.value.session_id);
  }
  if (session.value?.status === 'completed') {
    query.finishedNode = String(session.value.target_knowledge_node_id);
  }
  void router.push({ name: 'learn', query });
}
async function startNext(): Promise<void> {
  const current = session.value;
  const recommendation = continuation.value;
  if (!current || !recommendation || recommendation.knowledge_node_id === current.target_knowledge_node_id || isStartingNext.value) return;
  isStartingNext.value = true;
  actionError.value = '';
  try {
    const next = await createLearningSession({ course_id: current.course_id, target_knowledge_node_id: recommendation.knowledge_node_id });
    const completed = [...new Set([...completedTargets.value, current.target_knowledge_node_id])];
    await router.push({ name: 'learning-session', params: { sessionId: next.session_id }, query: { completed: completed.join(',') } });
  } catch (error: unknown) {
    actionError.value = normalizeApiError(error).message;
  } finally {
    isStartingNext.value = false;
  }
}
async function loadContinuation(id: number): Promise<void> {
  continuationLoading.value = true;
  continuationError.value = '';
  try {
    const result = await fetchSessionContinuation(id, completedTargets.value);
    if (session.value?.session_id === id) continuation.value = result.recommendation;
  } catch (error: unknown) {
    if (session.value?.session_id === id) continuationError.value = normalizeApiError(error).message;
  } finally {
    if (session.value?.session_id === id) continuationLoading.value = false;
  }
}
async function cancel(): Promise<void> {
  if (!session.value || isCancelling.value) return;
  isCancelling.value = true;
  actionError.value = '';
  try {
    session.value = await cancelLearningSession(session.value.session_id);
    backToLearn();
  } catch (error: unknown) {
    actionError.value = normalizeApiError(error).message;
  } finally {
    isCancelling.value = false;
  }
}

async function settle(): Promise<void> {
  const id = session.value?.session_id;
  if (!id || isSettling.value) return;
  isSettling.value = true;
  actionError.value = '';
  try {
    const result = await completeLearningSession(id);
    if (session.value?.session_id === id) {
      session.value = result;
      void loadContinuation(id);
    }
  } catch (error: unknown) {
    if (session.value?.session_id === id) actionError.value = normalizeApiError(error).message;
  } finally {
    isSettling.value = false;
  }
}

watch(sessionId, load, { immediate: true });
</script>

<template>
  <section class="page-view session-page">
    <button class="back-link" type="button" @click="backToLearn">
      <el-icon><ArrowLeft /></el-icon>返回学习页
    </button>
    <LoadingBlock v-if="isLoading" :count="3" />
    <ErrorState
      v-else-if="errorMessage"
      title="无法打开学习会话"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="session">
      <header class="session-header">
        <div>
          <p>{{ session.course_name }}</p>
          <h1>{{ session.target_knowledge_node_name }}</h1>
          <span>概念 → 练习 → 反馈</span>
        </div>
        <div class="session-header__actions">
          <el-tag v-if="session.status === 'created'" effect="plain">尚未开始</el-tag>
          <el-tag v-else-if="session.status === 'in_progress'" type="primary" effect="plain"
            >学习中</el-tag
          >
          <el-tag v-else-if="session.status === 'cancelled'" type="info" effect="plain"
            >已取消</el-tag
          >
          <el-tag v-else type="success" effect="plain">已完成</el-tag>
          <el-button
            v-if="canWrite"
            plain
            :loading="isCancelling"
            :disabled="isCancelling || pendingTaskId !== null"
            @click="cancel"
            >取消本次会话</el-button
          >
        </div>
      </header>

      <p v-if="actionError" class="session-action-error" role="alert">{{ actionError }}</p>
      <template v-if="session.status === 'completed'">
        <ol class="step-progress" aria-label="学习任务进度"><li>① 理解概念 · 已完成</li><li>② 针对练习 · 已完成</li><li class="current">③ 学习反馈 · 已完成</li></ol>
        <LearningSummary :session="session" :attempts="attempts" :continuation="continuation" :continuation-loading="continuationLoading" :continuation-error="continuationError" :retrying="isStartingNext" @retry="loadContinuation(session.session_id)" @back="backToLearn" @next="startNext" />
        <details class="session-history">
          <summary>查看 Tutor 辅导记录</summary>
          <TutorPanel
            :session-id="session.session_id"
            :course-id="session.course_id"
            :knowledge-node-name="session.target_knowledge_node_name"
            :read-only="true"
          />
        </details>
      </template>
      <div v-else class="session-workspace">
        <main class="session-workspace__main">
      <ol class="step-progress" aria-label="学习任务进度">
        <li :class="{ current: step === 'concept' }">① 理解概念 · {{ conceptDone ? '已完成' : '进行中' }}</li>
        <li :class="{ current: step === 'practice' }">② 针对练习 · {{ practiceDone ? '已完成' : conceptDone ? '进行中' : '未开始' }}</li>
        <li>③ 学习反馈 · 未开始</li>
      </ol>
      <section v-show="step === 'concept'" class="learning-content" aria-labelledby="learning-content-title">
        <header class="learning-content__header">
          <div>
            <span>课程原始资料</span>
            <h2 id="learning-content-title">概念理解</h2>
          </div>
          <small>内容来自当前课程的已解析资料，不是 AI 生成讲解</small>
        </header>
        <LoadingBlock v-if="learningContent.state.value === 'loading'" :count="2" />
        <ErrorState
          v-else-if="learningContent.state.value === 'error'"
          title="学习内容加载失败"
          :message="learningContent.errorMessage.value"
          @retry="retryContent"
        />
        <div v-else-if="learningContent.state.value === 'empty'" class="learning-content__empty">
          <h3>暂未找到相关课程内容</h3>
          <p>当前课程资料中没有可验证的相关片段。系统不会用生成内容填充此区域。</p>
        </div>
        <template v-else-if="learningContent.content.value">
          <p
            v-if="learningContent.content.value.knowledge_node_description"
            class="learning-content__description"
          >
            {{ learningContent.content.value.knowledge_node_description }}
          </p>
          <div class="source-list">
            <article
              v-for="segment in learningContent.content.value.segments"
              :key="`${segment.material_id}-${segment.segment_index}-${segment.fragment_index}`"
              class="source-excerpt"
            >
              <header>
                <div>
                  <strong>{{ segment.material_title }}</strong>
                  <span>{{ segment.material_type.toUpperCase() }} · {{ segment.source_reference }}</span>
                </div>
                <el-tag size="small" :type="segment.relevance === 'direct' ? 'primary' : 'info'" effect="plain">
                  {{ segment.relevance === 'direct' ? '知识点来源' : '课程内补充' }}
                </el-tag>
              </header>
              <details v-if="segment.text.length > 520">
                <summary>{{ segment.text.slice(0, 260) }}…</summary>
                <p>{{ segment.text }}</p>
              </details>
              <p v-else>{{ segment.text }}</p>
              <button type="button" class="source-excerpt__link" @click="openMaterial(segment.material_id)">
                查看原始资料
              </button>
            </article>
          </div>
        </template>
      </section>
      <div v-if="step === 'concept'" class="step-actions">
        <el-button v-if="canWrite" type="primary" :loading="pendingTaskId !== null" :disabled="pendingTaskId !== null" @click="startPractice">开始练习</el-button>
      </div>
      <section v-if="conceptDone" v-show="step === 'practice'" class="learning-content">
        <button type="button" class="back-link" @click="step = 'concept'">返回查看概念</button>
        <PracticePanel
          :session-id="session.session_id"
          :practice-assessment-id="session.practice_assessment_id"
          :enabled="canWrite"
          :read-only="!canWrite"
          @changed="refreshSession"
          @attempts="attempts = $event"
          @ask-tutor="askTutor"
        />
        <el-button v-if="canWrite && practiceDone" type="primary" :loading="isSettling" :disabled="isSettling" @click="settle">完成学习并查看结果</el-button>
      </section>
        </main>
        <TutorPanel
          ref="tutorPanel"
          :session-id="session.session_id"
          :course-id="session.course_id"
          :knowledge-node-name="session.target_knowledge_node_name"
          :read-only="!canWrite"
          @changed="refreshSession"
        />
      </div>
    </template>
  </section>
</template>

<style scoped>
.step-progress { display: flex; flex-wrap: wrap; gap: 12px; padding: 0; margin: 24px 0 0; list-style: none; color: var(--lp-text-secondary); }
.step-progress li { padding: 10px 14px; border-radius: var(--lp-radius-md); background: var(--lp-surface-subtle); }
.step-progress .current { color: var(--lp-primary); background: var(--lp-primary-soft); font-weight: 700; }
.step-actions { margin-top: 18px; }
.session-page {
  max-width: 1280px;
}
.session-history {
  margin-bottom: 24px;
}
.session-history summary {
  margin-bottom: 12px;
  color: var(--lp-primary);
  cursor: pointer;
  font-weight: 700;
}
.session-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.56fr);
  gap: 22px;
  align-items: start;
}
.session-workspace__main {
  min-width: 0;
}
.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  border: 1px solid #cadcf2;
  border-radius: var(--lp-radius-lg);
  background: linear-gradient(135deg, #f8fbff, #fff);
  box-shadow: var(--lp-shadow-sm);
}
.session-header p {
  margin: 0 0 4px;
  color: var(--lp-primary);
  font-size: 12px;
  font-weight: 700;
}
.session-header h1 {
  margin: 0 0 8px;
  color: var(--lp-ink);
  font-size: 28px;
}
.session-header span {
  color: var(--lp-text-secondary);
  font-size: 13px;
}
.session-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.session-action-error {
  margin: 16px 0 0;
  color: var(--lp-danger);
}
.learning-content {
  margin-top: 24px;
  padding: 26px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}
.learning-content__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--lp-border);
}
.learning-content__header span {
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.learning-content__header h2 {
  margin: 4px 0 0;
  color: var(--lp-ink);
  font-size: 21px;
}
.learning-content__header small {
  max-width: 360px;
  color: var(--lp-text-tertiary);
  line-height: 1.6;
  text-align: right;
}
.learning-content__description {
  max-width: 72ch;
  margin: 20px 0 0;
  color: var(--lp-text-secondary);
  line-height: 1.75;
}
.learning-content__empty {
  padding: 30px 4px 8px;
}
.learning-content__empty h3 {
  margin: 0 0 8px;
  color: var(--lp-ink);
  font-size: 17px;
}
.learning-content__empty p {
  margin: 0;
  color: var(--lp-text-secondary);
}
.source-list {
  display: grid;
  gap: 14px;
  margin-top: 20px;
}
.source-excerpt {
  padding: 20px;
  border-left: 3px solid #a9c7e9;
  border-radius: 0 var(--lp-radius-md) var(--lp-radius-md) 0;
  background: var(--lp-surface-subtle);
}
.source-excerpt header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
}
.source-excerpt strong,
.source-excerpt span {
  display: block;
}
.source-excerpt strong {
  color: var(--lp-ink);
  font-size: 14px;
}
.source-excerpt span {
  margin-top: 4px;
  color: var(--lp-text-tertiary);
  font-size: 12px;
}
.source-excerpt p,
.source-excerpt summary {
  max-width: 78ch;
  margin: 16px 0 0;
  color: var(--lp-text-secondary);
  line-height: 1.85;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.source-excerpt summary {
  cursor: pointer;
}
.source-excerpt__link {
  margin-top: 14px;
  padding: 0;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
}
.session-tasks {
  display: grid;
  gap: 14px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}
.session-task {
  display: flex;
  gap: 18px;
  padding: 22px;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
  background: var(--lp-surface);
}
.session-task__marker {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  place-items: center;
  border-radius: 50%;
  color: var(--lp-text-tertiary);
  background: var(--lp-surface-subtle);
  font-size: 18px;
}
.session-task__marker--in_progress {
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
}
.session-task__marker--completed {
  color: #25754d;
  background: #e9f6ef;
}
.session-task__body {
  min-width: 0;
  flex: 1;
}
.session-task__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.session-task__heading span {
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 700;
}
.session-task h2 {
  margin: 3px 0 8px;
  color: var(--lp-ink);
  font-size: 18px;
}
.session-task p {
  margin: 0;
  color: var(--lp-text-secondary);
  line-height: 1.7;
}
.session-task small {
  display: block;
  margin-top: 8px;
  color: var(--lp-text-tertiary);
}
@media (max-width: 960px) {
  .session-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 700px) {
  .session-header,
  .session-task__heading {
    align-items: stretch;
    flex-direction: column;
  }
  .session-header__actions {
    align-items: stretch;
    flex-direction: column;
  }
  .learning-content__header,
  .source-excerpt header {
    align-items: stretch;
    flex-direction: column;
  }
  .learning-content__header small {
    text-align: left;
  }
}
</style>
