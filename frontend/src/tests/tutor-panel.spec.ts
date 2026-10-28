import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TutorPanel from '@/components/learning/TutorPanel.vue';
import { fetchTutorMessages, sendTutorMessage } from '@/services/learningSessions';
import { ApiError } from '@/services/http';
import type { TutorExchange, TutorMessage } from '@/types/learningSession';

const routing = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('vue-router', async () => {
  const actual = await vi.importActual('vue-router');
  return { ...actual, useRouter: () => ({ push: routing.push }) };
});
vi.mock('@/services/learningSessions', () => ({
  fetchTutorMessages: vi.fn(),
  sendTutorMessage: vi.fn(),
}));

function message(
  id: number,
  role: TutorMessage['role'],
  content: string,
  options: Partial<TutorMessage> = {},
): TutorMessage {
  return {
    message_id: id,
    exchange_id: '00000000-0000-4000-8000-000000000001',
    session_id: 91,
    task_state_id: 101,
    role,
    mode: 'hint',
    content,
    citations: [],
    grounded: false,
    insufficient_evidence: false,
    created_at: '2026-10-25T08:00:00Z',
    ...options,
  };
}

function exchange(): TutorExchange {
  return {
    session_id: 91,
    user_message: message(1, 'user', '为什么替换这个缓存块？'),
    tutor_message: message(2, 'assistant', '先检查各块最近一次被访问的时间。', {
      citations: [
        {
          material_id: 51,
          material_title: 'Cache Lecture',
          material_type: 'pdf',
          source_reference: 'PDF 第 2 页',
          content_hash: 'a'.repeat(64),
        },
      ],
      grounded: true,
    }),
    reused: false,
  };
}

function mountPanel(sessionId = 91) {
  return mount(TutorPanel, {
    props: {
      sessionId,
      courseId: 7,
      knowledgeNodeName: 'LRU Replacement',
      readOnly: false,
    },
  });
}

describe('M7-3 Tutor panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTutorMessages).mockResolvedValue({ session_id: 91, messages: [] });
  });

  it('renders an empty state and all five teaching modes', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('AI Tutor');
    expect(wrapper.text()).toContain('当前辅导：LRU Replacement');
    expect(wrapper.text()).toContain('从一个问题开始');
    for (const label of ['给我提示', '引导我思考', '举个例子', '分步讲解', '完整解释']) {
      expect(wrapper.text()).toContain(label);
    }
  });

  it('sends the selected mode once while pending and renders the cited response', async () => {
    let resolve!: (value: TutorExchange) => void;
    vi.mocked(sendTutorMessage).mockReturnValue(new Promise((complete) => (resolve = complete)));
    const wrapper = mountPanel();
    await flushPromises();
    const full = wrapper.findAll('.tutor-modes button').find((button) => button.text() === '完整解释');
    await full?.trigger('click');
    await wrapper.find('textarea').setValue('为什么替换这个缓存块？');
    const send = wrapper.findAll('button').find((button) => button.text().includes('发送'));
    await send?.trigger('click');
    await send?.trigger('click');
    expect(sendTutorMessage).toHaveBeenCalledTimes(1);
    expect(vi.mocked(sendTutorMessage).mock.calls[0]?.[1]).toEqual({
      message: '为什么替换这个缓存块？',
      mode: 'full_explanation',
    });
    resolve(exchange());
    await flushPromises();
    expect(wrapper.text()).toContain('先检查各块最近一次被访问的时间');
    expect(wrapper.text()).toContain('Cache Lecture · PDF 第 2 页');
  });

  it('keeps the draft after failure and retries with the same idempotency key', async () => {
    vi.mocked(sendTutorMessage)
      .mockRejectedValueOnce(new ApiError('AI 请求超时', { code: 'AI_TIMEOUT', status: 504 }))
      .mockResolvedValueOnce(exchange());
    const wrapper = mountPanel();
    await flushPromises();
    await wrapper.find('textarea').setValue('请给我提示');
    const send = wrapper.findAll('button').find((button) => button.text().includes('发送'));
    await send?.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('AI 请求超时');
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('请给我提示');
    const retry = wrapper.findAll('button').find((button) => button.text() === '重试');
    await retry?.trigger('click');
    await flushPromises();
    expect(sendTutorMessage).toHaveBeenCalledTimes(2);
    expect(vi.mocked(sendTutorMessage).mock.calls[0]?.[2]).toBe(
      vi.mocked(sendTutorMessage).mock.calls[1]?.[2],
    );
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('');
  });

  it('retries loading history when the initial request fails', async () => {
    vi.mocked(fetchTutorMessages)
      .mockRejectedValueOnce(new ApiError('历史加载失败', { code: 'NETWORK_ERROR' }))
      .mockResolvedValueOnce({ session_id: 91, messages: [exchange().tutor_message] });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('历史加载失败');
    const retry = wrapper.findAll('button').find((button) => button.text() === '重试');
    await retry?.trigger('click');
    await flushPromises();
    expect(fetchTutorMessages).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('先检查各块最近一次被访问的时间');
  });

  it('restores history, displays insufficient evidence and opens a citation', async () => {
    const response = exchange().tutor_message;
    response.insufficient_evidence = true;
    vi.mocked(fetchTutorMessages).mockResolvedValue({
      session_id: 91,
      messages: [exchange().user_message, response],
    });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('一般性辅导');
    const citation = wrapper.find('.tutor-citations button');
    await citation.trigger('click');
    expect(routing.push).toHaveBeenCalledWith({
      name: 'material-detail',
      params: { courseId: 7, materialId: 51 },
    });
  });

  it('clears prior messages when the Session changes', async () => {
    vi.mocked(fetchTutorMessages)
      .mockResolvedValueOnce({ session_id: 91, messages: [exchange().tutor_message] })
      .mockResolvedValueOnce({ session_id: 92, messages: [] });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain('先检查各块最近一次被访问的时间');
    await wrapper.setProps({ sessionId: 92, knowledgeNodeName: 'Routing' });
    await flushPromises();
    expect(fetchTutorMessages).toHaveBeenLastCalledWith(92);
    expect(wrapper.text()).not.toContain('先检查各块最近一次被访问的时间');
    expect(wrapper.text()).toContain('从一个问题开始');
  });
});
