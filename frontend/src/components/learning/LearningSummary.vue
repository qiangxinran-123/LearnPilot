<script setup lang="ts">
import { computed } from 'vue';
import type { LearningSession } from '@/types/learningSession';
import { recommendationReasonLabel } from '@/components/learning/planPresentation';

const props = defineProps<{ session: LearningSession; retrying: boolean }>();
defineEmits<{ retry: []; back: [] }>();
const summary = computed(() => props.session.completion_summary);
const change = computed(() =>
  summary.value?.mastery_changes.find((item) => item.knowledge_node_id === props.session.target_knowledge_node_id),
);
function percentage(value: number | null | undefined): string {
  return value == null ? '暂无数据' : `${Math.max(0, Math.min(100, value)).toFixed(2).replace(/\.00$/, '')}%`;
}
function width(value: number | null | undefined): string {
  return `${Math.max(0, Math.min(100, value ?? 0))}%`;
}
const deltaLabel = computed(() => {
  const delta = change.value?.delta;
  if (delta == null) return '当前证据尚不足以比较变化';
  if (delta === 0) return '本次掌握度保持不变';
  return `${delta > 0 ? '提高' : '下降'} ${Math.abs(delta).toFixed(2).replace(/\.00$/, '')} 个百分点`;
});
const confidenceLabels: Record<string, string> = {
  insufficient: '证据不足', low: '较低', medium: '中等', high: '较高',
};
</script>

<template>
  <section class="summary" aria-labelledby="summary-title">
    <header class="summary__header">
      <p>{{ session.course_name }} · {{ session.target_knowledge_node_name }}</p>
      <h2 id="summary-title">本次学习已完成</h2>
      <span>结果已保存，可随时返回查看。</span>
    </header>
    <template v-if="summary">
      <div class="summary__stats" aria-label="练习结果">
        <div><strong>{{ summary.practice_summary.total_questions }}</strong><span>完成题数</span></div>
        <div><strong>{{ summary.practice_summary.correct_answers }}</strong><span>正确题数</span></div>
        <div><strong>{{ (summary.practice_summary.accuracy * 100).toFixed(0) }}%</strong><span>正确率</span></div>
      </div>
      <section class="summary__mastery">
        <h3>知识点掌握度</h3>
        <div v-for="entry in [{ label: '学习前', value: change?.before }, { label: '学习后', value: change?.after }]" :key="entry.label" class="summary__row">
          <span>{{ entry.label }}</span>
          <div class="summary__track" aria-hidden="true"><i :style="{ width: width(entry.value) }" /></div>
          <strong>{{ percentage(entry.value) }}</strong>
        </div>
        <p class="summary__delta">{{ deltaLabel }}</p>
        <p>本次形成 {{ summary.evidence_ids.length }} 条有效学习证据，系统依据实际答题结果重新计算掌握度。</p>
        <p v-if="change">当前置信度：{{ confidenceLabels[change.confidence] ?? change.confidence }}</p>
      </section>
      <section class="summary__next">
        <h3>下一步学习建议</h3>
        <template v-if="session.recommendation_refresh_status === 'failed' || session.recommendation_refresh_status === 'pending'">
          <p>学习结果已保存，学习建议暂时无法更新。</p>
          <el-button :loading="retrying" :disabled="retrying" @click="$emit('retry')">重试更新建议</el-button>
        </template>
        <template v-else-if="summary.recommendation">
          <strong>{{ summary.recommendation.title }}</strong>
          <ul><li v-for="code in summary.recommendation.reason_codes" :key="code">{{ recommendationReasonLabel(code) }}</li></ul>
          <p>{{ summary.recommendation.description }}</p>
          <el-button type="primary" plain @click="$emit('back')">查看学习路径</el-button>
        </template>
        <p v-else>当前没有可用的下一步推荐，可返回学习路径查看课程状态。</p>
      </section>
    </template>
    <p v-else>学习结果暂不可用，请返回学习路径后重试。</p>
  </section>
</template>

<style scoped>
.summary { margin: 24px 0; padding: 28px; background: var(--lp-surface); border: 1px solid var(--lp-border); border-radius: var(--lp-radius-lg); box-shadow: var(--lp-shadow-sm); }
.summary__header p { color: var(--lp-primary); font-size: 13px; font-weight: 700; }
.summary h2 { margin: 8px 0; color: var(--lp-ink); font-size: 25px; }
.summary__header span, .summary p { color: var(--lp-text-secondary); line-height: 1.7; }
.summary__stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 28px 0; padding: 18px; background: var(--lp-surface-subtle); border-radius: var(--lp-radius-md); }
.summary__stats strong, .summary__stats span { display: block; }
.summary__stats strong { color: var(--lp-ink); font-size: 24px; }
.summary__stats span { margin-top: 4px; color: var(--lp-text-secondary); font-size: 13px; }
.summary h3 { color: var(--lp-ink); font-size: 18px; }
.summary__row { display: grid; grid-template-columns: 55px minmax(0, 1fr) 85px; align-items: center; gap: 12px; margin: 14px 0; color: var(--lp-text-secondary); font-size: 14px; }
.summary__row strong { text-align: right; color: var(--lp-ink); }
.summary__track { height: 10px; border-radius: 10px; background: #e4edf8; overflow: hidden; }
.summary__track i { display: block; height: 100%; background: var(--lp-primary); border-radius: inherit; }
.summary__delta { font-weight: 700; color: var(--lp-ink) !important; }
.summary__next { margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--lp-border); }
@media (max-width: 600px) { .summary { padding: 20px; } .summary__stats { gap: 8px; padding: 14px; } .summary__row { grid-template-columns: 48px minmax(0, 1fr) 76px; gap: 8px; } }
</style>
