<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft, ArrowRight, Document, Link as LinkIcon } from '@element-plus/icons-vue';

import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import KnowledgeMasteryDetail from '@/components/knowledge/KnowledgeMasteryDetail.vue';
import { fetchCourse } from '@/services/courses';
import { normalizeApiError } from '@/services/http';
import {
  fetchKnowledgeModel,
  fetchKnowledgeNodeDetail,
  fetchKnowledgeRelationships,
} from '@/services/knowledge';
import { fetchMaterials } from '@/services/materials';
import { fetchNodeEvidence } from '@/services/mastery';
import type { CourseSummary, Material } from '@/types/course';
import type {
  KnowledgeEdge,
  KnowledgeEdgeEvidence,
  KnowledgeModelResponse,
  KnowledgeNode,
  KnowledgeNodeDetailResponse,
  KnowledgeRelationshipsResponse,
  KnowledgeSource,
} from '@/types/knowledge';
import type { KnowledgeEvidenceExplanation } from '@/types/mastery';

type RelationGroupKey = 'parent' | 'child' | 'prerequisite' | 'dependent';
type RelationGroup = {
  key: RelationGroupKey;
  title: string;
  hint: string;
  nodes: KnowledgeNode[];
};
type EvidenceRow = {
  edge: KnowledgeEdge;
  label: string;
  evidence: KnowledgeEdgeEvidence;
};
type SourceGroup = {
  key: string;
  material: Material | null;
  sources: KnowledgeSource[];
};

const route = useRoute();
const courseId = computed(() => Number(route.params.courseId));
const nodeId = computed(() => Number(route.params.nodeId));
const showMastery = computed(() => route.query.mode === 'mastery');
const returnTab = computed(() =>
  route.query.from === 'knowledge-structure' ? 'knowledge-structure' : 'overview',
);
const returnQuery = computed(() => ({
  tab: returnTab.value,
  ...(returnTab.value === 'knowledge-structure' ? { nodeId: String(nodeId.value) } : {}),
  ...(showMastery.value ? { mode: 'mastery' } : {}),
}));
const course = ref<CourseSummary | null>(null);
const detail = ref<KnowledgeNodeDetailResponse | null>(null);
const model = ref<KnowledgeModelResponse | null>(null);
const materials = ref<Material[]>([]);
const relationships = ref<KnowledgeRelationshipsResponse | null>(null);
const state = ref<'loading' | 'ready' | 'error'>('loading');
const errorMessage = ref('');
const materialsNotice = ref('');
const evidenceNotice = ref('');
const relationshipEvidenceExpanded = ref(false);
const masteryExplanation = ref<KnowledgeEvidenceExplanation | null>(null);
const masteryLoading = ref(false);
const masteryError = ref('');
let requestSequence = 0;
let masteryRequestSequence = 0;

const importanceLabel = computed(
  () => ({ low: '低', medium: '中', high: '高' })[detail.value?.node.importance ?? 'medium'],
);
const difficultyLabel = computed(
  () =>
    ({ basic: '基础', intermediate: '进阶', advanced: '高级' })[
      detail.value?.node.difficulty ?? 'intermediate'
    ],
);
const nodeById = computed(() => new Map((model.value?.nodes ?? []).map((node) => [node.id, node])));
const materialById = computed(
  () => new Map(materials.value.map((material) => [material.id, material])),
);
const validEdges = computed(() => {
  const currentNodeId = detail.value?.node.id;
  if (!currentNodeId) return [];
  return (detail.value?.related_edges ?? []).filter(
    (edge) =>
      edge.course_id === courseId.value &&
      (edge.source_node_id === currentNodeId || edge.target_node_id === currentNodeId) &&
      nodeById.value.has(edge.source_node_id) &&
      nodeById.value.has(edge.target_node_id),
  );
});
const relationGroups = computed<RelationGroup[]>(() => {
  const currentNodeId = detail.value?.node.id;
  const ids: Record<RelationGroupKey, Set<number>> = {
    parent: new Set(),
    child: new Set(),
    prerequisite: new Set(),
    dependent: new Set(),
  };
  for (const edge of validEdges.value) {
    if (edge.relation_type === 'contains') {
      if (edge.target_node_id === currentNodeId) ids.parent.add(edge.source_node_id);
      if (edge.source_node_id === currentNodeId) ids.child.add(edge.target_node_id);
    } else if (edge.relation_type === 'prerequisite') {
      if (edge.target_node_id === currentNodeId) ids.prerequisite.add(edge.source_node_id);
      if (edge.source_node_id === currentNodeId) ids.dependent.add(edge.target_node_id);
    }
  }
  const definitions: Array<Omit<RelationGroup, 'nodes'>> = [
    {
      key: 'prerequisite',
      title: '学习前可以先了解',
      hint: '课程知识结构中与当前知识直接相连的前置知识。',
    },
    {
      key: 'dependent',
      title: '接下来还可以看看',
      hint: '课程知识结构中以当前知识为基础的后续知识。',
    },
    { key: 'parent', title: '属于哪个主题？', hint: '当前知识点所属的直接上级主题。' },
    { key: 'child', title: '这个主题包含什么？', hint: '当前主题直接包含的下级知识。' },
  ];
  return definitions
    .map(({ key, title, hint }) => ({
      key,
      title,
      hint,
      nodes: [...ids[key]]
        .map((id) => nodeById.value.get(id))
        .filter((node): node is KnowledgeNode => node !== undefined)
        .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN') || a.id - b.id),
    }))
    .filter((group) => group.nodes.length > 0);
});
const learningRelationGroups = computed(() =>
  relationGroups.value.filter((group) => group.key === 'prerequisite' || group.key === 'dependent'),
);
const hierarchyRelationGroups = computed(() =>
  relationGroups.value.filter((group) => group.key === 'parent' || group.key === 'child'),
);
const evidenceByEdgeId = computed(() => {
  const result = new Map<number, KnowledgeEdgeEvidence[]>();
  const run = relationships.value?.run;
  if (run?.status !== 'success' || !run.is_current) return result;
  const edges = [
    ...(relationships.value?.contains_edges ?? []),
    ...(relationships.value?.prerequisite_edges ?? []),
  ];
  for (const edge of edges) {
    if (edge.course_id === courseId.value) {
      result.set(
        edge.id,
        edge.evidence.filter((item) => item.course_id === courseId.value),
      );
    }
  }
  return result;
});
const evidenceRows = computed<EvidenceRow[]>(() =>
  validEdges.value.flatMap((edge) => {
    const source = nodeById.value.get(edge.source_node_id);
    const target = nodeById.value.get(edge.target_node_id);
    if (!source || !target) return [];
    return (evidenceByEdgeId.value.get(edge.id) ?? []).map((evidence) => ({
      edge,
      label: `${source.name} → ${target.name}`,
      evidence,
    }));
  }),
);
const validSources = computed(() =>
  (detail.value?.sources ?? []).filter(
    (source) => source.knowledge_node_id === detail.value?.node.id,
  ),
);
const sourceGroups = computed<SourceGroup[]>(() => {
  const grouped = new Map<number, KnowledgeSource[]>();
  for (const source of validSources.value) {
    const existing = grouped.get(source.material_id) ?? [];
    existing.push(source);
    grouped.set(source.material_id, existing);
  }
  return [...grouped.entries()].map(([materialId, sources]) => ({
    key: `material-${materialId}`,
    material: materialById.value.get(materialId) ?? null,
    sources: [...sources].sort((a, b) => a.id - b.id),
  }));
});
const previewSourceIds = computed(
  () =>
    new Set(
      validSources.value
        .filter((source) => Boolean(source.original_text_excerpt?.trim()))
        .sort((left, right) => left.id - right.id)
        .slice(0, 2)
        .map((source) => source.id),
    ),
);
const learningMaterials = computed(() => {
  const ids = new Set(validSources.value.map((source) => source.material_id));
  for (const row of evidenceRows.value) {
    if (row.evidence.evidence_type === 'material' && row.evidence.material_id !== null) {
      ids.add(row.evidence.material_id);
    }
  }
  return [...ids]
    .map((id) => materialById.value.get(id))
    .filter((material): material is Material => material !== undefined);
});

function materialFor(materialId: number | null): Material | null {
  return materialId === null ? null : (materialById.value.get(materialId) ?? null);
}

function materialType(material: Material): string {
  return (material.extension || material.type || '资料').replace(/^\./, '').toUpperCase();
}

function nodeRoute(id: number) {
  return {
    name: 'knowledge-detail',
    params: { courseId: courseId.value, nodeId: id },
    query: { from: returnTab.value, ...(showMastery.value ? { mode: 'mastery' } : {}) },
  };
}

async function loadMastery(): Promise<void> {
  const sequence = ++masteryRequestSequence;
  masteryExplanation.value = null;
  masteryError.value = '';
  if (!showMastery.value) {
    masteryLoading.value = false;
    return;
  }
  const requestedCourseId = courseId.value;
  const requestedNodeId = nodeId.value;
  masteryLoading.value = true;
  try {
    const explanation = await fetchNodeEvidence(requestedCourseId, requestedNodeId);
    if (
      sequence !== masteryRequestSequence ||
      requestedCourseId !== courseId.value ||
      requestedNodeId !== nodeId.value
    ) {
      return;
    }
    if (
      explanation.course_id !== requestedCourseId ||
      explanation.knowledge_node_id !== requestedNodeId ||
      explanation.state.knowledge_node_id !== requestedNodeId
    ) {
      throw new Error('Mastery node mismatch');
    }
    masteryExplanation.value = explanation;
  } catch (error: unknown) {
    if (sequence === masteryRequestSequence) {
      masteryError.value = normalizeApiError(error).message;
    }
  } finally {
    if (sequence === masteryRequestSequence) masteryLoading.value = false;
  }
}

function materialRoute(materialId: number, tab: string, sourceReference?: string) {
  return {
    name: 'material-detail',
    params: { courseId: courseId.value, materialId },
    query: sourceReference ? { tab, source: sourceReference } : { tab },
  };
}

function evidenceTypeLabel(evidence: KnowledgeEdgeEvidence): string {
  if (evidence.evidence_type === 'material') return '课程资料依据';
  if (evidence.evidence_type === 'structural') return '结构约束说明 · 非资料原文';
  return '模型关系判断 · 非资料原文';
}

function sourcePreviewLabel(source: KnowledgeSource): string {
  return /(?:PDF\s*)?第\s*\d+\s*页/i.test(source.source_reference)
    ? '来源页内容节选（已核验）'
    : '资料原文节选（已核验）';
}

function sourceMaterialTitle(group: SourceGroup): string {
  return group.material?.title || group.sources[0]?.material_title || '来源资料已删除或不可访问';
}

async function loadDetail(): Promise<void> {
  const sequence = ++requestSequence;
  course.value = null;
  detail.value = null;
  model.value = null;
  materials.value = [];
  relationships.value = null;
  materialsNotice.value = '';
  evidenceNotice.value = '';
  relationshipEvidenceExpanded.value = false;
  errorMessage.value = '';
  state.value = 'loading';

  if (
    !Number.isInteger(courseId.value) ||
    courseId.value < 1 ||
    !Number.isInteger(nodeId.value) ||
    nodeId.value < 1
  ) {
    state.value = 'error';
    errorMessage.value = '知识点地址无效。';
    return;
  }

  const requestedCourseId = courseId.value;
  const requestedNodeId = nodeId.value;
  const [detailResult, modelResult, courseResult, materialsResult, relationshipsResult] =
    await Promise.allSettled([
      fetchKnowledgeNodeDetail(requestedCourseId, requestedNodeId),
      fetchKnowledgeModel(requestedCourseId, { canonicalOnly: true }),
      fetchCourse(requestedCourseId),
      fetchMaterials(requestedCourseId),
      fetchKnowledgeRelationships(requestedCourseId),
    ]);
  if (sequence !== requestSequence) return;

  if (detailResult.status === 'rejected' || modelResult.status === 'rejected') {
    const error =
      detailResult.status === 'rejected'
        ? detailResult.reason
        : modelResult.status === 'rejected'
          ? modelResult.reason
          : null;
    const apiError = normalizeApiError(error);
    errorMessage.value =
      apiError.status === 404 ? '知识点不存在或不属于当前课程。' : apiError.message;
    state.value = 'error';
    return;
  }
  const node = detailResult.value.node;
  const canonicalModel = modelResult.value;
  if (
    node.id !== requestedNodeId ||
    node.course_id !== requestedCourseId ||
    canonicalModel.course_id !== requestedCourseId ||
    !canonicalModel.nodes.some(
      (item) => item.id === requestedNodeId && item.course_id === requestedCourseId,
    )
  ) {
    errorMessage.value = '知识点不存在或不属于当前课程。';
    state.value = 'error';
    return;
  }
  detail.value = detailResult.value;
  model.value = canonicalModel;
  if (courseResult.status === 'fulfilled' && courseResult.value.id === requestedCourseId) {
    course.value = courseResult.value;
  }
  if (
    materialsResult.status === 'fulfilled' &&
    materialsResult.value.course_id === requestedCourseId
  ) {
    materials.value = materialsResult.value.materials.filter(
      (item) => item.course_id === requestedCourseId,
    );
  } else {
    materialsNotice.value = '资料信息暂不可用，暂不提供资料跳转。';
  }
  if (relationshipsResult.status === 'fulfilled') {
    relationships.value = relationshipsResult.value;
  } else {
    const error = normalizeApiError(relationshipsResult.reason);
    if (error.code !== 'KNOWLEDGE_RELATIONSHIP_NOT_READY' && error.status !== 409) {
      evidenceNotice.value = '关系依据暂时无法读取，可稍后重试。';
    }
  }
  state.value = 'ready';
  void loadMastery();
}

watch([courseId, nodeId], () => void loadDetail(), { immediate: true });
watch(showMastery, () => void loadMastery());
onBeforeUnmount(() => {
  requestSequence += 1;
  masteryRequestSequence += 1;
});
</script>

<template>
  <section class="page-view knowledge-page">
    <RouterLink
      class="back-link"
      :to="{ name: 'course-detail', params: { courseId }, query: returnQuery }"
    >
      <el-icon aria-hidden="true"><ArrowLeft /></el-icon>返回课程
    </RouterLink>

    <LoadingBlock v-if="state === 'loading'" />
    <ErrorState
      v-else-if="state === 'error'"
      title="知识详情加载失败"
      :message="errorMessage"
      @retry="loadDetail"
    />
    <template v-else-if="detail">
      <header class="knowledge-page__header">
        <div>
          <p class="knowledge-page__eyebrow">{{ course?.name || '课程知识结构' }} / 知识详情</p>
          <h1>{{ detail.node.name }}</h1>
          <p class="knowledge-page__intro">认识这个知识点，了解相关知识与真实课程出处。</p>
        </div>
        <div class="knowledge-page__tags" aria-label="课程知识属性">
          <span>重要程度：{{ importanceLabel }}</span>
          <span>学习难度：{{ difficultyLabel }}</span>
        </div>
      </header>

      <RouterLink
        class="knowledge-page__map-link"
        :to="{
          name: 'course-detail',
          params: { courseId },
          query: {
            tab: 'knowledge-structure',
            nodeId: String(nodeId),
            ...(showMastery ? { mode: 'mastery' } : {}),
          },
        }"
      >
        在知识地图中查看 <el-icon aria-hidden="true"><ArrowRight /></el-icon>
      </RouterLink>

      <KnowledgeMasteryDetail
        v-if="showMastery"
        :loading="masteryLoading"
        :error="masteryError"
        :explanation="masteryExplanation"
        @retry="loadMastery"
      />

      <div class="knowledge-page__grid">
        <div class="knowledge-page__main">
          <section class="knowledge-page__card" aria-labelledby="knowledge-concept-heading">
            <p class="knowledge-page__section-number">01 / 知识理解</p>
            <h2 id="knowledge-concept-heading">认识这个知识点</h2>
            <p v-if="detail.node.description.trim()" class="knowledge-page__description">
              {{ detail.node.description }}
            </p>
            <p v-else class="knowledge-page__empty">
              当前知识点尚无经过保存的概念说明。下方可查看已记录的课程资料片段。
            </p>
          </section>

          <section class="knowledge-page__card" aria-labelledby="knowledge-relations-heading">
            <p class="knowledge-page__section-number">02 / 知识关联</p>
            <h2 id="knowledge-relations-heading">和哪些知识有关？</h2>
            <p class="knowledge-page__muted">
              学习联系与主题归属分别来自课程中已经建立的真实关系。
            </p>
            <div v-if="learningRelationGroups.length" class="knowledge-page__relations">
              <section
                v-for="group in learningRelationGroups"
                :key="group.key"
                class="knowledge-page__relation-group knowledge-page__relation-group--learning"
                :aria-labelledby="`relation-${group.key}`"
              >
                <h3 :id="`relation-${group.key}`">{{ group.title }}</h3>
                <p>{{ group.hint }}</p>
                <ul>
                  <li v-for="node in group.nodes" :key="node.id">
                    <RouterLink :to="nodeRoute(node.id)">
                      <span>{{ node.name }}</span>
                      <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                    </RouterLink>
                  </li>
                </ul>
              </section>
            </div>
            <div v-if="hierarchyRelationGroups.length" class="knowledge-page__hierarchy-relations">
              <section
                v-for="group in hierarchyRelationGroups"
                :key="group.key"
                class="knowledge-page__relation-group knowledge-page__relation-group--hierarchy"
                :aria-labelledby="`relation-${group.key}`"
              >
                <div>
                  <h3 :id="`relation-${group.key}`">{{ group.title }}</h3>
                  <p>{{ group.hint }}</p>
                </div>
                <ul>
                  <li v-for="node in group.nodes" :key="node.id">
                    <RouterLink :to="nodeRoute(node.id)">
                      <span>{{ node.name }}</span>
                      <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                    </RouterLink>
                  </li>
                </ul>
              </section>
            </div>
            <p v-if="relationGroups.length === 0" class="knowledge-page__empty">
              当前还没有建立这个知识点与其他知识点的联系。
            </p>
          </section>

          <section class="knowledge-page__card" aria-labelledby="knowledge-sources-heading">
            <p class="knowledge-page__section-number">03 / 课程来源</p>
            <h2 id="knowledge-sources-heading">知识出处</h2>
            <p v-if="materialsNotice" class="knowledge-page__notice" role="status">
              {{ materialsNotice }}
            </p>
            <p v-if="sourceGroups.length === 0" class="knowledge-page__empty">
              当前知识点尚未记录资料来源。
            </p>
            <ul v-else class="knowledge-page__source-list">
              <li v-for="group in sourceGroups" :key="group.key">
                <div class="knowledge-page__source-heading">
                  <el-icon aria-hidden="true"><Document /></el-icon>
                  <div>
                    <h3>{{ sourceMaterialTitle(group) }}</h3>
                    <p v-if="group.material">{{ materialType(group.material) }}</p>
                  </div>
                </div>
                <ul class="knowledge-page__source-positions">
                  <li v-for="source in group.sources" :key="source.id">
                    <p
                      v-if="source.source_reference.trim()"
                      class="knowledge-page__source-location"
                    >
                      {{ source.source_reference }}
                    </p>
                    <div class="knowledge-page__source-actions">
                      <RouterLink
                        v-if="group.material || source.material_title"
                        class="knowledge-page__inline-link"
                        :to="materialRoute(source.material_id, 'content', source.source_reference)"
                      >
                        查看资料 <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                      </RouterLink>
                    </div>
                    <div
                      v-if="source.original_text_excerpt && previewSourceIds.has(source.id)"
                      :id="`source-evidence-${source.id}`"
                      class="knowledge-page__source-evidence"
                      role="region"
                      :aria-label="`${sourceMaterialTitle(group)}的已核验资料原文`"
                    >
                      <p>{{ sourcePreviewLabel(source) }}</p>
                      <blockquote>{{ source.original_text_excerpt }}</blockquote>
                      <small v-if="source.original_text_truncated"
                        >节选已截短；可查看资料阅读完整内容。</small
                      >
                    </div>
                    <p
                      v-else-if="!source.original_text_excerpt"
                      class="knowledge-page__unavailable"
                    >
                      暂无可直接预览的来源原文；请查看资料确认来源位置。
                    </p>
                    <p v-else class="knowledge-page__unavailable">
                      更多已核验来源已折叠；可查看资料阅读完整内容。
                    </p>
                    <p
                      v-if="!group.material && !source.material_title"
                      class="knowledge-page__unavailable"
                    >
                      资料不可访问，无法打开原文。
                    </p>
                  </li>
                </ul>
              </li>
            </ul>

            <p v-if="evidenceNotice" class="knowledge-page__notice" role="status">
              {{ evidenceNotice }}
            </p>
            <div v-if="evidenceRows.length" class="knowledge-page__evidence">
              <div class="knowledge-page__evidence-summary">
                <div>
                  <h3>知识关联依据</h3>
                  <p>关系判断与资料原文分开记录，共 {{ evidenceRows.length }} 条。</p>
                </div>
                <button
                  type="button"
                  class="knowledge-page__disclosure"
                  :aria-expanded="relationshipEvidenceExpanded"
                  aria-controls="relationship-evidence-list"
                  @click="relationshipEvidenceExpanded = !relationshipEvidenceExpanded"
                >
                  {{ relationshipEvidenceExpanded ? '收起依据' : '查看依据' }}
                </button>
              </div>
              <ul
                v-if="relationshipEvidenceExpanded"
                id="relationship-evidence-list"
                class="knowledge-page__evidence-list"
                role="region"
                aria-label="知识关联依据"
              >
                <li v-for="row in evidenceRows" :key="row.evidence.id">
                  <div class="knowledge-page__evidence-heading">
                    <span>{{
                      row.edge.relation_type === 'contains' ? '层级关系' : '先修关系'
                    }}</span>
                    <strong>{{ row.label }}</strong>
                  </div>
                  <p class="knowledge-page__evidence-type">
                    {{ evidenceTypeLabel(row.evidence) }}
                    <template v-if="row.evidence.evidence_type === 'material'">
                      · {{ materialFor(row.evidence.material_id)?.title || '资料已删除或不可访问' }}
                    </template>
                  </p>
                  <p v-if="row.evidence.reason" class="knowledge-page__reason">
                    {{ row.evidence.reason }}
                  </p>
                  <p
                    v-if="
                      row.evidence.evidence_type === 'material' && row.evidence.source_reference
                    "
                    class="knowledge-page__reference"
                  >
                    来源位置：{{ row.evidence.source_reference }}
                  </p>
                  <blockquote
                    v-if="row.evidence.evidence_type === 'material' && row.evidence.excerpt"
                  >
                    {{ row.evidence.excerpt }}
                  </blockquote>
                  <RouterLink
                    v-if="
                      row.evidence.evidence_type === 'material' &&
                      materialFor(row.evidence.material_id)
                    "
                    class="knowledge-page__inline-link"
                    :to="
                      materialRoute(
                        row.evidence.material_id!,
                        'content',
                        row.evidence.source_reference || undefined,
                      )
                    "
                  >
                    打开依据资料 <el-icon aria-hidden="true"><ArrowRight /></el-icon>
                  </RouterLink>
                </li>
              </ul>
            </div>
          </section>
        </div>

        <aside class="knowledge-page__aside" aria-labelledby="knowledge-next-heading">
          <section class="knowledge-page__card">
            <p class="knowledge-page__section-number">04 / 继续学习</p>
            <h2 id="knowledge-next-heading">从课程资料继续</h2>
            <p class="knowledge-page__muted">学习卡片和问答均针对你选择的单份资料。</p>
            <ul v-if="learningMaterials.length" class="knowledge-page__learning-list">
              <li v-for="material in learningMaterials" :key="material.id">
                <h3>{{ material.title }}</h3>
                <p>{{ materialType(material) }}</p>
                <div class="knowledge-page__learning-actions">
                  <RouterLink :to="materialRoute(material.id, 'content')">查看资料</RouterLink>
                  <RouterLink :to="materialRoute(material.id, 'cards')">学习卡片</RouterLink>
                  <RouterLink :to="materialRoute(material.id, 'qa')">单资料问答</RouterLink>
                </div>
              </li>
            </ul>
            <p v-else class="knowledge-page__empty">暂无可打开的关联资料。</p>
            <RouterLink
              class="knowledge-page__all-materials"
              :to="{ name: 'course-detail', params: { courseId }, query: { tab: 'materials' } }"
            >
              浏览全部课程资料 <el-icon aria-hidden="true"><LinkIcon /></el-icon>
            </RouterLink>
          </section>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.knowledge-page {
  max-width: 1180px;
  margin: 0 auto;
}

.knowledge-page .back-link {
  width: fit-content;
  text-decoration: none;
}

.knowledge-page__header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--lp-space-5);
  margin: var(--lp-space-5) 0 var(--lp-space-6);
}

.knowledge-page__eyebrow,
.knowledge-page__section-number {
  color: var(--lp-primary);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.07em;
}

.knowledge-page__header h1 {
  margin: 0.4rem 0;
  color: var(--lp-ink);
  font-size: clamp(1.7rem, 3vw, 2.25rem);
  line-height: 1.24;
}

.knowledge-page__intro,
.knowledge-page__muted,
.knowledge-page__empty,
.knowledge-page__unavailable {
  color: var(--lp-text-secondary);
  line-height: 1.7;
}

.knowledge-page__intro {
  margin-bottom: 0;
}

.knowledge-page__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.knowledge-page__map-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: var(--lp-space-4);
  color: var(--lp-primary);
  font-weight: 700;
  text-decoration: none;
}

.knowledge-page__map-link:hover {
  text-decoration: underline;
}

.knowledge-page__map-link:focus-visible {
  outline: 3px solid rgb(61 111 183 / 25%);
  outline-offset: 3px;
}

.knowledge-page__tags span {
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--lp-border);
  border-radius: 999px;
  color: var(--lp-text-secondary);
  background: var(--lp-surface);
  font-size: 0.8rem;
  white-space: nowrap;
}

.knowledge-page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 300px);
  align-items: start;
  gap: var(--lp-space-5);
}

.knowledge-page__main {
  display: grid;
  min-width: 0;
  gap: var(--lp-space-5);
}

.knowledge-page__card {
  min-width: 0;
  padding: var(--lp-space-5);
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-lg);
  background: var(--lp-surface);
  box-shadow: var(--lp-shadow-sm);
}

.knowledge-page__card h2 {
  margin: 0 0 0.7rem;
  color: var(--lp-ink);
  font-size: 1.15rem;
}

.knowledge-page__section-number {
  margin-bottom: 0.35rem;
}

.knowledge-page__description {
  margin: 0;
  color: var(--lp-text);
  font-size: 0.98rem;
  line-height: 1.85;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.knowledge-page__empty {
  margin: 0;
  padding: 0.8rem 0;
}

.knowledge-page__relations {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--lp-space-3);
  margin-top: var(--lp-space-4);
}

.knowledge-page__hierarchy-relations {
  display: grid;
  gap: var(--lp-space-3);
  margin-top: var(--lp-space-3);
}

.knowledge-page__relation-group {
  min-width: 0;
  padding: var(--lp-space-4);
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
  background: var(--lp-canvas);
}

.knowledge-page__relation-group--learning {
  border-color: #cbdcfb;
  background: #f7faff;
}

.knowledge-page__relation-group--hierarchy {
  display: grid;
  grid-template-columns: minmax(170px, 0.45fr) minmax(0, 1fr);
  align-items: start;
  gap: var(--lp-space-4);
  padding-block: var(--lp-space-3);
  background: var(--lp-surface);
}

.knowledge-page__relation-group h3,
.knowledge-page__source-list h3,
.knowledge-page__learning-list h3 {
  margin: 0;
  color: var(--lp-ink);
  font-size: 0.94rem;
}

.knowledge-page__relation-group p {
  margin: 0.2rem 0 0.7rem;
  color: var(--lp-text-secondary);
  font-size: 0.79rem;
}

.knowledge-page__relation-group ul,
.knowledge-page__source-list,
.knowledge-page__source-positions,
.knowledge-page__evidence-list,
.knowledge-page__learning-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.knowledge-page__relation-group li + li {
  margin-top: 0.4rem;
}

.knowledge-page__relation-group a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-sm);
  color: var(--lp-primary);
  background: #fff;
  font-weight: 600;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.knowledge-page__relation-group a:hover,
.knowledge-page__inline-link:hover,
.knowledge-page__disclosure:hover,
.knowledge-page__learning-actions a:hover {
  border-color: var(--lp-primary);
  background: var(--lp-primary-soft);
}

.knowledge-page__relation-group a:focus-visible,
.knowledge-page__inline-link:focus-visible,
.knowledge-page__disclosure:focus-visible,
.knowledge-page__learning-actions a:focus-visible {
  outline: 3px solid rgb(61 111 183 / 25%);
  outline-offset: 2px;
}

.knowledge-page__source-list,
.knowledge-page__evidence-list,
.knowledge-page__learning-list {
  display: grid;
  gap: var(--lp-space-3);
}

.knowledge-page__source-list > li,
.knowledge-page__evidence-list > li,
.knowledge-page__learning-list > li {
  min-width: 0;
  padding: var(--lp-space-4);
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-md);
}

.knowledge-page__source-positions {
  display: grid;
  gap: var(--lp-space-3);
  margin-top: var(--lp-space-3);
}

.knowledge-page__source-positions > li {
  min-width: 0;
  padding-top: var(--lp-space-3);
  border-top: 1px solid var(--lp-border);
}

.knowledge-page__source-location {
  margin: 0;
  color: var(--lp-text);
  font-size: 0.88rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.knowledge-page__source-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--lp-space-3);
  margin-top: 0.4rem;
}

.knowledge-page__source-heading {
  display: flex;
  align-items: flex-start;
  gap: var(--lp-space-3);
}

.knowledge-page__source-heading > .el-icon {
  margin-top: 0.15rem;
  color: var(--lp-primary);
  font-size: 1.15rem;
}

.knowledge-page__source-heading > div {
  min-width: 0;
}

.knowledge-page__source-heading h3 {
  overflow-wrap: anywhere;
}

.knowledge-page__source-heading p,
.knowledge-page__learning-list p {
  margin: 0.15rem 0 0;
  color: var(--lp-text-secondary);
  font-size: 0.82rem;
}

.knowledge-page blockquote {
  margin: var(--lp-space-3) 0 0;
  padding: 0.6rem 0.75rem;
  border-left: 3px solid var(--lp-border-strong);
  color: var(--lp-text);
  background: var(--lp-canvas);
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.knowledge-page__source-evidence {
  margin-top: var(--lp-space-3);
  padding: var(--lp-space-3);
  border-radius: var(--lp-radius-sm);
  background: var(--lp-canvas);
}

.knowledge-page__source-evidence > p {
  margin: 0;
  color: var(--lp-text-secondary);
  font-size: 0.78rem;
  font-weight: 700;
}

.knowledge-page__source-evidence blockquote {
  margin-top: 0.45rem;
  background: var(--lp-surface);
  max-height: 18rem;
  overflow: auto;
}

.knowledge-page__inline-link,
.knowledge-page__all-materials {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: var(--lp-space-3);
  color: var(--lp-primary);
  font-weight: 600;
  text-decoration: none;
}

.knowledge-page__source-actions .knowledge-page__inline-link {
  margin-top: 0;
}

.knowledge-page__disclosure {
  flex-shrink: 0;
  padding: 0;
  border: 0;
  color: var(--lp-primary);
  background: transparent;
  font: inherit;
  font-size: 0.86rem;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}

.knowledge-page__evidence {
  margin-top: var(--lp-space-5);
  padding-top: var(--lp-space-5);
  border-top: 1px solid var(--lp-border);
}

.knowledge-page__evidence-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--lp-space-4);
}

.knowledge-page__evidence h3 {
  margin: 0 0 0.2rem;
  color: var(--lp-ink);
  font-size: 1rem;
}

.knowledge-page__evidence-summary p {
  margin: 0;
  color: var(--lp-text-secondary);
  font-size: 0.82rem;
}

.knowledge-page__evidence-list {
  margin-top: var(--lp-space-3);
}

.knowledge-page__evidence-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.knowledge-page__evidence-heading span {
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  color: var(--lp-primary);
  background: var(--lp-primary-soft);
  font-size: 0.75rem;
  font-weight: 700;
}

.knowledge-page__evidence-heading strong {
  color: var(--lp-ink);
  font-size: 0.9rem;
}

.knowledge-page__evidence-type,
.knowledge-page__reason,
.knowledge-page__reference {
  margin: 0.4rem 0 0;
  color: var(--lp-text-secondary);
  font-size: 0.84rem;
  overflow-wrap: anywhere;
}

.knowledge-page__notice {
  padding: 0.55rem 0.8rem;
  border-radius: var(--lp-radius-sm);
  color: #795920;
  background: #fff7e7;
}

.knowledge-page__learning-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: var(--lp-space-3);
}

.knowledge-page__learning-actions a {
  padding: 0.35rem 0.55rem;
  border: 1px solid var(--lp-border);
  border-radius: var(--lp-radius-sm);
  color: var(--lp-primary);
  font-size: 0.79rem;
  font-weight: 600;
  text-decoration: none;
}

@media (max-width: 960px) {
  .knowledge-page__grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .knowledge-page__header {
    display: block;
  }

  .knowledge-page__tags {
    margin-top: var(--lp-space-3);
  }

  .knowledge-page__relations {
    grid-template-columns: 1fr;
  }

  .knowledge-page__relation-group--hierarchy {
    grid-template-columns: 1fr;
    gap: var(--lp-space-2);
  }

  .knowledge-page__evidence-summary {
    align-items: flex-start;
  }

  .knowledge-page__card {
    padding: var(--lp-space-4);
  }
}
</style>
