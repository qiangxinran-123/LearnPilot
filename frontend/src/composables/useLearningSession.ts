import { ref } from 'vue';

import { createLearningSession, fetchActiveLearningSession } from '@/services/learningSessions';
import { normalizeApiError } from '@/services/http';
import type { LearningSession, LearningSessionCreateRequest } from '@/types/learningSession';

export function useLearningSession() {
  const activeSession = ref<LearningSession | null>(null);
  const isLoading = ref(false);
  const isCreating = ref(false);
  const errorMessage = ref('');
  const activeLoadFailed = ref(false);
  let requestVersion = 0;

  async function loadActive(courseId: number | null): Promise<void> {
    const version = ++requestVersion;
    activeSession.value = null;
    errorMessage.value = '';
    activeLoadFailed.value = false;
    if (!courseId) {
      isLoading.value = false;
      return;
    }
    isLoading.value = true;
    try {
      const response = await fetchActiveLearningSession(courseId);
      if (version === requestVersion) activeSession.value = response.session;
    } catch {
      if (version === requestVersion) {
        activeLoadFailed.value = true;
        errorMessage.value = '学习会话加载失败，请重试；学习推荐仍可查看。';
      }
    } finally {
      if (version === requestVersion) isLoading.value = false;
    }
  }

  async function start(payload: LearningSessionCreateRequest): Promise<LearningSession | null> {
    if (isCreating.value) return null;
    isCreating.value = true;
    errorMessage.value = '';
    try {
      const session = await createLearningSession(payload);
      activeSession.value = session;
      return session;
    } catch (error: unknown) {
      const apiError = normalizeApiError(error);
      errorMessage.value =
        apiError.status !== undefined && apiError.status >= 500
          ? '学习会话暂时不可用，请稍后重试。'
          : apiError.message;
      return null;
    } finally {
      isCreating.value = false;
    }
  }

  return { activeSession, activeLoadFailed, errorMessage, isCreating, isLoading, loadActive, start };
}
