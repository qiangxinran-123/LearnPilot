<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { ChatLineRound, Document, Promotion } from '@element-plus/icons-vue';
import { useRouter } from 'vue-router';

import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { useTutor } from '@/composables/useTutor';
import type { TeachingStrategy } from '@/types/learningSession';

const props = defineProps<{
  sessionId: number;
  courseId: number;
  knowledgeNodeName: string;
  readOnly: boolean;
}>();
const emit = defineEmits<{ changed: [] }>();

const router = useRouter();
const tutor = useTutor();
const draft = ref('');
const selectedMode = ref<TeachingStrategy>('guided_question');
const messageList = ref<HTMLElement | null>(null);
const panelRoot = ref<HTMLElement | null>(null);

const modes: { value: TeachingStrategy; label: string }[] = [
  { value: 'hint', label: '给我提示' },
  { value: 'guided_question', label: '引导我思考' },
  { value: 'example', label: '举个例子' },
  { value: 'step_by_step_explanation', label: '分步讲解' },
  { value: 'full_explanation', label: '完整解释' },
];

async function scrollToLatest(): Promise<void> {
  await nextTick();
  const target = messageList.value?.lastElementChild as HTMLElement | null | undefined;
  target?.scrollIntoView?.({ block: 'nearest' });
}

async function send(): Promise<void> {
  const succeeded = await tutor.send(props.sessionId, draft.value, selectedMode.value);
  if (succeeded) {
    draft.value = '';
    emit('changed');
    await scrollToLatest();
  }
}

async function retry(): Promise<void> {
  const resent = await tutor.retry(props.sessionId);
  if (!resent) {
    await tutor.load(props.sessionId);
    return;
  }
  draft.value = '';
  emit('changed');
  await scrollToLatest();
}

function openMaterial(materialId: number): void {
  void router.push({
    name: 'material-detail',
    params: { courseId: props.courseId, materialId },
  });
}

function prepareQuestion(message: string, mode: TeachingStrategy): void {
  draft.value = message;
  selectedMode.value = mode;
  panelRoot.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
}

defineExpose({ prepareQuestion });

watch(
  () => props.sessionId,
  (sessionId) => {
    draft.value = '';
    selectedMode.value = 'guided_question';
    void tutor.load(sessionId);
  },
  { immediate: true },
);
</script>

<template>
  <aside ref="panelRoot" class="tutor-panel" aria-labelledby="tutor-title">
    <header class="tutor-panel__header">
      <div class="tutor-panel__icon" aria-hidden="true"><el-icon><ChatLineRound /></el-icon></div>
      <div>
        <h2 id="tutor-title">AI Tutor</h2>
        <p>当前辅导：{{ knowledgeNodeName }}</p>
      </div>
    </header>

    <LoadingBlock v-if="tutor.isLoading.value" :count="2" />
    <div v-else ref="messageList" class="tutor-messages" aria-live="polite">
      <div v-if="tutor.messages.value.length === 0" class="tutor-empty">
        <strong>从一个问题开始</strong>
        <p>选择辅导方式，再提出当前知识点中不理解的地方。</p>
      </div>
      <article
        v-for="message in tutor.messages.value"
        :key="message.message_id"
        class="tutor-message"
        :class="`tutor-message--${message.role}`"
      >
        <span>{{ message.role === 'user' ? '你' : 'Tutor' }}</span>
        <p>{{ message.content }}</p>
        <p v-if="message.insufficient_evidence" class="tutor-message__notice">
          当前课程资料不足以支持完整引用；请将此回答视为一般性辅导。
        </p>
        <ul v-if="message.citations.length" class="tutor-citations" aria-label="回答来源">
          <li v-for="citation in message.citations" :key="`${citation.material_id}-${citation.source_reference}`">
            <button type="button" @click="openMaterial(citation.material_id)">
              <el-icon><Document /></el-icon>
              <span>{{ citation.material_title }} · {{ citation.source_reference }}</span>
            </button>
          </li>
        </ul>
      </article>
    </div>

    <div v-if="!readOnly" class="tutor-compose">
      <div class="tutor-modes" aria-label="辅导方式">
        <button
          v-for="mode in modes"
          :key="mode.value"
          type="button"
          :class="{ 'is-active': selectedMode === mode.value }"
          :aria-pressed="selectedMode === mode.value"
          :disabled="tutor.isSending.value"
          @click="selectedMode = mode.value"
        >
          {{ mode.label }}
        </button>
      </div>
      <el-input
        v-model="draft"
        type="textarea"
        :rows="3"
        maxlength="2000"
        show-word-limit
        resize="none"
        placeholder="写下你对当前知识点的疑问…"
        :disabled="tutor.isSending.value"
        @keydown.ctrl.enter.prevent="send"
        @keydown.meta.enter.prevent="send"
      />
      <div class="tutor-compose__actions">
        <small>回答只使用当前 Session 上下文；Ctrl/⌘ + Enter 发送</small>
        <el-button
          type="primary"
          :icon="Promotion"
          :loading="tutor.isSending.value"
          :disabled="!draft.trim() || tutor.isSending.value"
          @click="send"
        >
          发送
        </el-button>
      </div>
    </div>
    <div v-else class="tutor-readonly">该会话已结束，历史辅导记录仍可查看。</div>

    <div v-if="tutor.errorMessage.value" class="tutor-error" role="alert">
      <span>{{ tutor.errorMessage.value }}</span>
      <button type="button" :disabled="tutor.isSending.value" @click="retry">重试</button>
    </div>
  </aside>
</template>

<style scoped>
.tutor-panel {
  position: sticky;
  top: 24px;
  display: flex;
  min-height: 620px;
  max-height: calc(100vh - 48px);
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #c9dbee;
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}
.tutor-panel__header {
  display: flex;
  gap: 12px;
  padding: 20px;
  border-bottom: 1px solid var(--lp-border);
  background: #f5f9fe;
}
.tutor-panel__icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  place-items: center;
  border-radius: 10px;
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
  font-size: 18px;
}
.tutor-panel h2 {
  margin: 0;
  color: var(--lp-ink);
  font-size: 18px;
}
.tutor-panel__header p {
  margin: 4px 0 0;
  color: var(--lp-text-secondary);
  font-size: 12px;
}
.tutor-messages {
  display: flex;
  min-height: 220px;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  padding: 18px;
}
.tutor-empty {
  margin: auto 0;
  padding: 24px 12px;
  text-align: center;
}
.tutor-empty strong {
  color: var(--lp-ink);
}
.tutor-empty p {
  margin: 8px auto 0;
  max-width: 30ch;
  color: var(--lp-text-tertiary);
  line-height: 1.6;
}
.tutor-message {
  max-width: 92%;
}
.tutor-message > span {
  display: block;
  margin-bottom: 5px;
  color: var(--lp-text-tertiary);
  font-size: 11px;
  font-weight: 700;
}
.tutor-message > p {
  margin: 0;
  padding: 11px 13px;
  border-radius: 4px 14px 14px;
  color: var(--lp-ink);
  background: #eef5fd;
  line-height: 1.75;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.tutor-message--user {
  align-self: flex-end;
}
.tutor-message--user > span {
  text-align: right;
}
.tutor-message--user > p {
  border-radius: 14px 4px 14px 14px;
  color: #fff;
  background: var(--lp-primary);
}
.tutor-message .tutor-message__notice {
  margin-top: 7px;
  padding: 8px 10px;
  border: 1px solid #e4d7a9;
  border-radius: 8px;
  color: #705a19;
  background: #fffbee;
  font-size: 12px;
}
.tutor-citations {
  display: grid;
  gap: 5px;
  margin: 9px 0 0;
  padding: 0;
  list-style: none;
}
.tutor-citations button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  text-align: left;
}
.tutor-compose {
  padding: 15px;
  border-top: 1px solid var(--lp-border);
  background: #fbfdff;
}
.tutor-modes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.tutor-modes button {
  padding: 5px 9px;
  border: 1px solid var(--lp-border);
  border-radius: 999px;
  color: var(--lp-text-secondary);
  background: var(--lp-surface);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}
.tutor-modes button.is-active {
  border-color: #8db5df;
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
}
.tutor-compose__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}
.tutor-compose__actions small {
  color: var(--lp-text-tertiary);
  font-size: 10px;
  line-height: 1.4;
}
.tutor-error,
.tutor-readonly {
  padding: 11px 15px;
  border-top: 1px solid var(--lp-border);
  color: var(--lp-text-secondary);
  background: var(--lp-surface-subtle);
  font-size: 12px;
}
.tutor-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--lp-danger);
}
.tutor-error button {
  flex: 0 0 auto;
  padding: 0;
  border: 0;
  color: inherit;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
}
@media (max-width: 960px) {
  .tutor-panel {
    position: static;
    min-height: 560px;
    max-height: none;
  }
  .tutor-messages {
    max-height: 520px;
  }
}
</style>
