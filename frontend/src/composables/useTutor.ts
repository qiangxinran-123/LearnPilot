import { ref } from 'vue';

import { fetchTutorMessages, sendTutorMessage } from '@/services/learningSessions';
import { normalizeApiError } from '@/services/http';
import type {
  TeachingStrategy,
  TutorMessage,
  TutorMessageCreateRequest,
} from '@/types/learningSession';

interface PendingTutorRequest {
  sessionId: number;
  payload: TutorMessageCreateRequest;
  idempotencyKey: string;
}

function requestKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `tutor-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useTutor() {
  const messages = ref<TutorMessage[]>([]);
  const isLoading = ref(false);
  const isSending = ref(false);
  const errorMessage = ref('');
  let requestVersion = 0;
  let activeSessionId: number | null = null;
  let pending: PendingTutorRequest | null = null;

  function clear(): void {
    requestVersion += 1;
    activeSessionId = null;
    messages.value = [];
    errorMessage.value = '';
    isLoading.value = false;
    pending = null;
  }

  async function load(sessionId: number): Promise<void> {
    const version = ++requestVersion;
    activeSessionId = sessionId;
    messages.value = [];
    errorMessage.value = '';
    isLoading.value = true;
    pending = null;
    try {
      const response = await fetchTutorMessages(sessionId);
      if (version === requestVersion) messages.value = response.messages;
    } catch (error: unknown) {
      if (version === requestVersion) errorMessage.value = normalizeApiError(error).message;
    } finally {
      if (version === requestVersion) isLoading.value = false;
    }
  }

  async function send(
    sessionId: number,
    message: string,
    mode: TeachingStrategy,
    retryRequest?: PendingTutorRequest,
  ): Promise<boolean> {
    if (isSending.value || !message.trim()) return false;
    const request =
      retryRequest ??
      ({
        sessionId,
        payload: { message: message.trim(), mode },
        idempotencyKey: requestKey(),
      } satisfies PendingTutorRequest);
    pending = request;
    isSending.value = true;
    errorMessage.value = '';
    try {
      const exchange = await sendTutorMessage(
        request.sessionId,
        request.payload,
        request.idempotencyKey,
      );
      if (activeSessionId !== request.sessionId) return false;
      const existing = new Set(messages.value.map((item) => item.message_id));
      messages.value = [
        ...messages.value,
        ...[exchange.user_message, exchange.tutor_message].filter(
          (item) => !existing.has(item.message_id),
        ),
      ];
      pending = null;
      return true;
    } catch (error: unknown) {
      if (activeSessionId === request.sessionId) {
        errorMessage.value = normalizeApiError(error).message;
      }
      return false;
    } finally {
      isSending.value = false;
    }
  }

  async function retry(sessionId: number): Promise<boolean> {
    if (!pending || pending.sessionId !== sessionId) return false;
    return send(sessionId, pending.payload.message, pending.payload.mode, pending);
  }

  return { clear, errorMessage, isLoading, isSending, load, messages, retry, send };
}
