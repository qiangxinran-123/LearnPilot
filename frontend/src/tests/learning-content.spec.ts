import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useLearningContent } from '@/composables/useLearningContent';
import { fetchLearningSessionContent } from '@/services/learningSessions';
import type { LearningContent } from '@/types/learningSession';

vi.mock('@/services/learningSessions', () => ({
  fetchLearningSessionContent: vi.fn(),
}));

function response(sessionId: number, title: string): LearningContent {
  return {
    session_id: sessionId,
    course_id: sessionId,
    knowledge_node_id: sessionId,
    knowledge_node_name: title,
    knowledge_node_description: '',
    phase: 'concept_learning',
    status: 'ready',
    grounded: true,
    segments: [
      {
        material_id: sessionId,
        material_title: title,
        material_type: 'pdf',
        segment_index: 0,
        fragment_index: 0,
        text: title,
        source_reference: 'PDF 第 1 页',
        relevance: 'direct',
        content_hash: 'a'.repeat(64),
        text_truncated: false,
      },
    ],
    limits: {
      max_segments: 6,
      max_segment_chars: 800,
      max_total_chars: 6600,
      max_segments_per_material: 2,
    },
  };
}

describe('M7-2 learning content state', () => {
  beforeEach(() => vi.clearAllMocks());

  it('clears old content immediately and ignores a stale response after session switching', async () => {
    let resolveOld!: (value: LearningContent) => void;
    vi.mocked(fetchLearningSessionContent)
      .mockReturnValueOnce(new Promise((resolve) => (resolveOld = resolve)))
      .mockResolvedValueOnce(response(2, '新课程资料'));
    const state = useLearningContent();

    const oldRequest = state.load(1);
    const newRequest = state.load(2);
    expect(state.content.value).toBeNull();
    await newRequest;
    expect(state.content.value?.session_id).toBe(2);
    resolveOld(response(1, '旧课程资料'));
    await oldRequest;
    await flushPromises();
    expect(state.content.value?.session_id).toBe(2);
    expect(state.content.value?.segments[0]?.material_title).toBe('新课程资料');
  });

  it('exposes loading before the server response is available', async () => {
    let resolve!: (value: LearningContent) => void;
    vi.mocked(fetchLearningSessionContent).mockReturnValue(
      new Promise((complete) => {
        resolve = complete;
      }),
    );
    const state = useLearningContent();
    const pending = state.load(3);
    expect(state.state.value).toBe('loading');
    resolve(response(3, '资料'));
    await pending;
    expect(state.state.value).toBe('ready');
  });
});
