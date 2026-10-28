import { httpClient } from '@/services/http';
import type {
  ActiveLearningSessionResponse,
  AdaptivePractice,
  LearningContent,
  LearningSession,
  LearningSessionCreateRequest,
  LearningSessionTaskPhase,
  LearningSessionTaskStatus,
  TutorExchange,
  TutorMessageCreateRequest,
  TutorMessageList,
} from '@/types/learningSession';

const basePath = '/learning/sessions';

export function createLearningSession(payload: LearningSessionCreateRequest) {
  return httpClient.post<LearningSession>(basePath, payload);
}

export function fetchActiveLearningSession(courseId: number) {
  return httpClient.get<ActiveLearningSessionResponse>(`${basePath}/active`, {
    params: { course_id: courseId },
  });
}

export function fetchLearningSession(sessionId: number) {
  return httpClient.get<LearningSession>(`${basePath}/${sessionId}`);
}

export function fetchLearningSessionContent(
  sessionId: number,
  phase: LearningSessionTaskPhase = 'concept_learning',
) {
  return httpClient.get<LearningContent>(`${basePath}/${sessionId}/content`, {
    params: { phase },
  });
}

export function updateLearningSessionTask(
  sessionId: number,
  phase: LearningSessionTaskPhase,
  status: LearningSessionTaskStatus,
) {
  return httpClient.patch<LearningSession>(`${basePath}/${sessionId}/tasks/${phase}`, { status });
}

export function cancelLearningSession(sessionId: number) {
  return httpClient.post<LearningSession>(`${basePath}/${sessionId}/cancel`);
}

export function completeLearningSession(sessionId: number) {
  return httpClient.post<LearningSession>(`${basePath}/${sessionId}/complete`);
}

export function fetchTutorMessages(sessionId: number) {
  return httpClient.get<TutorMessageList>(`${basePath}/${sessionId}/tutor/messages`);
}

export function sendTutorMessage(
  sessionId: number,
  payload: TutorMessageCreateRequest,
  idempotencyKey: string,
) {
  return httpClient.post<TutorExchange>(`${basePath}/${sessionId}/tutor/messages`, payload, {
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}

export function nextPracticeQuestion(sessionId: number) {
  return httpClient.post<AdaptivePractice>(`${basePath}/${sessionId}/practice/next`);
}

export function answerPracticeQuestion(
  sessionId: number,
  assessmentQuestionId: number,
  selectedOptions: string[],
) {
  return httpClient.put<AdaptivePractice>(
    `${basePath}/${sessionId}/practice/responses/${assessmentQuestionId}`,
    { selected_options: selectedOptions },
  );
}
