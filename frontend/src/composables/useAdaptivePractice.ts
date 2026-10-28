import { ref } from 'vue';

import { answerPracticeQuestion, nextPracticeQuestion } from '@/services/learningSessions';
import { normalizeApiError } from '@/services/http';
import type { AdaptivePractice } from '@/types/learningSession';

export function useAdaptivePractice() {
  const practice = ref<AdaptivePractice | null>(null);
  const isLoading = ref(false);
  const isSubmitting = ref(false);
  const errorMessage = ref('');
  let activeSessionId: number | null = null;
  let requestVersion = 0;

  function clear(): void {
    requestVersion += 1;
    activeSessionId = null;
    practice.value = null;
    errorMessage.value = '';
    isLoading.value = false;
    isSubmitting.value = false;
  }

  async function loadNext(sessionId: number): Promise<boolean> {
    if (isLoading.value || isSubmitting.value) return false;
    const version = ++requestVersion;
    activeSessionId = sessionId;
    isLoading.value = true;
    errorMessage.value = '';
    try {
      const result = await nextPracticeQuestion(sessionId);
      if (version !== requestVersion || activeSessionId !== sessionId) return false;
      practice.value = result;
      return true;
    } catch (error: unknown) {
      if (version === requestVersion && activeSessionId === sessionId) {
        errorMessage.value = normalizeApiError(error).message;
      }
      return false;
    } finally {
      if (version === requestVersion) isLoading.value = false;
    }
  }

  async function answer(sessionId: number, questionId: number, selected: string[]): Promise<boolean> {
    if (isLoading.value || isSubmitting.value || activeSessionId !== sessionId) return false;
    isSubmitting.value = true;
    errorMessage.value = '';
    try {
      const result = await answerPracticeQuestion(sessionId, questionId, selected);
      if (activeSessionId !== sessionId) return false;
      practice.value = result;
      return true;
    } catch (error: unknown) {
      if (activeSessionId === sessionId) errorMessage.value = normalizeApiError(error).message;
      return false;
    } finally {
      isSubmitting.value = false;
    }
  }

  return { answer, clear, errorMessage, isLoading, isSubmitting, loadNext, practice };
}
