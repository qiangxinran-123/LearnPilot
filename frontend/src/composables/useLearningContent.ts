import { ref } from 'vue';

import { fetchLearningSessionContent } from '@/services/learningSessions';
import { normalizeApiError } from '@/services/http';
import type { LearningContent, LearningSessionTaskPhase } from '@/types/learningSession';

export type LearningContentLoadState = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

export function useLearningContent() {
  const content = ref<LearningContent | null>(null);
  const state = ref<LearningContentLoadState>('idle');
  const errorMessage = ref('');
  let requestVersion = 0;

  function clear(): void {
    requestVersion += 1;
    content.value = null;
    errorMessage.value = '';
    state.value = 'idle';
  }

  async function load(
    sessionId: number,
    phase: LearningSessionTaskPhase = 'concept_learning',
  ): Promise<void> {
    const version = ++requestVersion;
    content.value = null;
    errorMessage.value = '';
    state.value = 'loading';
    try {
      const response = await fetchLearningSessionContent(sessionId, phase);
      if (version !== requestVersion) return;
      content.value = response;
      state.value = response.status;
    } catch (error: unknown) {
      if (version !== requestVersion) return;
      errorMessage.value = normalizeApiError(error).message;
      state.value = 'error';
    }
  }

  return { clear, content, errorMessage, load, state };
}
