<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import ErrorState from '@/components/feedback/ErrorState.vue';
import LoadingBlock from '@/components/feedback/LoadingBlock.vue';
import { normalizeApiError } from '@/services/http';
import { fetchLearningHistory, fetchProgressTrend } from '@/services/progressHistory';
import type { LearningHistory, ProgressTrend, TrendPoint, TrendRange } from '@/types/progressHistory';

const props = defineProps<{ courseId: number }>();
const router = useRouter();
const range = ref<TrendRange>('30d');
const trend = ref<ProgressTrend | null>(null);
const history = ref<LearningHistory | null>(null);
const trendLoading = ref(false);
const historyLoading = ref(false);
const trendError = ref('');
const historyError = ref('');
let trendVersion = 0;
let historyVersion = 0;
const date = (value: string) => new Date(value).toLocaleString();
const pointLabel = (point: TrendPoint) =>
  `${date(point.recorded_at)}：掌握度 ${Number(point.overall_mastery).toFixed(2)}%，覆盖率 ${(point.coverage_ratio * 100).toFixed(1)}%（${point.evaluated_node_count}/${point.evaluable_node_count}）`;
const plotted = computed(() => {
  const points = trend.value?.points ?? [];
  if (points.length < 2) return [];
  const times = points.map((point) => new Date(point.recorded_at).getTime());
  const first = times[0] ?? 0;
  const span = (times[times.length - 1] ?? first) - first;
  return points.map((point, index) => ({
    point,
    x: 45 + (span ? ((times[index] ?? first) - first) / span : 0.5) * 710,
    y: 15 + (100 - Number(point.overall_mastery)) * 2,
  }));
});
const lines = computed(() => {
  const groups = new Map<number, typeof plotted.value>();
  for (const item of plotted.value) {
    const group = groups.get(item.point.segment) ?? [];
    group.push(item); groups.set(item.point.segment, group);
  }
  return [...groups.values()].filter((group) => group.length >= 2)
    .map((group) => group.map((item) => `${item.x},${item.y}`).join(' '));
});

async function loadTrend(): Promise<void> {
  const version = ++trendVersion;
  trend.value = null; trendError.value = ''; trendLoading.value = true;
  try {
    const result = await fetchProgressTrend(props.courseId, range.value);
    if (version === trendVersion) trend.value = result;
  } catch (error: unknown) {
    if (version === trendVersion) trendError.value = normalizeApiError(error).message;
  } finally { if (version === trendVersion) trendLoading.value = false; }
}
async function loadHistory(append = false): Promise<void> {
  const version = ++historyVersion;
  const cursor = append ? history.value?.next_cursor ?? undefined : undefined;
  if (!append) history.value = null;
  historyError.value = ''; historyLoading.value = true;
  try {
    const result = await fetchLearningHistory(props.courseId, cursor);
    if (version === historyVersion) {
      history.value = append && history.value ? { ...result, events: [...history.value.events, ...result.events] } : result;
    }
  } catch (error: unknown) {
    if (version === historyVersion) historyError.value = normalizeApiError(error).message;
  } finally { if (version === historyVersion) historyLoading.value = false; }
}
function openEvent(nodeId: number): void {
  void router.push({ name: 'course-detail', params: { courseId: props.courseId },
    query: { tab: 'knowledge-structure', nodeId: String(nodeId) } });
}
watch(() => props.courseId, () => { void loadTrend(); void loadHistory(); }, { immediate: true });
watch(range, () => { void loadTrend(); });
</script>

<template>
  <section class="history-panel">
    <div class="panel-head"><div><h2>掌握度趋势</h2><p>当前知识结构下的叶子节点，等权统计；覆盖范围变化会影响比较。</p></div>
      <el-select v-model="range" aria-label="趋势时间范围">
        <el-option label="近 7 天" value="7d" /><el-option label="近 30 天" value="30d" /><el-option label="全部" value="all" />
      </el-select>
    </div>
    <LoadingBlock v-if="trendLoading" :count="1" />
    <ErrorState v-else-if="trendError" :message="trendError" @retry="loadTrend" />
    <template v-else-if="trend">
      <p v-if="trend.points.some((point) => point.coverage_ratio < 1)" class="notice">部分知识点尚无历史掌握度，曲线仅反映当时已有记录的部分。</p>
      <p v-if="trend.excluded_incompatible_history" class="notice">知识结构或算法已变化，不可比的历史记录未纳入图表。</p>
      <p v-if="trend.points.length" class="notice">本范围内记录起始：{{ date(trend.points[0]!.recorded_at) }}。每个点仅代表当时已评估部分。</p>
      <p v-if="trend.points.length < 2 || !lines.length" class="empty-note">学习记录正在积累，暂时无法形成掌握度趋势。</p>
      <div v-else class="trend-chart">
        <svg viewBox="0 0 780 240" role="img" aria-label="课程掌握度历史折线图">
          <line x1="45" y1="15" x2="45" y2="215" stroke="#bcc9d8" />
          <line x1="45" y1="215" x2="755" y2="215" stroke="#bcc9d8" />
          <text x="4" y="20">100%</text><text x="15" y="218">0%</text>
          <polyline v-for="(line, index) in lines" :key="index" :points="line" fill="none" stroke="#5d83b0" stroke-width="3" />
          <circle v-for="(item, index) in plotted" :key="index" :cx="item.x" :cy="item.y" r="5" fill="#315f9b" tabindex="0">
            <title>{{ pointLabel(item.point) }}</title>
          </circle>
        </svg>
        <div class="axis-dates"><span>{{ date(trend.points[0]!.recorded_at) }}</span><span>{{ date(trend.points[trend.points.length - 1]!.recorded_at) }}</span></div>
        <ul class="point-list"><li v-for="point in trend.points" :key="point.recorded_at">{{ pointLabel(point) }}</li></ul>
      </div>
    </template>
  </section>
  <section class="history-panel">
    <h2>学习历史</h2><p>展示已提交的诊断和已完成的学习会话。</p>
    <LoadingBlock v-if="historyLoading && !history" :count="1" />
    <ErrorState v-else-if="historyError" :message="historyError" @retry="loadHistory(false)" />
    <template v-else-if="history">
      <p v-if="!history.events.length" class="empty-note">还没有学习记录。完成诊断或学习任务后，这里将展示你的学习历史。</p>
      <div v-for="event in history.events" :key="event.id" class="event-row">
        <time>{{ date(event.occurred_at) }}</time>
        <div><strong>{{ event.event_type === 'diagnosis_completed' ? '完成诊断' : '完成学习会话' }}</strong>
          <p v-if="event.knowledge_node_name">关联知识点：{{ event.knowledge_node_name }}</p></div>
        <el-button v-if="event.knowledge_node_id !== null" @click="openEvent(event.knowledge_node_id)">查看知识点</el-button>
      </div>
      <el-button v-if="history.next_cursor" :loading="historyLoading" @click="loadHistory(true)">加载更多</el-button>
    </template>
  </section>
</template>

<style scoped>
.history-panel { background: #fff; border: 1px solid #e4eaf1; border-radius: 14px; padding: 24px; }
.history-panel h2 { color: #233851; margin: 0; font-size: 17px; }
.history-panel p { color: #66758a; margin: 8px 0 0; line-height: 1.6; }
.panel-head { display: flex; justify-content: space-between; gap: 20px; align-items: center; }
.panel-head .el-select { width: 150px; flex-shrink: 0; }
.notice, .empty-note { padding-top: 12px; }
.trend-chart { margin-top: 18px; }
.trend-chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.trend-chart text { fill: #66758a; font-size: 12px; }
.axis-dates { display: flex; justify-content: space-between; color: #66758a; font-size: 12px; gap: 15px; }
.point-list { color: #66758a; font-size: 13px; line-height: 1.7; max-height: 100px; overflow: auto; }
.event-row { display: grid; grid-template-columns: 170px 1fr auto; gap: 18px; align-items: center; padding: 18px 0; border-bottom: 1px solid #edf1f5; }
.event-row time { color: #66758a; font-size: 13px; }
.event-row p { margin-top: 4px; }
@media (max-width: 800px) { .panel-head { align-items: flex-start; flex-direction: column; } .event-row { grid-template-columns: 1fr; gap: 8px; } }
</style>
