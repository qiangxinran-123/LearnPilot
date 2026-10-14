import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue';

import {
  fetchKnowledgeBuildStatus,
  fetchKnowledgeModel,
  startKnowledgeBuild,
} from '@/services/knowledge';
import { normalizeApiError } from '@/services/http';
import type { KnowledgeBuildStatus, KnowledgeModelResponse } from '@/types/knowledge';

type LoadState = 'loading' | 'ready' | 'error';
const POLL_INTERVAL_MS = 2500;

export function useCourseKnowledgeWorkspace(courseId: Ref<number>) {
  const status = ref<KnowledgeBuildStatus | null>(null);
  const model = ref<KnowledgeModelResponse | null>(null);
  const statusState = ref<LoadState>('loading');
  const modelState = ref<LoadState>('loading');
  const statusError = ref('');
  const modelError = ref('');
  const buildError = ref('');
  const submitting = ref(false);
  let statusRequest = 0;
  let modelRequest = 0;
  let lifecycle = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;

  const isRunning = computed(() => submitting.value || status.value?.state === 'running');

  function clearPoll(): void {
    if (timer) clearTimeout(timer);
    timer = undefined;
  }

  function schedulePoll(epoch: number): void {
    clearPoll();
    if (disposed || epoch !== lifecycle || status.value?.state !== 'running') return;
    timer = setTimeout(() => {
      void refreshStatus(epoch);
    }, POLL_INTERVAL_MS);
  }

  async function refreshModel(epoch = lifecycle): Promise<void> {
    const request = ++modelRequest;
    modelState.value = model.value ? 'ready' : 'loading';
    modelError.value = '';
    try {
      const response = await fetchKnowledgeModel(courseId.value, { canonicalOnly: true });
      if (disposed || epoch !== lifecycle || request !== modelRequest) return;
      model.value = response;
      modelState.value = 'ready';
    } catch (error: unknown) {
      if (disposed || epoch !== lifecycle || request !== modelRequest) return;
      modelError.value = normalizeApiError(error).message;
      modelState.value = model.value ? 'ready' : 'error';
    }
  }

  async function refreshStatus(epoch = lifecycle): Promise<void> {
    const request = ++statusRequest;
    statusState.value = status.value ? 'ready' : 'loading';
    statusError.value = '';
    try {
      const response = await fetchKnowledgeBuildStatus(courseId.value);
      if (disposed || epoch !== lifecycle || request !== statusRequest) return;
      const wasRunning = status.value?.state === 'running';
      status.value = response;
      statusState.value = 'ready';
      if (response.state === 'running') {
        schedulePoll(epoch);
      } else {
        clearPoll();
        if (wasRunning) void refreshModel(epoch);
      }
    } catch (error: unknown) {
      if (disposed || epoch !== lifecycle || request !== statusRequest) return;
      statusError.value = normalizeApiError(error).message;
      statusState.value = status.value ? 'ready' : 'error';
      // A temporary network failure must not make a persisted run disappear.
      if (status.value?.state === 'running') schedulePoll(epoch);
    }
  }

  async function refresh(): Promise<void> {
    const epoch = lifecycle;
    await Promise.all([refreshStatus(epoch), refreshModel(epoch)]);
  }

  async function startBuild(): Promise<boolean> {
    if (isRunning.value || !status.value?.can_build) return false;
    const epoch = lifecycle;
    submitting.value = true;
    buildError.value = '';
    try {
      await startKnowledgeBuild(courseId.value);
      if (disposed || epoch !== lifecycle) return false;
      await refreshStatus(epoch);
      return true;
    } catch (error: unknown) {
      if (!disposed && epoch === lifecycle) {
        buildError.value = normalizeApiError(error).message;
        await refreshStatus(epoch);
      }
      return false;
    } finally {
      if (!disposed && epoch === lifecycle) submitting.value = false;
    }
  }

  watch(
    courseId,
    () => {
      lifecycle += 1;
      clearPoll();
      statusRequest += 1;
      modelRequest += 1;
      status.value = null;
      model.value = null;
      statusState.value = 'loading';
      modelState.value = 'loading';
      statusError.value = '';
      modelError.value = '';
      buildError.value = '';
      submitting.value = false;
      if (Number.isInteger(courseId.value) && courseId.value > 0) void refresh();
    },
    { immediate: true },
  );

  onBeforeUnmount(() => {
    disposed = true;
    lifecycle += 1;
    clearPoll();
    statusRequest += 1;
    modelRequest += 1;
  });

  return {
    status,
    model,
    statusState,
    modelState,
    statusError,
    modelError,
    buildError,
    isRunning,
    refresh,
    refreshStatus,
    refreshModel,
    startBuild,
  };
}
