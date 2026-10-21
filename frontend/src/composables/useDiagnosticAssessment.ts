import { computed, reactive, ref, type Ref } from 'vue';

import {
  fetchAssessment,
  fetchAssessmentResult,
  saveAssessmentResponse,
  startAssessment,
  submitAssessment,
} from '@/services/diagnostics';
import { normalizeApiError } from '@/services/http';
import type {
  AnswerSaveState,
  Assessment,
  DiagnosticResult,
} from '@/types/diagnostic';

export function useDiagnosticAssessment(assessmentId: Ref<number>) {
  const assessment = ref<Assessment | null>(null);
  const result = ref<DiagnosticResult | null>(null);
  const state = ref<'loading' | 'ready' | 'error'>('loading');
  const errorMessage = ref('');
  const isSubmitting = ref(false);
  const editingLocked = ref(false);
  const currentIndex = ref(0);
  const answers = reactive<Record<number, string[]>>({});
  const confirmedAnswers = reactive<Record<number, string[]>>({});
  const saveStates = reactive<Record<number, AnswerSaveState>>({});
  const revisions = new Map<number, number>();
  const saveChains = new Map<number, Promise<void>>();

  const currentQuestion = computed(() => assessment.value?.questions[currentIndex.value] ?? null);
  const answeredCount = computed(() =>
    assessment.value?.questions.filter((item) => (answers[item.assessment_question_id]?.length ?? 0) > 0).length ?? 0,
  );
  const confirmedAnsweredCount = computed(() =>
    assessment.value?.questions.filter(
      (item) => (confirmedAnswers[item.assessment_question_id]?.length ?? 0) > 0,
    ).length ?? 0,
  );
  const unansweredCount = computed(() => (assessment.value?.question_count ?? 0) - answeredCount.value);
  const isReadOnly = computed(
    () => editingLocked.value || assessment.value?.status === 'submitted',
  );

  function restore(response: Assessment): void {
    assessment.value = response;
    for (const question of response.questions) {
      const saved = [...(question.saved_answer ?? [])];
      answers[question.assessment_question_id] = saved;
      confirmedAnswers[question.assessment_question_id] = saved;
      saveStates[question.assessment_question_id] = saved.length ? 'saved' : 'idle';
    }
    const stored = Number(sessionStorage.getItem(`diagnostic:${response.id}:question`));
    currentIndex.value = Number.isInteger(stored)
      ? Math.min(Math.max(stored, 0), Math.max(response.question_count - 1, 0))
      : 0;
  }

  async function load(): Promise<void> {
    state.value = 'loading';
    errorMessage.value = '';
    try {
      let response = await fetchAssessment(assessmentId.value);
      if (response.status === 'ready') response = await startAssessment(assessmentId.value);
      restore(response);
      if (response.status === 'submitted') {
        editingLocked.value = true;
        result.value = await fetchAssessmentResult(assessmentId.value);
      }
      state.value = 'ready';
    } catch (error: unknown) {
      state.value = 'error';
      errorMessage.value = normalizeApiError(error).message;
    }
  }

  function goTo(index: number): void {
    if (!assessment.value) return;
    currentIndex.value = Math.min(Math.max(index, 0), Math.max(assessment.value.question_count - 1, 0));
    sessionStorage.setItem(`diagnostic:${assessment.value.id}:question`, String(currentIndex.value));
  }

  function updateAnswer(questionId: number, selectedOptions: string[]): void {
    if (isReadOnly.value) return;
    answers[questionId] = [...new Set(selectedOptions)];
    saveStates[questionId] = 'unsaved';
    const revision = (revisions.get(questionId) ?? 0) + 1;
    revisions.set(questionId, revision);
    queueSave(questionId, revision, [...answers[questionId]]);
  }

  function queueSave(questionId: number, revision: number, selectedOptions: string[]): void {
    const previous = saveChains.get(questionId) ?? Promise.resolve();
    const task = previous.then(async () => {
      if (assessment.value?.status !== 'in_progress') return;
      saveStates[questionId] = 'saving';
      try {
        const saved = await saveAssessmentResponse(assessment.value.id, questionId, selectedOptions);
        confirmedAnswers[questionId] = [...saved.selected_options];
        if (revisions.get(questionId) === revision) saveStates[questionId] = 'saved';
      } catch (error: unknown) {
        if (revisions.get(questionId) === revision) saveStates[questionId] = 'failed';
        throw error;
      }
    });
    const settled = task.catch(() => undefined).finally(() => {
      if (saveChains.get(questionId) === settled) saveChains.delete(questionId);
    });
    saveChains.set(questionId, settled);
  }

  function retrySave(questionId: number): void {
    if (saveStates[questionId] !== 'failed') return;
    const revision = (revisions.get(questionId) ?? 0) + 1;
    revisions.set(questionId, revision);
    saveStates[questionId] = 'unsaved';
    queueSave(questionId, revision, [...(answers[questionId] ?? [])]);
  }

  async function flushPendingSaves(): Promise<boolean> {
    while (saveChains.size) await Promise.all([...saveChains.values()]);
    return !Object.values(saveStates).some((item) => item === 'failed' || item === 'unsaved');
  }

  async function submit(): Promise<boolean> {
    if (!assessment.value || assessment.value.status === 'submitted') return true;
    editingLocked.value = true;
    isSubmitting.value = true;
    errorMessage.value = '';
    try {
      if (!(await flushPendingSaves())) {
        errorMessage.value = '仍有答案未保存，请重试保存后再提交。';
        return false;
      }
      result.value = await submitAssessment(assessment.value.id);
      assessment.value.status = 'submitted';
      assessment.value.submitted_at = result.value.submitted_at;
      return true;
    } catch (error: unknown) {
      try {
        const reconciled = await fetchAssessment(assessment.value.id);
        restore(reconciled);
        if (reconciled.status === 'submitted') {
          result.value = await fetchAssessmentResult(reconciled.id);
          return true;
        }
      } catch {
        // Keep the original safe user-facing error when reconciliation is unavailable.
      }
      errorMessage.value = normalizeApiError(error).message;
      return false;
    } finally {
      isSubmitting.value = false;
      editingLocked.value = assessment.value?.status === 'submitted';
    }
  }

  return {
    assessment,
    result,
    state,
    errorMessage,
    isSubmitting,
    answers,
    confirmedAnswers,
    saveStates,
    currentIndex,
    currentQuestion,
    answeredCount,
    confirmedAnsweredCount,
    unansweredCount,
    isReadOnly,
    load,
    goTo,
    updateAnswer,
    retrySave,
    flushPendingSaves,
    submit,
  };
}
