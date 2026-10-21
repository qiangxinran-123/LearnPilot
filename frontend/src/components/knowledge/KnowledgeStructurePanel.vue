<script setup lang="ts">
import { ArrowRight, MagicStick, RefreshRight, Search } from '@element-plus/icons-vue';
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router';
import type { ElTree } from 'element-plus';

import { presentBuildStatus } from '@/components/knowledge/buildStatus';
import KnowledgeFocusGraph from '@/components/knowledge/KnowledgeFocusGraph.vue';
import {
  adaptKnowledgeModelToFocus,
  canonicalNodeIndex,
  chooseDefaultFocusNodeId,
  directParentNodes,
} from '@/components/knowledge/knowledgeMapAdapter';
import {
  adaptKnowledgeModelToTree,
  searchKnowledgeTree,
  type KnowledgeTreeNode,
} from '@/components/knowledge/treeAdapter';
import type { Material } from '@/types/course';
import type { KnowledgeBuildStatus, KnowledgeModelResponse } from '@/types/knowledge';
import { fetchCourseMastery } from '@/services/mastery';
import { normalizeApiError } from '@/services/http';
import type { KnowledgeNodeMastery } from '@/types/mastery';
import {
  confidenceLabel,
  masteryScoreLabel,
  masteryStatusLabel,
} from '@/components/knowledge/masteryPresentation';

const props = defineProps<{
  courseId: number;
  materials: Material[];
  model: KnowledgeModelResponse | null;
  modelState: 'loading' | 'ready' | 'error';
  modelError: string;
  status: KnowledgeBuildStatus | null;
  isRunning: boolean;
}>();
const emit = defineEmits<{ retry: []; build: [] }>();
const route = useRoute();
const router = useRouter();
const treeRef = ref<InstanceType<typeof ElTree>>();
const search = ref('');
const focusNodeId = ref<number | null>(null);
const masteryByNodeId = ref<ReadonlyMap<number, KnowledgeNodeMastery>>(new Map());
const masteryState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle');
const masteryError = ref('');
let masteryRequest = 0;
let loadedMasteryCourseId: number | null = null;
let observedMasteryCourseId = props.courseId;
let observedMasteryModel = props.model;

const mapMode = computed<'structure' | 'mastery'>({
  get: () => (route.query.mode === 'mastery' ? 'mastery' : 'structure'),
  set(mode) {
    const query: LocationQueryRaw = { ...route.query, tab: 'knowledge-structure' };
    if (mode === 'mastery') query.mode = 'mastery';
    else delete query.mode;
    void router.replace({ name: 'course-detail', params: { courseId: props.courseId }, query });
  },
});

const hasNodes = computed(() => (props.model?.nodes.length ?? 0) > 0);
const treeData = computed(() => (props.model ? adaptKnowledgeModelToTree(props.model) : null));
const searchResult = computed(() => searchKnowledgeTree(treeData.value?.roots ?? [], search.value));
const matches = computed(() =>
  [...searchResult.value.matchedIds]
    .map((id) => treeData.value?.nodeById.get(id))
    .filter((node): node is KnowledgeTreeNode => node !== undefined),
);
const focusData = computed(() =>
  props.model
    ? adaptKnowledgeModelToFocus(props.model, focusNodeId.value)
    : {
        focusNode: null,
        prerequisiteNodes: [],
        dependentNodes: [],
        prerequisiteEdges: [],
        dependentEdges: [],
        ignoredEdgeIds: [],
      },
);
const parentTopics = computed(() =>
  props.model && focusNodeId.value !== null
    ? directParentNodes(props.model, focusNodeId.value)
    : [],
);
const containsCount = computed(
  () => props.model?.edges.filter((edge) => edge.relation_type === 'contains').length ?? 0,
);
const prerequisiteCount = computed(
  () => props.model?.edges.filter((edge) => edge.relation_type === 'prerequisite').length ?? 0,
);
const buildPresentation = computed(() => (props.status ? presentBuildStatus(props.status) : null));
const detailRoute = computed(() => ({
  name: 'knowledge-detail',
  params: { courseId: props.courseId, nodeId: focusNodeId.value },
  query: {
    from: 'knowledge-structure',
    ...(mapMode.value === 'mastery' ? { mode: 'mastery' } : {}),
  },
}));
const focusedMastery = computed(() =>
  focusNodeId.value === null ? undefined : masteryByNodeId.value.get(focusNodeId.value),
);

async function loadMastery(force = false): Promise<void> {
  if (!props.model || mapMode.value !== 'mastery') return;
  if (!force && loadedMasteryCourseId === props.courseId && masteryState.value === 'ready') return;
  const request = ++masteryRequest;
  const requestedCourseId = props.courseId;
  masteryState.value = 'loading';
  masteryError.value = '';
  try {
    const response = await fetchCourseMastery(requestedCourseId);
    if (request !== masteryRequest || requestedCourseId !== props.courseId) return;
    if (response.course_id !== requestedCourseId) throw new Error('Mastery course mismatch');
    const currentIds = canonicalNodeIndex(props.model);
    masteryByNodeId.value = new Map(
      response.nodes
        .filter((item) => currentIds.has(item.knowledge_node_id))
        .map((item) => [item.knowledge_node_id, item]),
    );
    loadedMasteryCourseId = requestedCourseId;
    masteryState.value = 'ready';
  } catch (error: unknown) {
    if (request !== masteryRequest || requestedCourseId !== props.courseId) return;
    masteryByNodeId.value = new Map();
    masteryError.value = normalizeApiError(error).message;
    masteryState.value = 'error';
  }
}

function queryNodeId(): number | null {
  const raw = Array.isArray(route.query.nodeId) ? route.query.nodeId[0] : route.query.nodeId;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}
function filterTreeNode(_query: string, node: KnowledgeTreeNode): boolean {
  return !search.value.trim() || searchResult.value.visibleIds.has(node.id);
}
function locateNode(nodeId: number): void {
  let parentId = treeData.value?.parentIdByNodeId.get(nodeId);
  while (parentId !== undefined) {
    treeRef.value?.getNode(parentId)?.expand();
    parentId = treeData.value?.parentIdByNodeId.get(parentId);
  }
  treeRef.value?.setCurrentKey(nodeId);
}
async function replaceFocusQuery(nodeId: number): Promise<void> {
  const query: Record<string, string | string[]> = {
    ...route.query,
    tab: 'knowledge-structure',
    nodeId: String(nodeId),
  };
  delete query.view;
  await router.replace({ name: 'course-detail', params: { courseId: props.courseId }, query });
}
function focusNode(nodeId: number): void {
  if (!props.model || !canonicalNodeIndex(props.model).has(nodeId)) return;
  focusNodeId.value = nodeId;
  locateNode(nodeId);
  if (queryNodeId() !== nodeId) void replaceFocusQuery(nodeId);
}
function clearSearch(): void {
  search.value = '';
}

watch(search, async () => {
  await nextTick();
  treeRef.value?.filter(search.value);
  for (const id of searchResult.value.expandedIds) treeRef.value?.getNode(id)?.expand();
});
watch(
  [() => props.courseId, () => props.model, () => route.query.nodeId],
  async () => {
    if (!props.model) {
      focusNodeId.value = null;
      return;
    }
    const nodeById = canonicalNodeIndex(props.model);
    const requested = queryNodeId();
    const nextId =
      requested !== null && nodeById.has(requested)
        ? requested
        : chooseDefaultFocusNodeId(props.model);
    focusNodeId.value = nextId;
    await nextTick();
    if (nextId !== null) {
      locateNode(nextId);
      if (requested !== nextId) await replaceFocusQuery(nextId);
    }
  },
  { immediate: true },
);
watch(
  [() => props.courseId, () => props.model, mapMode],
  ([nextCourseId, nextModel, mode]) => {
    if (nextCourseId !== observedMasteryCourseId || nextModel !== observedMasteryModel) {
      masteryRequest += 1;
      loadedMasteryCourseId = null;
      masteryByNodeId.value = new Map();
      masteryState.value = 'idle';
      masteryError.value = '';
      observedMasteryCourseId = nextCourseId;
      observedMasteryModel = nextModel;
    }
    if (mode === 'mastery') void loadMastery();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  masteryRequest += 1;
});
</script>

<template>
  <section class="knowledge-map" aria-labelledby="knowledge-map-heading">
    <header class="knowledge-map__header">
      <div>
        <h2 id="knowledge-map-heading">课程知识地图</h2>
        <p>从课程主题中找到知识点，沿真实的直接先修关系逐步探索。</p>
      </div>
      <el-radio-group v-model="mapMode" size="small" aria-label="知识地图展示模式">
        <el-radio-button value="structure">课程结构</el-radio-button>
        <el-radio-button value="mastery">我的掌握状态</el-radio-button>
      </el-radio-group>
      <el-button
        v-if="buildPresentation?.action && status?.can_build"
        type="primary"
        :disabled="isRunning"
        :loading="isRunning"
        @click="emit('build')"
      >
        <el-icon><RefreshRight v-if="hasNodes" /><MagicStick v-else /></el-icon
        >{{ buildPresentation.action }}
      </el-button>
    </header>
    <p v-if="isRunning" class="knowledge-map__status" role="status">
      {{ buildPresentation?.detail || '正在构建课程知识结构…' }}
    </p>
    <p
      v-if="status?.state === 'failed' || status?.state === 'update_failed'"
      class="knowledge-map__warning"
      role="alert"
    >
      {{ buildPresentation?.detail }}
    </p>
    <p v-if="modelError && model" class="knowledge-map__warning" role="alert">
      最新结果加载失败，当前仍展示已读取的知识结构：{{ modelError }}
    </p>
    <p
      v-if="mapMode === 'mastery' && masteryState === 'loading'"
      class="knowledge-map__status"
      role="status"
    >
      正在读取已保存的掌握状态…
    </p>
    <div
      v-if="mapMode === 'mastery' && masteryState === 'error'"
      class="knowledge-map__warning"
      role="alert"
    >
      掌握状态暂不可用，课程结构仍可正常查看：{{ masteryError }}
      <el-button link type="primary" @click="loadMastery(true)">重试</el-button>
    </div>

    <div v-if="modelState === 'loading' && !model" class="knowledge-map__message" role="status">
      正在加载课程知识结构…
    </div>
    <div v-else-if="modelState === 'error' && !model" class="knowledge-map__message" role="alert">
      <p>课程知识结构加载失败：{{ modelError }}</p>
      <el-button @click="emit('retry')">重试</el-button>
    </div>
    <div v-else-if="!hasNodes" class="knowledge-map__message">
      <p>当前课程暂无已确认的知识点。请先上传可解析资料，再主动生成知识结构。</p>
    </div>

    <template v-else-if="model && treeData && focusData.focusNode">
      <div class="knowledge-map__summary" aria-label="课程知识统计">
        <span
          ><strong>{{ model.nodes.length }}</strong> 个知识点</span
        ><span
          ><strong>{{ containsCount }}</strong> 条层级关系</span
        ><span
          ><strong>{{ prerequisiteCount }}</strong> 条先修关系</span
        >
      </div>
      <div class="knowledge-map__workspace">
        <aside class="knowledge-navigator" aria-labelledby="knowledge-navigator-heading">
          <div class="knowledge-navigator__heading">
            <div>
              <h3 id="knowledge-navigator-heading">课程知识导航</h3>
              <p>{{ treeData.roots.length }} 个顶层主题</p>
            </div>
          </div>
          <label class="knowledge-navigator__search"
            ><span class="visually-hidden">搜索课程知识点</span
            ><el-icon aria-hidden="true"><Search /></el-icon
            ><input
              v-model="search"
              type="search"
              maxlength="120"
              placeholder="搜索知识点"
            /><button v-if="search" type="button" @click="clearSearch">清空</button></label
          >
          <p v-if="search.trim() && !matches.length" class="knowledge-navigator__empty">
            没有找到匹配的知识点。
          </p>
          <div v-else class="knowledge-navigator__tree">
            <p v-if="search.trim()" class="knowledge-navigator__result-count">
              找到 {{ matches.length }} 个匹配项
            </p>
            <el-tree
              ref="treeRef"
              :data="treeData.roots"
              node-key="id"
              :props="{ label: 'label', children: 'children' }"
              :default-expanded-keys="treeData.roots.map((node) => node.id)"
              :current-node-key="focusNodeId"
              :filter-node-method="filterTreeNode"
              highlight-current
              @node-click="(node: KnowledgeTreeNode) => focusNode(node.id)"
            >
              <template #default="{ data }">
                <button
                  type="button"
                  class="knowledge-navigator__node"
                  :data-knowledge-tree-id="data.id"
                  :aria-current="data.id === focusNodeId ? 'true' : undefined"
                  @click.stop="focusNode(data.id)"
                >
                  <span>{{ data.label }}</span>
                  <small v-if="mapMode === 'mastery'">
                    {{ masteryScoreLabel(masteryByNodeId.get(data.id)) }}
                  </small>
                </button>
              </template>
            </el-tree>
          </div>
          <p v-if="treeData.ignoredEdgeIds.length" class="knowledge-map__warning" role="status">
            {{ treeData.ignoredEdgeIds.length }} 条异常层级关系未展示，知识点仍保留在导航中。
          </p>
        </aside>

        <main class="knowledge-map__main">
          <KnowledgeFocusGraph
            :data="focusData"
            :mastery-mode="mapMode === 'mastery'"
            :mastery-by-node-id="masteryByNodeId"
            @focus="focusNode"
          />
          <p v-if="focusData.ignoredEdgeIds.length" class="knowledge-map__warning" role="status">
            {{ focusData.ignoredEdgeIds.length }} 条异常先修关系未展示。
          </p>
          <section class="knowledge-preview" aria-labelledby="knowledge-preview-heading">
            <div class="knowledge-preview__content">
              <p class="knowledge-preview__label">当前知识点</p>
              <h3 id="knowledge-preview-heading">{{ focusData.focusNode.name }}</h3>
              <div v-if="parentTopics.length" class="knowledge-preview__topics">
                <span>属于</span
                ><button
                  v-for="topic in parentTopics"
                  :key="topic.id"
                  type="button"
                  @click="focusNode(topic.id)"
                >
                  {{ topic.name }}
                </button>
              </div>
              <p>{{ focusData.focusNode.description || '当前知识点尚无已保存的简短说明。' }}</p>
              <dl v-if="mapMode === 'mastery'" class="knowledge-preview__mastery">
                <div>
                  <dt>掌握度</dt>
                  <dd>{{ masteryScoreLabel(focusedMastery) }}</dd>
                </div>
                <div>
                  <dt>状态</dt>
                  <dd>
                    {{ masteryStatusLabel[focusedMastery?.mastery_status ?? 'not_assessed'] }}
                  </dd>
                </div>
                <div>
                  <dt>置信度</dt>
                  <dd>{{ confidenceLabel[focusedMastery?.confidence_level ?? 'insufficient'] }}</dd>
                </div>
                <div>
                  <dt>有效证据</dt>
                  <dd>{{ focusedMastery?.evidence_count ?? 0 }} 条</dd>
                </div>
              </dl>
            </div>
            <RouterLink class="knowledge-preview__detail" :to="detailRoute"
              >查看完整知识详情 <el-icon aria-hidden="true"><ArrowRight /></el-icon
            ></RouterLink>
          </section>
        </main>
      </div>
    </template>
  </section>
</template>

<style scoped>
.knowledge-map {
  min-width: 0;
  padding-top: var(--lp-space-3);
}
.knowledge-map__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--lp-space-5);
}
.knowledge-map__header h2,
.knowledge-navigator h3,
.knowledge-preview h3 {
  margin: 0;
  color: var(--lp-ink);
}
.knowledge-map__header p,
.knowledge-navigator__heading p {
  margin: 0.35rem 0 0;
  color: var(--lp-text-secondary);
  line-height: 1.6;
}
.knowledge-map__status,
.knowledge-map__warning,
.knowledge-map__message {
  margin-top: var(--lp-space-4);
  padding: 0.75rem 0.9rem;
  border-radius: var(--lp-radius-md);
}
.knowledge-map__status {
  color: #315b91;
  background: #edf4ff;
}
.knowledge-map__warning {
  color: #795920;
  background: #fff7e7;
}
.knowledge-map__message {
  display: grid;
  justify-items: start;
  gap: var(--lp-space-3);
  min-height: 12rem;
  align-content: center;
  color: var(--lp-text-secondary);
}
.knowledge-map__message p {
  margin: 0;
}
.knowledge-map__summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--lp-space-4);
  margin: var(--lp-space-5) 0 var(--lp-space-4);
  color: var(--lp-text-secondary);
  font-size: 0.82rem;
}
.knowledge-map__summary strong {
  color: var(--lp-ink);
}
.knowledge-map__workspace {
  display: grid;
  grid-template-columns: minmax(240px, 28%) minmax(0, 1fr);
  align-items: start;
  gap: var(--lp-space-4);
}
.knowledge-navigator {
  position: sticky;
  top: var(--lp-space-4);
  min-width: 0;
  max-height: min(70vh, 46rem);
  padding: var(--lp-space-4);
  overflow: hidden;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
}
.knowledge-navigator__heading {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-3);
}
.knowledge-navigator__heading h3 {
  font-size: 1rem;
}
.knowledge-navigator__heading p {
  font-size: 0.75rem;
}
.knowledge-navigator__search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: var(--lp-space-4);
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
  color: var(--lp-text-secondary);
  background: var(--lp-canvas);
}
.knowledge-navigator__search:focus-within {
  border-color: var(--lp-primary);
  box-shadow: 0 0 0 3px rgb(61 111 183 / 12%);
}
.knowledge-navigator__search input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  color: var(--lp-text);
  background: transparent;
}
.knowledge-navigator__search button {
  padding: 0;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  font-size: 0.75rem;
  cursor: pointer;
}
.knowledge-navigator__tree {
  max-height: calc(min(70vh, 46rem) - 8rem);
  margin-top: var(--lp-space-3);
  overflow: auto;
  scrollbar-width: thin;
}
.knowledge-navigator__result-count,
.knowledge-navigator__empty {
  margin: var(--lp-space-3) 0;
  color: var(--lp-text-secondary);
  font-size: 0.78rem;
}
.knowledge-navigator :deep(.el-tree) {
  --el-tree-node-hover-bg-color: #f2f6fc;
  background: transparent;
}
.knowledge-navigator :deep(.el-tree-node__content) {
  min-height: 2.35rem;
  height: auto;
  border-radius: 8px;
}
.knowledge-navigator :deep(.el-tree-node.is-current > .el-tree-node__content) {
  color: var(--lp-primary);
  background: #eaf2ff;
  font-weight: 700;
}
.knowledge-navigator__node {
  border: 0;
  min-width: 0;
  padding: 0.35rem 0.2rem;
  color: inherit;
  background: transparent;
  font: inherit;
  text-align: left;
  line-height: 1.35;
  overflow-wrap: anywhere;
  cursor: pointer;
}
.knowledge-navigator__node small {
  margin-left: 0.45rem;
  color: #687891;
  font-size: 0.68rem;
  font-weight: 700;
}
.knowledge-navigator__node:focus-visible {
  border-radius: 5px;
  outline: 2px solid var(--lp-primary);
  outline-offset: 2px;
}
.knowledge-map__main {
  display: grid;
  min-width: 0;
  gap: var(--lp-space-4);
}
.knowledge-preview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lp-space-5);
  min-width: 0;
  padding: var(--lp-space-5);
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}
.knowledge-preview__content {
  min-width: 0;
}
.knowledge-preview__label {
  margin: 0 0 0.25rem !important;
  color: var(--lp-primary) !important;
  font-size: 0.75rem;
  font-weight: 700;
}
.knowledge-preview h3 {
  font-size: 1.15rem;
}
.knowledge-preview p {
  max-width: 48rem;
  margin: 0.65rem 0 0;
  color: var(--lp-text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.knowledge-preview__mastery {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin: 0.85rem 0 0;
}
.knowledge-preview__mastery div {
  min-width: 6.5rem;
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  background: #f4f7fb;
}
.knowledge-preview__mastery dt {
  color: var(--lp-text-secondary);
  font-size: 0.68rem;
}
.knowledge-preview__mastery dd {
  margin: 0.18rem 0 0;
  color: var(--lp-ink);
  font-size: 0.8rem;
  font-weight: 700;
}
.knowledge-preview__topics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.55rem;
  color: var(--lp-text-secondary);
  font-size: 0.78rem;
}
.knowledge-preview__topics button {
  padding: 0.2rem 0.5rem;
  border: 1px solid #ccd9eb;
  border-radius: 999px;
  color: var(--lp-primary);
  background: #f7faff;
  cursor: pointer;
}
.knowledge-preview__detail {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.45rem;
  padding: 0.72rem 1rem;
  border-radius: var(--lp-radius-md);
  color: #fff;
  background: var(--lp-primary);
  font-weight: 700;
  text-decoration: none;
}
.knowledge-preview__detail:hover {
  filter: brightness(0.95);
}
.knowledge-preview__detail:focus-visible,
.knowledge-preview__topics button:focus-visible,
.knowledge-navigator__search button:focus-visible {
  outline: 3px solid rgb(61 111 183 / 25%);
  outline-offset: 2px;
}
@media (max-width: 960px) {
  .knowledge-map__workspace {
    grid-template-columns: 1fr;
  }
  .knowledge-navigator {
    position: static;
    max-height: none;
  }
  .knowledge-navigator__tree {
    max-height: 22rem;
  }
}
@media (max-width: 600px) {
  .knowledge-map__header,
  .knowledge-preview {
    display: grid;
  }
  .knowledge-map__header :deep(.el-button),
  .knowledge-preview__detail {
    width: 100%;
    justify-content: center;
  }
  .knowledge-map__workspace {
    gap: var(--lp-space-3);
  }
  .knowledge-navigator,
  .knowledge-preview {
    padding: var(--lp-space-4);
  }
}
</style>
