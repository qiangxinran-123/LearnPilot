<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ArrowLeft,
  ChatRound,
  Delete,
  Document,
  DocumentCopy,
  Reading,
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

import EmptyState from '@/components/common/EmptyState.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import {
  askMaterialQuestion,
  fetchMaterialCards,
  fetchMaterialSummary,
  generateMaterialCards,
  generateMaterialSummary,
} from '@/services/ai-materials';
import { ApiError, normalizeApiError } from '@/services/http';
import { deleteMaterial, fetchMaterial, fetchMaterialContent } from '@/services/materials';
import type {
  CardGenerationResponse,
  Material,
  MaterialContentResponse,
  MaterialQAResponse,
  MaterialSummaryResponse,
} from '@/types/course';

const route = useRoute();
const router = useRouter();
const courseId = computed(() => Number(route.params.courseId));
const materialId = computed(() => Number(route.params.materialId));
const material = ref<Material | null>(null);
const content = ref<MaterialContentResponse | null>(null);
const summary = ref<MaterialSummaryResponse | null>(null);
const cards = ref<CardGenerationResponse | null>(null);
const qaAnswer = ref<MaterialQAResponse | null>(null);
const state = ref<'loading' | 'ready' | 'error'>('loading');
const errorMessage = ref('');
const summaryLoading = ref(false);
const cardsLoading = ref(false);
const qaLoading = ref(false);
const qaQuestion = ref('');
const aiError = ref('');
const expandedCardId = ref<number | null>(null);
const activeTab = computed<'content' | 'summary' | 'cards' | 'qa'>({
  get() {
    const tab = route.query.tab;
    return tab === 'summary' || tab === 'cards' || tab === 'qa' ? tab : 'content';
  },
  set(tab) {
    void router.replace({ query: { ...route.query, tab } });
  },
});
const sourceReference = computed(() =>
  typeof route.query.source === 'string' ? route.query.source.slice(0, 240) : '',
);
let materialRequest = 0;
const parseFailed = computed(() => material.value?.extraction_status !== 'SUCCESS');
const parseFailureTitle = computed(() => {
  if (material.value?.extraction_status === 'LEGACY_CONTENT_PARTIAL') return '旧版资料内容不完整';
  if (material.value?.extraction_status === 'LEGACY_CONTENT_UNAVAILABLE')
    return '旧版资料缺少完整文本';
  return '资料解析失败';
});
const parseFailureMessage = computed(() => {
  if (material.value?.extraction_status === 'LEGACY_CONTENT_PARTIAL')
    return '旧版仅保存了部分提取文本。请重新上传原文件后再使用资料 AI 工具。';
  if (material.value?.extraction_status === 'LEGACY_CONTENT_UNAVAILABLE')
    return '旧版没有保存完整提取文本。请重新上传原文件后再使用资料 AI 工具。';
  return '文件已保存，但暂时无法读取其中的文本。请确认文件完整后重新上传。';
});
const qaProvenance = computed(() => {
  const answer = qaAnswer.value;
  return answer?.provider
    ? '回答来源：' +
        answer.provider +
        ' / ' +
        (answer.model ?? 'unknown') +
        ' · ' +
        (answer.prompt_version ?? 'unknown')
    : '';
});

function formatBytes(value: number): string {
  return value < 1024 ? `${value} B` : `${Math.ceil(value / 1024)} KB`;
}
function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
      }).format(date);
}

async function loadMaterial(): Promise<void> {
  const request = ++materialRequest;
  const requestedCourseId = courseId.value;
  const requestedMaterialId = materialId.value;
  if (!Number.isInteger(courseId.value) || !Number.isInteger(materialId.value)) {
    state.value = 'error';
    errorMessage.value = '资料地址无效。';
    return;
  }
  state.value = 'loading';
  errorMessage.value = '';
  aiError.value = '';
  material.value = null;
  content.value = null;
  summary.value = null;
  cards.value = null;
  qaAnswer.value = null;
  try {
    const loadedMaterial = await fetchMaterial(requestedMaterialId);
    if (request !== materialRequest) return;
    if (loadedMaterial.course_id !== requestedCourseId)
      throw new ApiError('资料不属于当前课程。', { status: 404 });
    const [contentResponse, summaryResponse, cardsResponse] = await Promise.all([
      loadedMaterial.extraction_status === 'SUCCESS'
        ? fetchMaterialContent(requestedMaterialId)
        : Promise.resolve(null),
      fetchMaterialSummary(requestedMaterialId),
      fetchMaterialCards(requestedMaterialId),
    ]);
    if (
      request !== materialRequest ||
      courseId.value !== requestedCourseId ||
      materialId.value !== requestedMaterialId
    )
      return;
    material.value = loadedMaterial;
    content.value = contentResponse;
    summary.value = summaryResponse;
    cards.value = cardsResponse;
    state.value = 'ready';
  } catch (error: unknown) {
    if (request !== materialRequest) return;
    state.value = 'error';
    errorMessage.value = normalizeApiError(error).message;
  }
}
async function generateSummary(): Promise<void> {
  if (parseFailed.value) return;
  summaryLoading.value = true;
  aiError.value = '';
  try {
    summary.value = await generateMaterialSummary(materialId.value);
  } catch (error: unknown) {
    aiError.value = normalizeApiError(error).message;
  } finally {
    summaryLoading.value = false;
  }
}
async function generateCards(): Promise<void> {
  if (parseFailed.value) return;
  cardsLoading.value = true;
  aiError.value = '';
  try {
    cards.value = await generateMaterialCards(materialId.value);
  } catch (error: unknown) {
    aiError.value = normalizeApiError(error).message;
  } finally {
    cardsLoading.value = false;
  }
}
async function askQuestion(): Promise<void> {
  const question = qaQuestion.value.trim();
  if (!question || parseFailed.value) return;
  qaLoading.value = true;
  aiError.value = '';
  try {
    qaAnswer.value = await askMaterialQuestion(materialId.value, question);
  } catch (error: unknown) {
    aiError.value = normalizeApiError(error).message;
  } finally {
    qaLoading.value = false;
  }
}
async function removeMaterial(): Promise<void> {
  try {
    await deleteMaterial(materialId.value);
    ElMessage.success('资料已删除。');
    await router.push(`/courses/${courseId.value}`);
  } catch (error: unknown) {
    ElMessage.error(normalizeApiError(error).message);
  }
}
function toggleCard(cardId: number): void {
  expandedCardId.value = expandedCardId.value === cardId ? null : cardId;
}
watch(
  [courseId, materialId],
  () => {
    materialRequest += 1;
    void loadMaterial();
  },
  { immediate: true },
);
</script>

<template>
  <section class="page-view material-workspace">
    <button
      class="back-link"
      type="button"
      @click="router.push(`/courses/${courseId}?tab=materials`)"
    >
      <el-icon aria-hidden="true"><ArrowLeft /></el-icon>返回课程
    </button>
    <LoadingBlock v-if="state === 'loading'" />
    <ErrorState
      v-else-if="state === 'error'"
      title="资料加载失败"
      :message="errorMessage"
      @retry="loadMaterial"
    />
    <template v-else-if="material">
      <header class="material-workspace__header">
        <div class="material-workspace__title-row">
          <div class="material-row__icon" aria-hidden="true">
            <el-icon><Document /></el-icon>
          </div>
          <div>
            <h1>{{ material.title }}</h1>
            <p>
              {{ material.original_filename || material.filename || '未命名资料'
              }}<span v-if="material.size_bytes"> · {{ formatBytes(material.size_bytes) }}</span
              ><span v-if="formatDate(material.created_at)">
                · {{ formatDate(material.created_at) }}</span
              >
            </p>
          </div>
        </div>
        <el-popconfirm
          width="280"
          title="删除资料会同时删除解析内容、摘要、学习卡片和本地文件，此操作无法撤销。"
          confirm-button-text="确认删除"
          cancel-button-text="取消"
          @confirm="removeMaterial"
        >
          <template #reference
            ><el-button type="danger" plain
              ><el-icon><Delete /></el-icon>删除资料</el-button
            ></template
          >
        </el-popconfirm>
      </header>
      <p v-if="sourceReference" class="material-source-note">
        来源位置：{{ sourceReference }}。当前资料页暂不支持精确定位，下面展示资料内容。
      </p>
      <section v-if="parseFailed" class="parse-failure" role="alert">
        <el-icon aria-hidden="true"><Document /></el-icon>
        <div>
          <h2>{{ parseFailureTitle }}</h2>
          <p>{{ parseFailureMessage }}</p>
        </div>
      </section>
      <el-tabs v-model="activeTab" class="material-tabs">
        <el-tab-pane label="内容" name="content">
          <section v-if="content" class="content-panel">
            <div class="content-panel__meta">
              <span>{{ content.parser_name }} · {{ content.total_length }} 字符</span
              ><span v-if="content.page_count">共 {{ content.page_count }} 页</span>
            </div>
            <pre>{{ content.text }}</pre>
            <p v-if="content.has_more" class="content-panel__note">当前仅展示部分文本内容。</p>
          </section>
          <p v-else class="content-panel__note">完整文本暂不可用，请重新上传原文件。</p>
        </el-tab-pane>
        <el-tab-pane label="摘要" name="summary">
          <section class="ai-tool-panel">
            <div v-if="summary?.summary" class="summary-layout">
              <article class="summary-overview">
                <h2>核心概览</h2>
                <p>{{ summary.summary.overview }}</p>
              </article>
              <article
                v-for="section in [
                  { title: '关键概念', items: summary.summary.key_concepts },
                  { title: '重要内容', items: summary.summary.important_points },
                  { title: '易错点', items: summary.summary.common_mistakes },
                  { title: '复习建议', items: summary.summary.review_suggestions },
                ]"
                :key="section.title"
                class="summary-section"
              >
                <h3>{{ section.title }}</h3>
                <ul v-if="section.items.length">
                  <li v-for="item in section.items" :key="item">{{ item }}</li>
                </ul>
                <p v-else>当前没有可展示的内容。</p>
              </article>
              <p class="ai-provenance">
                生成来源：{{ summary.summary.provider }} / {{ summary.summary.model }} ·
                {{ summary.summary.prompt_version }}
              </p>
              <el-button
                v-if="!parseFailed"
                :loading="summaryLoading"
                plain
                @click="generateSummary"
                >重新生成摘要</el-button
              >
            </div>
            <EmptyState
              v-else
              :icon="Reading"
              title="尚未生成摘要"
              description="将资料整理为核心概览、重要概念和复习要点。"
            >
              <template v-if="!parseFailed" #action
                ><el-button type="primary" :loading="summaryLoading" @click="generateSummary"
                  >生成摘要</el-button
                ></template
              >
            </EmptyState>
          </section>
        </el-tab-pane>
        <el-tab-pane label="学习卡片" name="cards">
          <section class="ai-tool-panel">
            <div v-if="cards?.cards.length" class="study-card-list">
              <button
                v-for="card in cards.cards"
                :key="card.id"
                class="study-card"
                type="button"
                :aria-expanded="expandedCardId === card.id"
                @click="toggleCard(card.id)"
              >
                <span class="study-card__label">问题 {{ card.order_index }}</span
                ><strong>{{ card.question }}</strong>
                <p v-if="expandedCardId === card.id">{{ card.answer }}</p>
                <small v-if="card.knowledge_hint">{{ card.knowledge_hint }}</small
                ><small v-if="card.source_reference">来源：{{ card.source_reference }}</small>
              </button>
              <el-button v-if="!parseFailed" :loading="cardsLoading" plain @click="generateCards"
                >重新生成学习卡片</el-button
              >
              <p v-if="cards.cards_method" class="ai-provenance">
                生成来源：{{ cards.cards_method }}
              </p>
            </div>
            <EmptyState
              v-else
              :icon="DocumentCopy"
              title="尚未生成学习卡片"
              description="从资料中生成便于回顾的问答卡片。"
            >
              <template v-if="!parseFailed" #action
                ><el-button type="primary" :loading="cardsLoading" @click="generateCards"
                  >生成学习卡片</el-button
                ></template
              >
            </EmptyState>
          </section>
        </el-tab-pane>
        <el-tab-pane label="资料问答" name="qa">
          <section class="qa-panel">
            <div class="qa-panel__intro">
              <el-icon aria-hidden="true"><ChatRound /></el-icon>
              <div>
                <h2>针对当前资料提问</h2>
                <p>围绕当前资料提问，并查看回答依据。回答只基于已解析内容。</p>
              </div>
            </div>
            <form @submit.prevent="askQuestion">
              <el-input
                v-model="qaQuestion"
                :disabled="parseFailed"
                type="textarea"
                :rows="3"
                maxlength="1000"
                show-word-limit
                placeholder="例如：这份资料主要讲了哪些核心概念？"
              /><el-button
                type="primary"
                native-type="submit"
                :loading="qaLoading"
                :disabled="parseFailed || !qaQuestion.trim()"
                >提问</el-button
              >
            </form>
            <article v-if="qaAnswer" class="qa-answer">
              <p>{{ qaAnswer.answer }}</p>
              <div v-if="qaAnswer.references.length" class="qa-answer__references">
                <span>参考资料</span>
                <ul>
                  <li v-for="reference in qaAnswer.references" :key="reference">{{ reference }}</li>
                </ul>
              </div>
            </article>
            <p v-if="qaProvenance" class="ai-provenance">{{ qaProvenance }}</p>
          </section>
        </el-tab-pane>
      </el-tabs>
      <p v-if="aiError" class="ai-error" role="alert">{{ aiError }}</p>
    </template>
  </section>
</template>

<style scoped>
.material-source-note {
  margin: 1rem 0 0;
  padding: 0.7rem 0.9rem;
  border: 1px solid #d7e4f3;
  border-radius: 10px;
  color: #395a7e;
  background: #f5f9fe;
  font-size: 0.83rem;
}
</style>
