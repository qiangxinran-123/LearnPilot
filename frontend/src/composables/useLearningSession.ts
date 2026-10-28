import { ref } from 'vue';

import { createLearningSession, fetchActiveLearningSession } from '@/services/learningSessions';
import { normalizeApiError } from '@/services/http';
import type { LearningSession, LearningSessionCreateRequest } from '@/types/learningSession';

export function useLearningSession() {
  const activeSession = ref<LearningSession | null>(null);
  const isLoading = ref(false);
  const isCreating = ref(false);
  const errorMessage = ref('');
  let requestVersion = 0;

  async function loadActive(courseId: number | null): Promise<void> {
    const version = ++requestVersion;
    activeSession.value = null;
    errorMessage.value = '';
    if (!courseId) return;
    isLoading.value = true;
    try {
      const response = await fetchActiveLearningSession(courseId);
      if (version === requestVersion) activeSession.value = response.session;
    } catch (error: unknown) {
      if (version === requestVersion) errorMessage.value = normalizeApiError(error).message;
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
      errorMessage.value = normalizeApiError(error).message;
      return null;
    } finally {
      isCreating.value = false;
    }
  }

  return { activeSession, errorMessage, isCreating, isLoading, loadActive, start };
}
