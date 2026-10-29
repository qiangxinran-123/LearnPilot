<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Collection } from '@element-plus/icons-vue';
import EmptyState from '@/components/common/EmptyState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import ProgressHistoryPanel from '@/components/progress/ProgressHistoryPanel.vue';
import ReviewRiskPanel from '@/components/progress/ReviewRiskPanel.vue';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { normalizeApiError } from '@/services/http';
import { fetchKnowledgeModel } from '@/services/knowledge';
import { fetchProgressKnowledge, fetchProgressOverview } from '@/services/progress';
import { useCourseStore } from '@/stores/courses';
import type { KnowledgeNode } from '@/types/knowledge';
import type { ConfidenceLevel, MasteryStatus } from '@/types/mastery';
import type { ProgressKnowledge, ProgressNode, ProgressOverview } from '@/types/progress';

const route = useRoute();
const router = useRouter();
const courses = useCourseStore();
const selectedCourseId = ref<number | null>(null);
const overview = ref<ProgressOverview | null>(null);
const knowledge = ref<ProgressKnowledge | null>(null);
const modelNodes = ref<KnowledgeNode[]>([]);
const selectedParent = ref('all');
const loading = ref(false);
const error = ref('');
let requestVersion = 0;

const statusLabels: Record<MasteryStatus, string> = {
  good_performance: '表现良好',
  needs_reinforcement: '需要巩固',
  possibly_weak: '可能薄弱',
  needs_attention: '需要关注',
  not_assessed: '尚未评估',
};
const confidenceLabels: Record<ConfidenceLevel, string> = {
  insufficient: '证据不足', low: '低', medium: '中', high: '高',
};
const statusOrder: MasteryStatus[] = ['good_performance', 'needs_reinforcement', 'possibly_weak', 'needs_attention', 'not_assessed'];
const parentOptions = computed(() => {
  const ids = new Set(knowledge.value?.nodes.flatMap((node) => node.parent_ids) ?? []);
  return modelNodes.value.filter((node) => ids.has(node.id)).sort((a, b) => a.id - b.id);
});
const visibleNodes = computed(() => {
  const nodes = knowledge.value?.nodes ?? [];
  const filtered = selectedParent.value === 'all' ? nodes : selectedParent.value === 'isolated'
    ? nodes.filter((node) => node.parent_ids.length === 0)
    : nodes.filter((node) => node.parent_ids.includes(Number(selectedParent.value)));
  return [...filtered].sort((a, b) => a.node_id - b.node_id);
});
const hasIsolated = computed(() => knowledge.value?.nodes.some((node) => node.parent_ids.length === 0) ?? false);

function score(value: string | null): string {
  return value === null ? '暂无数据' : `${Number(value).toFixed(2)}%`;
}
function nodeStatus(node: ProgressNode): string {
  if (node.calculation_state === 'stale') return '状态已过期';
  if (node.calculation_state === 'not_calculated') return '尚未计算';
  return statusLabels[node.mastery_status];
}
function openNode(node: ProgressNode): void {
  if (selectedCourseId.value === null) return;
  void router.push({ name: 'course-detail', params: { courseId: selectedCourseId.value }, query: {
    tab: 'knowledge-structure', nodeId: String(node.node_id),
  } });
}
async function load(): Promise<void> {
  const courseId = selectedCourseId.value;
  const version = ++requestVersion;
  overview.value = null;
  knowledge.value = null;
  modelNodes.value = [];
  selectedParent.value = 'all';
  error.value = '';
  if (courseId === null) { loading.value = false; return; }
  loading.value = true;
  try {
    const [nextOverview, nextKnowledge, model] = await Promise.all([
      fetchProgressOverview(courseId), fetchProgressKnowledge(courseId), fetchKnowledgeModel(courseId),
    ]);
    if (version !== requestVersion) return;
    overview.value = nextOverview;
    knowledge.value = nextKnowledge;
    modelNodes.value = model.nodes;
  } catch (reason: unknown) {
    if (version === requestVersion) error.value = normalizeApiError(reason).message;
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}
watch(selectedCourseId, (id) => {
  void load();
  if (id !== null && String(route.query.courseId ?? '') !== String(id)) {
    void router.replace({ name: 'progress', query: { courseId: String(id) } });
  }
});
watch(() => courses.courses, (items) => {
  if (items.some((course) => course.id === selectedCourseId.value)) return;
  const query = Number(route.query.courseId);
  selectedCourseId.value = items.find((course) => course.id === query)?.id ?? items[0]?.id ?? null;
}, { immediate: true });
onMounted(() => { void courses.loadCourses(); });
</script>

<template>
  <section class="page-view progress-page">
    <PageHeader title="学习进展" description="从已有学习证据了解掌握情况与下一步重点。" />
    <div class="progress-course">
      <div><p>当前课程</p><strong>{{ courses.courses.find((course) => course.id === selectedCourseId)?.name ?? '请选择课程' }}</strong></div>
      <el-select v-if="courses.courses.length" v-model="selectedCourseId" aria-label="选择课程">
        <el-option v-for="course in courses.courses" :key="course.id" :label="course.name" :value="course.id" />
      </el-select>
    </div>
    <LoadingBlock v-if="courses.state === 'idle' || courses.isLoading || loading" />
    <ErrorState v-else-if="courses.hasError" :message="courses.errorMessage" @retry="courses.loadCourses(true)" />
    <ErrorState v-else-if="error" :message="error" @retry="load" />
    <EmptyState v-else-if="!courses.courses.length" :icon="Collection" title="还没有课程" description="创建课程并完成诊断后，即可查看学习进展。" />
    <template v-else-if="overview && knowledge">
      <div class="summary-grid">
        <section class="progress-panel summary-main">
          <h2>当前已评估知识掌握情况</h2>
          <strong v-if="overview.overall_mastery !== null" class="summary-score">{{ score(overview.overall_mastery) }}</strong>
          <strong v-else class="summary-empty">暂无足够学习数据</strong>
          <p>当前结果仅基于已评估的知识点，不代表整个课程的掌握程度。</p>
        </section>
        <section class="progress-panel">
          <h2>评估覆盖情况</h2>
          <strong class="coverage-count">已评估 {{ overview.evaluated_node_count }} / {{ overview.evaluable_node_count }} 个知识点</strong>
          <p>{{ overview.coverage_ratio === null ? '课程尚无可评估知识点' : `覆盖率 ${(overview.coverage_ratio * 100).toFixed(1)}%` }}</p>
        </section>
      </div>
      <section class="progress-panel distribution">
        <h2>知识状态分布</h2>
        <p>按可评估的叶子知识点统计，尚未评估包含证据不足或状态过期的节点。</p>
        <div class="status-list"><span v-for="status in statusOrder" :key="status"><i :class="'status-' + status"></i>{{ statusLabels[status] }} <b>{{ overview.status_counts[status] }}</b></span></div>
      </section>
      <section class="progress-panel comparison">
        <div class="section-head">
          <div><h2>知识点掌握对比</h2><p>仅比较叶子知识点；选择模块查看其直接子节点。</p></div>
          <el-select v-model="selectedParent" aria-label="筛选知识模块">
            <el-option label="全部知识点" value="all" />
            <el-option v-if="hasIsolated" label="独立知识点" value="isolated" />
            <el-option v-for="parent in parentOptions" :key="parent.id" :label="parent.name" :value="String(parent.id)" />
          </el-select>
        </div>
        <p v-if="!visibleNodes.length" class="empty-note">暂无可比较的知识点。</p>
        <div v-else class="chart" aria-label="知识点掌握度横向对比">
          <div v-for="node in visibleNodes" :key="node.node_id" class="chart-row">
            <button class="node-link" @click="openNode(node)">{{ node.name }}</button>
            <div class="bar-track" :aria-label="`${node.name}：${score(node.mastery_score)}`">
              <div v-if="node.mastery_score !== null" class="bar-fill" :style="{ width: `${Number(node.mastery_score)}%` }"></div>
            </div>
            <strong>{{ score(node.mastery_score) }}</strong>
            <span>{{ nodeStatus(node) }} · 置信度：{{ confidenceLabels[node.confidence_level] }}</span>
          </div>
        </div>
      </section>
      <ReviewRiskPanel v-if="selectedCourseId !== null" :course-id="selectedCourseId" :weak-nodes="overview.weak_nodes" :evaluated-count="overview.evaluated_node_count" />
      <ProgressHistoryPanel v-if="selectedCourseId !== null" :course-id="selectedCourseId" />
    </template>
  </section>
</template>

<style scoped>
.progress-page { display: grid; gap: 22px; }
.progress-course, .progress-panel { background: var(--el-bg-color, #fff); border: 1px solid #e4eaf1; border-radius: 14px; padding: 24px; }
.progress-course, .section-head { display: flex; justify-content: space-between; align-items: center; gap: 24px; }
.progress-course p, .progress-panel p { color: #66758a; margin: 8px 0 0; line-height: 1.6; }
.progress-course strong { font-size: 18px; }
.progress-course .el-select, .section-head .el-select { width: 230px; flex-shrink: 0; }
.progress-panel h2 { color: #233851; margin: 0; font-size: 17px; }
.summary-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 18px; }
.summary-score { display: block; font-size: 42px; color: #315f9b; margin-top: 14px; }
.summary-empty, .coverage-count { display: block; font-size: 21px; margin-top: 20px; color: #30455f; }
.status-list { display: flex; flex-wrap: wrap; gap: 16px 25px; margin-top: 20px; color: #43556c; }
.status-list i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; background: #a7b1bd; }
.status-list .status-good_performance { background: #4c9a82; }
.status-list .status-needs_reinforcement { background: #d8a64e; }
.status-list .status-possibly_weak, .status-list .status-needs_attention { background: #cd7771; }
.chart { display: grid; gap: 18px; margin-top: 24px; }
.chart-row { display: grid; grid-template-columns: minmax(140px, 1.1fr) minmax(130px, 2fr) 80px minmax(140px, 1fr); align-items: center; gap: 14px; color: #66758a; font-size: 13px; }
.node-link { border: 0; background: none; text-align: left; padding: 0; color: #315f9b; cursor: pointer; overflow-wrap: anywhere; font: inherit; font-weight: 600; }
.node-link:focus-visible { outline: 2px solid #315f9b; outline-offset: 4px; }
.bar-track { height: 10px; background: #eaf0f6; border-radius: 8px; overflow: hidden; }
.bar-fill { height: 100%; background: #5d83b0; border-radius: inherit; }
.chart-row strong { color: #30455f; }
.weak-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 0; border-top: 1px solid #edf1f5; }
.weak-row:first-of-type { margin-top: 18px; }
.weak-row p { margin-top: 5px; }
.weak-row span { color: #78879a; font-size: 13px; }
.empty-note { padding: 18px 0 0; }
@media (max-width: 800px) { .summary-grid { grid-template-columns: 1fr; } .chart-row { grid-template-columns: 1fr 1fr; } .chart-row > span { grid-column: 1 / -1; } .progress-course, .section-head { align-items: flex-start; flex-direction: column; } }
</style>
