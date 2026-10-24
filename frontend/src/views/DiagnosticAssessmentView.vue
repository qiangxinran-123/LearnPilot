<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Check, Warning } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { useDiagnosticAssessment } from '@/composables/useDiagnosticAssessment';

const route = useRoute();
const router = useRouter();
const assessmentId = computed(() => Number(route.params.assessmentId));
const submitDialogOpen = ref(false);
const exitDialogOpen = ref(false);
const isExiting = ref(false);
const pendingDestination = ref('/diagnose');
let allowNavigation = false;
const diagnostic = useDiagnosticAssessment(assessmentId);
const progressPercentage = computed(() => {
  const total = diagnostic.assessment.value?.question_count ?? 0;
  return total ? Math.round((diagnostic.confirmedAnsweredCount.value / total) * 100) : 0;
});
const currentAnswer = computed(() => diagnostic.answers[diagnostic.currentQuestion.value?.assessment_question_id ?? -1] ?? []);

function typeLabel(type: string): string {
  return { single_choice: '单选题', true_false: '判断题', multiple_choice: '多选题' }[type] ?? type;
}
function saveLabel(questionId: number): string {
  return { idle: '未作答', unsaved: '未保存', saving: '保存中', saved: '已保存', failed: '保存失败' }[
    diagnostic.saveStates[questionId] ?? 'idle'
  ];
}
function isPendingSave(questionId: number): boolean {
  const status = diagnostic.saveStates[questionId] ?? 'idle';
  return status === 'unsaved' || status === 'saving';
}
function selectSingle(value: string | number | boolean | undefined): void {
  const question = diagnostic.currentQuestion.value;
  if (question && typeof value === 'string') diagnostic.updateAnswer(question.assessment_question_id, [value]);
}
function selectMultiple(value: unknown): void {
  const question = diagnostic.currentQuestion.value;
  if (question && Array.isArray(value) && value.every((item) => typeof item === 'string')) {
    diagnostic.updateAnswer(question.assessment_question_id, value);
  }
}
async function confirmSubmit(): Promise<void> {
  const succeeded = await diagnostic.submit();
  if (succeeded) { submitDialogOpen.value = false; ElMessage.success('诊断已提交。'); }
  else if (diagnostic.errorMessage.value) ElMessage.error(diagnostic.errorMessage.value);
}

function requestExit(destination = '/diagnose'): void {
  if (!diagnostic.assessment.value || diagnostic.assessment.value.status === 'submitted') {
    void router.push(destination);
    return;
  }
  pendingDestination.value = destination;
  exitDialogOpen.value = true;
}
function continueAnswering(): void {
  exitDialogOpen.value = false;
}
function completeExit(): void {
  allowNavigation = true;
  exitDialogOpen.value = false;
  void router.push(pendingDestination.value);
}
async function saveAndExit(): Promise<void> {
  if (isExiting.value) return;
  isExiting.value = true;
  const succeeded = await diagnostic.saveDraftForExit();
  isExiting.value = false;
  if (succeeded) completeExit();
  else ElMessage.error('保存失败，请重试。当前作答尚未确认保存。');
}
async function discardAndExit(): Promise<void> {
  if (isExiting.value) return;
  isExiting.value = true;
  const succeeded = await diagnostic.discardDraft();
  isExiting.value = false;
  if (succeeded) completeExit();
  else ElMessage.error('未能放弃本次作答，请重试。');
}
function handleBeforeUnload(event: BeforeUnloadEvent): void {
  if (
    diagnostic.assessment.value?.status === 'in_progress'
    && diagnostic.hasPendingDraftChanges.value
  ) {
    event.preventDefault();
    event.returnValue = '';
  }
}
onBeforeRouteLeave((to) => {
  if (
    allowNavigation
    || diagnostic.assessment.value?.status !== 'in_progress'
    || diagnostic.result.value
  ) return true;
  pendingDestination.value = to.fullPath;
  exitDialogOpen.value = true;
  return false;
});
onMounted(() => window.addEventListener('beforeunload', handleBeforeUnload));
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload));
void diagnostic.load();
</script>

<template>
  <section class="page-view assessment-page">
    <button class="back-link" type="button" @click="requestExit()"><el-icon><ArrowLeft /></el-icon>退出诊断</button>
    <LoadingBlock v-if="diagnostic.state.value === 'loading'" :count="2" />
    <ErrorState v-else-if="diagnostic.state.value === 'error'" title="诊断加载失败" :message="diagnostic.errorMessage.value" @retry="diagnostic.load" />
    <template v-else-if="diagnostic.assessment.value">
      <section v-if="diagnostic.result.value" class="completion-card" aria-live="polite">
        <div class="completion-icon"><el-icon><Check /></el-icon></div>
        <p class="eyebrow">ASSESSMENT COMPLETE</p><h1>诊断已完成</h1><p>{{ diagnostic.result.value.course_name }}</p>
        <dl class="score-grid">
          <div><dt>题目</dt><dd>{{ diagnostic.result.value.total_questions }}</dd></div>
          <div><dt>正确</dt><dd>{{ diagnostic.result.value.correct_questions }}</dd></div>
          <div><dt>正确率</dt><dd>{{ Math.round(diagnostic.result.value.accuracy * 100) }}%</dd></div>
        </dl>
        <p class="completion-note">可查看本次知识点表现、错题解析与课程资料来源。</p>
        <div class="completion-actions"><el-button type="primary" @click="router.push({ name: 'diagnostic-report', params: { assessmentId } })">查看诊断报告</el-button><el-button @click="router.push('/diagnose')">返回诊断记录</el-button></div>
      </section>

      <template v-else>
        <header class="assessment-header">
          <div><p class="eyebrow">INITIAL DIAGNOSTIC</p><h1>{{ diagnostic.assessment.value.course_name }}</h1></div>
          <div class="assessment-progress"><span>{{ diagnostic.confirmedAnsweredCount.value }} / {{ diagnostic.assessment.value.question_count }} 已保存</span><el-progress :percentage="progressPercentage" :show-text="false" :stroke-width="7" /></div>
        </header>
        <div class="assessment-layout">
          <aside class="question-navigator" aria-label="题号导航">
            <div class="navigator-title"><h2>题目导航</h2><span>点击切换</span></div>
            <div class="number-grid">
              <button v-for="(question, index) in diagnostic.assessment.value.questions" :key="question.assessment_question_id" type="button"
                :class="{ current: index === diagnostic.currentIndex.value, answered: (diagnostic.confirmedAnswers[question.assessment_question_id]?.length ?? 0) > 0, pending: isPendingSave(question.assessment_question_id) }"
                :aria-label="`第 ${index + 1} 题`" @click="diagnostic.goTo(index)">{{ index + 1 }}</button>
            </div>
            <div class="navigator-legend"><span><i class="answered"></i>已答</span><span><i></i>未答</span></div>
          </aside>
          <main v-if="diagnostic.currentQuestion.value" class="question-card">
            <div class="question-meta"><span>第 {{ diagnostic.currentIndex.value + 1 }} 题</span><span class="type-badge">{{ typeLabel(diagnostic.currentQuestion.value.question_type) }}</span><span class="save-indicator" :class="`save-indicator--${diagnostic.saveStates[diagnostic.currentQuestion.value.assessment_question_id] ?? 'idle'}`">{{ saveLabel(diagnostic.currentQuestion.value.assessment_question_id) }}</span></div>
            <h2>{{ diagnostic.currentQuestion.value.stem }}</h2>
            <el-radio-group v-if="diagnostic.currentQuestion.value.question_type !== 'multiple_choice'" :model-value="currentAnswer[0]" :disabled="diagnostic.isReadOnly.value" class="answer-options" @change="selectSingle">
              <el-radio v-for="option in diagnostic.currentQuestion.value.options" :key="option.key" :value="option.key" border><span class="option-key">{{ option.key }}</span>{{ option.text }}</el-radio>
            </el-radio-group>
            <el-checkbox-group v-else :model-value="currentAnswer" :disabled="diagnostic.isReadOnly.value" class="answer-options" @change="selectMultiple">
              <el-checkbox v-for="option in diagnostic.currentQuestion.value.options" :key="option.key" :value="option.key" border><span class="option-key">{{ option.key }}</span>{{ option.text }}</el-checkbox>
            </el-checkbox-group>
            <div v-if="diagnostic.saveStates[diagnostic.currentQuestion.value.assessment_question_id] === 'failed'" class="save-error" role="alert"><span>答案保存失败，请检查网络后重试。</span><el-button size="small" @click="diagnostic.retrySave(diagnostic.currentQuestion.value.assessment_question_id)">重试保存</el-button></div>
            <footer class="question-actions">
              <el-button :disabled="diagnostic.currentIndex.value === 0" @click="diagnostic.goTo(diagnostic.currentIndex.value - 1)">上一题</el-button>
              <el-button v-if="diagnostic.currentIndex.value < diagnostic.assessment.value.question_count - 1" type="primary" @click="diagnostic.goTo(diagnostic.currentIndex.value + 1)">下一题</el-button>
              <el-button v-else type="primary" @click="submitDialogOpen = true">提交诊断</el-button>
            </footer>
          </main>
        </div>
        <div class="mobile-submit"><el-button type="primary" @click="submitDialogOpen = true">提交诊断</el-button></div>
      </template>
    </template>

    <el-dialog v-model="submitDialogOpen" title="确认提交诊断" width="min(92vw, 460px)" :close-on-click-modal="!diagnostic.isSubmitting.value">
      <div class="submit-summary"><el-icon><Warning /></el-icon><p>共 {{ diagnostic.assessment.value?.question_count }} 题，已答 {{ diagnostic.answeredCount.value }} 题，未答 {{ diagnostic.unansweredCount.value }} 题。</p></div>
      <p v-if="diagnostic.unansweredCount.value > 0" class="submit-warning">仍有 {{ diagnostic.unansweredCount.value }} 道题未作答，提交后不能修改答案。</p>
      <p>系统会先等待所有答案完成保存，再由后端确定性评分。</p>
      <template #footer><el-button :disabled="diagnostic.isSubmitting.value" @click="submitDialogOpen = false">返回检查</el-button><el-button type="primary" :loading="diagnostic.isSubmitting.value" @click="confirmSubmit">确认提交</el-button></template>
    </el-dialog>

    <el-dialog
      v-model="exitDialogOpen"
      title="确定退出本次诊断？"
      width="min(92vw, 500px)"
      :close-on-click-modal="!isExiting"
      :close-on-press-escape="!isExiting"
      :show-close="!isExiting"
    >
      <p class="exit-description">你可以保存当前作答进度，下次继续完成；也可以放弃本次尚未提交的答案。</p>
      <template #footer>
        <div class="exit-actions">
          <el-button :disabled="isExiting" @click="continueAnswering">继续答题</el-button>
          <el-button type="danger" plain :disabled="isExiting" @click="discardAndExit">放弃本次作答</el-button>
          <el-button type="primary" :loading="isExiting" @click="saveAndExit">保存并退出</el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.back-link { display: inline-flex; align-items: center; gap: 7px; margin-bottom: 20px; padding: 0; border: 0; color: var(--lp-text-secondary); background: transparent; cursor: pointer; }
.eyebrow { margin: 0 0 5px; color: var(--lp-primary); font-size: 11px; font-weight: 750; letter-spacing: .14em; }
.assessment-page { min-width: 0; max-width: 100%; }
.assessment-header { display: flex; min-width: 0; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.assessment-header > div { min-width: 0; }
.assessment-header h1 { margin: 0; color: var(--lp-ink); font-size: 25px; overflow-wrap: anywhere; }
.assessment-progress { width: min(360px, 40vw); color: var(--lp-text-secondary); font-size: 12px; }
.assessment-progress span { display: block; margin-bottom: 7px; text-align: right; }
.assessment-layout { display: grid; min-width: 0; max-width: 100%; grid-template-columns: 210px minmax(0, 1fr); gap: 20px; }
.question-navigator, .question-card { border: 1px solid var(--lp-border); border-radius: var(--lp-radius-lg); background: var(--lp-surface); box-shadow: var(--lp-shadow-sm); }
.question-navigator { align-self: start; padding: 18px; }
.navigator-title { display: flex; align-items: baseline; justify-content: space-between; }
.navigator-title h2 { margin: 0; color: var(--lp-ink); font-size: 15px; }
.navigator-title span { color: var(--lp-text-tertiary); font-size: 11px; }
.number-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 18px 0; }
.number-grid button { aspect-ratio: 1; border: 1px solid var(--lp-border); border-radius: 7px; color: var(--lp-text-secondary); background: #fff; cursor: pointer; }
.number-grid button.answered { border-color: #bcd5f4; color: var(--lp-primary); background: var(--lp-primary-soft); }
.number-grid button.pending { border-style: dashed; }
.number-grid button.current { border-color: var(--lp-primary); color: #fff; background: var(--lp-primary); }
.navigator-legend { display: flex; gap: 14px; color: var(--lp-text-tertiary); font-size: 11px; }
.navigator-legend span { display: flex; align-items: center; gap: 5px; }
.navigator-legend i { width: 8px; height: 8px; border: 1px solid var(--lp-border); border-radius: 2px; }
.navigator-legend i.answered { border-color: #bcd5f4; background: var(--lp-primary-soft); }
.question-card { min-width: 0; max-width: 100%; min-height: 520px; padding: clamp(24px, 4vw, 46px); box-sizing: border-box; }
.question-meta { display: flex; min-width: 0; flex-wrap: wrap; align-items: center; gap: 10px; color: var(--lp-text-secondary); font-size: 12px; }
.type-badge { padding: 3px 8px; border-radius: 999px; color: var(--lp-primary); background: var(--lp-primary-soft); }
.save-indicator { margin-left: auto; }
.save-indicator--saved { color: #287548; }
.save-indicator--failed, .save-indicator--unsaved { color: var(--lp-danger); }
.question-card h2 { min-width: 0; max-width: 100%; margin: 24px 0 28px; color: var(--lp-ink); font-size: clamp(20px, 2vw, 25px); font-weight: 620; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.answer-options { display: grid; min-width: 0; max-width: 100%; gap: 12px; }
.answer-options :deep(.el-radio), .answer-options :deep(.el-checkbox) { width: 100%; min-width: 0; max-width: 100%; min-height: 54px; height: auto; margin: 0; padding: 13px 16px; align-items: flex-start; box-sizing: border-box; white-space: normal; }
.answer-options :deep(.el-radio__input), .answer-options :deep(.el-checkbox__input) { flex: 0 0 auto; margin-top: 3px; }
.answer-options :deep(.el-radio__label), .answer-options :deep(.el-checkbox__label) { min-width: 0; max-width: 100%; padding-right: 0; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.option-key { display: inline-grid; width: 24px; height: 24px; margin-right: 9px; place-items: center; border-radius: 5px; color: var(--lp-text-secondary); background: var(--lp-surface-subtle); font-size: 12px; font-weight: 700; }
.save-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; padding: 10px 12px; border-radius: 7px; color: var(--lp-danger); background: var(--lp-danger-soft); }
.question-actions { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin-top: 38px; padding-top: 18px; border-top: 1px solid var(--lp-border); }
.mobile-submit { display: none; }
.completion-card { max-width: 680px; margin: 5vh auto; padding: 48px; border: 1px solid var(--lp-border); border-radius: var(--lp-radius-lg); background: var(--lp-surface); text-align: center; box-shadow: var(--lp-shadow-md); }
.completion-icon { display: grid; width: 48px; height: 48px; margin: 0 auto 18px; place-items: center; border-radius: 50%; color: #287548; background: #eaf7ef; font-size: 25px; }
.completion-card h1 { margin-bottom: 8px; color: var(--lp-ink); }
.completion-card > p:not(.eyebrow) { color: var(--lp-text-secondary); }
.score-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 28px 0; }
.score-grid div { padding: 18px; border: 1px solid var(--lp-border); border-radius: var(--lp-radius-md); }
.score-grid dt { color: var(--lp-text-tertiary); font-size: 12px; }
.score-grid dd { margin: 6px 0 0; color: var(--lp-ink); font-size: 25px; font-weight: 700; }
.completion-note { padding-top: 18px; border-top: 1px solid var(--lp-border); }
.completion-actions { display:flex; justify-content:center; gap:10px; flex-wrap:wrap; }
.submit-summary { display: flex; align-items: center; gap: 10px; color: var(--lp-ink); }
.submit-summary p { margin: 0; font-weight: 600; }
.submit-summary .el-icon { color: #b47a20; font-size: 22px; }
.submit-warning { color: #8a5b14; }
.exit-description { margin: 0; color: var(--lp-text-secondary); line-height: 1.7; }
.exit-actions { display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
@media (max-width: 900px) { .assessment-layout { grid-template-columns: 1fr; } .question-navigator { order: 2; } .number-grid { grid-template-columns: repeat(10, 1fr); } }
@media (max-width: 620px) { .assessment-header { align-items: stretch; flex-direction: column; } .assessment-progress { width: 100%; } .assessment-progress span { text-align: left; } .number-grid { grid-template-columns: repeat(5, 1fr); } .question-card { min-height: 0; padding: 22px 18px; } .mobile-submit { display: flex; justify-content: flex-end; margin-top: 14px; } .score-grid { grid-template-columns: 1fr; } .completion-card { padding: 30px 20px; } }
</style>
