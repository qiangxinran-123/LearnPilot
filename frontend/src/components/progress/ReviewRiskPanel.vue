<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { normalizeApiError } from '@/services/http';
import { fetchReviewRisk } from '@/services/reviewRisk';
import type { ConfidenceLevel, MasteryStatus } from '@/types/mastery';
import type { ProgressNode } from '@/types/progress';
import type { ReviewRiskResponse } from '@/types/reviewRisk';

const props = defineProps<{ courseId: number; weakNodes: ProgressNode[]; evaluatedCount: number }>();
const router = useRouter();
const data = ref<ReviewRiskResponse | null>(null);
const loading = ref(false);
const error = ref('');
let version = 0;
const confidence: Record<ConfidenceLevel, string> = { insufficient: '证据不足', low: '低', medium: '中', high: '高' };
const masteryStatus: Record<MasteryStatus, string> = {
  not_assessed: '尚未评估', good_performance: '表现良好', needs_reinforcement: '需要巩固',
  possibly_weak: '可能薄弱', needs_attention: '需要关注',
};
const reminders = computed(() => data.value?.items.filter((item) =>
  item.risk_level === 'review_due' || item.risk_level === 'watch' ||
  (item.mastery_score !== null && ['possibly_weak', 'needs_attention'].includes(item.mastery_status))
) ?? []);
const remainingWeak = computed(() => {
  const present = new Set(reminders.value.map((item) => item.knowledge_node_id));
  const observed = new Set(data.value?.items.map((item) => item.knowledge_node_id) ?? []);
  return props.weakNodes.filter((node) => !present.has(node.node_id) && !observed.has(node.node_id));
});
async function load(): Promise<void> {
  const current = ++version;
  data.value = null; error.value = ''; loading.value = true;
  try {
    const result = await fetchReviewRisk(props.courseId);
    if (current === version) data.value = result;
  } catch (reason: unknown) {
    if (current === version) error.value = normalizeApiError(reason).message;
  } finally { if (current === version) loading.value = false; }
}
function openNode(id: number): void {
  void router.push({ name: 'course-detail', params: { courseId: props.courseId },
    query: { tab: 'knowledge-structure', nodeId: String(id) } });
}
watch(() => props.courseId, () => { void load(); }, { immediate: true });
</script>

<template>
  <section class="review-panel">
    <h2>需要重点巩固</h2>
    <p>根据当前掌握状态和已提交的练习证据提供提醒；这不是遗忘预测或学习推荐。</p>
    <LoadingBlock v-if="loading" :count="1" />
    <ErrorState v-else-if="error" title="复习提醒加载失败" :message="error" @retry="load" />
    <template v-else-if="data">
      <p v-if="evaluatedCount === 0" class="notice">完成诊断或学习后，这里将显示需要巩固的知识。</p>
      <p v-else-if="!reminders.length && !remainingWeak.length" class="notice">目前没有识别到明显的复习提醒。</p>
      <p v-if="data.counts.insufficient_data > 0" class="notice">部分知识点证据不足或状态不可用，暂无法判断复习需求。</p>
      <p v-if="data.total_node_count > data.items.length" class="notice">当前显示前 {{ data.items.length }} 个知识点的提醒。</p>
      <div v-for="item in reminders" :key="item.knowledge_node_id" class="review-row">
        <div>
          <strong>{{ item.name }}</strong>
          <span class="badge">{{ item.risk_level === 'review_due' ? '建议巩固' : item.risk_level === 'watch' ? '关注' : '当前知识薄弱' }}</span>
          <p>{{ item.reason_text }}</p>
          <p v-if="item.mastery_score !== null">{{ masteryStatus[item.mastery_status] }} · 掌握度 {{ Number(item.mastery_score).toFixed(2) }}% · 置信度 {{ confidence[item.confidence_level] }} · 学习证据 {{ item.evidence_count }} 条</p>
          <p v-if="item.last_practice_at">最近有效练习：{{ new Date(item.last_practice_at).toLocaleString() }}</p>
        </div>
        <el-button @click="openNode(item.knowledge_node_id)">查看知识点</el-button>
      </div>
    </template>
    <div v-for="node in remainingWeak" :key="'weak-' + node.node_id" class="review-row">
      <div><strong>{{ node.name }}</strong><span class="badge">当前知识薄弱</span>
        <p>当前掌握状态提示该知识点可能薄弱，值得巩固。</p>
        <p>{{ masteryStatus[node.mastery_status] }} · 掌握度 {{ Number(node.mastery_score).toFixed(2) }}% · 置信度 {{ confidence[node.confidence_level] }} · 学习证据 {{ node.evidence_count }} 条</p>
      </div>
      <el-button @click="openNode(node.node_id)">查看知识点</el-button>
    </div>
  </section>
</template>

<style scoped>
.review-panel { background: #fff; border: 1px solid #e4eaf1; border-radius: 14px; padding: 24px; }
.review-panel h2 { color: #233851; margin: 0; font-size: 17px; }
.review-panel p { color: #66758a; margin: 8px 0 0; line-height: 1.6; }
.notice { padding-top: 10px; }
.review-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 0; border-top: 1px solid #edf1f5; }
.review-row strong { overflow-wrap: anywhere; color: #30455f; }
.review-row p { font-size: 13px; }
.badge { margin-left: 10px; color: #996154; background: #fbefec; border-radius: 12px; padding: 3px 9px; font-size: 12px; }
@media (max-width: 800px) { .review-row { align-items: flex-start; flex-direction: column; } }
</style>
