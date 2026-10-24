import { ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useDiagnosticAssessment } from '@/composables/useDiagnosticAssessment';
import { discardAssessment, fetchAssessment, fetchAssessmentResult, saveAssessmentResponse, submitAssessment } from '@/services/diagnostics';

vi.mock('@/services/diagnostics', () => ({
  discardAssessment: vi.fn(),
  fetchAssessment: vi.fn(),
  fetchAssessmentResult: vi.fn(),
  saveAssessmentResponse: vi.fn(),
  startAssessment: vi.fn(),
  submitAssessment: vi.fn(),
}));

const assessment = {
  id: 7,
  course_id: 2,
  course_name: '计算机组成',
  status: 'in_progress' as const,
  question_count: 1,
  answered_count: 1,
  created_at: '2026-10-17T10:00:00Z',
  started_at: '2026-10-17T10:01:00Z',
  submitted_at: null,
  questions: [{
    assessment_question_id: 71,
    order_index: 0,
    question_type: 'single_choice' as const,
    stem: 'Cache 命中时发生什么？',
    options: [{ key: 'A', text: '直接读取缓存' }, { key: 'B', text: '总是访问磁盘' }],
    difficulty: 'easy' as const,
    saved_answer: ['A'],
  }],
};

describe('useDiagnosticAssessment', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(fetchAssessment).mockResolvedValue(structuredClone(assessment));
  });

  it('restores server-saved answers after refresh', async () => {
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();
    expect(diagnostic.answers[71]).toEqual(['A']);
    expect(diagnostic.confirmedAnswers[71]).toEqual(['A']);
    expect(diagnostic.confirmedAnsweredCount.value).toBe(1);
  });

  it('continues from the first unanswered question when no local position exists', async () => {
    const answeredQuestion = assessment.questions[0]!;
    vi.mocked(fetchAssessment).mockResolvedValue({
      ...structuredClone(assessment),
      question_count: 3,
      answered_count: 1,
      questions: [
        answeredQuestion,
        { ...answeredQuestion, assessment_question_id: 72, order_index: 1, saved_answer: null },
        { ...answeredQuestion, assessment_question_id: 73, order_index: 2, saved_answer: null },
      ],
    });
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();

    expect(diagnostic.currentIndex.value).toBe(1);
    expect(diagnostic.currentQuestion.value?.assessment_question_id).toBe(72);
  });

  it('serializes saves so an older request cannot overwrite the latest answer', async () => {
    let releaseFirst!: () => void;
    vi.mocked(saveAssessmentResponse)
      .mockImplementationOnce(() => new Promise((resolve) => {
        releaseFirst = () => resolve({ assessment_question_id: 71, selected_options: ['A'], answered_at: 'now' });
      }))
      .mockResolvedValueOnce({ assessment_question_id: 71, selected_options: ['B'], answered_at: 'later' });
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();
    diagnostic.updateAnswer(71, ['A']);
    diagnostic.updateAnswer(71, ['B']);
    await Promise.resolve();
    expect(saveAssessmentResponse).toHaveBeenCalledTimes(1);
    releaseFirst();
    expect(await diagnostic.flushPendingSaves()).toBe(true);
    expect(saveAssessmentResponse).toHaveBeenNthCalledWith(2, 7, 71, ['B']);
    expect(diagnostic.confirmedAnswers[71]).toEqual(['B']);
    expect(diagnostic.saveStates[71]).toBe('saved');
  });

  it('does not claim a failed answer is saved', async () => {
    vi.mocked(saveAssessmentResponse).mockRejectedValue(new Error('offline'));
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();
    diagnostic.updateAnswer(71, ['B']);
    expect(await diagnostic.flushPendingSaves()).toBe(false);
    expect(diagnostic.saveStates[71]).toBe('failed');
  });

  it('discards only through the server and clears the saved position after success', async () => {
    vi.mocked(discardAssessment).mockResolvedValue({ assessment_id: 7, discarded: true });
    sessionStorage.setItem('diagnostic:7:question', '0');
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();

    expect(await diagnostic.discardDraft()).toBe(true);
    expect(discardAssessment).toHaveBeenCalledTimes(1);
    expect(discardAssessment).toHaveBeenCalledWith(7);
    expect(sessionStorage.getItem('diagnostic:7:question')).toBeNull();
  });

  it('keeps the draft position when discard fails', async () => {
    vi.mocked(discardAssessment).mockRejectedValue(new Error('offline'));
    sessionStorage.setItem('diagnostic:7:question', '0');
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();

    expect(await diagnostic.discardDraft()).toBe(false);
    expect(sessionStorage.getItem('diagnostic:7:question')).toBe('0');
  });

  it('waits for pending saves before submit and uses the server result', async () => {
    vi.mocked(saveAssessmentResponse).mockResolvedValue({ assessment_question_id: 71, selected_options: ['B'], answered_at: 'now' });
    vi.mocked(submitAssessment).mockResolvedValue({
      assessment_id: 7, course_id: 2, course_name: assessment.course_name, submitted_at: '2026-10-17T11:00:00Z',
      total_questions: 1, answered_questions: 1, correct_questions: 0, total_points: 1, earned_points: 0, accuracy: 0,
      report_policy_version: 'diagnostic_node_performance_v1', covered_knowledge_nodes: 0, needs_attention_nodes: 0,
      knowledge_performance: [], question_reviews: [],
    });
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();
    diagnostic.updateAnswer(71, ['B']);
    expect(await diagnostic.submit()).toBe(true);
    expect(vi.mocked(saveAssessmentResponse).mock.invocationCallOrder[0]!).toBeLessThan(
      vi.mocked(submitAssessment).mock.invocationCallOrder[0]!,
    );
    expect(diagnostic.result.value?.correct_questions).toBe(0);
    expect(diagnostic.assessment.value?.status).toBe('submitted');
  });

  it('reconciles a timed-out submission from server state', async () => {
    vi.mocked(submitAssessment).mockRejectedValue(new Error('timeout'));
    vi.mocked(fetchAssessment)
      .mockResolvedValueOnce(structuredClone(assessment))
      .mockResolvedValueOnce({ ...structuredClone(assessment), status: 'submitted', submitted_at: '2026-10-17T11:00:00Z' });
    vi.mocked(fetchAssessmentResult).mockResolvedValue({
      assessment_id: 7, course_id: 2, course_name: assessment.course_name, submitted_at: '2026-10-17T11:00:00Z',
      total_questions: 1, answered_questions: 1, correct_questions: 1, total_points: 1, earned_points: 1, accuracy: 1,
      report_policy_version: 'diagnostic_node_performance_v1', covered_knowledge_nodes: 0, needs_attention_nodes: 0,
      knowledge_performance: [], question_reviews: [],
    });
    const diagnostic = useDiagnosticAssessment(ref(7));
    await diagnostic.load();
    expect(await diagnostic.submit()).toBe(true);
    expect(diagnostic.result.value?.accuracy).toBe(1);
  });
});
