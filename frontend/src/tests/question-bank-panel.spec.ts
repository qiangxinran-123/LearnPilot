import { defineComponent } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import QuestionBankPanel from '@/components/diagnostic/QuestionBankPanel.vue';
import {
  approveDiagnosticQuestion,
  fetchDiagnosticQuestions,
  fetchQuestionBankReadiness,
  prepareCourseDiagnosticQuestions,
  rejectDiagnosticQuestion,
} from '@/services/diagnostics';
import { ApiError } from '@/services/http';
import { fetchKnowledgeBuildStatus, startKnowledgeBuild } from '@/services/knowledge';
import type {
  CourseQuestionPreparationResponse,
  QuestionBankItem,
  QuestionBankReadiness,
} from '@/types/diagnostic';
import type { KnowledgeBuildStatus } from '@/types/knowledge';

const push = vi.fn();
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}));
vi.mock('@/services/diagnostics', () => ({
  approveDiagnosticQuestion: vi.fn(),
  fetchDiagnosticQuestions: vi.fn(),
  fetchQuestionBankReadiness: vi.fn(),
  prepareCourseDiagnosticQuestions: vi.fn(),
  rejectDiagnosticQuestion: vi.fn(),
}));
vi.mock('@/services/knowledge', () => ({
  fetchKnowledgeBuildStatus: vi.fn(),
  startKnowledgeBuild: vi.fn(),
}));

const DialogStub = defineComponent({
  props: { modelValue: Boolean, title: String },
  emits: ['update:modelValue'],
  template: `
    <section v-if="modelValue" class="dialog-stub">
      <h2>{{ title }}</h2>
      <slot />
      <footer><slot name="footer" /></footer>
    </section>
  `,
});

const pendingQuestion: QuestionBankItem = {
  question_id: 91,
  course_id: 7,
  knowledge_node_id: 11,
  knowledge_node_name: '补码表示',
  question_type: 'single_choice',
  difficulty: 'easy',
  stem: '关于补码表示，以下哪项正确？',
  options: [
    { key: 'A', text: '选项一' },
    { key: 'B', text: '选项二' },
  ],
  correct_answer: ['A'],
  explanation: '课程资料说明补码按此规则解释。',
  source_refs: [
    {
      material_id: 3,
      material_title: '计算机系统讲义',
      source_reference: '第 2 章：整数表示',
      excerpt: '补码表示用于统一处理有符号整数运算。',
    },
  ],
  validation_status: 'pending',
  created_at: '2026-10-22T10:00:00Z',
};

function readiness(overrides: Partial<QuestionBankReadiness> = {}): QuestionBankReadiness {
  return {
    course_id: 7,
    validated_count: 0,
    pending_count: 0,
    rejected_count: 0,
    covered_core_nodes: 0,
    total_core_nodes: 59,
    minimum_required: 8,
    required_questions: 8,
    can_start: false,
    reason_code: 'QUESTION_BANK_INSUFFICIENT',
    required_nodes: [
      {
        knowledge_node_id: 11,
        knowledge_node_name: '补码表示',
        has_validated_question: false,
        has_pending_question: false,
      },
    ],
    ...overrides,
  };
}

function buildStatus(overrides: Partial<KnowledgeBuildStatus> = {}): KnowledgeBuildStatus {
  return {
    course_id: 7,
    state: 'ready',
    stage: null,
    job_id: 1,
    material_count: 2,
    ready_material_count: 2,
    synced_material_count: 2,
    pending_sync_material_count: 0,
    pending_parse_material_count: 0,
    failed_material_count: 0,
    last_added_node_count: 0,
    last_reused_node_count: 59,
    node_count: 59,
    contains_edge_count: 20,
    prerequisite_edge_count: 12,
    needs_update: false,
    can_build: true,
    has_model: true,
    error_code: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

function generated(question = pendingQuestion): CourseQuestionPreparationResponse {
  return {
    course_id: 7,
    planned_count: 1,
    generated_count: 1,
    failed_count: 0,
    pending_review_count: 1,
    questions: [question],
    failures: [],
  };
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

const wrappers: VueWrapper[] = [];

async function mountPanel(): Promise<VueWrapper> {
  const wrapper = mount(QuestionBankPanel, {
    props: { courseId: 7, courseName: '计算机系统' },
    global: { stubs: { ElDialog: DialogStub } },
  });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}

function button(wrapper: VueWrapper, label: string) {
  const match = wrapper.findAll('button').find((item) => item.text().includes(label));
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}

async function openQuestionBankRecords(wrapper: VueWrapper): Promise<void> {
  await button(wrapper, '查看题库记录').trigger('click');
  await flushPromises();
}

describe('QuestionBankPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(readiness());
    vi.mocked(fetchDiagnosticQuestions).mockResolvedValue({ count: 0, questions: [] });
    vi.mocked(fetchKnowledgeBuildStatus).mockResolvedValue(buildStatus());
  });

  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  });

  it('loads readiness and the list without sending generation or review requests', async () => {
    const wrapper = await mountPanel();

    expect(fetchQuestionBankReadiness).toHaveBeenCalledOnce();
    expect(fetchDiagnosticQuestions).toHaveBeenCalledOnce();
    expect(fetchKnowledgeBuildStatus).toHaveBeenCalledOnce();
    expect(prepareCourseDiagnosticQuestions).not.toHaveBeenCalled();
    expect(approveDiagnosticQuestion).not.toHaveBeenCalled();
    expect(rejectDiagnosticQuestion).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('有效题目');
    expect(wrapper.text()).toContain('0 / 59');
    expect(wrapper.text()).toContain('查看题库记录');
    expect(wrapper.find('.question-row').exists()).toBe(false);
  });

  it('requires one explicit synchronization action and then supplements only the real question gap', async () => {
    vi.mocked(fetchKnowledgeBuildStatus)
      .mockResolvedValueOnce(
        buildStatus({
          state: 'update_available',
          needs_update: true,
          ready_material_count: 3,
          synced_material_count: 2,
          pending_sync_material_count: 1,
        }),
      )
      .mockResolvedValueOnce(
        buildStatus({ node_count: 61, last_added_node_count: 2, last_reused_node_count: 59 }),
      )
      .mockResolvedValue(
        buildStatus({ node_count: 61, last_added_node_count: 2, last_reused_node_count: 59 }),
      );
    vi.mocked(startKnowledgeBuild).mockResolvedValue({
      job_id: 2,
      status: 'success',
      stage: null,
      reused: false,
    });
    vi.mocked(prepareCourseDiagnosticQuestions).mockResolvedValue(generated());
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('检测到新的课程资料');
    await button(wrapper, '同步新增资料并更新诊断').trigger('click');
    expect(startKnowledgeBuild).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('可能调用真实 AI');

    const confirmSync = button(wrapper, '确认同步');
    await confirmSync.trigger('click');
    await confirmSync.trigger('click');
    await flushPromises();

    expect(startKnowledgeBuild).toHaveBeenCalledOnce();
    expect(startKnowledgeBuild).toHaveBeenCalledWith(7);
    expect(prepareCourseDiagnosticQuestions).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('已同步新增资料');
    expect(wrapper.text()).toContain('新增知识点');
    expect(wrapper.text()).toContain('2');
    expect(wrapper.text()).toContain('新增待审核题');
  });

  it('reports a partial update and never retries paid question generation automatically', async () => {
    vi.mocked(fetchKnowledgeBuildStatus)
      .mockResolvedValueOnce(buildStatus({ state: 'update_available', needs_update: true }))
      .mockResolvedValue(buildStatus({ node_count: 60 }));
    vi.mocked(startKnowledgeBuild).mockResolvedValue({
      job_id: 2,
      status: 'success',
      stage: null,
      reused: false,
    });
    vi.mocked(prepareCourseDiagnosticQuestions).mockRejectedValue(
      new ApiError('provider unavailable', { code: 'AI_PROVIDER_ERROR', status: 502 }),
    );
    const wrapper = await mountPanel();

    await button(wrapper, '同步新增资料并更新诊断').trigger('click');
    await button(wrapper, '确认同步').trigger('click');
    await flushPromises();

    expect(prepareCourseDiagnosticQuestions).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('课程知识已同步，部分诊断题尚未补充完成');
    expect(wrapper.text()).toContain('题目生成服务暂时不可用');
    expect(wrapper.text()).toContain('继续补充题目');
  });

  it('keeps question records collapsed until requested and preserves the empty state', async () => {
    const wrapper = await mountPanel();

    expect(wrapper.text()).not.toContain('当前课程还没有诊断题目');
    await openQuestionBankRecords(wrapper);
    expect(wrapper.text()).toContain('当前课程还没有诊断题目');
  });

  it('requires confirmation, sends one bounded course request, and blocks duplicate submits', async () => {
    const response = deferred<CourseQuestionPreparationResponse>();
    vi.mocked(prepareCourseDiagnosticQuestions).mockReturnValue(response.promise);
    const wrapper = await mountPanel();

    await button(wrapper, '准备诊断').trigger('click');
    expect(prepareCourseDiagnosticQuestions).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('最多调用真实 AI 生成 4 道题');
    expect(wrapper.text()).toContain('可能产生模型费用');

    const confirm = button(wrapper, '确认准备');
    await confirm.trigger('click');
    await confirm.trigger('click');
    expect(prepareCourseDiagnosticQuestions).toHaveBeenCalledOnce();
    expect(prepareCourseDiagnosticQuestions).toHaveBeenCalledWith(7);

    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(
      readiness({
        pending_count: 1,
        required_nodes: [
          {
            knowledge_node_id: 11,
            knowledge_node_name: '补码表示',
            has_validated_question: false,
            has_pending_question: true,
          },
        ],
      }),
    );
    vi.mocked(fetchDiagnosticQuestions).mockResolvedValue({
      count: 1,
      questions: [pendingQuestion],
    });
    response.resolve(generated());
    await flushPromises();

    expect(wrapper.text()).toContain('待审核');
    expect(prepareCourseDiagnosticQuestions).toHaveBeenCalledOnce();
  });

  it('does not retry a failed paid generation request or fabricate a question', async () => {
    vi.mocked(prepareCourseDiagnosticQuestions).mockRejectedValue(
      new ApiError('timeout', { code: 'AI_TIMEOUT', status: 503 }),
    );
    const wrapper = await mountPanel();

    await button(wrapper, '准备诊断').trigger('click');
    await button(wrapper, '确认准备').trigger('click');
    await flushPromises();

    expect(prepareCourseDiagnosticQuestions).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('请先刷新题库状态');
    expect(wrapper.text()).not.toContain(pendingQuestion.stem);
    expect(fetchDiagnosticQuestions).toHaveBeenCalledOnce();
  });

  it('shows complete review evidence and waits for approve before refreshing server state', async () => {
    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(
      readiness({
        pending_count: 1,
        required_nodes: [
          {
            knowledge_node_id: 11,
            knowledge_node_name: '补码表示',
            has_validated_question: false,
            has_pending_question: true,
          },
        ],
      }),
    );
    vi.mocked(fetchDiagnosticQuestions).mockResolvedValue({
      count: 1,
      questions: [pendingQuestion],
    });
    const approval = deferred<{ question: QuestionBankItem }>();
    vi.mocked(approveDiagnosticQuestion).mockReturnValue(approval.promise);
    const wrapper = await mountPanel();

    await openQuestionBankRecords(wrapper);
    await button(wrapper, '查看并审核').trigger('click');
    expect(wrapper.text()).toContain(pendingQuestion.stem);
    expect(wrapper.text()).toContain('正确答案');
    expect(wrapper.text()).toContain('课程资料说明');
    expect(wrapper.text()).toContain('计算机系统讲义');
    expect(wrapper.text()).toContain('第 2 章：整数表示');

    await button(wrapper, '审核通过').trigger('click');
    await button(wrapper, '审核通过').trigger('click');
    expect(approveDiagnosticQuestion).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('待审核');

    const validated = { ...pendingQuestion, validation_status: 'validated' as const };
    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(
      readiness({
        validated_count: 1,
        pending_count: 0,
        covered_core_nodes: 1,
        required_nodes: [
          {
            knowledge_node_id: 11,
            knowledge_node_name: '补码表示',
            has_validated_question: true,
            has_pending_question: false,
          },
        ],
      }),
    );
    vi.mocked(fetchDiagnosticQuestions).mockResolvedValue({
      count: 1,
      questions: [validated],
    });
    approval.resolve({ question: validated });
    await flushPromises();

    expect(fetchQuestionBankReadiness).toHaveBeenCalledTimes(2);
    expect(fetchDiagnosticQuestions).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll('.question-bank__metrics dd')[0]?.text()).toBe('1');
    expect(wrapper.text()).toContain('1 / 59');
    expect(prepareCourseDiagnosticQuestions).not.toHaveBeenCalled();
  });

  it('rejects only through the official API and keeps readiness server-authoritative', async () => {
    vi.mocked(fetchQuestionBankReadiness)
      .mockResolvedValueOnce(
        readiness({
          pending_count: 1,
          required_nodes: [
            {
              knowledge_node_id: 11,
              knowledge_node_name: '补码表示',
              has_validated_question: false,
              has_pending_question: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(readiness({ rejected_count: 1 }));
    vi.mocked(fetchDiagnosticQuestions)
      .mockResolvedValueOnce({ count: 1, questions: [pendingQuestion] })
      .mockResolvedValueOnce({
        count: 1,
        questions: [{ ...pendingQuestion, validation_status: 'rejected' }],
      });
    vi.mocked(rejectDiagnosticQuestion).mockResolvedValue({
      question: { ...pendingQuestion, validation_status: 'rejected' },
    });
    const wrapper = await mountPanel();

    await openQuestionBankRecords(wrapper);
    await button(wrapper, '查看并审核').trigger('click');
    await button(wrapper, '拒绝题目').trigger('click');
    await flushPromises();

    expect(rejectDiagnosticQuestion).toHaveBeenCalledOnce();
    expect(rejectDiagnosticQuestion).toHaveBeenCalledWith(7, 91);
    expect(wrapper.findAll('.question-bank__metrics dd')[0]?.text()).toBe('0');
    await openQuestionBankRecords(wrapper);
    expect(wrapper.text()).toContain('已拒绝');
  });

  it('preserves the pending state when review fails and allows a safe refresh', async () => {
    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(
      readiness({
        pending_count: 1,
        required_nodes: [
          {
            knowledge_node_id: 11,
            knowledge_node_name: '补码表示',
            has_validated_question: false,
            has_pending_question: true,
          },
        ],
      }),
    );
    vi.mocked(fetchDiagnosticQuestions).mockResolvedValue({
      count: 1,
      questions: [pendingQuestion],
    });
    vi.mocked(approveDiagnosticQuestion).mockRejectedValue(
      new ApiError('conflict', { code: 'QUESTION_INVALID_STATE', status: 409 }),
    );
    const wrapper = await mountPanel();

    await openQuestionBankRecords(wrapper);
    await button(wrapper, '查看并审核').trigger('click');
    await button(wrapper, '审核通过').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('题目状态已发生变化');
    expect(wrapper.text()).toContain('待审核');
    expect(fetchQuestionBankReadiness).toHaveBeenCalledOnce();
    expect(fetchDiagnosticQuestions).toHaveBeenCalledOnce();

    await button(wrapper, '关闭').trigger('click');
    await button(wrapper, '刷新状态').trigger('click');
    await flushPromises();
    expect(fetchQuestionBankReadiness).toHaveBeenCalledTimes(2);
  });

  it('closes the current records when switching courses', async () => {
    vi.mocked(fetchDiagnosticQuestions).mockResolvedValue({ count: 1, questions: [pendingQuestion] });
    const wrapper = await mountPanel();
    await openQuestionBankRecords(wrapper);
    expect(wrapper.text()).toContain(pendingQuestion.stem);

    await wrapper.setProps({ courseId: 8, courseName: '离散数学' });
    await flushPromises();

    expect(wrapper.text()).not.toContain(pendingQuestion.stem);
    expect(fetchQuestionBankReadiness).toHaveBeenLastCalledWith(8);
    expect(fetchDiagnosticQuestions).toHaveBeenLastCalledWith(8);
  });

  it('shows READY from the backend and navigates to Diagnose with the current course', async () => {
    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(
      readiness({
        validated_count: 8,
        covered_core_nodes: 8,
        can_start: true,
        reason_code: null,
        required_nodes: [],
      }),
    );
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('诊断已就绪');
    await button(wrapper, '开始诊断').trigger('click');
    expect(wrapper.emitted('start')).toHaveLength(1);
    expect(prepareCourseDiagnosticQuestions).not.toHaveBeenCalled();
  });

  it('renders a recoverable load error without paid side effects', async () => {
    vi.mocked(fetchQuestionBankReadiness).mockRejectedValue(new ApiError('网络异常'));
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('题库状态加载失败');
    expect(wrapper.text()).toContain('网络异常');
    expect(prepareCourseDiagnosticQuestions).not.toHaveBeenCalled();

    vi.mocked(fetchQuestionBankReadiness).mockResolvedValue(readiness());
    await button(wrapper, '重新加载').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('当前覆盖目标');
  });
});
