<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { DocumentChecked, RefreshRight, WarningFilled } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import {
  approveDiagnosticQuestion,
  fetchDiagnosticQuestions,
  fetchQuestionBankReadiness,
  prepareCourseDiagnosticQuestions,
  rejectDiagnosticQuestion,
} from '@/services/diagnostics';
import { normalizeApiError } from '@/services/http';
import { fetchKnowledgeBuildStatus, startKnowledgeBuild } from '@/services/knowledge';
import type {
  QuestionBankItem,
  QuestionBankReadiness,
  QuestionDifficulty,
  QuestionValidationStatus,
} from '@/types/diagnostic';
import type { KnowledgeBuildStatus } from '@/types/knowledge';

const props = defineProps<{ courseId: number; courseName: string }>();
const emit = defineEmits<{ start: []; knowledge: [] }>();
const state = ref<'loading' | 'ready' | 'error'>('loading');
const errorMessage = ref('');
const readiness = ref<QuestionBankReadiness | null>(null);
const questions = ref<QuestionBankItem[]>([]);
const knowledgeStatus = ref<KnowledgeBuildStatus | null>(null);
const preparationOpen = ref(false);
const synchronizationOpen = ref(false);
const questionBankOpen = ref(false);
const reviewQuestion = ref<QuestionBankItem | null>(null);
const isPreparing = ref(false);
const reviewingAction = ref<'approve' | 'reject' | null>(null);
const actionError = ref('');
const synchronizationState = ref<'idle' | 'running' | 'completed' | 'partial' | 'failed'>('idle');
const synchronizationError = ref('');
const synchronizationResult = ref<{
  addedNodes: number;
  currentNodes: number;
  generatedQuestions: number;
  failedQuestions: number;
} | null>(null);
let requestVersion = 0;
let disposed = false;

const missingCoverage = computed(() =>
  Math.max((readiness.value?.total_core_nodes ?? 0) - (readiness.value?.covered_core_nodes ?? 0), 0),
);
const hasPreparationTargets = computed(() =>
  Boolean(readiness.value?.required_nodes.some((node) => !node.has_validated_question && !node.has_pending_question)),
);
const preparationLabel = computed(() => readiness.value?.validated_count === 0 ? '准备诊断' : '补充诊断题');

function statusLabel(status: QuestionValidationStatus): string {
  return { pending: '待审核', validated: '已通过', rejected: '已拒绝' }[status];
}
function typeLabel(type: QuestionBankItem['question_type']): string {
  return { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题' }[type];
}
function difficultyLabel(difficulty: QuestionDifficulty): string {
  return { easy: '基础', medium: '中等', hard: '进阶' }[difficulty];
}
function friendlyError(error: unknown): string {
  const normalized = normalizeApiError(error);
  const messages: Record<string, string> = {
    AI_NOT_CONFIGURED: '当前尚未配置题目生成服务，请联系维护人员完成配置。',
    AI_TIMEOUT: '模型请求超时。请先刷新题库状态，确认是否已有新题，再决定是否重试。',
    AI_RATE_LIMITED: '题目生成服务当前繁忙，请稍后手动重试。',
    AI_PROVIDER_ERROR: '题目生成服务暂时不可用，请稍后手动重试。',
    QUESTION_DUPLICATE: '生成结果与现有题目重复，未保存重复题目。',
    QUESTION_INVALID_STATE: '题目状态已发生变化，请刷新后重新检查。',
    QUESTION_SOURCE_INVALID: '题目关联的课程来源已失效，请刷新后重新检查。',
    KNOWLEDGE_MODEL_NOT_READY: '课程知识结构尚未准备完成。',
  };
  return normalized.code ? (messages[normalized.code] ?? normalized.message) : normalized.message;
}
async function loadQuestionBank(): Promise<void> {
  const request = ++requestVersion;
  const requestedCourseId = props.courseId;
  state.value = 'loading';
  errorMessage.value = '';
  actionError.value = '';
  try {
    const [bank, list, build] = await Promise.all([
      fetchQuestionBankReadiness(requestedCourseId),
      fetchDiagnosticQuestions(requestedCourseId),
      fetchKnowledgeBuildStatus(requestedCourseId),
    ]);
    if (disposed || request !== requestVersion || requestedCourseId !== props.courseId) return;
    readiness.value = bank;
    questions.value = list.questions;
    knowledgeStatus.value = build;
    state.value = 'ready';
    if (build.state === 'running' && synchronizationState.value !== 'running') {
      void monitorExistingKnowledgeBuild(requestedCourseId, request);
    }
  } catch (error: unknown) {
    if (disposed || request !== requestVersion || requestedCourseId !== props.courseId) return;
    state.value = 'error';
    errorMessage.value = friendlyError(error);
  }
}
function waitForNextBuildPoll(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 800));
}
async function waitForKnowledgeBuild(
  courseId: number,
  version: number,
): Promise<KnowledgeBuildStatus | null> {
  while (!disposed && version === requestVersion && courseId === props.courseId) {
    const status = await fetchKnowledgeBuildStatus(courseId);
    if (disposed || version !== requestVersion || courseId !== props.courseId) return null;
    knowledgeStatus.value = status;
    if (status.state !== 'running') return status;
    await waitForNextBuildPoll();
  }
  return null;
}
async function monitorExistingKnowledgeBuild(courseId: number, version: number): Promise<void> {
  try {
    const completed = await waitForKnowledgeBuild(courseId, version);
    if (completed && completed.state !== 'running' && courseId === props.courseId) {
      await loadQuestionBank();
    }
  } catch {
    // The next explicit refresh will surface the durable backend state.
  }
}
async function confirmSynchronization(): Promise<void> {
  if (synchronizationState.value === 'running') return;
  const courseId = props.courseId;
  const version = requestVersion;
  synchronizationState.value = 'running';
  synchronizationError.value = '';
  synchronizationResult.value = null;
  try {
    const job = await startKnowledgeBuild(courseId);
    if (disposed || version !== requestVersion || courseId !== props.courseId) return;
    let completed = knowledgeStatus.value;
    if (job.status === 'running') completed = await waitForKnowledgeBuild(courseId, version);
    else completed = await fetchKnowledgeBuildStatus(courseId);
    if (!completed || disposed || version !== requestVersion || courseId !== props.courseId) return;
    knowledgeStatus.value = completed;
    if (!['ready'].includes(completed.state)) {
      throw new Error(completed.error_message || '课程知识同步未完成，请稍后重试。');
    }

    await loadQuestionBank();
    if (disposed || courseId !== props.courseId) return;
    let generatedQuestions = 0;
    let failedQuestions = 0;
    if (!readiness.value?.can_start && hasPreparationTargets.value) {
      try {
        const preparation = await prepareCourseDiagnosticQuestions(courseId);
        generatedQuestions = preparation.generated_count;
        failedQuestions = preparation.failed_count;
      } catch (error: unknown) {
        synchronizationState.value = 'partial';
        synchronizationError.value = friendlyError(error);
      }
      await loadQuestionBank();
    }
    synchronizationResult.value = {
      addedNodes: completed.last_added_node_count,
      currentNodes: completed.node_count,
      generatedQuestions,
      failedQuestions,
    };
    if (synchronizationState.value !== 'partial') {
      synchronizationState.value = failedQuestions > 0 ? 'partial' : 'completed';
    }
    synchronizationOpen.value = false;
  } catch (error: unknown) {
    if (disposed || courseId !== props.courseId) return;
    synchronizationState.value = 'failed';
    synchronizationError.value = friendlyError(error);
  }
}
async function confirmPreparation(): Promise<void> {
  if (isPreparing.value) return;
  const requestedCourseId = props.courseId;
  const request = requestVersion;
  isPreparing.value = true;
  actionError.value = '';
  try {
    const result = await prepareCourseDiagnosticQuestions(requestedCourseId);
    if (disposed || request !== requestVersion || requestedCourseId !== props.courseId) return;
    preparationOpen.value = false;
    await loadQuestionBank();
    if (result.failed_count > 0) {
      ElMessage.warning(`已生成 ${result.generated_count} 道待审核题，另有 ${result.failed_count} 道未生成。`);
    } else if (result.generated_count > 0) {
      ElMessage.success(`已生成 ${result.generated_count} 道题，请完成审核后开始诊断。`);
    } else {
      ElMessage.info('当前目标节点已有合格题或待审核题，无需重复生成。');
    }
  } catch (error: unknown) {
    actionError.value = friendlyError(error);
  } finally {
    isPreparing.value = false;
  }
}
function openReview(question: QuestionBankItem): void {
  actionError.value = '';
  questionBankOpen.value = false;
  reviewQuestion.value = question;
}
async function submitReview(action: 'approve' | 'reject'): Promise<void> {
  const question = reviewQuestion.value;
  if (!question || question.validation_status !== 'pending' || reviewingAction.value) return;
  reviewingAction.value = action;
  actionError.value = '';
  try {
    if (action === 'approve') await approveDiagnosticQuestion(props.courseId, question.question_id);
    else await rejectDiagnosticQuestion(props.courseId, question.question_id);
    reviewQuestion.value = null;
    await loadQuestionBank();
    ElMessage.success(action === 'approve' ? '题目已审核通过。' : '题目已拒绝。');
  } catch (error: unknown) {
    actionError.value = friendlyError(error);
  } finally {
    reviewingAction.value = null;
  }
}
function closePreparation(open: boolean): void {
  if (!open && !isPreparing.value) preparationOpen.value = false;
}
function closeReview(open: boolean): void {
  if (!open && !reviewingAction.value) reviewQuestion.value = null;
}
watch(() => props.courseId, () => {
  requestVersion += 1;
  readiness.value = null;
  questions.value = [];
  knowledgeStatus.value = null;
  preparationOpen.value = false;
  questionBankOpen.value = false;
  reviewQuestion.value = null;
  synchronizationOpen.value = false;
  synchronizationState.value = 'idle';
  synchronizationError.value = '';
  synchronizationResult.value = null;
  void loadQuestionBank();
}, { immediate: true });
onBeforeUnmount(() => { disposed = true; requestVersion += 1; });
</script>

<template>
  <section class="question-bank" aria-labelledby="question-bank-title">
    <header class="question-bank__header">
      <div><h2 id="question-bank-title">{{ courseName }} · 诊断准备</h2><p>题库按当前课程知识结构规划；新题经人工审核后才会用于诊断。</p></div>
      <el-button v-if="state !== 'loading'" plain :icon="RefreshRight" @click="loadQuestionBank">刷新状态</el-button>
    </header>
    <el-skeleton v-if="state === 'loading'" :rows="5" animated />
    <div v-else-if="state === 'error'" class="question-bank__error" role="alert">
      <el-icon><WarningFilled /></el-icon><div><h3>题库状态加载失败</h3><p>{{ errorMessage }}</p><el-button plain @click="loadQuestionBank">重新加载</el-button></div>
    </div>
    <template v-else-if="readiness">
      <section
        v-if="knowledgeStatus?.needs_update || knowledgeStatus?.state === 'running' || synchronizationResult || synchronizationState === 'failed'"
        class="knowledge-sync"
        :class="{ 'knowledge-sync--partial': synchronizationState === 'partial' || synchronizationState === 'failed' }"
        aria-live="polite"
      >
        <div>
          <h3 v-if="synchronizationState === 'running' || knowledgeStatus?.state === 'running'">正在整理新增知识并更新诊断题……</h3>
          <h3 v-else-if="synchronizationState === 'partial'">课程知识已同步，部分诊断题尚未补充完成</h3>
          <h3 v-else-if="synchronizationState === 'completed'">已同步新增资料</h3>
          <h3 v-else-if="synchronizationState === 'failed'">新增资料同步失败</h3>
          <h3 v-else>检测到新的课程资料</h3>
          <p v-if="synchronizationState === 'idle'">新增资料尚未纳入当前课程知识结构。同步后，LearnPilot 将按真实覆盖缺口补充诊断题。</p>
          <p v-else-if="synchronizationState === 'running'">系统正在执行知识提取、节点复用和关系校验，请勿重复提交。</p>
          <p v-if="synchronizationError" class="question-bank__action-error" role="alert">{{ synchronizationError }}</p>
          <dl v-if="synchronizationResult" class="knowledge-sync__result">
            <div><dt>新增知识点</dt><dd>{{ synchronizationResult.addedNodes }}</dd></div>
            <div><dt>当前知识点</dt><dd>{{ synchronizationResult.currentNodes }}</dd></div>
            <div><dt>新增待审核题</dt><dd>{{ synchronizationResult.generatedQuestions }}</dd></div>
            <div v-if="synchronizationResult.failedQuestions"><dt>未补充题目</dt><dd>{{ synchronizationResult.failedQuestions }}</dd></div>
          </dl>
          <p v-if="knowledgeStatus?.failed_material_count">另有 {{ knowledgeStatus.failed_material_count }} 份资料解析失败，未纳入本次同步。</p>
          <p v-if="knowledgeStatus?.pending_parse_material_count">另有 {{ knowledgeStatus.pending_parse_material_count }} 份资料尚未解析完成。</p>
        </div>
        <el-button
          v-if="knowledgeStatus?.needs_update || synchronizationState === 'failed' || synchronizationState === 'partial'"
          type="primary"
          :loading="synchronizationState === 'running' || knowledgeStatus?.state === 'running'"
          :disabled="synchronizationState === 'running' || knowledgeStatus?.state === 'running'"
          @click="synchronizationOpen = true"
        >{{ synchronizationState === 'partial' ? '继续补充题目' : '同步新增资料并更新诊断' }}</el-button>
      </section>
      <div class="question-bank__summary" :class="{ 'question-bank__summary--ready': readiness.can_start }">
        <div class="question-bank__status"><el-icon><DocumentChecked /></el-icon><div>
          <strong>{{ readiness.can_start ? '诊断已就绪' : '题库尚需准备' }}</strong>
          <p v-if="readiness.can_start">当前题量与知识点覆盖满足诊断启动条件。</p>
          <p v-else-if="readiness.total_core_nodes === 0">当前课程还没有可诊断的知识结构。</p>
          <p v-else>至少需要 {{ readiness.minimum_required }} 道合格题，并满足对应知识点覆盖要求。</p>
        </div></div>
        <dl class="question-bank__metrics">
          <div><dt>有效题目</dt><dd>{{ readiness.validated_count }}</dd></div>
          <div><dt>知识点覆盖</dt><dd>{{ readiness.covered_core_nodes }} / {{ readiness.total_core_nodes }}</dd></div>
          <div><dt>尚未覆盖</dt><dd>{{ missingCoverage }}</dd></div>
          <div><dt>待人工审核</dt><dd>{{ readiness.pending_count }}</dd></div>
        </dl>
        <div class="question-bank__primary-action">
          <el-button v-if="readiness.can_start" type="primary" size="large" @click="emit('start')">开始诊断</el-button>
          <el-button v-else-if="readiness.total_core_nodes === 0" type="primary" plain @click="emit('knowledge')">前往课程知识结构</el-button>
          <el-button v-else-if="hasPreparationTargets" type="primary" size="large" :disabled="isPreparing" @click="preparationOpen = true">{{ preparationLabel }}</el-button>
          <p v-else-if="readiness.pending_count > 0">请先审核下方待处理题目，审核结果会更新诊断准备状态。</p>
        </div>
      </div>
      <p v-if="actionError" class="question-bank__action-error" role="alert">{{ actionError }}</p>
      <section v-if="readiness.required_nodes.length" class="question-bank__coverage" aria-labelledby="coverage-title">
        <h3 id="coverage-title">当前覆盖目标</h3><p>顺序与范围来自后端组卷规则，不按全部知识点机械出题。</p>
        <ul><li v-for="node in readiness.required_nodes" :key="node.knowledge_node_id"><span>{{ node.knowledge_node_name }}</span><el-tag :type="node.has_validated_question ? 'success' : node.has_pending_question ? 'warning' : 'info'" effect="plain">{{ node.has_validated_question ? '已覆盖' : node.has_pending_question ? '待审核' : '待准备' }}</el-tag></li></ul>
      </section>
      <section class="question-bank__records-entry" aria-labelledby="questions-title">
        <div><h3 id="questions-title">题库记录</h3><p>共 {{ questions.length }} 道题；待审核题目不会进入正式诊断。</p></div>
        <el-button plain @click="questionBankOpen = true">查看题库记录</el-button>
      </section>
    </template>

    <el-dialog :model-value="preparationOpen" title="确认准备诊断题" width="min(560px, 92vw)" :close-on-click-modal="!isPreparing" :show-close="!isPreparing" @update:model-value="closePreparation">
      <p><strong>课程：</strong>{{ courseName }}</p><el-alert title="系统将按当前缺失覆盖规划一个受限批次，最多调用真实 AI 生成 4 道题。此操作可能产生模型费用，生成后仍需逐题人工审核。" type="warning" :closable="false" show-icon /><p v-if="actionError" class="question-bank__action-error" role="alert">{{ actionError }}</p>
      <template #footer><el-button :disabled="isPreparing" @click="preparationOpen = false">取消</el-button><el-button type="primary" :loading="isPreparing" @click="confirmPreparation">{{ isPreparing ? '正在准备诊断题' : '确认准备' }}</el-button></template>
    </el-dialog>
    <el-dialog
      v-model="synchronizationOpen"
      title="同步新增资料并更新诊断"
      width="min(580px, 92vw)"
      :close-on-click-modal="synchronizationState !== 'running'"
      :show-close="synchronizationState !== 'running'"
    >
      <p><strong>课程：</strong>{{ courseName }}</p>
      <p>将只处理尚未同步且已成功解析的课程资料，复用现有知识节点，并按题库真实缺口补充待审核题目。</p>
      <el-alert title="知识提取、关系分析和缺口补题可能调用真实 AI 并产生模型费用。系统不会自动批准生成的题目。" type="warning" :closable="false" show-icon />
      <p v-if="synchronizationError" class="question-bank__action-error" role="alert">{{ synchronizationError }}</p>
      <template #footer>
        <el-button :disabled="synchronizationState === 'running'" @click="synchronizationOpen = false">取消</el-button>
        <el-button type="primary" :loading="synchronizationState === 'running'" :disabled="synchronizationState === 'running'" @click="confirmSynchronization">
          {{ synchronizationState === 'running' ? '正在同步' : '确认同步' }}
        </el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="questionBankOpen" :title="`${courseName} · 题库记录`" width="min(860px, 94vw)" destroy-on-close>
      <section class="question-bank__questions question-bank__questions--dialog" aria-label="完整题库记录">
        <article v-for="question in questions" :key="question.question_id" class="question-row"><div><p>{{ question.knowledge_node_name ?? '关联知识点异常' }}</p><h4>{{ question.stem }}</h4></div><el-tag :type="question.validation_status === 'validated' ? 'success' : question.validation_status === 'pending' ? 'warning' : 'info'" effect="plain">{{ statusLabel(question.validation_status) }}</el-tag><el-button plain @click="openReview(question)">{{ question.validation_status === 'pending' ? '查看并审核' : '查看详情' }}</el-button></article>
        <p v-if="questions.length === 0" class="question-bank__empty">当前课程还没有诊断题目。</p>
      </section>
    </el-dialog>
    <el-dialog :model-value="Boolean(reviewQuestion)" title="诊断题审核" width="min(760px, 94vw)" :close-on-click-modal="!reviewingAction" :show-close="!reviewingAction" @update:model-value="closeReview">
      <article v-if="reviewQuestion" class="review-detail">
        <div class="review-detail__meta"><el-tag effect="plain">{{ reviewQuestion.knowledge_node_name ?? '关联知识点异常' }}</el-tag><span>{{ typeLabel(reviewQuestion.question_type) }}</span><span>{{ difficultyLabel(reviewQuestion.difficulty) }}</span><el-tag>{{ statusLabel(reviewQuestion.validation_status) }}</el-tag></div>
        <section><h3>题目</h3><p>{{ reviewQuestion.stem }}</p><ol v-if="reviewQuestion.options.length"><li v-for="option in reviewQuestion.options" :key="option.key"><strong>{{ option.key }}.</strong> {{ option.text }}</li></ol></section>
        <section><h3>正确答案</h3><p>{{ reviewQuestion.correct_answer.join('、') }}</p></section><section><h3>答案解析</h3><p>{{ reviewQuestion.explanation }}</p></section>
        <section><h3>课程来源</h3><article v-for="(source, index) in reviewQuestion.source_refs" :key="`${source.material_id}-${source.source_reference}-${index}`" class="source-ref"><strong>{{ source.material_title ?? '课程资料' }}</strong><p>{{ source.source_reference }}</p><blockquote v-if="source.excerpt">{{ source.excerpt }}</blockquote></article></section>
        <p v-if="actionError" class="question-bank__action-error" role="alert">{{ actionError }}</p>
      </article>
      <template #footer><el-button :disabled="Boolean(reviewingAction)" @click="reviewQuestion = null">关闭</el-button><template v-if="reviewQuestion?.validation_status === 'pending'"><el-button type="danger" plain :loading="reviewingAction === 'reject'" :disabled="Boolean(reviewingAction)" @click="submitReview('reject')">拒绝题目</el-button><el-button type="primary" :loading="reviewingAction === 'approve'" :disabled="Boolean(reviewingAction)" @click="submitReview('approve')">审核通过</el-button></template></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.question-bank { min-height: 300px; }
.question-bank__header, .question-bank__section-heading, .question-bank__records-entry, .question-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.question-bank__header { margin-bottom: 1rem; }
.question-bank__header h2, .question-bank h3, .question-bank h4 { margin: 0; color: var(--lp-ink); }
.question-bank__header p, .question-bank__coverage > p, .question-bank__section-heading p, .question-bank__records-entry p, .question-bank__empty { margin: .35rem 0 0; color: var(--lp-text-secondary); }
.question-bank__error, .question-bank__status { display: flex; align-items: flex-start; gap: .8rem; }
.question-bank__error { padding: 1rem; border: 1px solid #edcfca; border-radius: 12px; color: #8f3c34; background: #fff6f4; }
.question-bank__error h3, .question-bank__error p, .question-bank__status p { margin: 0 0 .4rem; }
.question-bank__summary { padding: 1rem; border: 1px solid #eadfbd; border-radius: 14px; background: #fffbef; }
.knowledge-sync { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:1rem; padding:1rem; border:1px solid #c9ddf5; border-radius:14px; background:#f2f7fd; }
.knowledge-sync--partial { border-color:#ead6aa; background:#fffaf0; }
.knowledge-sync h3, .knowledge-sync p { margin:0; }
.knowledge-sync p { margin-top:.35rem; color:var(--lp-text-secondary); }
.knowledge-sync__result { display:flex; flex-wrap:wrap; gap:.75rem 1.25rem; margin:.8rem 0 0; }
.knowledge-sync__result div { display:flex; gap:.35rem; }.knowledge-sync__result dt { color:var(--lp-text-secondary); }.knowledge-sync__result dd { margin:0; color:var(--lp-ink); font-weight:700; }
.question-bank__summary--ready { border-color: #cde8d6; background: #f1fbf5; }
.question-bank__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; margin: 1rem 0; }
.question-bank__metrics div { padding: .7rem; border-radius: 10px; background: rgb(255 255 255 / 78%); }
.question-bank__metrics dt { color: var(--lp-text-secondary); font-size: .76rem; }
.question-bank__metrics dd { margin: .2rem 0 0; color: var(--lp-ink); font-size: 1.05rem; font-weight: 700; }
.question-bank__primary-action { display: flex; align-items: center; gap: .75rem; }
.question-bank__primary-action p { margin: 0; color: var(--lp-text-secondary); }
.question-bank__coverage, .question-bank__records-entry { margin-top: 1.3rem; }
.question-bank__coverage ul { display: flex; flex-wrap: wrap; gap: .5rem; padding: 0; list-style: none; }
.question-bank__coverage li { display: flex; align-items: center; gap: .5rem; padding: .55rem .7rem; border: 1px solid var(--lp-border); border-radius: 10px; background: var(--lp-surface); }
.question-bank__records-entry { padding-top: 1rem; border-top: 1px solid var(--lp-border); }
.question-bank__questions--dialog { max-height: 62vh; padding-right: .25rem; overflow-y: auto; }
.question-row { margin-top: .65rem; padding: .8rem; border: 1px solid var(--lp-border); border-radius: 12px; background: var(--lp-surface); }
.question-row > div { min-width: 0; flex: 1; }.question-row p { margin: 0; color: var(--lp-primary); font-size: .76rem; font-weight: 700; }.question-row h4 { max-width:100%; margin-top:.25rem; font-size:.92rem; font-weight:600; white-space:pre-wrap; overflow-wrap:anywhere; }
.question-bank__action-error { margin: .85rem 0 0; padding: .7rem .8rem; border-radius: 10px; color: #9b3f37; background: #fff3f1; }
.review-detail { display: grid; min-width:0; gap: 1rem; }.review-detail__meta { display: flex; flex-wrap: wrap; align-items: center; gap: .55rem; }.review-detail section { min-width:0; padding:.8rem; border:1px solid var(--lp-border); border-radius:10px; }.review-detail section h3, .review-detail section p, .review-detail li, .source-ref blockquote { max-width:100%; margin-top:0; white-space:pre-wrap; overflow-wrap:anywhere; }.source-ref { min-width:0; padding:.65rem; background:#f7f9fc; }.source-ref blockquote { margin:.5rem 0 0; color:var(--lp-text-secondary); }
@media (max-width: 720px) { .question-bank__header, .question-bank__records-entry, .question-row, .knowledge-sync { align-items: stretch; flex-direction: column; }.question-bank__metrics { grid-template-columns: repeat(2, 1fr); } }
</style>
