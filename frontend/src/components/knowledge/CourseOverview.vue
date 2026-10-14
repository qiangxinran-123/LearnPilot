<script setup lang="ts">
import { ArrowRight, Document, Search, Share } from '@element-plus/icons-vue';
import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { presentBuildStatus } from '@/components/knowledge/buildStatus';
import { fetchCanonicalNodes } from '@/services/knowledge';
import { normalizeApiError } from '@/services/http';
import type { Material } from '@/types/course';
import type { CanonicalNodePage, KnowledgeBuildStatus } from '@/types/knowledge';

const props = defineProps<{
  courseId: number;
  materials: Material[];
  status: KnowledgeBuildStatus | null;
  statusState: 'loading' | 'ready' | 'error';
  statusError: string;
  buildError: string;
  isRunning: boolean;
}>();

const emit = defineEmits<{
  materials: [];
  structure: [];
  upload: [];
  build: [];
}>();

const search = ref('');
const expanded = ref(false);
const offset = ref(0);
const page = ref<CanonicalNodePage | null>(null);
const listState = ref<'loading' | 'ready' | 'error'>('loading');
const listError = ref('');
const searchRegion = ref<HTMLElement>();
const searchInput = ref<HTMLInputElement>();
let debounceTimer: ReturnType<typeof setTimeout> | undefined;
let requestId = 0;
let disposed = false;

const pageSize = computed(() => (expanded.value ? 24 : 6));
const presentation = computed(() => (props.status ? presentBuildStatus(props.status) : null));
const relationshipCount = computed(
  () => (props.status?.contains_edge_count ?? 0) + (props.status?.prerequisite_edge_count ?? 0),
);

async function loadNodes(): Promise<void> {
  const currentRequest = ++requestId;
  const requestedCourse = props.courseId;
  listState.value = 'loading';
  listError.value = '';
  try {
    const result = await fetchCanonicalNodes(requestedCourse, {
      query: search.value.trim(),
      offset: offset.value,
      limit: pageSize.value,
    });
    if (disposed || currentRequest !== requestId || props.courseId !== requestedCourse) return;
    page.value = result;
    listState.value = 'ready';
  } catch (error: unknown) {
    if (disposed || currentRequest !== requestId || props.courseId !== requestedCourse) return;
    page.value = null;
    listState.value = 'error';
    listError.value = normalizeApiError(error).message;
  }
}

function showAll(): void {
  expanded.value = true;
  offset.value = 0;
}

function changePage(nextOffset: number): void {
  if (!page.value || nextOffset < 0 || nextOffset >= page.value.total) return;
  offset.value = nextOffset;
  void loadNodes();
  searchRegion.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
}

function focusSearch(): void {
  searchRegion.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  searchInput.value?.focus();
}

function refreshList(): void {
  offset.value = 0;
  void loadNodes();
}

watch(
  [() => props.courseId, search, expanded],
  (value, previous) => {
    if (debounceTimer) clearTimeout(debounceTimer);
    requestId += 1;
    if (value[0] !== previous?.[0]) {
      search.value = '';
      expanded.value = false;
      page.value = null;
    }
    offset.value = 0;
    const delay = previous?.[1] !== undefined && value[1] !== previous[1] ? 220 : 0;
    if (delay) debounceTimer = setTimeout(() => void loadNodes(), delay);
    else void loadNodes();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  disposed = true;
  requestId += 1;
  if (debounceTimer) clearTimeout(debounceTimer);
});

defineExpose({ focusSearch, refreshList });
</script>

<template>
  <div class="course-overview">
    <section
      v-if="presentation"
      class="overview-build"
      :class="`overview-build--${presentation.tone}`"
      aria-live="polite"
    >
      <div class="overview-build__copy">
        <strong>{{ presentation.title }}</strong>
        <p>{{ presentation.detail }}</p>
        <p v-if="buildError" class="overview-build__error" role="alert">{{ buildError }}</p>
      </div>
      <div class="overview-build__action">
        <el-button
          v-if="presentation.action && status?.can_build"
          type="primary"
          :loading="isRunning"
          :disabled="isRunning"
          @click="emit('build')"
          >{{ presentation.action }}</el-button
        >
        <el-button
          v-else-if="status?.state === 'no_materials'"
          type="primary"
          @click="emit('upload')"
        >
          上传资料
        </el-button>
        <span v-else-if="status?.state === 'running'" class="overview-build__working">
          请稍候，可离开本页后返回查看
        </span>
      </div>
    </section>
    <section
      v-else-if="statusState === 'error'"
      class="overview-build overview-build--error"
      role="alert"
    >
      <div class="overview-build__copy">
        <strong>知识构建状态暂不可用</strong>
        <p>{{ statusError }}</p>
      </div>
    </section>
    <section v-else class="overview-build overview-build--neutral" role="status">
      正在读取课程知识构建状态…
    </section>

    <section class="overview-stats" aria-label="课程统计">
      <article class="overview-stat">
        <span class="overview-stat__label">课程资料</span>
        <strong>{{ materials.length }}</strong>
        <span class="overview-stat__hint">当前课程的真实资料</span>
      </article>
      <article class="overview-stat">
        <span class="overview-stat__label">知识点</span>
        <strong>{{ status ? status.node_count : '—' }}</strong>
        <span class="overview-stat__hint">已确认的课程知识</span>
      </article>
      <article class="overview-stat">
        <span class="overview-stat__label">知识关系</span>
        <strong>{{ status ? relationshipCount : '—' }}</strong>
        <span class="overview-stat__hint">层级与先修关系</span>
      </article>
    </section>

    <section class="overview-actions" aria-label="学习任务入口">
      <button class="overview-action" type="button" @click="emit('materials')">
        <span class="overview-action__icon"
          ><el-icon><Document /></el-icon
        ></span>
        <span class="overview-action__copy">
          <strong>理解课程资料</strong>
          <small>摘要、学习卡片、资料问答</small>
        </span>
        <el-icon class="overview-action__arrow"><ArrowRight /></el-icon>
      </button>
      <button class="overview-action" type="button" @click="focusSearch">
        <span class="overview-action__icon"
          ><el-icon><Search /></el-icon
        ></span>
        <span class="overview-action__copy">
          <strong>查找知识点</strong>
          <small>搜索概念、查看知识详情</small>
        </span>
        <el-icon class="overview-action__arrow"><ArrowRight /></el-icon>
      </button>
      <button class="overview-action" type="button" @click="emit('structure')">
        <span class="overview-action__icon"
          ><el-icon><Share /></el-icon
        ></span>
        <span class="overview-action__copy">
          <strong>了解课程结构</strong>
          <small>知识层级、先修关系</small>
        </span>
        <el-icon class="overview-action__arrow"><ArrowRight /></el-icon>
      </button>
    </section>

    <section
      ref="searchRegion"
      class="overview-knowledge"
      aria-labelledby="course-knowledge-heading"
    >
      <div class="overview-knowledge__heading">
        <div>
          <h2 id="course-knowledge-heading">课程知识点</h2>
          <p>从已确认的课程知识出发，查看概念、关联和真实资料依据。</p>
        </div>
        <button
          v-if="!expanded && (page?.total ?? 0) > 0"
          type="button"
          class="overview-link"
          @click="showAll"
        >
          查看全部 <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
      <label class="overview-search">
        <span class="visually-hidden">搜索当前课程知识点名称</span>
        <el-icon aria-hidden="true"><Search /></el-icon>
        <input
          ref="searchInput"
          v-model="search"
          type="search"
          maxlength="120"
          placeholder="搜索知识点名称"
        />
      </label>

      <p v-if="listState === 'loading'" class="overview-knowledge__message" role="status">
        正在加载知识点…
      </p>
      <div v-else-if="listState === 'error'" class="overview-knowledge__message" role="alert">
        <span>{{ listError }}</span>
        <el-button plain @click="loadNodes">重试</el-button>
      </div>
      <p v-else-if="!page?.nodes.length" class="overview-knowledge__message">
        {{ search.trim() ? '没有找到匹配的课程知识点。' : '当前课程暂无已确认的知识点。' }}
      </p>
      <div v-else class="overview-node-list">
        <article v-for="node in page.nodes" :key="node.id" class="overview-node">
          <div class="overview-node__body">
            <h3>{{ node.name }}</h3>
            <p v-if="node.description">{{ node.description }}</p>
            <p v-else class="overview-node__muted">暂无概念说明，可在详情中查看已有资料依据。</p>
          </div>
          <router-link
            :to="`/courses/${courseId}/knowledge/${node.id}?from=overview`"
            class="overview-node__link"
          >
            查看知识详情 <el-icon><ArrowRight /></el-icon>
          </router-link>
        </article>
      </div>
      <div v-if="expanded && page && page.total > page.limit" class="overview-pagination">
        <span
          >第 {{ page.offset + 1 }}–{{
            Math.min(page.offset + page.nodes.length, page.total)
          }}
          项，共 {{ page.total }} 项</span
        >
        <div>
          <el-button
            :disabled="offset === 0"
            plain
            @click="changePage(Math.max(0, offset - pageSize))"
            >上一页</el-button
          >
          <el-button
            :disabled="offset + pageSize >= page.total"
            plain
            @click="changePage(offset + pageSize)"
            >下一页</el-button
          >
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.course-overview {
  display: grid;
  gap: 1.25rem;
  padding-top: 0.25rem;
}
.overview-build {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 0.95rem 1.2rem;
  border: 1px solid #d8e4f2;
  border-radius: 12px;
  background: #f5f9fe;
}
.overview-build--success {
  border-color: #d3e8db;
  background: #f6fcf8;
}
.overview-build--warning {
  border-color: #eadfbe;
  background: #fffcf5;
}
.overview-build--error {
  border-color: #f0d1cf;
  background: #fff8f7;
}
.overview-build--active {
  border-color: #bed5f3;
  background: #f3f8ff;
}
.overview-build__copy strong {
  color: var(--lp-ink);
  font-size: 0.92rem;
}
.overview-build__copy p {
  margin: 0.18rem 0 0;
  color: var(--lp-text-secondary);
  font-size: 0.82rem;
}
.overview-build__copy .overview-build__error {
  color: var(--lp-danger);
}
.overview-build__working {
  color: var(--lp-primary);
  font-size: 0.8rem;
}
.overview-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}
.overview-stat {
  display: grid;
  gap: 0.2rem;
  min-width: 0;
  padding: 1.1rem 1.25rem;
  border: 1px solid var(--lp-border);
  border-radius: 12px;
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}
.overview-stat__label {
  color: var(--lp-text-secondary);
  font-size: 0.82rem;
  font-weight: 600;
}
.overview-stat strong {
  color: var(--lp-ink);
  font-size: 1.72rem;
  line-height: 1.25;
}
.overview-stat__hint {
  color: var(--lp-text-tertiary);
  font-size: 0.75rem;
}
.overview-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}
.overview-action {
  display: flex;
  min-width: 0;
  min-height: 88px;
  align-items: center;
  gap: 0.8rem;
  padding: 0.9rem 1rem;
  border: 1px solid var(--lp-border);
  border-radius: 12px;
  color: inherit;
  background: #fff;
  box-shadow: var(--lp-shadow-sm);
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.18s,
    box-shadow 0.18s,
    transform 0.18s;
}
.overview-action:hover,
.overview-action:focus-visible {
  border-color: #a8c6e9;
  box-shadow: var(--lp-shadow-md);
  transform: translateY(-2px);
}
.overview-action__icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  place-items: center;
  border-radius: 10px;
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
  font-size: 19px;
}
.overview-action__copy {
  display: grid;
  min-width: 0;
  gap: 0.17rem;
}
.overview-action__copy strong {
  color: var(--lp-ink);
  font-size: 0.9rem;
}
.overview-action__copy small {
  color: var(--lp-text-secondary);
  font-size: 0.75rem;
  line-height: 1.4;
}
.overview-action__arrow {
  flex: 0 0 auto;
  margin-left: auto;
  color: var(--lp-primary);
}
.overview-knowledge {
  min-width: 0;
  padding: 1.25rem;
  border: 1px solid var(--lp-border);
  border-radius: 14px;
  background: #fff;
  box-shadow: var(--lp-shadow-sm);
  scroll-margin-top: 24px;
}
.overview-knowledge__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.overview-knowledge__heading h2 {
  margin: 0;
  color: var(--lp-ink);
  font-size: 1.18rem;
}
.overview-knowledge__heading p {
  margin: 0.2rem 0 0;
  color: var(--lp-text-secondary);
  font-size: 0.8rem;
}
.overview-link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  flex: 0 0 auto;
  padding: 0.15rem 0;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  cursor: pointer;
  font-size: 0.81rem;
  font-weight: 650;
}
.overview-link:hover {
  text-decoration: underline;
}
.overview-search {
  display: flex;
  width: min(100%, 470px);
  align-items: center;
  gap: 0.55rem;
  margin: 1rem 0 0.85rem;
  padding: 0.57rem 0.78rem;
  border: 1px solid var(--lp-border-strong);
  border-radius: 9px;
  color: var(--lp-text-tertiary);
}
.overview-search:focus-within {
  border-color: var(--lp-primary);
  box-shadow: 0 0 0 3px rgb(31 95 174 / 12%);
}
.overview-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  color: var(--lp-ink);
  background: transparent;
  font-size: 0.85rem;
}
.overview-node-list {
  display: grid;
}
.overview-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  min-width: 0;
  padding: 0.72rem 0.1rem;
  border-top: 1px solid #ebeff5;
}
.overview-node__body {
  min-width: 0;
}
.overview-node h3 {
  margin: 0;
  color: var(--lp-ink);
  font-size: 0.88rem;
  font-weight: 650;
}
.overview-node p {
  max-width: 780px;
  margin: 0.16rem 0 0;
  overflow: hidden;
  color: var(--lp-text-secondary);
  font-size: 0.78rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.overview-node .overview-node__muted {
  color: var(--lp-text-tertiary);
}
.overview-node__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  flex: 0 0 auto;
  color: var(--lp-primary);
  font-size: 0.78rem;
  font-weight: 650;
  text-decoration: none;
}
.overview-node__link:hover {
  text-decoration: underline;
}
.overview-knowledge__message {
  display: flex;
  min-height: 90px;
  align-items: center;
  gap: 1rem;
  margin: 0;
  color: var(--lp-text-secondary);
}
.overview-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #ebeff5;
  color: var(--lp-text-secondary);
  font-size: 0.78rem;
}
.overview-pagination > div {
  display: flex;
  gap: 0.5rem;
}
@media (max-width: 900px) {
  .overview-actions {
    grid-template-columns: 1fr;
  }
  .overview-action {
    min-height: 70px;
  }
}
@media (max-width: 600px) {
  .overview-build,
  .overview-knowledge__heading,
  .overview-pagination {
    align-items: flex-start;
    flex-direction: column;
  }
  .overview-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.5rem;
  }
  .overview-stat {
    padding: 0.8rem;
  }
  .overview-stat strong {
    font-size: 1.3rem;
  }
  .overview-stat__hint {
    display: none;
  }
  .overview-node {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.35rem;
  }
  .overview-node p {
    white-space: normal;
  }
}
</style>
