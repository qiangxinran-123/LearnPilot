<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { CircleCheck, QuestionFilled, Right } from '@element-plus/icons-vue';

import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { useAdaptivePractice } from '@/composables/useAdaptivePractice';
import type { PracticeAttempt, TeachingStrategy } from '@/types/learningSession';

const props = defineProps<{
  sessionId: number;
  practiceAssessmentId: number | null;
  enabled: boolean;
  readOnly: boolean;
}>();
const emit = defineEmits<{
  changed: [];
  askTutor: [request: { message: string; mode: TeachingStrategy }];
  attempts: [attempts: PracticeAttempt[]];
  finish: [];
}>();

const adaptive = useAdaptivePractice();
const selectedOptions = ref<string[]>([]);
const validationMessage = ref('');
const generationMessage = computed(() => {
  const code = adaptive.practice.value?.generation_error;
  if (!code) return '';
  const messages: Record<string, string> = {
    QUESTION_SOURCE_INSUFFICIENT: '当前知识点缺少可用于出题的资料来源。',
    KNOWLEDGE_MODEL_NOT_READY: '课程知识结构尚未准备好，暂时无法生成题目。',
    AI_TIMEOUT: '生成题目超时，可稍后重试。',
    AI_RATE_LIMITED: 'AI 服务请求较多，可稍后重试。',
    AI_NOT_CONFIGURED: 'AI 服务尚未配置，暂时无法生成题目。',
    AI_AUTHENTICATION_FAILED: 'AI 服务认证失败，请检查服务配置。',
    AI_PROVIDER_ERROR: 'AI 服务暂时不可用，可稍后重试。',
    QUESTION_DUPLICATE: '生成的题目与已有题目重复，可稍后重试。',
    QUESTION_SOURCE_INVALID: '生成题目的来源未通过检查，可稍后重试。',
    QUESTION_QUALITY_INVALID: '生成的题目未通过格式或质量检查，可稍后重试。',
    QUESTION_INVALID_OUTPUT: '生成的题目格式无效，可稍后重试。',
  };
  return messages[code] ?? '本次未能生成可用的新题，可稍后重试。';
});

const question = computed(() => adaptive.practice.value?.current_question ?? null);
const latestAttempt = computed(() => adaptive.practice.value?.attempts.at(-1) ?? null);
const singleSelection = computed(() => selectedOptions.value[0] ?? '');
const difficultyLabel = computed(() => {
  const labels = { easy: '基础', medium: '中等', hard: '进阶' } as const;
  return adaptive.practice.value ? labels[adaptive.practice.value.current_difficulty] : '';
});
watch(() => adaptive.practice.value, (practice) => {
  if (practice) emit('attempts', practice.attempts);
});

async function loadNext(restore = false): Promise<void> {
  selectedOptions.value = [];
  validationMessage.value = '';
  if (await adaptive.loadNext(props.sessionId, restore)) emit('changed');
}

async function submitAnswer(): Promise<void> {
  if (!question.value) return;
  if (selectedOptions.value.length === 0) {
    validationMessage.value = '请先选择一个有效答案。';
    return;
  }
  const succeeded = await adaptive.answer(
    props.sessionId,
    question.value.assessment_question_id,
    selectedOptions.value,
  );
  if (succeeded) {
    selectedOptions.value = [];
    emit('changed');
  }
}

function selectSingle(value: string | number | boolean | undefined): void {
  selectedOptions.value = value === undefined ? [] : [String(value)];
  validationMessage.value = '';
}

function selectMultiple(value: Array<string | number>): void {
  selectedOptions.value = value.map(String);
  validationMessage.value = '';
}

function askForHint(): void {
  if (!question.value) return;
  emit('askTutor', {
    mode: 'hint',
    message: `我正在回答练习题“${question.value.stem}”。请只给我一个提示，不要透露正确答案。`,
  });
}

function explainMistake(): void {
  if (!latestAttempt.value) return;
  emit('askTutor', {
    mode: 'step_by_step_explanation',
    message: `请结合我刚完成的练习题“${latestAttempt.value.stem}”，分步解释这道题以及我的错误。`,
  });
}

watch(
  () => [props.sessionId, props.practiceAssessmentId, props.enabled] as const,
  ([sessionId, assessmentId, enabled]) => {
    const current = adaptive.practice.value;
    if (enabled && current?.session_id === sessionId && current.assessment_id === assessmentId) return;
    adaptive.clear();
    selectedOptions.value = [];
    validationMessage.value = '';
    if (enabled && assessmentId !== null) void loadNext(true);
  },
  { immediate: true },
);
</script>

<template>
  <section class="practice-panel" aria-labelledby="practice-title">
    <header class="practice-panel__header">
      <div>
        <span>根据作答表现逐题安排</span>
        <h3 id="practice-title">针对练习</h3>
      </div>
      <div v-if="adaptive.practice.value" class="practice-meta">
        <strong>已完成 {{ adaptive.practice.value.answered_count }} / {{ adaptive.practice.value.max_questions }} 题</strong>
        <span>{{ difficultyLabel }}</span>
      </div>
    </header>

    <p v-if="!enabled && !readOnly" class="practice-guidance">完成前两个学习阶段后，即可开始真实题库练习。</p>
    <p v-else-if="readOnly && !adaptive.practice.value" class="practice-guidance">该会话已结束，不能开始新的练习。</p>
    <LoadingBlock v-else-if="adaptive.isLoading.value" :count="2" />

    <div v-else-if="!adaptive.practice.value" class="practice-start">
      <p>系统优先选用未做过的已验证题目，题库不足时会尝试生成练习题。</p>
      <el-button type="primary" :disabled="!enabled" @click="loadNext()">开始针对练习</el-button>
    </div>

    <div v-else-if="adaptive.practice.value.status === 'question_bank_empty'" class="practice-empty">
      <strong>当前知识点暂无可用练习题</strong>
      <p v-if="generationMessage">{{ generationMessage }}</p>
      <p>练习已暂停，已提交的答案和学习进度已保存。</p>
      <el-button v-if="enabled && !readOnly" plain @click="loadNext()">重试获取新题</el-button>
      <el-button v-if="enabled && !readOnly && adaptive.practice.value.answered_count > 0" type="primary" @click="$emit('finish')">结束本轮并查看建议</el-button>
    </div>

    <div v-else-if="adaptive.practice.value.status === 'completed'" class="practice-summary">
      <el-icon><CircleCheck /></el-icon>
      <div>
        <h4>本次练习已完成</h4>
        <p v-if="adaptive.practice.value.summary">
          完成 {{ adaptive.practice.value.summary.answered_count }} 题，答对
          {{ adaptive.practice.value.summary.correct_count }} 题，正确率
          {{ Math.round(Number(adaptive.practice.value.summary.accuracy) * 100) }}%。
        </p>
        <small v-if="adaptive.practice.value.completion_reason === 'mastered'">已达到知识点掌握标准。</small>
        <small v-else>练习结果与掌握度已保存。完成会话后可查看学习建议。</small>
      </div>
    </div>

    <template v-else>
      <article v-if="question" class="practice-question">
        <div class="practice-question__index">
          <span>第 {{ question.question_number }} 题</span>
          <el-tag size="small" effect="plain">{{ difficultyLabel }}</el-tag>
        </div>
        <h4>{{ question.stem }}</h4>
        <p v-if="question.auto_checked" class="practice-guidance">自动生成练习题，已通过格式与来源检查，答案尚未经人工核验。</p>
        <el-checkbox-group
          v-if="question.question_type === 'multiple_choice'"
          :model-value="selectedOptions"
          class="practice-options"
          :disabled="adaptive.isSubmitting.value"
          @change="selectMultiple"
        >
          <el-checkbox v-for="option in question.options" :key="option.key" :value="option.key" border>
            {{ option.key }}. {{ option.text }}
          </el-checkbox>
        </el-checkbox-group>
        <el-radio-group
          v-else
          :model-value="singleSelection"
          class="practice-options"
          :disabled="adaptive.isSubmitting.value"
          @change="selectSingle"
        >
          <el-radio v-for="option in question.options" :key="option.key" :value="option.key" border>
            <span v-if="question.question_type === 'true_false'" class="boolean-option">{{ option.key === 'TRUE' ? '正确' : '错误' }}</span><template v-else>{{ option.text }}</template>
          </el-radio>
        </el-radio-group>
        <p v-if="validationMessage" class="practice-error" role="alert">{{ validationMessage }}</p>
        <div class="practice-actions">
          <button type="button" class="practice-tutor-link" @click="askForHint">
            <el-icon><QuestionFilled /></el-icon>我不理解这道题
          </button>
          <el-button
            type="primary"
            :loading="adaptive.isSubmitting.value"
            :disabled="adaptive.isSubmitting.value"
            @click="submitAnswer"
          >
            提交答案
          </el-button>
        </div>
      </article>

      <article v-if="latestAttempt" class="practice-feedback" :class="{ 'is-correct': latestAttempt.is_correct }">
        <header>
          <strong>{{ latestAttempt.is_correct ? '回答正确' : '需要再理解一下' }}</strong>
          <span>第 {{ latestAttempt.question_number }} 题 · {{ latestAttempt.difficulty }}</span>
        </header>
        <p>你的答案：{{ latestAttempt.selected_options.join('、') }}</p>
        <p>{{ latestAttempt.auto_checked ? '自动生成参考答案（未经人工核验）' : '正确答案' }}：{{ latestAttempt.correct_answer.join('、') }}</p>
        <p>{{ latestAttempt.explanation }}</p>
        <small v-if="latestAttempt.source_refs.length">
          来源：{{ latestAttempt.source_refs.map((item) => item.source_reference).join('；') }}
        </small>
        <div class="practice-feedback__actions">
          <button v-if="!latestAttempt.is_correct" type="button" @click="explainMistake">让 Tutor 解释错题</button>
          <el-button v-if="!question" type="primary" plain :icon="Right" @click="loadNext()">下一题</el-button>
        </div>
      </article>
    </template>

    <div v-if="adaptive.errorMessage.value" class="practice-error practice-error--api" role="alert">
      <span>{{ adaptive.errorMessage.value }}</span>
      <button type="button" @click="question ? submitAnswer() : loadNext()">重试</button>
    </div>
  </section>
</template>

<style scoped>
.practice-panel {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--lp-border);
}
.practice-panel__header,
.practice-question__index,
.practice-actions,
.practice-feedback header,
.practice-feedback__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.practice-panel__header span,
.practice-question__index > span {
  color: var(--lp-primary);
  font-size: 11px;
  font-weight: 700;
}
.practice-panel__header h3 {
  margin: 3px 0 0;
  color: var(--lp-ink);
  font-size: 18px;
}
.practice-meta {
  display: flex;
  align-items: baseline;
  gap: 9px;
}
.practice-meta strong {
  color: var(--lp-ink);
  font-size: 19px;
}
.practice-meta span {
  color: var(--lp-text-secondary);
}
.practice-start,
.practice-guidance,
.practice-empty {
  margin: 16px 0 0;
  color: var(--lp-text-secondary);
  line-height: 1.7;
}
.practice-start {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.practice-start p,
.practice-empty p {
  margin: 0;
}
.practice-question {
  margin-top: 18px;
}
.practice-question h4 {
  max-width: 72ch;
  margin: 14px 0 18px;
  color: var(--lp-ink);
  font-size: 17px;
  line-height: 1.65;
}
.boolean-option { white-space: nowrap; }
.practice-options {
  display: grid;
  gap: 10px;
}
.practice-options :deep(.el-radio),
.practice-options :deep(.el-checkbox) {
  width: 100%;
  height: auto;
  min-height: 42px;
  margin: 0;
  padding: 10px 13px;
  white-space: normal;
}
.practice-actions {
  margin-top: 18px;
}
.practice-tutor-link,
.practice-feedback button,
.practice-error--api button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
}
.practice-feedback {
  margin-top: 18px;
  padding: 16px;
  border-left: 3px solid #d09b43;
  background: #fffaf0;
}
.practice-feedback.is-correct {
  border-left-color: #3f9467;
  background: #f1faf5;
}
.practice-feedback header strong {
  color: var(--lp-ink);
}
.practice-feedback header span,
.practice-feedback small {
  color: var(--lp-text-tertiary);
  font-size: 11px;
}
.practice-feedback p {
  margin: 9px 0 0;
  color: var(--lp-text-secondary);
  line-height: 1.65;
}
.practice-feedback small {
  display: block;
  margin-top: 9px;
}
.practice-feedback__actions {
  margin-top: 14px;
}
.practice-summary {
  display: flex;
  gap: 14px;
  margin-top: 18px;
  padding: 18px;
  color: #246b48;
  background: #edf8f2;
}
.practice-summary > .el-icon {
  margin-top: 2px;
  font-size: 22px;
}
.practice-summary h4,
.practice-summary p {
  margin: 0;
}
.practice-summary p {
  margin-top: 6px;
  color: var(--lp-text-secondary);
}
.practice-summary small {
  display: block;
  margin-top: 8px;
  color: var(--lp-text-tertiary);
}
.practice-error {
  margin: 10px 0 0;
  color: var(--lp-danger);
  font-size: 12px;
}
.practice-error--api {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: #fff4f4;
}
@media (max-width: 620px) {
  .practice-start,
  .practice-actions,
  .practice-feedback__actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
