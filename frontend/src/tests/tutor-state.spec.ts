import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useTutor } from '@/composables/useTutor';
import { fetchTutorMessages, sendTutorMessage } from '@/services/learningSessions';
import type { TutorExchange, TutorMessageList } from '@/types/learningSession';

vi.mock('@/services/learningSessions', () => ({
  fetchTutorMessages: vi.fn(),
  sendTutorMessage: vi.fn(),
}));

function history(sessionId: number, content: string): TutorMessageList {
  return {
    session_id: sessionId,
    messages: [
      {
        message_id: sessionId,
        exchange_id: '00000000-0000-4000-8000-000000000001',
        session_id: sessionId,
        task_state_id: sessionId,
        role: 'assistant',
        mode: 'guided_question',
        content,
        citations: [],
        grounded: false,
        insufficient_evidence: true,
        created_at: '2026-10-25T08:00:00Z',
      },
    ],
  };
}

describe('M7-3 Tutor state', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows loading and ignores a stale history response after Session switching', async () => {
    let resolveOld!: (value: TutorMessageList) => void;
    vi.mocked(fetchTutorMessages)
      .mockReturnValueOnce(new Promise((resolve) => (resolveOld = resolve)))
      .mockResolvedValueOnce(history(2, '新会话'));
    const tutor = useTutor();
    const oldLoad = tutor.load(1);
    expect(tutor.isLoading.value).toBe(true);
    await tutor.load(2);
    expect(tutor.messages.value[0]?.content).toBe('新会话');
    resolveOld(history(1, '旧会话'));
    await oldLoad;
    expect(tutor.messages.value[0]?.content).toBe('新会话');
  });

  it('does not call send for blank content', async () => {
    const tutor = useTutor();
    expect(await tutor.send(1, '   ', 'hint')).toBe(false);
    expect(sendTutorMessage).not.toHaveBeenCalled();
  });

  it('ignores a stale Tutor response after Session switching', async () => {
    let resolveOld!: (value: TutorExchange) => void;
    vi.mocked(fetchTutorMessages).mockResolvedValue({ session_id: 2, messages: [] });
    vi.mocked(sendTutorMessage).mockReturnValue(new Promise((resolve) => (resolveOld = resolve)));
    const tutor = useTutor();
    await tutor.load(1);
    const oldSend = tutor.send(1, '旧会话问题', 'hint');
    await tutor.load(2);
    resolveOld({
      session_id: 1,
      reused: false,
      user_message: history(1, '旧会话问题').messages[0]!,
      tutor_message: history(1, '旧会话回答').messages[0]!,
    });
    expect(await oldSend).toBe(false);
    expect(tutor.messages.value).toEqual([]);
  });
});
